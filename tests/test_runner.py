import sys
from pathlib import Path
import os
import openai

os.environ.pop("OPENAI_API_KEY", None)
openai.api_key = None

sys.path.append(str(Path(__file__).resolve().parent.parent))  # noqa: E402

import pytest  # noqa: E402

from food_security import food_security_analyst  # noqa: E402
from simple_agents import Agent, Runner  # noqa: E402


agent = Agent(
    name="Test", instructions="Test agent", tools=[food_security_analyst]
)


@pytest.mark.asyncio
async def test_memory_absent():
    messages = [
        {"role": "system", "content": "test"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hello! How can I assist you today?"},
        {"role": "user", "content": "what did i just say"},
    ]
    result = await Runner.run(agent, input=messages)
    assert result.final_output == "hello"

@pytest.mark.asyncio
async def test_memory_last_message_phrase():
    messages = [
        {"role": "system", "content": "test"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hello! How can I assist you today?"},
        {"role": "user", "content": "what was my last message?"},
    ]
    result = await Runner.run(agent, input=messages)
    assert result.final_output == "hello"

@pytest.mark.asyncio
async def test_food_security_flow_start():
    result = await Runner.run(agent, input="I want to analyze rice")
    assert "price of rice last month" in result.final_output.lower()


@pytest.mark.asyncio
async def test_food_security_progress_summary():
    local_agent = Agent(name="T", instructions="Test agent", tools=[food_security_analyst])
    await Runner.run(local_agent, input="analyze wheat")
    summary = await Runner.run(local_agent, input="summary")
    assert "commodity name: wheat" in summary.final_output.lower()
