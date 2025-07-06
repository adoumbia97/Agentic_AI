from __future__ import annotations

import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Union

if TYPE_CHECKING:  # pragma: no cover - used for linting only
    from food_security import FoodSecurityHandler

try:
    import openai
except Exception:  # pragma: no cover - openai optional for tests
    openai = None


def function_tool(func: Callable) -> Callable:
    """Decorator to mark a function as an agent tool."""
    func.is_tool = True
    return func


@dataclass
class Agent:
    name: str
    instructions: str
    tools: List[Callable]
    history: List[Dict[str, Any]] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict, repr=False)
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(__name__), repr=False
    )


class Result:
    def __init__(self, final_output: str):
        self.final_output = final_output


def _parse_food_security_reply(
    text: str, handler: FoodSecurityHandler
) -> Dict[str, Any]:
    """Extract the next required value from a user reply."""
    pending = next((k for k in handler.order if k not in handler.data), None)
    if not pending:
        return {}
    if pending in {"price_last_month", "price_two_months_ago"}:
        match = re.search(r"[-+]?\d*\.?\d+", text)
        if match:
            return {pending: float(match.group())}
    elif pending == "availability_level":
        for lvl in ["high", "moderate", "low"]:
            if lvl in text:
                return {pending: lvl}
    else:
        words = text.split()
        if words:
            return {pending: words[0]}
    return {}


class Runner:
    @staticmethod
    async def run(
        agent: Agent,
        input: Union[str, List[dict]],
        history_size: int = 20,
    ) -> Result:
        """Chat runner using OpenAI if configured with basic fallback."""

        def _simple_reply(msg: str, hist: List[dict]) -> str:
            prev_user = ""
            for m in reversed(hist[:-1]):
                if m.get("role") == "user":
                    prev_user = m.get("content", "")
                    break

            lowered = msg.lower().strip()

            if (
                any(
                    phrase in lowered
                    for phrase in [
                        "what did i just say",
                        "what was my last message",
                        "what was my last question",
                        "what did i just ask",
                    ]
                )
                and prev_user
            ):
                return prev_user

            fs_key = "food_security_handler"
            if fs_key in agent.state:
                from food_security import FoodSecurityHandler

                handler: FoodSecurityHandler = agent.state[fs_key]
                prompt = handler.collect(**_parse_food_security_reply(lowered, handler))
                if "analysis:" in prompt.lower():
                    agent.state.pop(fs_key, None)
                return prompt

            match = re.search(r"(?:analy[sz]e|analysis(?: of)?)\s+(\w+)", lowered)
            if match:
                from food_security import FoodSecurityHandler

                commodity = match.group(1)
                agent.state[fs_key] = FoodSecurityHandler({"commodity_name": commodity})
                return (
                    f"Sure, I can help with a food security analysis. Let's start. "
                    f"What was the price of {commodity} last month?"
                )

            for tool in agent.tools:
                if lowered.startswith(tool.__name__.lower()):
                    remainder = msg[len(tool.__name__) :].strip()
                    parts = remainder.split()
                    sig = inspect.signature(tool)
                    if len(parts) == len(sig.parameters):
                        try:
                            return str(tool(*parts))
                        except Exception as exc:
                            return f"Error running tool {tool.__name__}: {exc}"
                    if tool.__name__ == "food_security_analyst":
                        from food_security import FoodSecurityHandler

                        commodity = parts[0] if parts else ""
                        agent.state[fs_key] = FoodSecurityHandler(
                            {"commodity_name": commodity} if commodity else {}
                        )
                        first_prompt = agent.state[fs_key].collect(
                            commodity_name=commodity or None
                        )
                        return (
                            f"Sure, to analyze {commodity}, could you tell me the price last month?"
                            if commodity
                            else first_prompt
                        )
                    return f"Error running tool {tool.__name__}: incorrect arguments"

            weather_tool = next(
                (t for t in agent.tools if t.__name__ == "get_weather"),
                None,
            )
            if weather_tool:
                match = re.search(
                    r"(?:weather|forecast|temperature|umbrella|rain)"
                    r".*(?:in|for|of) ([A-Za-z ]+)",
                    lowered,
                )
                if not match:
                    match = re.search(
                        r"([A-Za-z ]+)\s+(?:weather|forecast)",
                        lowered,
                    )
                if match:
                    grp = match.lastindex or 1
                    city = match.group(grp).strip().title()
                    try:
                        return str(weather_tool(city))
                    except Exception as exc:
                        return f"Error running tool get_weather: {exc}"

            if lowered in {"hi", "hello"}:
                return "Hello! How can I assist you today?"
            if lowered == "help":
                return (
                    "Ask about the weather, fetch docs with 'fetch_doc',"
                    " show the time with 'show_time', or clear history with "
                    "'clear history'."
                )

            return "I'm not sure how to help with that."

        if isinstance(input, list):
            incoming = [
                {
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                }
                for m in input
                if m.get("role") != "system"
            ]
            if incoming:
                message = incoming[-1]["content"]
                agent.history = incoming[-history_size:]
            else:
                message = ""
        else:
            message = str(input)
            agent.history.append({"role": "user", "content": message})
            agent.history = agent.history[-history_size:]

        if not openai or not getattr(openai, "api_key", None):
            reply = _simple_reply(message, agent.history)
            agent.history.append({"role": "assistant", "content": reply})
            agent.history = agent.history[-history_size:]
            agent.logger.debug("[local] user=%s reply=%s", message, reply)
            return Result(reply)

        messages = [{"role": "system", "content": agent.instructions}] + agent.history

        print("Sending messages to OpenAI:", messages)

        requested_tool = None
        for tool in agent.tools:
            if re.search(rf"\b{tool.__name__}\b", message, re.IGNORECASE):
                requested_tool = tool
                break

        def _tool_spec(func: Callable) -> Dict[str, Any]:
            if hasattr(func, "openai_schema"):
                return func.openai_schema  # type: ignore[return-value]
            sig = inspect.signature(func)
            params = {name: {"type": "string"} for name in sig.parameters}
            return {
                "name": func.__name__,
                "description": func.__doc__ or "",
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": list(params.keys()),
                },
            }

        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo-0613",
                messages=messages,
                functions=(
                    [_tool_spec(t) for t in agent.tools] if requested_tool else None
                ),
                function_call=(
                    {"name": requested_tool.__name__} if requested_tool else "none"
                ),
            )
            print("OpenAI response:", response)
            msg = response.choices[0].message
            if msg.get("function_call"):
                name = msg["function_call"]["name"]
                args = json.loads(msg["function_call"].get("arguments", "{}"))
                tool = next(
                    (t for t in agent.tools if t.__name__ == name),
                    None,
                )
                result = ""
                if tool:
                    try:
                        result = tool(**args)
                    except Exception as exc:
                        result = f"Error running tool {name}: {exc}"
                agent.history.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "function_call": msg["function_call"],
                    }
                )
                agent.history.append(
                    {
                        "role": "function",
                        "name": name,
                        "content": str(result),
                    }
                )
                follow = await openai.ChatCompletion.acreate(
                    model="gpt-3.5-turbo-0613",
                    messages=[{"role": "system", "content": agent.instructions}]
                    + agent.history,
                )
                final = follow.choices[0].message.content
            else:
                final = msg.get("content", "")
            if not final.strip():
                final = "Hmm, something went wrong. Can you try again?"
            agent.history.append({"role": "assistant", "content": final})
            agent.history = agent.history[-history_size:]
            agent.logger.debug("[openai] user=%s reply=%s", message, final)
            return Result(final)
        except Exception as exc:
            agent.logger.exception("OpenAI request failed: %s", exc)
            reply = "Hmm, something went wrong. Can you try again?"
            agent.history.append({"role": "assistant", "content": reply})
            agent.history = agent.history[-history_size:]
            return Result(reply)
