import sqlite3
import pandas as pd
import streamlit as st
import os

DB_PATH = os.getenv("DB_PATH", "data/geopulse.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data(ttl=300)
def load_articles(source: str = "all"):
    conn = get_connection()
    if source == "all":
        df = pd.read_sql_query("""
            SELECT title, section, source, sentiment_score, sentiment_label,
                   geo_tags, published_at, url, first_paragraph
            FROM articles
            WHERE sentiment_score IS NOT NULL
            AND published_at >= datetime('now', '-7 days')
            ORDER BY published_at DESC
            LIMIT 500
        """, conn)
    else:
        df = pd.read_sql_query("""
            SELECT title, section, source, sentiment_score, sentiment_label,
                   geo_tags, published_at, url, first_paragraph
            FROM articles
            WHERE sentiment_score IS NOT NULL
            AND source = ?
            AND published_at >= datetime('now', '-7 days')
            ORDER BY published_at DESC
            LIMIT 500
        """, conn, params=(source,))
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_source_breakdown():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT source,
               COUNT(*) as total_articles,
               SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END) as negative,
               ROUND(AVG(sentiment_score), 3) as avg_sentiment
        FROM articles
        WHERE sentiment_score IS NOT NULL
        GROUP BY source
        ORDER BY total_articles DESC
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_deviations():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT callsign, zones, lat, lon, altitude_m, velocity_ms, detected_at
        FROM route_deviations
        ORDER BY detected_at DESC
        LIMIT 1000
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_flight_prices():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT origin, destination, price_usd, airline, fetched_at
        FROM flight_prices
        ORDER BY fetched_at DESC
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_sentiment_trend():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT date(published_at) as date,
               AVG(sentiment_score) as avg_sentiment,
               COUNT(*) as article_count,
               SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END) as negative_count
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND published_at >= datetime('now', '-90 days')
        GROUP BY date(published_at)
        ORDER BY date ASC
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=300)
def load_deviation_trend():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT date(detected_at) as date, zones, COUNT(*) as count
        FROM route_deviations
        GROUP BY date(detected_at), zones
        ORDER BY date ASC
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=300)
def load_fuel_history():
    conn = get_connection()
    try:
        df = pd.read_sql_query("""
            SELECT week_date, price_usd_per_gallon
            FROM jet_fuel_prices
            ORDER BY week_date ASC
        """, conn)
        df["week_date"] = pd.to_datetime(df["week_date"])
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_summary_metrics():
    conn = get_connection()
    cursor = conn.cursor()
    metrics = {}

    cursor.execute("SELECT COUNT(*) as c FROM articles")
    metrics["total_articles"] = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) as c FROM flight_states")
    metrics["total_flight_states"] = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) as c FROM route_deviations")
    metrics["total_deviations"] = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) as c FROM flight_prices")
    metrics["total_prices"] = cursor.fetchone()["c"]

    cursor.execute("""
        SELECT AVG(sentiment_score) as avg
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND published_at >= datetime('now', '-7 days')
    """)
    row = cursor.fetchone()
    metrics["avg_sentiment_7d"] = round(float(row["avg"] or 0), 3)

    try:
        cursor.execute("""
            SELECT price_usd_per_gallon FROM jet_fuel_prices
            ORDER BY week_date DESC LIMIT 1
        """)
        row = cursor.fetchone()
        metrics["latest_fuel_price"] = round(float(row["price_usd_per_gallon"]), 3) if row else 3.10
    except Exception:
        metrics["latest_fuel_price"] = 3.10

    cursor.execute("""
        SELECT zones, COUNT(*) as c FROM route_deviations
        WHERE detected_at >= datetime('now', '-24 hours')
        GROUP BY zones ORDER BY c DESC LIMIT 1
    """)
    row = cursor.fetchone()
    metrics["top_zone_24h"] = row["zones"] if row else "N/A"

    conn.close()
    return metrics