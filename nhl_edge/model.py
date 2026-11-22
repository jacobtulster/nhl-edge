from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nhl_edge.config import MODEL_B_FEATURES, MODEL_PATH


def train_model_b(frame: pd.DataFrame, path: Path = MODEL_PATH) -> dict:
    usable = frame.dropna(subset=MODEL_B_FEATURES + ["target"]).copy()
    if len(usable) < 200:
        raise ValueError(f"Not enough completed games to train ({len(usable)}).")

    pipeline = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=0.1, max_iter=2000),
    )
    pipeline.fit(usable[MODEL_B_FEATURES], usable["target"])

    bundle = {
        "model": pipeline,
        "features": MODEL_B_FEATURES,
        "training_games": int(len(usable)),
        "training_seasons": sorted(
            int(s) for s in usable["season"].dropna().unique().tolist()
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    return bundle


def load_model(path: Path = MODEL_PATH) -> dict:
    return joblib.load(path)


def predict_home_win_prob(bundle: dict, feature_rows: pd.DataFrame) -> list[float]:
    model = bundle["model"]
    cols = bundle["features"]
    probs = model.predict_proba(feature_rows[cols])[:, 1]
    return [float(p) for p in probs]
