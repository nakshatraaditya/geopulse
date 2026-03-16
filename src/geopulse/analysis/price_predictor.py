import logging
import json
import numpy as np
import pandas as pd
from geopulse.db.db import get_connection
from geopulse.analysis.price_model import estimate_all_routes, ROUTE_CONFIG
from geopulse.flights.fuel import get_latest_fuel_price, get_fuel_price_history

logger = logging.getLogger(__name__)

def build_training_data(db_path: str) -> pd.DataFrame:
    
    conn = get_connection(db_path)

    articles = pd.read_sql_query("""
        SELECT
            date(published_at) as date,
            sentiment_score,
            sentiment_label,
            geo_tags
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND geo_tags IS NOT NULL
        AND geo_tags != '[]'
    """, conn)

    deviations = pd.read_sql_query("""
        SELECT
            date(detected_at) as date,
            zones,
            COUNT(*) as count
        FROM route_deviations
        GROUP BY date(detected_at), zones
    """, conn)

    fuel = pd.read_sql_query("""
        SELECT week_date, price_usd_per_gallon
        FROM jet_fuel_prices
        ORDER BY week_date ASC
    """, conn)

    conn.close()

    if articles.empty or deviations.empty:
        logger.warning("Insufficient data to build training set")
        return pd.DataFrame()

    articles["geo_tags"] = articles["geo_tags"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else []
    )
    articles["date"] = pd.to_datetime(articles["date"])

    daily_sentiment = articles.groupby("date").agg(
        avg_sentiment=("sentiment_score", "mean"),
        negative_count=("sentiment_label", lambda x: (x == "negative").sum()),
        article_count=("sentiment_score", "count")
    ).reset_index()

    deviations["date"] = pd.to_datetime(deviations["date"])
    daily_deviations = deviations.groupby("date").agg(
        total_deviations=("count", "sum")
    ).reset_index()

    merged = pd.merge(daily_sentiment, daily_deviations, on="date", how="left")
    merged["total_deviations"] = merged["total_deviations"].fillna(0)

    if not fuel.empty:
        fuel["week_date"] = pd.to_datetime(fuel["week_date"])
        merged = pd.merge_asof(
            merged.sort_values("date"),
            fuel.sort_values("week_date"),
            left_on="date",
            right_on="week_date",
            direction="backward"
        )
        merged["price_usd_per_gallon"] = merged[
            "price_usd_per_gallon"
        ].fillna(2.50)
    else:
        merged["price_usd_per_gallon"] = 2.50

    rows = []
    for _, row in merged.iterrows():
        for (origin, destination), config in ROUTE_CONFIG.items():
            estimate = estimate_price_fast(
                base_fare=config["base_fare_gbp"],
                distance_km=config["distance_km"],
                fuel_price=row.get("price_usd_per_gallon", 2.50),
                avg_sentiment=row["avg_sentiment"],
                deviation_count=int(row["total_deviations"]),
                active_zones=[],
                days_to_departure=30
            )
            rows.append({
                "date":               row["date"],
                "origin":             origin,
                "destination":        destination,
                "avg_sentiment":      row["avg_sentiment"],
                "negative_count":     row["negative_count"],
                "article_count":      row["article_count"],
                "total_deviations":   row["total_deviations"],
                "fuel_price":         row.get("price_usd_per_gallon", 2.50),
                "estimated_price":    estimate,
                "distance_km":        config["distance_km"],
            })

    df = pd.DataFrame(rows)
    logger.info(f"Built training set: {len(df)} rows across {len(ROUTE_CONFIG)} routes")
    return df

def estimate_price_fast(
    base_fare: float,
    distance_km: float,
    fuel_price: float,
    avg_sentiment: float,
    deviation_count: int,
    active_zones: list,
    days_to_departure: int
) -> float:
    """Lightweight price estimate for batch training data generation."""
    from geopulse.analysis.price_model import (
        sentiment_to_multiplier,
        deviation_to_multiplier,
        days_to_multiplier,
        FUEL_BURN_PER_KM,
        GALLONS_TO_GBP
    )
    fuel_cost = distance_km * FUEL_BURN_PER_KM * fuel_price * GALLONS_TO_GBP
    sent_mult = sentiment_to_multiplier(avg_sentiment)
    dev_mult  = deviation_to_multiplier(deviation_count)
    day_mult  = days_to_multiplier(days_to_departure)
    return (base_fare + fuel_cost) * sent_mult * dev_mult * day_mult

def train_price_model(db_path: str) -> dict:
    
    try:
        from xgboost import XGBRegressor
        from sklearn.model_selection import cross_val_score
        from sklearn.metrics import mean_absolute_error
    except ImportError as e:
        return {"status": "missing_dependency", "error": str(e)}

    df = build_training_data(db_path)

    if df.empty or len(df) < 10:
        return {
            "status": "insufficient_data",
            "message": "Run the pipeline daily for a week to build enough data"
        }

    feature_cols = [
        "avg_sentiment",
        "negative_count",
        "total_deviations",
        "fuel_price",
        "distance_km",
    ]

    X = df[feature_cols].fillna(0).values
    y = df["estimated_price"].values

    model = XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        verbosity=0
    )

    cv_scores = cross_val_score(
        model, X, y,
        cv=min(5, len(df) // 2),
        scoring="neg_mean_absolute_error"
    )

    model.fit(X, y)
    preds = model.predict(X)
    mae = mean_absolute_error(y, preds)

    importances = dict(zip(feature_cols, model.feature_importances_))

    result = {
        "status":              "trained",
        "rows_used":           len(df),
        "mae_gbp":             round(float(mae), 2),
        "cv_mae_gbp":          round(float(-cv_scores.mean()), 2),
        "feature_importances": {
            k: round(float(v), 4) for k, v in importances.items()
        },
        "model":               model
    }

    logger.info(
        f"Price model trained — MAE: £{result['mae_gbp']} "
        f"CV MAE: £{result['cv_mae_gbp']}"
    )
    logger.info(f"Feature importances: {result['feature_importances']}")
    return result

def predict_all_routes(db_path: str) -> list[dict]:
    
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT AVG(sentiment_score) as avg_sentiment
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND date(published_at) >= date('now', '-7 days')
    """)
    row = cursor.fetchone()
    avg_sentiment = float(row["avg_sentiment"] or 0)

    cursor.execute("""
    SELECT COUNT(*) as total
    FROM route_deviations
    WHERE detected_at >= datetime('now', '-1 hours')
    """)
    row = cursor.fetchone()
    recent_deviations = int(row["total"] or 0)

    cursor.execute("""
        SELECT DISTINCT zones FROM route_deviations
        WHERE date(detected_at) >= date('now', '-1 days')
    """)
    active_zones = list({
        z.strip()
        for row in cursor.fetchall()
        for z in row["zones"].split(",")
        if z.strip()
    })

    conn.close()

    fuel_price = get_latest_fuel_price(db_path)

    logger.info(
        f"Predicting prices — sentiment: {avg_sentiment:.3f}, "
        f"deviations: {recent_deviations}, "
        f"active zones: {active_zones}, "
        f"fuel: ${fuel_price:.2f}/gal"
    )

    estimates = estimate_all_routes(
        db_path=db_path,
        avg_sentiment=avg_sentiment,
        deviation_count=recent_deviations,
        active_zones=active_zones,
        days_to_departure=30
    )

    model_result = train_price_model(db_path)
    model_status = model_result.get("status", "not_trained")

    for estimate in estimates:
        estimate["model_status"]  = model_status
        estimate["fuel_price"]    = fuel_price
        estimate["active_zones"]  = active_zones
        estimate["avg_sentiment"] = avg_sentiment

    return estimates