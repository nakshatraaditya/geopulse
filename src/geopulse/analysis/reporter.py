import logging
from datetime import datetime
from geopulse.analysis.correlator import compute_correlations
from geopulse.analysis.predictor import train_and_evaluate
from geopulse.db.db import get_connection

logger = logging.getLogger(__name__)

ZONE_LABELS = {
    "russian_airspace":      "Russian airspace",
    "ukrainian_airspace":    "Ukrainian airspace",
    "iranian_airspace":      "Iranian airspace",
    "iraqi_syrian_airspace": "Iraqi/Syrian airspace",
    "red_sea_corridor":      "Red Sea corridor",
}

def generate_report(db_path: str) -> dict:
    logger.info("Generating Phase 3 report...")

    correlations = compute_correlations(db_path)
    model_results = train_and_evaluate(db_path)

    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM articles")
    total_articles = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM articles
        WHERE geo_tags != '[]' AND geo_tags IS NOT NULL
    """)
    geo_tagged = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM route_deviations")
    total_deviations = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT zones, COUNT(*) as count
        FROM route_deviations
        GROUP BY zones
        ORDER BY count DESC
        LIMIT 5
    """)
    top_zones = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT callsign, zones, detected_at
        FROM route_deviations
        ORDER BY detected_at DESC
        LIMIT 10
    """)
    recent_deviations = [dict(row) for row in cursor.fetchall()]

    conn.close()

    findings = []
    for zone, stats in correlations.items():
        corr = stats.get("correlation")
        label = ZONE_LABELS.get(zone, zone)
        if corr is not None:
            if abs(corr) >= 0.5:
                strength = "strong"
            elif abs(corr) >= 0.3:
                strength = "moderate"
            else:
                strength = "weak"
            direction = "positive" if corr > 0 else "negative"
            findings.append(
                f"{label}: {strength} {direction} correlation "
                f"({corr}) between negative news and flight deviations"
            )

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "data_summary": {
            "total_articles": total_articles,
            "geo_tagged_articles": geo_tagged,
            "total_deviations": total_deviations,
            "top_violation_zones": top_zones,
        },
        "correlations": correlations,
        "model": model_results,
        "findings": findings,
        "recent_deviations": recent_deviations,
    }

    logger.info(f"Report generated — {len(findings)} key findings")
    for f in findings:
        logger.info(f"  >> {f}")

    return report