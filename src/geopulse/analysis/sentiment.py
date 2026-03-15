import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

analyser = SentimentIntensityAnalyzer()

def score_text(text: str) -> dict:

    if not text or not text.strip():
        return {"sentiment_score": 0.0, "sentiment_label": "neutral"}

    scores = analyser.polarity_scores(text)
    compound = round(scores["compound"], 4)

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {
        "sentiment_score": compound,
        "sentiment_label": label
    }

def score_article(title: str, first_paragraph: str = "") -> dict:

    text = f"{title}. {first_paragraph or ''}"
    return score_text(text)