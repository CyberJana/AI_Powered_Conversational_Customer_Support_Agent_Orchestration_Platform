"""Composite confidence scoring and escalation trigger detection (FR-13/FR-14).

The composite score is a deterministic weighted average over signals that
are already produced by real pipeline components (never a new LLM call, and
never a fabricated number):

  - intent        : intent classification confidence (app.services.intent_service)
  - retrieval     : top RAG chunk similarity score (app.services.rag_service)
  - source_coverage: fraction of the retrieval top-k window actually filled
  - grounding     : fraction of retrieved sources the final answer actually
                    cited (``[n]`` markers), i.e. a real measurement of the
                    generated text, not a guess
  - tool_success  : fraction of this turn's tool calls that succeeded

Any signal that does not apply to a given turn (e.g. no RAG was performed,
or no tools were called) is omitted rather than defaulted to a fake value,
and the remaining weights are renormalized so the composite score still
reflects only what was actually measured.
"""
import re
from dataclasses import dataclass

WEIGHTS: dict[str, float] = {
    "intent": 0.25,
    "retrieval": 0.25,
    "source_coverage": 0.15,
    "grounding": 0.20,
    "tool_success": 0.15,
}

#: Heuristic sensitive-topic triggers (FR-14): matching any of these in the
#: raw customer message forces escalation regardless of confidence score.
SENSITIVE_KEYWORDS = (
    "lawsuit", "legal action", "sue you", "lawyer", "attorney",
    "suicide", "self harm", "self-harm", "kill myself", "hurt myself",
    "data breach", "fraud", "identity theft",
)

#: Consecutive low-confidence assistant turns before "repeated failure" fires.
REPEATED_FAILURE_WINDOW = 2

#: Fallback threshold used wherever no Agent-specific confidence_threshold
#: applies (e.g. the evaluation harness, or a conversation with no linked
#: Agent). Mirrors app.config.Settings.default_confidence_threshold.
DEFAULT_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class ConfidenceSignals:
    intent_confidence: float | None = None
    retrieval_relevance: float | None = None
    source_coverage: float | None = None
    grounding_score: float | None = None
    tool_success_rate: float | None = None


def compute_confidence(signals: ConfidenceSignals) -> float:
    """Weighted average over whichever signals are not None, renormalized
    so missing (not-applicable) signals don't bias the score toward 0 or 1.
    Returns 0.0 if no signal applies at all (should not normally happen,
    since intent confidence is always available).
    """
    values = {
        "intent": signals.intent_confidence,
        "retrieval": signals.retrieval_relevance,
        "source_coverage": signals.source_coverage,
        "grounding": signals.grounding_score,
        "tool_success": signals.tool_success_rate,
    }
    applicable = {k: v for k, v in values.items() if v is not None}
    if not applicable:
        return 0.0
    total_weight = sum(WEIGHTS[k] for k in applicable)
    weighted_sum = sum(WEIGHTS[k] * v for k, v in applicable.items())
    return max(0.0, min(1.0, weighted_sum / total_weight))


def grounding_score(answer: str, num_sources: int) -> float | None:
    """Fraction of retrieved sources actually cited (``[1]``, ``[2]``, ...)
    in the generated answer. Returns None when there was nothing to ground
    against (no sources retrieved), so the signal is excluded rather than
    treated as a failure.
    """
    if num_sources <= 0:
        return None
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    cited = {n for n in cited if 1 <= n <= num_sources}
    return max(0.0, min(1.0, len(cited) / num_sources))


@dataclass
class EscalationCheck:
    should_escalate: bool
    reason: str | None = None


def detect_trigger(
    *,
    intent: str,
    message: str,
    tool_failed: bool = False,
    has_security_event: bool = False,
    repeated_low_confidence: bool = False,
) -> EscalationCheck:
    """Checks the explicit FR-14 escalation triggers that are independent of
    the composite confidence score. Threshold-based escalation is handled
    separately by the caller comparing compute_confidence(...) to the
    agent's (or default) confidence_threshold.
    """
    if intent == "human_agent_request":
        return EscalationCheck(True, "Customer explicitly requested a human agent.")

    lowered = message.lower()
    for keyword in SENSITIVE_KEYWORDS:
        if keyword in lowered:
            return EscalationCheck(True, f"Message matched sensitive-topic trigger: '{keyword}'.")

    if tool_failed:
        return EscalationCheck(True, "A tool call failed during this turn.")

    if has_security_event:
        return EscalationCheck(True, "A security event was recorded for this conversation.")

    if repeated_low_confidence:
        return EscalationCheck(
            True, f"{REPEATED_FAILURE_WINDOW}+ consecutive low-confidence responses in this conversation."
        )

    return EscalationCheck(False, None)
