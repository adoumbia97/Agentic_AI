from dataclasses import dataclass, field
from typing import Callable, List, Union, Any, Dict
import re
import inspect
import json
import logging

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
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(__name__), repr=False
    )


class Result:
    def __init__(self, final_output: str):
        self.final_output = final_output


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

            if "what did i just say" in lowered and prev_user:
                return prev_user

            for tool in agent.tools:
                if lowered.startswith(tool.__name__.lower()):
                    arg = msg[len(tool.__name__):].strip()
                    try:
                        return str(tool(arg))
                    except Exception as exc:
                        return f"Error running tool {tool.__name__}: {exc}"

            weather_tool = next(
                (t for t in agent.tools if t.__name__ == "get_weather"),
                None,
            )
            if weather_tool:
                match = re.search(
                    r"(?:weather|forecast|temperature|umbrella|rain)"
                    r".*(?:in|for) ([A-Za-z ]+)",
                    lowered,
                )
                if match:
                    city = match.group(1).strip().title()
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

        messages = [
            {"role": "system", "content": agent.instructions}
        ] + agent.history

        print("Sending messages to OpenAI:", messages)

        requested_tool = None
        for tool in agent.tools:
            if re.search(rf"\b{tool.__name__}\b", message, re.IGNORECASE):
                requested_tool = tool
                break

        def _tool_spec(func: Callable) -> Dict[str, Any]:
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
                functions=[_tool_spec(t) for t in agent.tools]
                if requested_tool
                else None,
                function_call={"name": requested_tool.__name__}
                if requested_tool
                else "none",
            )
            print("OpenAI response:", response)
            msg = response.choices[0].message
            if msg.get("function_call"):
                name = msg["function_call"]["name"]
                args = json.loads(
                    msg["function_call"].get("arguments", "{}")
                )
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
                agent.history.append({
                    "role": "assistant",
                    "content": "",
                    "function_call": msg["function_call"],
                })
                agent.history.append({
                    "role": "function",
                    "name": name,
                    "content": str(result),
                })
                follow = await openai.ChatCompletion.acreate(
                    model="gpt-3.5-turbo-0613",
                    messages=[
                        {"role": "system", "content": agent.instructions}
                    ]
                    + agent.history,
                )
                final = follow.choices[0].message.content
            else:
                final = msg.get("content", "")
            if not final.strip():
                final = "..."
            agent.history.append({"role": "assistant", "content": final})
            agent.history = agent.history[-history_size:]
            agent.logger.debug("[openai] user=%s reply=%s", message, final)
            return Result(final)
        except Exception as exc:
            agent.logger.exception("OpenAI request failed: %s", exc)
            reply = _simple_reply(message, agent.history)
            agent.history.append({"role": "assistant", "content": reply})
            agent.history = agent.history[-history_size:]
            return Result(reply)
