import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import openai

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from simple_agents import Agent, Runner  # noqa: E402
from food_security import FoodSecurityHandler  # noqa: E402


@pytest.mark.asyncio
async def test_runner_uses_updated_model():
    mock_client = Mock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(choices=[Mock(message={"content": "hi"})])
    )
    mock_client.aclose = AsyncMock()
    with patch.object(openai, "api_key", "test"):
        with patch("simple_agents.get_async_client", return_value=mock_client):
            agent = Agent(name="T", instructions="test", tools=[])
            await Runner.run(agent, "hello")
            assert (
                mock_client.chat.completions.create.call_args.kwargs["model"]
                == "gpt-3.5-turbo"
            )
            assert "tool_choice" not in mock_client.chat.completions.create.call_args.kwargs


def test_food_security_analysis_uses_updated_model():
    mock_resp = Mock(choices=[Mock(message=Mock(content="Analysis: ok"))])
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = mock_resp
    with patch.object(openai, "api_key", "test"):
        with patch("food_security.get_client", return_value=mock_client):
            handler = FoodSecurityHandler(
                {
                    "commodity_name": "rice",
                    "price_last_month": 1,
                    "price_two_months_ago": 2,
                    "availability_level": "high",
                    "country": "USA",
                }
            )
            text = handler._analysis()
            assert text.startswith("Analysis:")
            assert (
                mock_client.chat.completions.create.call_args.kwargs["model"]
                == "gpt-3.5-turbo"
            )
