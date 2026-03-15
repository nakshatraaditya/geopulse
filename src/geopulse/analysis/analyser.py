import logging
import json
from geopulse.analysis.sentiment import score_article
from geopulse.analysis.tagger import tag_article
from geopulse.db.db import get_connection

logger = logging.getLogger(__name__)

def run_analysis(db_path: str):
    
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Add geo_tags and flight_relevant columns if they don't exist yet
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN geo_tags TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN flight_relevant INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()

    # Fetch unscored articles
    cursor.execute("""
        SELECT id, title, first_paragraph
        FROM articles
        WHERE sentiment_score IS NULL
    """)
    rows = cursor.fetchall()

    if not rows:
        logger.info("No unscored articles found")
        conn.close()
        return

    logger.info(f"Scoring {len(rows)} articles...")

    scored = 0
    tagged_geo = 0
    tagged_flight = 0

    for row in rows:
        article_id = row["id"]
        title = row["title"] or ""
        paragraph = row["first_paragraph"] or ""

        sentiment = score_article(title, paragraph)
        tags = tag_article(title, paragraph)

        try:
            cursor.execute("""
                UPDATE articles
                SET sentiment_score = ?,
                    sentiment_label = ?,
                    geo_tags = ?,
                    flight_relevant = ?
                WHERE id = ?
            """, (
                sentiment["sentiment_score"],
                sentiment["sentiment_label"],
                json.dumps(tags["geo_tags"]),
                int(tags["flight_relevant"]),
                article_id
            ))
            scored += 1
            if tags["geo_tags"]:
                tagged_geo += 1
            if tags["flight_relevant"]:
                tagged_flight += 1
        except Exception as e:
            logger.error(f"Failed to update article {article_id}: {e}")

    conn.commit()
    conn.close()

    logger.info(f"Scored {scored} articles")
    logger.info(f"Geo-tagged {tagged_geo} articles")
    logger.info(f"Flight-relevant {tagged_flight} articles")

def get_summary(db_path: str) -> dict:
    """Return a summary of sentiment across geo-tagged articles."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sentiment_label,
            COUNT(*) as count,
            ROUND(AVG(sentiment_score), 4) as avg_score
        FROM articles
        WHERE sentiment_score IS NOT NULL
        GROUP BY sentiment_label
        ORDER BY count DESC
    """)
    sentiment_breakdown = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM articles
        WHERE geo_tags != '[]'
        AND geo_tags IS NOT NULL
    """)
    geo_tagged_total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM articles
        WHERE flight_relevant = 1
    """)
    flight_relevant_total = cursor.fetchone()["total"]

    conn.close()

    return {
        "sentiment_breakdown": sentiment_breakdown,
        "geo_tagged_articles": geo_tagged_total,
        "flight_relevant_articles": flight_relevant_total
    }