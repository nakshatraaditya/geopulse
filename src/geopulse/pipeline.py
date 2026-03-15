import os
import logging
from dotenv import load_dotenv
from geopulse.db.db import initialise_db, get_connection
from geopulse.news.guardian import fetch_articles, save_articles
from geopulse.flights.aviationstack import fetch_flights, save_flights
from geopulse.flights.opensky import fetch_all_regions, save_states
from geopulse.analysis.deviation import analyse_states
from geopulse.analysis.analyser import run_analysis, get_summary
from geopulse.analysis.reporter import generate_report

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/pipeline.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

WATCHED_ROUTES = [
    ("LHR", "DXB"),
    ("LHR", "TLV"),
    ("LHR", "DEL"),
    ("LHR", "BKK"),
    ("LHR", "HKG"),
    ("LHR", "NRT"),
]

def save_deviations(deviations: list[dict], db_path: str):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    saved = 0
    for d in deviations:
        try:
            cursor.execute("""
                INSERT INTO route_deviations
                (callsign, icao24, lat, lon, zones, altitude_m, velocity_ms)
                VALUES
                (:callsign, :icao24, :lat, :lon, :zones, :altitude_m, :velocity_ms)
            """, d)
            saved += 1
        except Exception as e:
            logger.error(f"Failed to save deviation: {e}")
    conn.commit()
    conn.close()
    logger.info(f"Saved {saved} deviation records")

def run():
    db_path = os.getenv("DB_PATH", "data/geopulse.db")
    initialise_db(db_path)

    
    logger.info("=" * 40)
    logger.info("STEP 1: Fetching Guardian news (90 days)")
    logger.info("=" * 40)
    articles = fetch_articles(
        api_key=os.getenv("GUARDIAN_API_KEY"),
        days_back=90
    )
    save_articles(articles, db_path)

    
    logger.info("=" * 40)
    logger.info("STEP 2: Fetching Aviationstack prices")
    logger.info("=" * 40)
    for origin, destination in WATCHED_ROUTES:
        flights = fetch_flights(
            api_key=os.getenv("AVIATIONSTACK_API_KEY"),
            origin=origin,
            destination=destination
        )
        save_flights(flights, origin, destination, db_path)

    
    logger.info("=" * 40)
    logger.info("STEP 3: Fetching OpenSky flight states")
    logger.info("=" * 40)
    states = fetch_all_regions(
        client_id=os.getenv("OPENSKY_CLIENT_ID"),
        client_secret=os.getenv("OPENSKY_CLIENT_SECRET")
    )
    save_states(states, db_path)

    
    logger.info("=" * 40)
    logger.info("STEP 4: Analysing route deviations")
    logger.info("=" * 40)
    deviations = analyse_states(states)
    if deviations:
        save_deviations(deviations, db_path)
        logger.warning(
            f"ALERT: {len(deviations)} flights detected "
            f"over restricted airspace"
        )
    else:
        logger.info("No restricted zone violations detected")

   
    logger.info("=" * 40)
    logger.info("STEP 5: Sentiment analysis + geo tagging")
    logger.info("=" * 40)
    run_analysis(db_path)
    summary = get_summary(db_path)
    logger.info(f"Sentiment breakdown: {summary['sentiment_breakdown']}")
    logger.info(f"Geo-tagged articles: {summary['geo_tagged_articles']}")
    logger.info(f"Flight-relevant articles: {summary['flight_relevant_articles']}")

    logger.info("=" * 40)
    logger.info("STEP 6: Correlation + prediction report")
    logger.info("=" * 40)
    report = generate_report(db_path)
    logger.info(f"Total deviations recorded: {report['data_summary']['total_deviations']}")
    logger.info(f"Key findings: {len(report['findings'])}")
    for finding in report["findings"]:
        logger.info(f"  >> {finding}")
    logger.info(f"Model status: {report['model'].get('status', 'n/a')}")
    
    logger.info("=" * 40)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 40)

    
    
if __name__ == "__main__":
    run()