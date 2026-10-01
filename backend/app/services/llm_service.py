"""Thin wrapper around the OpenAI SDK for chat completions.

Raises a clear, actionable error if no API key is configured rather than
returning a fake/mocked response — see docs/architecture.md.
"""
import json

from openai import OpenAI

from app.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = (
    "You are a helpful, honest customer support assistant for AICSP. "
    "Answer clearly and concisely. If you are not confident in an answer, "
    "say so plainly rather than guessing."
)


class OpenAIKeyMissingError(RuntimeError):
    """Raised when a real OpenAI call is attempted without a configured API key."""


def _client() -> OpenAI:
    if not settings.has_openai_key:
        raise OpenAIKeyMissingError(
            "OPENAI_API_KEY is not configured. Set it in backend/.env to enable live chat "
            "responses (see .env.example). No mocked/fake responses are returned."
        )
    return OpenAI(api_key=settings.openai_api_key)


def generate_chat_reply(history: list[dict[str, str]]) -> str:
    """history: list of {"role": "user"|"assistant", "content": str}, oldest first."""
    client = _client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    completion = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        temperature=0.3,
    )
    return completion.choices[0].message.content or ""


GROUNDED_SYSTEM_PROMPT = (
    "You are a helpful, honest customer support assistant for AICSP. "
    "Answer the user's question using ONLY the numbered context passages below. "
    "Cite the passage numbers you relied on in square brackets, e.g. [1]. "
    "If the context does not contain enough information to answer, say so "
    "plainly instead of guessing."
)


def generate_grounded_reply(history: list[dict[str, str]], context_passages: list[str]) -> str:
    """history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    context_passages: retrieved knowledge-base chunk texts, most relevant first.
    """
    client = _client()
    context_block = "\n\n".join(f"[{i + 1}] {passage}" for i, passage in enumerate(context_passages))
    system_prompt = f"{GROUNDED_SYSTEM_PROMPT}\n\nContext:\n{context_block}"
    messages = [{"role": "system", "content": system_prompt}, *history]
    completion = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        temperature=0.2,
    )
    return completion.choices[0].message.content or ""


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Returns one embedding vector per input text, preserving order."""
    if not texts:
        return []
    client = _client()
    response = client.embeddings.create(model=settings.openai_embedding_model, input=texts)
    return [item.embedding for item in response.data]


def classify_intent(message: str, intent_labels: list[str]) -> tuple[str, float]:
    """Classifies `message` into one of `intent_labels` using a JSON-constrained
    chat completion. Returns (intent_name, confidence in [0, 1]). Falls back to
    ("unknown", 0.0) if the model's output can't be parsed as one of the
    allowed labels — this is a parsing safeguard, not a fabricated answer; the
    underlying LLM call still must succeed (raises OpenAIKeyMissingError if
    not configured).
    """
    client = _client()
    system_prompt = (
        "Classify the user's message into exactly one of these intents: "
        f"{', '.join(intent_labels)}. "
        'Respond with strict JSON only: {"intent": "<label>", "confidence": <0-1 float>}. '
        'Use "unknown" if none of the other labels clearly apply.'
    )
    completion = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
        intent = str(parsed.get("intent", "unknown"))
        confidence = float(parsed.get("confidence", 0.0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return "unknown", 0.0

    if intent not in intent_labels:
        return "unknown", 0.0
    return intent, max(0.0, min(1.0, confidence))


def extract_tool_arguments(message: str, tool_name: str, tool_description: str, input_schema: dict) -> dict:
    """Uses a JSON-constrained chat completion to extract the arguments for a
    tool call from the user's message, per `input_schema` (a JSON Schema
    object, see app.models.agent.Tool.input_schema). Returns a dict of
    extracted arguments (possibly missing optional/unresolvable fields);
    callers validate the result against the schema before executing.
    """
    client = _client()
    system_prompt = (
        f"Extract the arguments needed to call the tool '{tool_name}' ({tool_description}) "
        "from the user's message. The tool's JSON Schema is below. Respond with strict JSON "
        "only, containing just the argument values (no extra keys, no wrapper object).\n\n"
        f"Schema: {json.dumps(input_schema)}"
    )
    completion = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
