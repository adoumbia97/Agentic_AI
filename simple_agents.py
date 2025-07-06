from dataclasses import dataclass
from typing import Callable, List, Union
import re


def function_tool(func: Callable) -> Callable:
    """Decorator to mark a function as an agent tool."""
    func.is_tool = True
    return func


@dataclass
class Agent:
    name: str
    instructions: str
    tools: List[Callable]


class Result:
    def __init__(self, final_output: str):
        self.final_output = final_output


class Runner:
    @staticmethod
    async def run(
        agent: Agent,
        input: Union[str, List[dict]],
        history_size: int = 3,
    ) -> Result:
        """
        Lightweight runner that executes tools or returns canned responses.
        """

        # Extract message content and maintain short history
        history: List[dict] = []
        if isinstance(input, list) and input:
            history = input[-(history_size * 2 + 1):]
            message = input[-1].get("content", "")
        else:
            message = str(input)

        # Find the previous user message
        prev_user = ""
        for m in reversed(history[:-1]):
            if m.get("role") == "user":
                prev_user = m.get("content", "")
                break

        lowered = message.lower().strip()

        # Memory-based reply for simple recall
        if "what did i just say" in lowered and prev_user:
            return Result(prev_user)

        # Tool invocation when message starts with tool name
        for tool in agent.tools:
            if lowered.startswith(tool.__name__.lower()):
                arg = message[len(tool.__name__):].strip()
                try:
                    result = tool(arg)
                except Exception as exc:
                    result = f"Error running tool {tool.__name__}: {exc}"
                return Result(str(result))

        # Natural language trigger for get_weather
        weather_tool = next(
            (t for t in agent.tools if t.__name__ == "get_weather"),
            None,
        )
        if weather_tool:
            match = re.search(
                r"(?:weather|umbrella).* in ([A-Za-z ]+)",
                lowered,
            )
            if match:
                city = match.group(1).strip().title()
                try:
                    result = weather_tool(city)
                except Exception as exc:
                    result = f"Error running tool get_weather: {exc}"
                return Result(str(result))

        # Very small set of canned replies so the bot feels conversational
        if lowered in {"hi", "hello"}:
            return Result("Hello! How can I assist you today?")
        if lowered == "help":
            return Result(
                "Ask about the weather, fetch docs with 'fetch_doc',"
                " show the time with 'show_time', or clear history with "
                "'clear history'."
            )

        # Default behaviour: generic fallback
        return Result("I'm not sure how to help with that.")
