import logging
import json
import numpy as np
import pandas as pd
from geopulse.analysis.correlator import build_correlation_table

logger = logging.getLogger(__name__)

def build_features(db_path: str) -> pd.DataFrame:
    
    table = build_correlation_table(db_path)

    if table.empty:
        logger.warning("No data to build features from")
        return pd.DataFrame()

    table["rerouting_detected"] = (table["deviation_count"] > 0).astype(int)
    return table

def train_and_evaluate(db_path: str) -> dict:
    
    try:
        from xgboost import XGBClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import LabelEncoder
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return {}

    df = build_features(db_path)

    if df.empty or len(df) < 5:
        logger.warning(
            "Not enough data to train model — "
            "run pipeline daily for a week to build up history"
        )
        return {"status": "insufficient_data", "rows": len(df)}

    feature_cols = ["avg_sentiment", "negative_count", "article_count"]
    X = df[feature_cols].fillna(0).values
    y = df["rerouting_detected"].values

    if len(np.unique(y)) < 2:
        logger.warning("Only one class in target — need more varied data")
        return {"status": "single_class", "rows": len(df)}

    model = XGBClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        use_label_encoder=False,
        eval_metric="logloss",
        verbosity=0
    )

    scores = cross_val_score(model, X, y, cv=min(3, len(df)), scoring="accuracy")
    model.fit(X, y)

    importances = dict(zip(feature_cols, model.feature_importances_))

    result = {
        "status": "trained",
        "rows_used": len(df),
        "cv_accuracy": round(float(scores.mean()), 4),
        "cv_std": round(float(scores.std()), 4),
        "feature_importances": {
            k: round(float(v), 4) for k, v in importances.items()
        }
    }

    logger.info(f"Model trained — accuracy: {result['cv_accuracy']} "
                f"(+/- {result['cv_std']})")
    logger.info(f"Feature importances: {result['feature_importances']}")

    return result

def predict_rerouting_risk(
    avg_sentiment: float,
    negative_count: int,
    article_count: int,
    db_path: str
) -> dict:
    
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return {"error": "xgboost not installed"}

    df = build_features(db_path)

    if df.empty or len(df) < 5:
        return {"status": "insufficient_data"}

    feature_cols = ["avg_sentiment", "negative_count", "article_count"]
    X = df[feature_cols].fillna(0).values
    y = df["rerouting_detected"].values

    if len(np.unique(y)) < 2:
        return {"status": "single_class"}

    model = XGBClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        use_label_encoder=False,
        eval_metric="logloss",
        verbosity=0
    )
    model.fit(X, y)

    features = np.array([[avg_sentiment, negative_count, article_count]])
    prob = float(model.predict_proba(features)[0][1])

    if prob >= 0.7:
        risk = "HIGH"
    elif prob >= 0.4:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "rerouting_probability": round(prob, 4),
        "risk_level": risk,
        "features_used": {
            "avg_sentiment": avg_sentiment,
            "negative_count": negative_count,
            "article_count": article_count
        }
    }