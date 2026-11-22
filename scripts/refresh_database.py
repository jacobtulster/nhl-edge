#!/usr/bin/env python3
"""Pull / update NHL games (NHL web API fallback + optional BallDontLie)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from nhl_edge.balldontlie import (
    current_nba_season,
    fetch_games_for_dates,
    fetch_season_games,
    games_to_dataframe,
    is_final,
    merge_prefer_finals,
    recent_date_strings,
)
from nhl_edge.config import DATA_DIR, GAMES_PATH, HISTORICAL_SEASONS


def _save(games: pd.DataFrame) -> None:
    games = games.copy()
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    # Prefer finals / scored rows when duplicate ids appear after a merge.
    prefer = games.apply(is_final, axis=1).astype(int) * 2 + (
        games["home_points"].notna() & games["away_points"].notna()
    ).astype(int)
    games = games.assign(_prefer=prefer)
    games = (
        games.sort_values(["game_id", "_prefer"])
        .drop_duplicates("game_id", keep="last")
        .drop(columns=["_prefer"])
        .sort_values(["game_date", "game_id"])
    )
    games.to_csv(GAMES_PATH, index=False)
    completed = games[games.apply(is_final, axis=1)]
    print(f"Saved {len(games)} games → {GAMES_PATH}")
    print(f"Completed finals: {len(completed)}")


def _seasons_present(games: pd.DataFrame) -> set[int]:
    if games.empty or "season" not in games.columns:
        return set()
    return {int(s) for s in games["season"].dropna().unique().tolist()}


def bootstrap_missing_seasons(existing: pd.DataFrame | None = None) -> pd.DataFrame:
    """Download any missing seasons one at a time, saving after each."""
    season_now = current_nba_season()
    wanted = sorted(set(HISTORICAL_SEASONS + [season_now]))
    games = existing.copy() if existing is not None else pd.DataFrame()
    have = _seasons_present(games)
    missing = [s for s in wanted if s not in have]

    if not missing:
        print("All historical seasons already present.")
        return games

    print(f"Need seasons: {missing}")
    for season in missing:
        print(f"Fetching season {season}…")
        raw = fetch_season_games(season)
        part = games_to_dataframe(raw)
        print(f"  parsed {len(part)} games")
        games = pd.concat([games, part], ignore_index=True) if not games.empty else part
        _save(games)
    return games


def incremental_recent(existing: pd.DataFrame, days: int = 14) -> pd.DataFrame:
    """Hourly path: only refresh the last N days (few API calls)."""
    season_now = current_nba_season()
    dates = recent_date_strings(days=days)
    print(f"Incremental refresh: last {days} days ({dates[-1]} → {dates[0]})")
    raw = fetch_games_for_dates(dates, season_now)
    recent = games_to_dataframe(raw)
    print(f"  fetched {len(recent)} games in window")
    if recent.empty:
        return existing
    return merge_prefer_finals(existing, recent)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force re-download of all configured seasons",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.full:
        if GAMES_PATH.exists():
            GAMES_PATH.unlink()
        bootstrap_missing_seasons()
        return 0

    if not GAMES_PATH.exists():
        print("No local DB yet — bootstrapping season by season.")
        bootstrap_missing_seasons()
        return 0

    existing = pd.read_csv(GAMES_PATH)
    existing["game_date"] = pd.to_datetime(existing["game_date"], errors="coerce")

    # Fill any missing historical seasons, then do a cheap recent-window update
    games = bootstrap_missing_seasons(existing)
    games = incremental_recent(games, days=14)
    _save(games)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
