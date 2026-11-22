from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
GAMES_PATH = DATA_DIR / "games.csv"
TEAM_STATE_PATH = DATA_DIR / "team_state.csv"
MODEL_PATH = DATA_DIR / "model_b.joblib"
EV_BOARD_PATH = DOCS_DIR / "ev_board.json"
PICKS_PATH = DOCS_DIR / "picks.json"
# Auto-log board recommendations at or above this EV (model_prob × decimal − 1)
MIN_EV_TO_TRACK = float(os.environ.get("NHL_EDGE_MIN_EV", "0") or "0")

load_dotenv(ROOT / ".env")

BALLDONTLIE_API_KEY = os.environ.get("BALLDONTLIE_API_KEY", "").strip()
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "").strip()

# Elo params — NHL home ice is smaller than NBA home court
BASE_ELO = 1500.0
HOME_ADVANTAGE = 45.0
K_FACTOR = 20.0
SEASON_CARRYOVER = 0.75

MODEL_B_FEATURES = [
    "home_elo_difference",
    "home_recent_form_advantage",
    "home_avg_margin_5",
    "away_avg_margin_5",
    "home_avg_margin_10",
    "away_avg_margin_10",
]

# Seasons to keep in the local DB (BallDontLie NHL season = start year)
# Start years (2024 → NHL season code 20242025).
# Keep this short like NBA Edge free-tier tweak — enough for Model B, fewer API calls.
HISTORICAL_SEASONS = [2024, 2025]

RUN_HOUR_START_ET = 8
RUN_HOUR_END_ET = 23  # inclusive (11pm Eastern)

BALLDONTLIE_GAMES_URL = "https://api.balldontlie.io/nhl/v1/games"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/icehockey_nhl/odds"
