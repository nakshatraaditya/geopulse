CREATE_ARTICLES = """
CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    published_at    TEXT,
    section         TEXT,
    first_paragraph TEXT,
    url             TEXT UNIQUE,
    sentiment_score REAL,
    sentiment_label TEXT,
    ingested_at     TEXT DEFAULT (datetime('now'))
);
"""
CREATE_FLIGHTS = """
CREATE TABLE IF NOT EXISTS flight_prices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    origin         TEXT NOT NULL,
    destination    TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    price_usd      REAL NOT NULL,
    airline        TEXT,
    fetched_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(origin, destination, departure_date, airline)
);
"""
CREATE_ROUTES = """
CREATE TABLE IF NOT EXISTS watch_routes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    label TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
"""

CREATE_DEVIATIONS = """
CREATE TABLE IF NOT EXISTS route_deviations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    callsign TEXT,
    icao24 TEXT,
    lat REAL,
    lon REAL,
    zones TEXT,
    altitude_m REAL,
    velocity_ms REAL,
    detected_at TEXT DEFAULT (datetime('now'))
    );"""

