from dataclasses import dataclass, field
from typing import Any, Dict

try:
    import openai
except Exception:  # pragma: no cover - openai optional for tests
    openai = None

from simple_agents import function_tool

# OpenAI-compatible function schema
FOOD_SECURITY_SCHEMA = {
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
        name = self.data["commodity_name"]
        country = self.data["country"]
        last = float(self.data["price_last_month"])
        prev = float(self.data["price_two_months_ago"])
        avail = self.data["availability_level"].lower()

        system_prompt = (
            "You are a professional food security analyst. "
            "Use the provided figures to generate a comprehensive market assessment. "
            "Discuss price trends in percent and volatility, the impact of current "
            "availability, any relevant country context such as policy, climate or "
            "conflict, and close with possible recommendations. Your reply must "
            "contain at least eight sentences and begin with 'Analysis:'"
        )

        user_content = (
            f"Commodity: {name}\n"
            f"Country: {country}\n"
            f"Price last month: {last}\n"
            f"Price two months ago: {prev}\n"
            f"Availability level: {avail}"
        )

        if openai and getattr(openai, "api_key", None):
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo-0613",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                )
                text = response.choices[0].message.content.strip()
                if not text.lower().startswith("analysis"):
                    text = f"Analysis: {text}"
                return text
            except Exception as exc:  # pragma: no cover - network call
                return (
                    "Analysis: An error occurred while contacting the analysis "
                    f"service: {exc}"
                )

        change = last - prev
        pct = (change / prev) * 100 if prev else 0
        trend = (
            "increased" if change > 0 else "decreased" if change < 0 else "remained stable"
        )
        availability_text = {
            "high": "supplies are plentiful",
            "moderate": "supplies are somewhat constrained",
            "low": "there are significant shortages",
        }.get(avail, "availability information is unclear")
        return (
            "Analysis: "
            f"The price of {name} in {country} has {trend} by {pct:.1f}% over the last "
            f"two months, moving from {prev} to {last}. Current availability is {avail}, "
            f"meaning {availability_text}. These market conditions may affect household "
            f"purchasing power and broader food security. Continued monitoring and risk "
            "mitigation efforts are advised."
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
