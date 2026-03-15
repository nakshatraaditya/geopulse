import logging

logger = logging.getLogger(__name__)

REGION_KEYWORDS = {
    "russian_airspace": [
        "russia", "russian", "moscow", "kremlin", "putin",
        "ukraine war", "nato russia", "sanctions russia",
        "siberia", "siberian"
    ],
    "ukrainian_airspace": [
        "ukraine", "ukrainian", "kyiv", "zelensky",
        "donbas", "kharkiv", "odesa", "mariupol",
        "ukraine war", "ukraine conflict", "ukraine invasion"
    ],
    "iranian_airspace": [
        "iran", "iranian", "tehran", "khamenei",
        "nuclear deal", "irgc", "strait of hormuz",
        "iran sanctions", "iran nuclear"
    ],
    "iraqi_syrian_airspace": [
        "iraq", "iraqi", "baghdad", "syria", "syrian",
        "damascus", "isis", "isil", "islamic state",
        "kurdish", "kurdistan"
    ],
    "red_sea_corridor": [
        "red sea", "houthi", "houthis", "yemen",
        "gulf of aden", "suez", "strait of bab",
        "shipping attack", "tanker attack"
    ],
}

FLIGHT_IMPACT_KEYWORDS = [
    "airspace", "flight ban", "no fly", "aviation",
    "airline", "reroute", "divert", "diverted",
    "flight path", "air travel", "air traffic",
    "fuel cost", "jet fuel", "flight price",
    "cargo flight", "passenger flight"
]

def tag_article(title: str, first_paragraph: str = "") -> dict:
    
    text = f"{title} {first_paragraph or ''}".lower()

    geo_tags = []
    for zone, keywords in REGION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            geo_tags.append(zone)

    flight_relevant = any(kw in text for kw in FLIGHT_IMPACT_KEYWORDS)

    return {
        "geo_tags": geo_tags,
        "flight_relevant": flight_relevant
    }