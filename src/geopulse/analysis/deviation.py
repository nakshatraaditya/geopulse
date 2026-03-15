import logging
from geopulse.analysis.nofly import check_point, get_zone_description

logger = logging.getLogger(__name__)


PRE_CONFLICT_DURATIONS = {
    ("LHR", "DXB"): 420,         
    ("LHR", "TLV"): 270,  
    ("LHR", "DEL"): 510,   
    ("LHR", "BKK"): 660,   
    ("LHR", "HKG"): 720,   
    ("LHR", "NRT"): 780,            
    ("LHR", "BOM"): 540,           
    ("LHR", "PEK"): 780,          
    ("LHR", "AUH"): 450,       
}


DEVIATION_THRESHOLD = 0.10


FUEL_COST_PER_MINUTE_USD = 85

def analyse_states(states: list[dict]) -> list[dict]:
    
    deviations = []

    for state in states:
        lat = state.get("lat")
        lon = state.get("lon")

        if lat is None or lon is None:
            continue

        zones = check_point(lat, lon)

        if zones:
            descriptions = [get_zone_description(z) for z in zones]
            logger.warning(
                f"Flight {state.get('callsign', 'UNKNOWN')} "
                f"detected over: {', '.join(zones)}"
            )
            deviations.append({
                "callsign":    state.get("callsign", "UNKNOWN"),
                "icao24":      state.get("icao24"),
                "lat":         lat,
                "lon":         lon,
                "zones":       ", ".join(zones),
                "altitude_m":  state.get("altitude_m"),
                "velocity_ms": state.get("velocity_ms"),
            })

    logger.info(
        f"Analysed {len(states)} states — "
        f"{len(deviations)} over restricted zones"
    )
    return deviations

def estimate_reroute_cost(origin: str, destination: str,
                          actual_duration_mins: float) -> dict:
    
    baseline = PRE_CONFLICT_DURATIONS.get((origin, destination))

    if not baseline:
        logger.warning(f"No baseline found for {origin}→{destination}")
        return {}

    extra_mins = actual_duration_mins - baseline
    pct_increase = (extra_mins / baseline) * 100
    is_rerouted = pct_increase > (DEVIATION_THRESHOLD * 100)
    extra_fuel_usd = max(0, extra_mins) * FUEL_COST_PER_MINUTE_USD

    result = {
        "origin":             origin,
        "destination":        destination,
        "baseline_mins":      baseline,
        "actual_mins":        round(actual_duration_mins, 1),
        "extra_mins":         round(extra_mins, 1),
        "pct_increase":       round(pct_increase, 1),
        "is_rerouted":        is_rerouted,
        "est_extra_fuel_usd": round(extra_fuel_usd, 2),
    }

    if is_rerouted:
        logger.warning(
            f"{origin}→{destination} flagged as rerouted: "
            f"+{result['extra_mins']}min "
            f"(+{result['pct_increase']}%) "
            f"est. extra cost ${result['est_extra_fuel_usd']:,.0f}"
        )
    else:
        logger.info(
            f"{origin}→{destination}: within normal range "
            f"({result['pct_increase']:+.1f}%)"
        )

    return result

def batch_estimate(route_durations: list[dict]) -> list[dict]:
    
    results = []
    for item in route_durations:
        result = estimate_reroute_cost(
            origin=item["origin"],
            destination=item["destination"],
            actual_duration_mins=item["actual_duration_mins"]
        )
        if result:
            results.append(result)

    results.sort(key=lambda x: x.get("pct_increase", 0), reverse=True)
    return results