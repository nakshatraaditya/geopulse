import pandas as pd
import json
import logging
from geopulse.db.db import get_connection
from geopulse.analysis.price_model import estimate_price, ROUTE_CONFIG
from geopulse.flights.fuel import get_fuel_price_history

logger = logging.getLogger(__name__)

ZONE_KEYWORDS = {
    "russian_airspace":      ["russia", "russian", "putin", "moscow", "kremlin"],
    "ukrainian_airspace":    ["ukraine", "ukrainian", "kyiv", "zelensky"],
    "iranian_airspace":      ["iran", "iranian", "tehran", "nuclear"],
    "iraqi_syrian_airspace": ["iraq", "syria", "iraqi", "syrian", "isis"],
    "red_sea_corridor":      ["red sea", "houthi", "yemen", "shipping"],
}

def detect_sentiment_spikes(db_path: str,
                             std_multiplier: float = 1.5) -> pd.DataFrame:
    
    conn = get_connection(db_path)

    articles = pd.read_sql_query("""
        SELECT
            date(published_at) as date,
            title,
            first_paragraph,
            sentiment_score,
            sentiment_label,
            geo_tags
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND geo_tags IS NOT NULL
        AND geo_tags != '[]'
    """, conn)
    conn.close()

    articles["date"]     = pd.to_datetime(articles["date"])
    articles["geo_tags"] = articles["geo_tags"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else []
    )

    events = []

    for zone, keywords in ZONE_KEYWORDS.items():
        zone_articles = articles[
            articles["geo_tags"].apply(lambda tags: zone in tags)
        ].copy()

        if zone_articles.empty:
            continue

        daily = zone_articles.groupby("date").agg(
            article_count  = ("sentiment_score", "count"),
            avg_sentiment  = ("sentiment_score", "mean"),
            negative_count = ("sentiment_label",
                              lambda x: (x == "negative").sum())
        ).reset_index()

        if len(daily) < 7:
            continue

        rolling_mean = daily["negative_count"].rolling(7, min_periods=3).mean()
        rolling_std  = daily["negative_count"].rolling(7, min_periods=3).std()
        threshold    = rolling_mean + (std_multiplier * rolling_std)

        spikes = daily[daily["negative_count"] > threshold].copy()

        for _, row in spikes.iterrows():
            top_articles = zone_articles[
                zone_articles["date"] == row["date"]
            ].nsmallest(3, "sentiment_score")[["title", "sentiment_score"]]

            events.append({
                "date":            row["date"],
                "zone":            zone,
                "negative_count":  int(row["negative_count"]),
                "avg_sentiment":   round(float(row["avg_sentiment"]), 4),
                "article_count":   int(row["article_count"]),
                "rolling_mean":    round(float(rolling_mean[row.name]), 2),
                "spike_magnitude": round(
                    float(row["negative_count"] /
                          max(rolling_mean[row.name], 1)), 2
                ),
                "top_headlines":   top_articles["title"].tolist(),
            })

    df = pd.DataFrame(events)
    if not df.empty:
        df = df.sort_values("date", ascending=False)
        logger.info(
            f"Detected {len(df)} sentiment spikes across "
            f"{df['zone'].nunique()} zones"
        )
    return df

def run_backtest(db_path: str) -> pd.DataFrame:
    
    spikes    = detect_sentiment_spikes(db_path)
    fuel_df   = get_fuel_price_history(db_path)
    conn      = get_connection(db_path)
    results   = []

    if spikes.empty:
        logger.warning("No sentiment spikes detected — need more data")
        conn.close()
        return pd.DataFrame()

    for _, event in spikes.iterrows():
        date_str = event["date"].strftime("%Y-%m-%d")

        # Get fuel price nearest to event date
        fuel_near  = fuel_df[fuel_df["week_date"] <= event["date"]]
        fuel_price = float(fuel_near["price_usd_per_gallon"].iloc[-1]) \
            if not fuel_near.empty else 2.50

        # Get deviation count around event date
        dev_df = pd.read_sql_query(f"""
            SELECT COUNT(*) as count FROM route_deviations
            WHERE date(detected_at) BETWEEN
            date('{date_str}', '-1 days') AND
            date('{date_str}', '+1 days')
        """, conn)
        deviation_count = int(dev_df["count"].iloc[0] or 0)

        for (origin, destination), config in ROUTE_CONFIG.items():
            if event["zone"] not in config["zones"]:
                continue

            # Price WITH zone active (event scenario)
            price_with_zone = estimate_price(
                origin=origin,
                destination=destination,
                db_path=db_path,
                avg_sentiment=event["avg_sentiment"],
                deviation_count=deviation_count,
                active_zones=[event["zone"]],
                days_to_departure=30,
                fuel_price_override=fuel_price
            )

            # Baseline price WITHOUT zone active
            price_baseline = estimate_price(
                origin=origin,
                destination=destination,
                db_path=db_path,
                avg_sentiment=0.0,
                deviation_count=0,
                active_zones=[],
                days_to_departure=30,
                fuel_price_override=fuel_price
            )

            if price_with_zone and price_baseline:
                uplift = (
                    price_with_zone["estimated_price_gbp"] -
                    price_baseline["estimated_price_gbp"]
                )
                results.append({
                    "date":              date_str,
                    "zone":              event["zone"],
                    "route":             config["label"],
                    "spike_magnitude":   event["spike_magnitude"],
                    "avg_sentiment":     event["avg_sentiment"],
                    "negative_articles": event["negative_count"],
                    "fuel_price":        fuel_price,
                    "baseline_price":    price_baseline["estimated_price_gbp"],
                    "event_price":       price_with_zone["estimated_price_gbp"],
                    "price_uplift_gbp":  round(uplift, 2),
                    "uplift_pct":        round(
                        (uplift / price_baseline["estimated_price_gbp"]) * 100, 1
                    ),
                    "risk_level":        price_with_zone["risk_level"],
                    "top_headlines":     " | ".join(
                        event["top_headlines"][:2]
                    ),
                })

    conn.close()
    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values(["date", "uplift_pct"], ascending=[False, False])
        logger.info(
            f"Backtest complete — {len(df)} route-event predictions"
        )
    return df

def summarise_backtest(db_path: str) -> dict:
    """Return a high-level summary of backtest findings."""
    df = run_backtest(db_path)
    if df.empty:
        return {"status": "insufficient_data"}

    return {
        "status":             "complete",
        "total_events":       df.groupby(["date", "zone"]).ngroups,
        "routes_affected":    df["route"].nunique(),
        "avg_uplift_pct":     round(df["uplift_pct"].mean(), 1),
        "max_uplift_pct":     round(df["uplift_pct"].max(), 1),
        "max_uplift_route":   df.loc[df["uplift_pct"].idxmax(), "route"],
        "max_uplift_zone":    df.loc[df["uplift_pct"].idxmax(), "zone"],
        "top_events":         df.head(5).to_dict(orient="records"),
    }