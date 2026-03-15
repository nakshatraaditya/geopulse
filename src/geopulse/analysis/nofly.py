from shapely.geometry import Point, Polygon

NO_FLY_ZONES = {
    "russian_airspace": Polygon([
        (27.0, 68.0), (180.0, 68.0), (180.0, 41.0),
        (27.0, 41.0), (27.0, 68.0)
    ]),
    "ukrainian_airspace": Polygon([
        (22.0, 52.5), (40.0, 52.5), (40.0, 44.0),
        (22.0, 44.0), (22.0, 52.5)
    ]),
    "iranian_airspace": Polygon([
        (44.0, 39.5), (63.5, 39.5), (63.5, 25.0),
        (44.0, 25.0), (44.0, 39.5)
    ]),
    "iraqi_syrian_airspace": Polygon([
        (35.5, 37.5), (48.5, 37.5), (48.5, 29.0),
        (35.5, 29.0), (35.5, 37.5)
    ]),
    "red_sea_corridor": Polygon([
        (32.0, 30.0), (45.0, 30.0), (45.0, 12.0),
        (32.0, 12.0), (32.0, 30.0)
    ]),
}

def check_point(lat: float, lon: float) -> list[str]:
    """Check if a single coordinate falls inside any no-fly zone."""
    point = Point(lon, lat)
    return [
        zone for zone, polygon in NO_FLY_ZONES.items()
        if polygon.contains(point)
    ]

def check_path(coordinates: list[tuple]) -> dict:
    """Check if a flight path crosses any no-fly zones.
    
    Args:
        coordinates: list of (lat, lon) tuples representing the flight path
    
    Returns:
        dict with 'crosses_no_fly_zone' bool and 'zones' list
    """
    zones_crossed = set()
    for lat, lon in coordinates:
        crossed = check_point(lat, lon)
        zones_crossed.update(crossed)
    return {
        "crosses_no_fly_zone": len(zones_crossed) > 0,
        "zones": list(zones_crossed)
    }

def get_zone_description(zone_name: str) -> str:
    """Return a human readable description of a no-fly zone."""
    descriptions = {
        "russian_airspace":     "Russian airspace — closed to Western carriers since Feb 2022",
        "ukrainian_airspace":   "Ukrainian airspace — closed due to ongoing conflict",
        "iranian_airspace":     "Iranian airspace — periodically avoided due to escalation risk",
        "iraqi_syrian_airspace":"Iraqi/Syrian airspace — avoided due to regional instability",
        "red_sea_corridor":     "Red Sea corridor — avoided due to Houthi attack risk",
    }
    return descriptions.get(zone_name, zone_name)