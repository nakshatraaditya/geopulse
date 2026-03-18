import pandas as pd
import numpy as np
import json
import logging
from scipy import stats
from geopulse.db.db import get_connection
from geopulse.flights.fuel import get_fuel_price_history

logger = logging.getLogger(__name__)

def test_directional_accuracy(db_path: str) -> dict:
    from geopulse.analysis.backtester import run_backtest
    df = run_backtest(db_path)

    if df.empty:
        return {"status": "insufficient_data"}

    total    = len(df)
    correct  = len(df[df["price_uplift_gbp"] > 0])
    accuracy = round((correct / total) * 100, 1)

    by_zone = df.groupby("zone")["price_uplift_gbp"].apply(
        lambda x: round((x > 0).sum() / len(x) * 100, 1)
    ).to_dict()

    by_route = df.groupby("route")["price_uplift_gbp"].apply(
        lambda x: round((x > 0).sum() / len(x) * 100, 1)
    ).to_dict()

    result = {
        "status":                   "complete",
        "total_predictions":        int(total),
        "correct_direction":        int(correct),
        "directional_accuracy_pct": float(accuracy),
        "by_zone":                  {k: float(v) for k, v in by_zone.items()},
        "by_route":                 {k: float(v) for k, v in by_route.items()},
        "interpretation": (
            "STRONG" if accuracy >= 80 else
            "MODERATE" if accuracy >= 60 else
            "WEAK"
        )
    }

    logger.info(
        f"Directional accuracy: {accuracy}% "
        f"({correct}/{total} correct)"
    )
    return result

def test_sentiment_fuel_correlation(db_path: str) -> dict:
    conn = get_connection(db_path)

    sentiment_df = pd.read_sql_query("""
        SELECT
            date(published_at) as date,
            AVG(sentiment_score) as avg_sentiment,
            SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END)
                as negative_count,
            COUNT(*) as article_count
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND geo_tags != '[]'
        AND geo_tags IS NOT NULL
        GROUP BY date(published_at)
        ORDER BY date ASC
    """, conn)
    conn.close()

    fuel_df = get_fuel_price_history(db_path)

    if sentiment_df.empty or fuel_df.empty:
        return {"status": "insufficient_data"}

    sentiment_df["date"]     = pd.to_datetime(sentiment_df["date"])
    fuel_df["week_date"]     = pd.to_datetime(fuel_df["week_date"])
    fuel_df["fuel_change_pct"] = fuel_df["price_usd_per_gallon"].pct_change() * 100

    merged = pd.merge_asof(
        sentiment_df.sort_values("date"),
        fuel_df[["week_date", "price_usd_per_gallon",
                 "fuel_change_pct"]].sort_values("week_date"),
        left_on="date",
        right_on="week_date",
        direction="backward"
    ).dropna()

    if len(merged) < 10:
        return {"status": "insufficient_data",
                "message": "Need more overlapping data points"}

    corr_level, p_level   = stats.pearsonr(
        merged["avg_sentiment"], merged["price_usd_per_gallon"]
    )
    corr_change, p_change = stats.pearsonr(
        merged["negative_count"], merged["fuel_change_pct"].fillna(0)
    )
    spearman_corr, spearman_p = stats.spearmanr(
        merged["avg_sentiment"], merged["price_usd_per_gallon"]
    )

    result = {
        "status":     "complete",
        "data_points": int(len(merged)),
        "date_range": f"{merged['date'].min().date()} to {merged['date'].max().date()}",
        "sentiment_vs_fuel_level": {
            "pearson_r":     round(float(corr_level), 4),
            "p_value":       round(float(p_level), 4),
            "significant":   bool(p_level < 0.05),
            "direction":     "negative" if corr_level < 0 else "positive",
            "interpretation": (
                "Strong" if abs(corr_level) >= 0.5 else
                "Moderate" if abs(corr_level) >= 0.3 else
                "Weak"
            )
        },
        "negative_news_vs_fuel_change": {
            "pearson_r":   round(float(corr_change), 4),
            "p_value":     round(float(p_change), 4),
            "significant": bool(p_change < 0.05),
        },
        "spearman_correlation": {
            "rho":         round(float(spearman_corr), 4),
            "p_value":     round(float(spearman_p), 4),
            "significant": bool(spearman_p < 0.05),
        },
        "avg_fuel_price": round(float(merged["price_usd_per_gallon"].mean()), 3),
        "avg_sentiment":  round(float(merged["avg_sentiment"].mean()), 4),
    }

    logger.info(
        f"Sentiment-fuel correlation: r={corr_level:.3f} "
        f"(p={p_level:.3f})"
    )
    return result

def run_full_validation(db_path: str) -> dict:
    logger.info("Running full validation suite...")

    directional = test_directional_accuracy(db_path)
    fuel_corr   = test_sentiment_fuel_correlation(db_path)

    report = {
        "validation_1_backtesting": {
            "description": "Auto-detected sentiment spikes vs price uplift",
            "status":      "see backtester module"
        },
        "validation_2_directional": directional,
        "validation_3_fuel_correlation": fuel_corr,
        "overall_verdict": _overall_verdict(directional, fuel_corr)
    }

    return report

def _overall_verdict(directional: dict, fuel_corr: dict) -> str:
    signals = 0
    if directional.get("directional_accuracy_pct", 0) >= 70:
        signals += 1
    if directional.get("interpretation") == "STRONG":
        signals += 1
    if fuel_corr.get("sentiment_vs_fuel_level", {}).get("significant"):
        signals += 1
    if fuel_corr.get("spearman_correlation", {}).get("significant"):
        signals += 1

    if signals >= 3:
        return "STRONG — model signals are statistically validated"
    elif signals >= 2:
        return "MODERATE — model shows meaningful signal"
    else:
        return "DEVELOPING — more data needed for strong validation"