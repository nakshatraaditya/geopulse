import requests
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

analyser = SentimentIntensityAnalyzer()

RSS_FEEDS = {
    "bbc": [
        {"url": "http://feeds.bbci.co.uk/news/world/rss.xml",             "region": "world"},
        {"url": "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "region": "middle-east"},
        {"url": "http://feeds.bbci.co.uk/news/world/europe/rss.xml",      "region": "europe"},
        {"url": "http://feeds.bbci.co.uk/news/world/asia/rss.xml",        "region": "asia"},
    ],
    "aljazeera": [
        {"url": "https://www.aljazeera.com/xml/rss/all.xml", "region": "world"},
    ],
    "france24": [
        {"url": "https://www.france24.com/en/rss",                        "region": "world"},
        {"url": "https://www.france24.com/en/middle-east/rss",            "region": "middle-east"},
        {"url": "https://www.france24.com/en/europe/rss",                 "region": "europe"},
    ],
    
}

GEOPOLITICAL_KEYWORDS = [
    "war", "conflict", "attack", "strike", "sanction", "missile",
    "airspace", "aviation", "flight ban", "no-fly", "reroute",
    "ukraine", "russia", "iran", "houthi", "red sea", "middle east",
    "nato", "nuclear", "bomb", "troops", "military", "ceasefire",
    "embargo", "blockade", "diplomat", "treaty", "escalat",
]

def is_geopolitical(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in GEOPOLITICAL_KEYWORDS)

def parse_rss_date(date_str: str) -> str:
    if not date_str:
        return datetime.utcnow().isoformat()
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return datetime.utcnow().isoformat()

def fetch_rss_feed(url: str, source: str, region: str,
                   days_back: int = 90) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; GeoPulse/1.0; "
            "+https://github.com/geopulse)"
        )
    }
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"RSS fetch error [{source} — {url}]: {e}")
        return []

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        logger.error(f"RSS parse error [{source}]: {e}")
        return []

    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    articles = []

    for item in root.iter("item"):
        title   = item.findtext("title", "").strip()
        link    = item.findtext("link", "").strip()
        summary = item.findtext("description", "").strip()
        pub_raw = item.findtext("pubDate", "") or item.findtext("published", "")
        pub_dt  = parse_rss_date(pub_raw)

        try:
            if datetime.fromisoformat(pub_dt.replace("Z","")).replace(
                tzinfo=None
            ) < cutoff:
                continue
        except Exception:
            pass

        if not is_geopolitical(title, summary):
            continue

        scores  = analyser.polarity_scores(f"{title}. {summary}")
        compound = round(scores["compound"], 4)
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        articles.append({
            "source":          source,
            "title":           title,
            "published_at":    pub_dt,
            "section":         region,
            "first_paragraph": summary[:500] if summary else "",
            "url":             link,
            "sentiment_score": compound,
            "sentiment_label": label,
        })

    logger.info(
        f"Fetched {len(articles)} geopolitical articles "
        f"from {source} [{region}]"
    )
    return articles

def fetch_all_rss(days_back: int = 90) -> list[dict]:
    all_articles = []
    for source, feeds in RSS_FEEDS.items():
        for feed in feeds:
            articles = fetch_rss_feed(
                url=feed["url"],
                source=source,
                region=feed["region"],
                days_back=days_back
            )
            all_articles.extend(articles)
    logger.info(f"Total RSS articles fetched: {len(all_articles)}")
    return all_articles

def save_rss_articles(articles: list[dict], db_path: str):
    from geopulse.db.db import get_connection
    conn   = get_connection(db_path)
    cursor = conn.cursor()
    saved  = 0

    for article in articles:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO articles
                (source, title, published_at, section,
                 first_paragraph, url, sentiment_score, sentiment_label)
                VALUES
                (:source, :title, :published_at, :section,
                 :first_paragraph, :url, :sentiment_score, :sentiment_label)
            """, article)
            if cursor.rowcount:
                saved += 1
        except Exception as e:
            logger.error(f"Failed to save RSS article: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} new RSS articles to database")
    return saved