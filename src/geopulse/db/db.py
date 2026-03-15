import sqlite3
import os
import logging
from geopulse.db.schema import CREATE_ARTICLES, CREATE_FLIGHTS, CREATE_ROUTES, CREATE_DEVIATIONS

logger = logging.getLogger(__name__)

def get_connection(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def initialise_db(db_path: str):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(CREATE_ARTICLES)
        cursor.execute(CREATE_FLIGHTS)
        cursor.execute(CREATE_ROUTES)
        cursor.execute(CREATE_DEVIATIONS)
        conn.commit()
        logger.info(f"Database initialised at {db_path}")
    except Exception as e:
        logger.error(f"Error initialising database: {e}")
    finally:
        conn.close()