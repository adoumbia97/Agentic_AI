import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # noqa: E402

import pytest  # noqa: E402

from food_security import food_security_analyst  # noqa: E402
from simple_agents import Agent, Runner, function_tool  # noqa: E402


@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."


agent = Agent(
    name="Test", instructions="Test agent", tools=[get_weather, food_security_analyst]
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
async def test_weather_intent_parsing():
    result = await Runner.run(agent, input="What's the weather in Paris?")
    assert result.final_output == "The weather in Paris is sunny."


@pytest.mark.asyncio
async def test_weather_variations():
    res1 = await Runner.run(agent, input="Bamako weather?")
    assert res1.final_output == "The weather in Bamako is sunny."
    res2 = await Runner.run(agent, input="What is the weather of Bamako")
    assert res2.final_output == "The weather in Bamako is sunny."


@pytest.mark.asyncio
async def test_food_security_flow_start():
    result = await Runner.run(agent, input="I want to analyze rice")
    assert "price of rice last month" in result.final_output.lower()
