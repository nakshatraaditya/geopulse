import sys
sys.path.insert(0, "src")

from geopulse.analysis.price_model import (
    sentiment_to_multiplier,
    deviation_to_multiplier,
    days_to_multiplier,
)

def test_very_negative_sentiment_raises_price():
    assert sentiment_to_multiplier(-0.8) > 1.0

def test_positive_sentiment_lowers_price():
    assert sentiment_to_multiplier(0.8) < 1.0

def test_neutral_sentiment_no_change():
    assert sentiment_to_multiplier(0.0) == 1.0

def test_high_deviations_raises_price():
    assert deviation_to_multiplier(150) > deviation_to_multiplier(5)

def test_no_deviations_no_change():
    assert deviation_to_multiplier(0) == 1.0

def test_last_minute_most_expensive():
    assert days_to_multiplier(2) > days_to_multiplier(30)

def test_sweet_spot_cheapest():
    assert days_to_multiplier(30) <= days_to_multiplier(7)
    assert days_to_multiplier(30) <= days_to_multiplier(100)