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
        """Very small runner that echoes or executes a matching tool."""
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

        # Default behaviour: echo message
        return Result(message)
