import requests
import logging
import time

logger = logging.getLogger(__name__)

BASE_URL = "https://opensky-network.org/api"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

WATCHED_BOUNDING_BOXES = {
    "UK_to_Middle_East": {
        "routes": [("LHR", "DXB"), ("LHR", "TLV"), ("LHR", "AUH")],
        "lamin": 24.0, "lomin": -10.0, "lamax": 52.0, "lomax": 60.0
    },
    "UK_to_Asia": {
        "routes": [("LHR", "DEL"), ("LHR", "BKK"), ("LHR", "BOM")],
        "lamin": 10.0, "lomin": -10.0, "lamax": 52.0, "lomax": 105.0
    },
    "UK_to_Far_East": {
        "routes": [("LHR", "HKG"), ("LHR", "NRT"), ("LHR", "PEK")],
        "lamin": 10.0, "lomin": -10.0, "lamax": 60.0, "lomax": 145.0
    },
}

def get_token(client_id: str, client_secret: str) -> str:
    response = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }, timeout=10)
    response.raise_for_status()
    token = response.json()["access_token"]
    logger.info("OpenSky token obtained successfully")
    return token

def get_states(lamin: float, lomin: float,
               lamax: float, lomax: float,
               token: str = None) -> list:
    url = f"{BASE_URL}/states/all"
    params = {
        "lamin": lamin,
        "lomin": lomin,
        "lamax": lamax,
        "lomax": lomax
    }
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        states = data.get("states", []) or []
        logger.info(f"Fetched {len(states)} aircraft states")
        return states
    except requests.RequestException as e:
        logger.error(f"OpenSky error: {e}")
        return []

def parse_state(state: list) -> dict:
    return {
        "icao24":         state[0],
        "callsign":       (state[1] or "").strip(),
        "origin_country": state[2],
        "timestamp":      state[3],
        "lat":            state[6],
        "lon":            state[5],
        "altitude_m":     state[7],
        "velocity_ms":    state[9],
        "heading":        state[10],
        "on_ground":      state[8],
    }

def fetch_all_regions(client_id: str = None,
                      client_secret: str = None) -> list[dict]:
    token = None
    if client_id and client_secret:
        try:
            token = get_token(client_id, client_secret)
        except Exception as e:
            logger.error(f"Failed to get OpenSky token: {e}")

    all_states = []
    for region_name, config in WATCHED_BOUNDING_BOXES.items():
        logger.info(f"Fetching states for region: {region_name}")
        raw_states = get_states(
            lamin=config["lamin"],
            lomin=config["lomin"],
            lamax=config["lamax"],
            lomax=config["lomax"],
            token=token
        )
        parsed = [parse_state(s) for s in raw_states if s[6] and s[5]]
        all_states.extend(parsed)
        time.sleep(1)
    return all_states

def save_states(states: list[dict], db_path: str):
    from geopulse.db.db import get_connection
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flight_states (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            icao24         TEXT,
            callsign       TEXT,
            origin_country TEXT,
            lat            REAL,
            lon            REAL,
            altitude_m     REAL,
            velocity_ms    REAL,
            heading        REAL,
            on_ground      INTEGER,
            recorded_at    TEXT DEFAULT (datetime('now'))
        )
    """)

    saved = 0
    for state in states:
        try:
            cursor.execute("""
                INSERT INTO flight_states
                (icao24, callsign, origin_country, lat, lon,
                 altitude_m, velocity_ms, heading, on_ground)
                VALUES
                (:icao24, :callsign, :origin_country, :lat, :lon,
                 :altitude_m, :velocity_ms, :heading, :on_ground)
            """, state)
            saved += 1
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} flight states")
