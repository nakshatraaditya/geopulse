import requests
import streamlit as st
import os
from datetime import datetime, timedelta

GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY", "")
BASE_URL = "https://content.guardianapis.com/search"

GEOPOLITICAL_TOPICS = [
    "geopolitics", "aviation", "airspace", "sanctions",
    "conflict", "war", "ukraine", "iran", "middle east",
    "red sea", "houthi", "russia"
]

@st.cache_data(ttl=600)
def fetch_live_news(query: str = "geopolitics aviation",
                    days_back: int = 7,
                    page_size: int = 20) -> list[dict]:
    if not GUARDIAN_API_KEY:
        return []

    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "api-key":      GUARDIAN_API_KEY,
        "q":            query,
        "from-date":    from_date,
        "show-fields":  "trailText,thumbnail,byline",
        "page-size":    page_size,
        "order-by":     "newest",
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        results = response.json()["response"]["results"]
        return results
    except Exception:
        return []

def render_news_card(article: dict, badge_color: str = "#378ADD"):
    fields    = article.get("fields", {})
    title     = article.get("webTitle", "")
    section   = article.get("sectionName", "")
    date      = article.get("webPublicationDate", "")[:10]
    url       = article.get("webUrl", "")
    summary   = fields.get("trailText", "")
    thumbnail = fields.get("thumbnail", "")

    with st.container(border=True):
        col1, col2 = st.columns([4, 1]) if thumbnail else [st.columns([1])[0], None]
        with col1:
            st.markdown(f"**[{title}]({url})**")
            if summary:
                st.caption(summary[:200] + "..." if len(summary) > 200 else summary)
            st.caption(f"{section} · {date}")
        if col2 and thumbnail:
            with col2:
                st.image(thumbnail, width=100)