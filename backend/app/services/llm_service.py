"""Thin wrapper around the OpenAI SDK for chat completions.

Raises a clear, actionable error if no API key is configured rather than
returning a fake/mocked response — see docs/architecture.md.
"""
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


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Returns one embedding vector per input text, preserving order."""
    if not texts:
        return []
    client = _client()
    response = client.embeddings.create(model=settings.openai_embedding_model, input=texts)
    return [item.embedding for item in response.data]
