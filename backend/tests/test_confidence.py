"""Composite confidence scoring + escalation trigger unit tests (Phase 10,
FR-13/FR-14). Pure functions - no DB/HTTP needed.
"""
from app.services import confidence_service
from app.services.confidence_service import ConfidenceSignals


def test_compute_confidence_with_all_signals():
    signals = ConfidenceSignals(
        intent_confidence=0.8,
        retrieval_relevance=0.6,
        source_coverage=1.0,
        grounding_score=0.5,
        tool_success_rate=1.0,
    )
    score = confidence_service.compute_confidence(signals)
    expected = 0.25 * 0.8 + 0.25 * 0.6 + 0.15 * 1.0 + 0.20 * 0.5 + 0.15 * 1.0
    assert round(score, 4) == round(expected, 4)


def test_compute_confidence_renormalizes_missing_signals():
    # Only intent_confidence applies (no RAG, no tools): the composite
    # should equal the intent confidence itself, not be diluted toward 0.
    signals = ConfidenceSignals(intent_confidence=0.9)
    assert confidence_service.compute_confidence(signals) == 0.9


def test_compute_confidence_no_signals_returns_zero():
    assert confidence_service.compute_confidence(ConfidenceSignals()) == 0.0


def test_compute_confidence_clamped_to_unit_interval():
    signals = ConfidenceSignals(intent_confidence=1.5)
    assert confidence_service.compute_confidence(signals) == 1.0


def test_grounding_score_no_sources_returns_none():
    assert confidence_service.grounding_score("Some answer with no citations.", 0) is None


def test_grounding_score_counts_valid_citations():
    answer = "The refund policy allows returns within 30 days [1]. See also [2]."
    assert confidence_service.grounding_score(answer, 2) == 1.0


def test_grounding_score_partial_citations():
    answer = "The refund policy allows returns within 30 days [1]."
    assert confidence_service.grounding_score(answer, 2) == 0.5


def test_grounding_score_ignores_out_of_range_citations():
    answer = "See [1] and [99] for details."
    assert confidence_service.grounding_score(answer, 1) == 1.0


def test_detect_trigger_human_agent_request():
    result = confidence_service.detect_trigger(intent="human_agent_request", message="let me talk to a person")
    assert result.should_escalate is True
    assert "human agent" in result.reason.lower()


def test_detect_trigger_sensitive_keyword():
    result = confidence_service.detect_trigger(intent="complaint", message="I am going to sue you over this")
    assert result.should_escalate is True
    assert "sensitive" in result.reason.lower()


def test_detect_trigger_tool_failure():
    result = confidence_service.detect_trigger(intent="order_tracking", message="where is my order", tool_failed=True)
    assert result.should_escalate is True
    assert "tool call failed" in result.reason.lower()


def test_detect_trigger_security_event():
    result = confidence_service.detect_trigger(intent="faq", message="hello", has_security_event=True)
    assert result.should_escalate is True
    assert "security event" in result.reason.lower()


def test_detect_trigger_repeated_low_confidence():
    result = confidence_service.detect_trigger(intent="faq", message="hello", repeated_low_confidence=True)
    assert result.should_escalate is True
    assert "low-confidence" in result.reason.lower()


def test_detect_trigger_no_match_returns_false():
    result = confidence_service.detect_trigger(intent="faq", message="what are your hours?")
    assert result.should_escalate is False
    assert result.reason is None
