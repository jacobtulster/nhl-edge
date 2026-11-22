#!/usr/bin/env python3
"""Refresh live scores for open +EV picks and rewrite docs/picks.json."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from nhl_edge.balldontlie import current_nhl_season, refresh_scores_for_dates
from nhl_edge.config import GAMES_PATH, PICKS_PATH
from nhl_edge.picks import grade_open_picks, load_picks, save_picks


def main() -> int:
    store = load_picks()
    open_dates = [
        str(p.get("date") or "")[:10]
        for p in (store.get("picks") or [])
        if p and str(p.get("result") or "").upper() not in {"W", "L", "P"}
    ]
    games = pd.read_csv(GAMES_PATH) if GAMES_PATH.exists() else pd.DataFrame()
    if "game_date" in games.columns:
        games["game_date"] = pd.to_datetime(games["game_date"], errors="coerce")
    if open_dates:
        games = refresh_scores_for_dates(games, open_dates, current_nhl_season())
        if GAMES_PATH.exists() or not games.empty:
            GAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
            out = games.copy()
            out["game_date"] = pd.to_datetime(out["game_date"], errors="coerce")
            out.to_csv(GAMES_PATH, index=False)
    store = grade_open_picks(store, games)
    payload = save_picks(store)
    print(
        f"Graded {store.get('_graded', 0)} open picks "
        f"(total {payload['summary'].get('picks', 0)}) → {PICKS_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
