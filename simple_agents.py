from dataclasses import dataclass
from typing import Callable, List, Any, Union


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
    async def run(agent: Agent, input: Union[str, List[dict]]) -> Result:
        """Lightweight runner that executes tools or returns canned responses."""
        # Extract message content
        if isinstance(input, list) and input:
            message = input[-1].get("content", "")
        else:
            message = str(input)

        # Try to invoke a tool if message starts with tool name
        for tool in agent.tools:
            if message.lower().startswith(tool.__name__.lower()):
                arg = message[len(tool.__name__):].strip()
                try:
                    result = tool(arg)
                except Exception as exc:
                    result = f"Error running tool {tool.__name__}: {exc}"
                return Result(str(result))

        # Very small set of canned replies so the bot feels conversational
        lowered = message.lower().strip()
        if lowered in {"hi", "hello"}:
            return Result("Hello! How can I assist you today?")
        if lowered == "help":
            return Result(
                "You can ask me about the weather, fetch docs with 'fetch_doc', "
                "show the current time with 'show_time', or clear history with "
                "'clear history'."
            )

        # Default behaviour: generic fallback
        return Result("I'm not sure how to help with that.")
