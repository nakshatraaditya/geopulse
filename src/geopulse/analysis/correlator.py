import json
import logging
import pandas as pd
from geopulse.db.db import get_connection

logger = logging.getLogger(__name__)

ZONE_TO_ROUTES = {
    "russian_airspace":      [("LHR", "HKG"), ("LHR", "NRT"), ("LHR", "DEL")],
    "ukrainian_airspace":    [("LHR", "HKG"), ("LHR", "NRT"), ("LHR", "DEL")],
    "iranian_airspace":      [("LHR", "DXB"), ("LHR", "AUH"), ("LHR", "DEL")],
    "iraqi_syrian_airspace": [("LHR", "DXB"), ("LHR", "TLV"), ("LHR", "AUH")],
    "red_sea_corridor":      [("LHR", "DXB"), ("LHR", "AUH"), ("LHR", "BKK")],
}

def load_articles(db_path: str) -> pd.DataFrame:
    conn = get_connection(db_path)
    df = pd.read_sql_query("""
        SELECT
            id,
            title,
            published_at,
            section,
            sentiment_score,
            sentiment_label,
            geo_tags,
            flight_relevant
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND geo_tags IS NOT NULL
        AND geo_tags != '[]'
    """, conn)
    conn.close()

    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    df["date"] = df["published_at"].dt.date
    df["geo_tags"] = df["geo_tags"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else []
    )
    return df

def load_deviations(db_path: str) -> pd.DataFrame:
    conn = get_connection(db_path)
    df = pd.read_sql_query("""
        SELECT
            callsign,
            zones,
            detected_at
        FROM route_deviations
    """, conn)
    conn.close()

    df["detected_at"] = pd.to_datetime(df["detected_at"], errors="coerce", utc=True)
    df["date"] = df["detected_at"].dt.date
    return df

def build_correlation_table(db_path: str) -> pd.DataFrame:
    
    articles = load_articles(db_path)
    deviations = load_deviations(db_path)

    rows = []

    for zone in ZONE_TO_ROUTES.keys():
        zone_articles = articles[
            articles["geo_tags"].apply(lambda tags: zone in tags)
        ].copy()

        zone_deviations = deviations[
            deviations["zones"].str.contains(zone, na=False)
        ].copy()

        daily_sentiment = zone_articles.groupby("date").agg(
            article_count=("id", "count"),
            avg_sentiment=("sentiment_score", "mean"),
            negative_count=("sentiment_label",
                            lambda x: (x == "negative").sum())
        ).reset_index()

        daily_deviations = zone_deviations.groupby("date").agg(
            deviation_count=("callsign", "count")
        ).reset_index()

        merged = pd.merge(
            daily_sentiment,
            daily_deviations,
            on="date",
            how="outer"
        ).fillna(0)

        merged["zone"] = zone
        rows.append(merged)

    if not rows:
        logger.warning("No correlation data found")
        return pd.DataFrame()

    result = pd.concat(rows, ignore_index=True)
    logger.info(f"Built correlation table with {len(result)} zone-day rows")
    return result

def compute_correlations(db_path: str) -> dict:
    
    table = build_correlation_table(db_path)

    if table.empty:
        return {}

    results = {}
    for zone in table["zone"].unique():
        zone_data = table[table["zone"] == zone]

        if len(zone_data) < 2:
            continue

        corr = zone_data["negative_count"].corr(
            zone_data["deviation_count"]
        )
        results[zone] = {
            "correlation": round(float(corr), 4) if pd.notna(corr) else None,
            "days_observed": len(zone_data),
            "total_negative_articles": int(zone_data["negative_count"].sum()),
            "total_deviations": int(zone_data["deviation_count"].sum()),
            "avg_daily_sentiment": round(
                float(zone_data["avg_sentiment"].mean()), 4
            )
        }
        logger.info(
            f"{zone}: correlation={results[zone]['correlation']} "
            f"({results[zone]['days_observed']} days)"
        )

    return results