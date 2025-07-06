import sys
from pathlib import Path
import os
import openai

os.environ.pop("OPENAI_API_KEY", None)
openai.api_key = None

sys.path.append(str(Path(__file__).resolve().parent.parent))  # noqa: E402

from food_security import FoodSecurityHandler  # noqa: E402


def test_handler_collects_and_analyzes():
    handler = FoodSecurityHandler()

    step1 = handler.collect()
    assert "commodity" in step1.lower()

    step2 = handler.collect(commodity_name="maize")
    assert "price last month" in step2.lower()

    step3 = handler.collect(price_last_month=110)
    assert "price two months ago" in step3.lower()

    step4 = handler.collect(price_two_months_ago=100)
    assert "availability" in step4.lower()

    step5 = handler.collect(availability_level="high")
    assert "country" in step5.lower()

    final = handler.collect(country="Kenya")
    assert "analysis failed:" in final.lower()
