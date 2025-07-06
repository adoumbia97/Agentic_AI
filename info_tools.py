from __future__ import annotations

import logging
from pathlib import Path
import requests

from simple_agents import function_tool

DOCS_DIR = Path("docs")


@function_tool
def get_information(topic: str, source: str) -> str:
    """Retrieve information on a topic from 'kb' or 'internet'."""
    topic = topic.lower().strip()
    if source == "kb":
        file_path = DOCS_DIR / f"{topic}.txt"
        if file_path.is_file():
            return file_path.read_text(encoding="utf-8")
        return "No information found in the knowledge base."
    if source == "internet":
        try:
            resp = requests.get(
                f"https://duckduckgo.com/?q={topic}&format=json", timeout=10
            )
            if resp.ok:
                data = resp.json()
                abstract = data.get("Abstract") or "No information found."
                return abstract
            return f"Internet search failed with status {resp.status_code}."
        except Exception as exc:  # pragma: no cover - network call
            logging.getLogger(__name__).error("Internet search failed: %s", exc)
            return f"Internet search failed: {exc}"
    return "Invalid source. Use 'internet' or 'kb'."


get_information.openai_schema = {
    "type": "function",
    "function": {
        "name": "get_information",
        "description": (
            "Retrieve additional information from a topic using either the"
            " internet or the knowledge base."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "source": {"type": "string", "enum": ["internet", "kb"]},
            },
            "required": ["topic", "source"],
        },
    },
}
