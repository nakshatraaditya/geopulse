import json
import logging
from datetime import datetime
from geopulse.db.db import get_connection
from geopulse.analysis.price_predictor import predict_all_routes

logger = logging.getLogger(__name__)

def record_spot_check(db_path: str, route_prices: dict):
    conn   = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spot_checks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            check_date     TEXT NOT NULL,
            route          TEXT NOT NULL,
            model_price    REAL NOT NULL,
            real_price     REAL NOT NULL,
            difference_gbp REAL NOT NULL,
            difference_pct REAL NOT NULL,
            risk_level     TEXT,
            notes          TEXT,
            recorded_at    TEXT DEFAULT (datetime('now'))
        )
    """)

    predictions = predict_all_routes(db_path)
    pred_map    = {p["label"]: p for p in predictions}
    today       = datetime.utcnow().strftime("%Y-%m-%d")
    saved       = 0

    for route_label, real_price in route_prices.items():
        pred = pred_map.get(route_label)
        if not pred:
            logger.warning(f"No prediction found for {route_label}")
            continue

        model_price    = pred["estimated_price_gbp"]
        diff_gbp       = real_price - model_price
        diff_pct       = (diff_gbp / model_price) * 100

        cursor.execute("""
            INSERT INTO spot_checks
            (check_date, route, model_price, real_price,
             difference_gbp, difference_pct, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            today, route_label, model_price, real_price,
            round(diff_gbp, 2), round(diff_pct, 1),
            pred["risk_level"]
        ))
        saved += 1
        logger.info(
            f"{route_label}: model £{model_price:.0f} vs "
            f"real £{real_price:.0f} "
            f"(diff: {diff_pct:+.1f}%)"
        )

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} spot check records")

def get_spot_check_summary(db_path: str) -> dict:
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                AVG(ABS(difference_pct)) as avg_abs_error_pct,
                MIN(ABS(difference_pct)) as min_error_pct,
                MAX(ABS(difference_pct)) as max_error_pct,
                AVG(difference_gbp) as avg_diff_gbp,
                SUM(CASE WHEN ABS(difference_pct) <= 15 THEN 1 ELSE 0 END)
                    as within_15pct,
                SUM(CASE WHEN ABS(difference_pct) <= 25 THEN 1 ELSE 0 END)
                    as within_25pct
            FROM spot_checks
        """)
        row = cursor.fetchone()

        if not row or row["total"] == 0:
            conn.close()
            return {"status": "no_data",
                    "message": "No spot checks recorded yet"}

        total = row["total"]
        result = {
            "status":              "complete",
            "total_checks":        total,
            "avg_abs_error_pct":   round(float(row["avg_abs_error_pct"] or 0), 1),
            "min_error_pct":       round(float(row["min_error_pct"] or 0), 1),
            "max_error_pct":       round(float(row["max_error_pct"] or 0), 1),
            "avg_diff_gbp":        round(float(row["avg_diff_gbp"] or 0), 2),
            "within_15pct":        row["within_15pct"],
            "within_25pct":        row["within_25pct"],
            "pct_within_15":       round(row["within_15pct"] / total * 100, 1),
            "pct_within_25":       round(row["within_25pct"] / total * 100, 1),
        }

        cursor.execute("""
            SELECT check_date, route, model_price, real_price,
                   difference_pct, risk_level
            FROM spot_checks
            ORDER BY recorded_at DESC
            LIMIT 20
        """)
        result["recent_checks"] = [dict(r) for r in cursor.fetchall()]

        conn.close()
        return result

    except Exception as e:
        conn.close()
        return {"status": "error", "message": str(e)}