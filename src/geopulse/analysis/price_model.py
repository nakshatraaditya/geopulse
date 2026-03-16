import logging
from geopulse.flights.fuel import get_latest_fuel_price

logger = logging.getLogger(__name__)

ROUTE_CONFIG = {
    ("LHR", "DXB"): {
        "distance_km":   5500,
        "base_fare_gbp": 380,
        "label":         "London → Dubai",
        "zones":         ["iranian_airspace", "red_sea_corridor"],
    },
    ("LHR", "TLV"): {
        "distance_km":   3600,
        "base_fare_gbp": 220,
        "label":         "London → Tel Aviv",
        "zones":         ["iraqi_syrian_airspace"],
    },
    ("LHR", "DEL"): {
        "distance_km":   6700,
        "base_fare_gbp": 420,
        "label":         "London → Delhi",
        "zones":         ["iranian_airspace", "russian_airspace"],
    },
    ("LHR", "BKK"): {
        "distance_km":   9500,
        "base_fare_gbp": 520,
        "label":         "London → Bangkok",
        "zones":         ["russian_airspace", "red_sea_corridor"],
    },
    ("LHR", "HKG"): {
        "distance_km":   9600,
        "base_fare_gbp": 580,
        "label":         "London → Hong Kong",
        "zones":         ["russian_airspace"],
    },
    ("LHR", "NRT"): {
        "distance_km":   9600,
        "base_fare_gbp": 620,
        "label":         "London → Tokyo",
        "zones":         ["russian_airspace"],
    },
}

#FUEL_BURN_PER_KM = 0.023
#GALLONS_TO_GBP   = 0.79
BASE_FUEL_PRICE  = 2.50

ZONE_MULTIPLIERS = {
    "russian_airspace":      1.06,
    "ukrainian_airspace":    1.04,
    "iranian_airspace":      1.05,
    "iraqi_syrian_airspace": 1.03,
    "red_sea_corridor":      1.07,
}

def sentiment_to_multiplier(avg_sentiment: float) -> float:
    if avg_sentiment <= -0.5:
        return 1.04
    elif avg_sentiment <= -0.2:
        return 1.02
    elif avg_sentiment >= 0.5:
        return 0.99
    else:
        return 1.0

def deviation_to_multiplier(deviation_count: int) -> float:
    if deviation_count >= 500:
        return 1.08
    elif deviation_count >= 200:
        return 1.05
    elif deviation_count >= 100:
        return 1.03
    elif deviation_count >= 50:
        return 1.01
    else:
        return 1.0

def days_to_multiplier(days_to_departure: int) -> float:
    if days_to_departure <= 3:
        return 1.35
    elif days_to_departure <= 7:
        return 1.20
    elif days_to_departure <= 14:
        return 1.10
    elif days_to_departure <= 21:
        return 1.03
    elif days_to_departure <= 56:
        return 1.0
    elif days_to_departure <= 90:
        return 1.05
    else:
        return 1.12

def estimate_price(
    origin: str,
    destination: str,
    db_path: str,
    avg_sentiment: float = 0.0,
    deviation_count: int = 0,
    active_zones: list = None,
    days_to_departure: int = 30,
    fuel_price_override: float = None
) -> dict:
    route = ROUTE_CONFIG.get((origin, destination))
    if not route:
        logger.warning(f"No route config for {origin}→{destination}")
        return {}

    fuel_price  = fuel_price_override or get_latest_fuel_price(db_path)
    base        = route["base_fare_gbp"]
    active      = active_zones or []

    # Fuel is ~28% of base fare at $2.50/gal baseline
    # Scale proportionally with actual fuel price
    fuel_adjustment = base * 0.28 * (fuel_price / BASE_FUEL_PRICE - 1)

    zone_mult = 1.0
    triggered_zones = []
    for zone in route["zones"]:
        if zone in active:
            mult = ZONE_MULTIPLIERS.get(zone, 1.0)
            zone_mult = max(zone_mult, mult)
            triggered_zones.append(zone)

    sent_mult      = sentiment_to_multiplier(avg_sentiment)
    deviation_mult = deviation_to_multiplier(deviation_count)
    days_mult      = days_to_multiplier(days_to_departure)

    estimated_price = (
        (base + fuel_adjustment)
        * zone_mult
        * sent_mult
        * deviation_mult
        * days_mult
    )

    pct_above_base = ((estimated_price - base) / base) * 100

    if pct_above_base >= 30:
        risk_level = "CRITICAL"
    elif pct_above_base >= 20:
        risk_level = "HIGH"
    elif pct_above_base >= 10:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    result = {
        "origin":              origin,
        "destination":         destination,
        "label":               route["label"],
        "base_fare_gbp":       round(base, 2),
        "fuel_adjustment_gbp": round(fuel_adjustment, 2),
        "fuel_price_usd_gal":  round(fuel_price, 4),
        "zone_multiplier":     round(zone_mult, 4),
        "sentiment_mult":      round(sent_mult, 4),
        "deviation_mult":      round(deviation_mult, 4),
        "days_mult":           round(days_mult, 4),
        "estimated_price_gbp": round(estimated_price, 2),
        "pct_above_base":      round(pct_above_base, 1),
        "risk_level":          risk_level,
        "triggered_zones":     triggered_zones,
        "days_to_departure":   days_to_departure,
    }

    logger.info(
        f"{route['label']}: £{result['estimated_price_gbp']} "
        f"(+{result['pct_above_base']}%) — {risk_level}"
    )
    return result

def estimate_all_routes(
    db_path: str,
    avg_sentiment: float = 0.0,
    deviation_count: int = 0,
    active_zones: list = None,
    days_to_departure: int = 30
) -> list[dict]:
    """Run price estimation across all watched routes."""
    results = []
    for origin, destination in ROUTE_CONFIG.keys():
        result = estimate_price(
            origin=origin,
            destination=destination,
            db_path=db_path,
            avg_sentiment=avg_sentiment,
            deviation_count=deviation_count,
            active_zones=active_zones,
            days_to_departure=days_to_departure
        )
        if result:
            results.append(result)
    results.sort(key=lambda x: x["pct_above_base"], reverse=True)
    return results