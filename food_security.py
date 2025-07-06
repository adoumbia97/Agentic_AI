from dataclasses import dataclass, field
from typing import Any, Dict
import logging

try:
    import openai
except Exception:  # pragma: no cover - openai optional for tests
    openai = None

from openai_config import load_api_key, get_client

from simple_agents import function_tool, _msg_attr

# OpenAI-compatible tool schema
FOOD_SECURITY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "food_security_analyst",
        "description": (
            "Provide an expert level food security analysis using recent prices "
            "and availability levels for a commodity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "commodity_name": {
                    "type": "string",
                    "description": "Name of the commodity",
                },
                "price_last_month": {
                    "type": "number",
                    "description": "Price of the commodity last month",
                },
                "price_two_months_ago": {
                    "type": "number",
                    "description": "Price two months ago",
                },
                "availability_level": {
                    "type": "string",
                    "enum": ["high", "moderate", "low"],
                    "description": "Current availability level",
                },
                "country": {
                    "type": "string",
                    "description": "Country of interest",
                },
            },
            "required": [
                "commodity_name",
                "price_last_month",
                "price_two_months_ago",
                "availability_level",
                "country",
            ],
        },
    },
}


@dataclass
class FoodSecurityHandler:
    """Stateful handler that collects required fields before analysis."""

    data: Dict[str, Any] = field(default_factory=dict)

    order = [
        "commodity_name",
        "price_last_month",
        "price_two_months_ago",
        "availability_level",
        "country",
    ]

    def collect(self, **kwargs) -> str:
        """Collect fields and return either a prompt or the final analysis."""
        self.data.update({k: v for k, v in kwargs.items() if v is not None})
        for key in self.order:
            if key not in self.data:
                if key == "commodity_name":
                    return "What commodity would you like to analyze?"
                if key == "price_last_month":
                    item = self.data.get("commodity_name", "it")
                    return f"Sure, to analyze {item}, could you tell me the price last month?"
                if key == "price_two_months_ago":
                    return "And what was the price two months ago?"
                if key == "availability_level":
                    item = self.data.get("commodity_name", "it")
                    return f"How is {item} availability now: high, moderate, or low?"
                if key == "country":
                    item = self.data.get("commodity_name", "this commodity")
                    return f"Which country are we assessing for {item}?"
        return self._analysis()

    def _analysis(self) -> str:
        """Generate a detailed market assessment using OpenAI."""
        name = self.data["commodity_name"]
        country = self.data["country"]
        last = float(self.data["price_last_month"])
        prev = float(self.data["price_two_months_ago"])
        avail = self.data["availability_level"]

        load_api_key()
        if not openai or not getattr(openai, "api_key", None):
            return "Analysis failed: OpenAI API key not configured."

        system_prompt = (
            "You are a professional food security analyst. Use the provided figures "
            "to produce a thorough assessment. Discuss price trends in percentage and "
            "volatility, the impact of availability, any relevant country context such "
            "as policy, climate, or conflict, and conclude with potential recommendations. "
            "Your reply must contain at least eight sentences and begin with 'Analysis:'"
        )

        user_content = (
            f"Commodity: {name}\n"
            f"Price last month: {last}\n"
            f"Price two months ago: {prev}\n"
            f"Availability level: {avail}\n"
            f"Country: {country}"
        )

        try:
            client = get_client()
            if not client:
                raise RuntimeError("OpenAI client not configured")
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            client.close()
            try:
                choice = response.choices[0]
                msg = _msg_attr(choice, "message")
                text = str(_msg_attr(msg, "content", "")).strip()
            except Exception:
                logging.getLogger(__name__).error(
                    "Invalid food security response structure: %s", response
                )
                text = ""
            if not text.lower().startswith("analysis"):
                text = f"Analysis: {text}"
            return text
        except Exception as exc:  # pragma: no cover - network call
            return (
                "Analysis: An error occurred while contacting the analysis service: "
                f"{exc}"
            )


@function_tool
def food_security_analyst(
    commodity_name: str,
    price_last_month: float,
    price_two_months_ago: float,
    availability_level: str,
    country: str,
) -> str:
    """Return expert food security analysis."""
    handler = FoodSecurityHandler(
        {
            "commodity_name": commodity_name,
            "price_last_month": price_last_month,
            "price_two_months_ago": price_two_months_ago,
            "availability_level": availability_level,
            "country": country,
        }
    )
    return handler.collect()


food_security_analyst.openai_schema = FOOD_SECURITY_SCHEMA
