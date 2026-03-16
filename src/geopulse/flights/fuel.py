import requests
import logging
import pandas as pd
from geopulse.db.db import get_connection

logger = logging.getLogger(__name__)

BASE_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"

def fetch_fuel_prices(api_key: str, start: str = "2022-01-01") -> list[dict]:
   
    params = {
        "api_key":            api_key,
        "frequency":          "weekly",
        "data[0]":            "value",
        "facets[product][]":  "EPJK",
        "facets[duoarea][]":  "RGC",
        "start":              start,
        "sort[0][column]":    "period",
        "sort[0][direction]": "desc",
        "offset":             0,
        "length":             5000
    }

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=15
        )
        response.raise_for_status()
        data    = response.json()
        records = data.get("response", {}).get("data", [])
        logger.info(f"Fetched {len(records)} weekly fuel price records from EIA")
        return records
    except requests.RequestException as e:
        logger.error(f"EIA API error: {e}")
        return []

def normalise(record: dict) -> dict:
    return {
        "week_date":            record.get("period", ""),
        "price_usd_per_gallon": float(record.get("value", 0) or 0),
        "series_id":            record.get("series-description", "jet_fuel"),
    }

def save_fuel_prices(records: list[dict], db_path: str):
    conn   = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jet_fuel_prices (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            week_date            TEXT UNIQUE,
            price_usd_per_gallon REAL NOT NULL,
            series_id            TEXT,
            fetched_at           TEXT DEFAULT (datetime('now'))
        )
    """)

    saved = 0
    for record in records:
        row = normalise(record)
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO jet_fuel_prices
                (week_date, price_usd_per_gallon, series_id)
                VALUES (:week_date, :price_usd_per_gallon, :series_id)
            """, row)
            if cursor.rowcount:
                saved += 1
        except Exception as e:
            logger.error(f"Failed to save fuel record: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} new fuel price records")

def get_latest_fuel_price(db_path: str) -> float:
    """Return the most recent weekly jet fuel price in USD/gallon."""
    conn   = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price_usd_per_gallon
        FROM jet_fuel_prices
        ORDER BY week_date DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return float(row["price_usd_per_gallon"]) if row else 2.50

def get_fuel_price_history(db_path: str) -> pd.DataFrame:
    """Return full fuel price history as a DataFrame."""
    conn = get_connection(db_path)
    df   = pd.read_sql_query("""
        SELECT week_date, price_usd_per_gallon
        FROM jet_fuel_prices
        ORDER BY week_date ASC
    """, conn)
    conn.close()
    df["week_date"] = pd.to_datetime(df["week_date"])
    return df