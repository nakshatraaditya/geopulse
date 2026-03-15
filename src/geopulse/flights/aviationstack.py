import requests
import logging

logger = logging.getLogger(__name__)

BASE_URL = "http://api.aviationstack.com/v1/flights"

def fetch_flights(api_key: str, origin: str, destination: str) -> list[dict]:
    params = {
        "access_key": api_key,
        "dep_iata": origin,
        "arr_iata": destination,
        "limit": 10
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
        logger.info(f"Fetched {len(data)} flights [{origin}→{destination}]")
        return data
    except requests.RequestException as e:
        logger.error(f"Aviationstack error [{origin}→{destination}]: {e}")
        return []

def normalise(flight: dict, origin: str, destination: str) -> dict:
    departure = flight.get("departure", {})
    arrival = flight.get("arrival", {})
    airline = flight.get("airline", {})
    price = flight.get("price", {})

    return {
        "origin": origin,
        "destination": destination,
        "departure_date": (departure.get("scheduled") or "")[:10],
        "price_usd": float(price.get("total", 0.0)),
        "airline": airline.get("name", ""),
    }

def save_flights(flights: list[dict], origin: str, destination: str, db_path: str):
    from geopulse.db.db import get_connection
    conn = get_connection(db_path)
    cursor = conn.cursor()
    saved = 0

    for flight in flights:
        row = normalise(flight, origin, destination)
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO flight_prices
                (origin, destination, departure_date, price_usd, airline)
                VALUES (:origin, :destination, :departure_date, :price_usd, :airline)
            """, row)
            if cursor.rowcount:
                saved += 1
        except Exception as e:
            logger.error(f"Failed to save flight: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} new flights [{origin}→{destination}]")