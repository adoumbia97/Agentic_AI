from dataclasses import dataclass, field
from typing import Any, Dict

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
        },
        "required": [
            "commodity_name",
            "price_last_month",
            "price_two_months_ago",
            "availability_level",
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
        return self._analysis()

    def _analysis(self) -> str:
        name = self.data["commodity_name"]
        last = float(self.data["price_last_month"])
        prev = float(self.data["price_two_months_ago"])
        avail = self.data["availability_level"].lower()
        change = last - prev
        pct = (change / prev) * 100 if prev else 0
        trend = (
            "increased"
            if change > 0
            else "decreased" if change < 0 else "remained stable"
        )
        availability_text = {
            "high": "supplies are plentiful",
            "moderate": "supplies are somewhat constrained",
            "low": "there are significant shortages",
        }.get(avail, "availability information is unclear")
        return (
            f"Commodity: {name}\n"
            f"Price last month: {last}\n"
            f"Price two months ago: {prev}\n"
            f"Availability: {avail}\n\n"
            f"Analysis: The price has {trend} by {pct:.1f}% compared with two months ago "
            f"and {availability_text}."
        )


@function_tool
def food_security_analyst(
    commodity_name: str,
    price_last_month: float,
    price_two_months_ago: float,
    availability_level: str,
) -> str:
    """Return expert food security analysis."""
    handler = FoodSecurityHandler(
        {
            "commodity_name": commodity_name,
            "price_last_month": price_last_month,
            "price_two_months_ago": price_two_months_ago,
            "availability_level": availability_level,
        }
    )
    return handler.collect()


food_security_analyst.openai_schema = FOOD_SECURITY_SCHEMA
