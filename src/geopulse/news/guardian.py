import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://content.guardianapis.com/search"

GEOPOLITICAL_KEYWORDS = ["geopolitical", "international relations", "diplomacy", "global politics", "foreign policy", "world", 
                         "us-news", "middle-east", "asia", "africa", "europe", "war", "conflict", "friction","attack", "WW3"
                         ]

def fetch_articles(api_key: str, days_back: int = 90) -> list[dict]:
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    to_date = datetime.utcnow().strftime("%Y-%m-%d")

    all_articles = []
    
    for section in GEOPOLITICAL_KEYWORDS:
        page = 1
        while True:
            params = {
                "api-key": api_key,
                "section": section,
                "from-date": from_date,
                "to-date": to_date,
                "show-fields": "trailText,firstPublicationDate",
                "page-size": 50,
                "page": page,
                "order-by": "newest"
            }
            try:
                response = requests.get(BASE_URL, params=params, timeout=10)
                response.raise_for_status()
                body = response.json()["response"]
                results = body["results"]
                all_articles.extend(results)
                logger.info(f"Fetched page {page} [{section}] — {len(results)} articles")

                if page >= body["pages"]:
                    break
                page += 1

            except requests.RequestException as e:
                logger.error(f"Guardian error [{section}] page {page}: {e}")
                break

    logger.info(f"Totale articles fetched: {len(all_articles)}")
    return all_articles

def normalise(raw: dict) -> dict:
    fields = raw.get("fields", {})
    return {
        "source": "The Guardian",
        "title": raw.get("webTitle", ""),
        "published_at": fields.get("firstPublicationDate", ""),
        "section": raw.get("sectionName", ""),
        "first_paragraph": fields.get("trailText", ""),
        "url": raw.get("webUrl", "")
    }

def save_articles(articles: list[dict], db_path: str):
    from geopulse.db.db import get_connection
    conn = get_connection(db_path)
    cursor = conn.cursor()
    saved = 0

    for article in articles:
        row = normalise(article)
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO articles
                (source, title, published_at, section, first_paragraph, url)
                VALUES (:source, :title, :published_at, :section, :first_paragraph, :url)
            """, row)
            if cursor.rowcount:
                saved += 1
        except Exception as e:
            logger.error(f"Failed to save article: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} new articles to database")
