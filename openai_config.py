from __future__ import annotations

import logging
import os
import httpx

try:
    import openai
except Exception:  # pragma: no cover - openai optional for tests
    openai = None


def load_api_key() -> str | None:
    """Load OpenAI API key from environment or optional .env file."""
    if not openai:
        return None
    if getattr(openai, "api_key", None):
        return openai.api_key

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        try:
            import dotenv  # type: ignore

            dotenv.load_dotenv()
            key = os.getenv("OPENAI_API_KEY")
        except Exception:
            key = None

    if key:
        openai.api_key = key
    else:
        logging.getLogger(__name__).warning("OpenAI API key not configured.")
    return key


def require_api_key() -> str:
    """Ensure an API key is loaded, raising RuntimeError if missing."""
    key = load_api_key()
    if not key:
        raise RuntimeError("OpenAI API key not configured.")
    return key


def get_async_client() -> "openai.AsyncOpenAI | None":
    """Return an AsyncOpenAI client or None if not configured."""
    if not load_api_key() or not openai:
        return None
    return openai.AsyncOpenAI(
        http_client=httpx.AsyncClient(proxy=None, trust_env=False)
    )


def get_client() -> "openai.OpenAI | None":
    """Return a synchronous OpenAI client or None if not configured."""
    if not load_api_key() or not openai:
        return None
    return openai.OpenAI(http_client=httpx.Client(proxy=None, trust_env=False))
