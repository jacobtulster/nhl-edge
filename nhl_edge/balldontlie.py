from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from nhl_edge.config import BALLDONTLIE_API_KEY, BALLDONTLIE_GAMES_URL

# Free-tier safe default
REQUEST_DELAY = float(os.environ.get("NHL_EDGE_REQUEST_DELAY", "1.5"))


def _headers() -> dict[str, str]:
    if not BALLDONTLIE_API_KEY:
        raise ValueError(
            "Missing BALLDONTLIE_API_KEY. Set it in .env or GitHub Actions secrets."
        )
    return {"Authorization": BALLDONTLIE_API_KEY}


def _get(params: list[tuple[str, Any]], max_retries: int = 12) -> dict:
    for attempt in range(max_retries):
        response = requests.get(
            BALLDONTLIE_GAMES_URL,
            headers=_headers(),
            params=params,
            timeout=30,
        )
        if response.status_code == 429:
            wait = min(int(response.headers.get("Retry-After", 20)), 30)
            print(f"Rate limited (attempt {attempt + 1}/{max_retries}); waiting {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        if REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)
        return response.json()
    raise RuntimeError("BallDontLie rate limit exceeded after retries.")


def fetch_games(seasons: list[int], label: str = "games") -> list[dict]:
    games: list[dict] = []
    cursor: int | None = None
    seen_cursors: set[int] = set()
    page = 0
    max_pages = 80

    while page < max_pages:
        page += 1
        params: list[tuple[str, Any]] = [("per_page", 100)]
        for season in seasons:
            params.append(("seasons[]", season))
        if cursor is not None:
            params.append(("cursor", cursor))

        payload = _get(params)
        batch = payload.get("data") or []
        games.extend(batch)

        meta = payload.get("meta") or {}
        next_cursor = meta.get("next_cursor")
        print(f"  {label} page {page}: +{len(batch)} (total {len(games)})")

        if not next_cursor or not batch:
            break
        if next_cursor in seen_cursors:
            print("  Stopping: repeated cursor.")
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return games


def fetch_season_games(season: int) -> list[dict]:
    return fetch_games([season], label=f"season {season}")


def fetch_games_for_dates(dates: list[str], season: int) -> list[dict]:
    params: list[tuple[str, Any]] = [
        ("seasons[]", season),
        ("per_page", 100),
    ]
    for d in dates:
        params.append(("dates[]", d))
    payload = _get(params)
    return payload.get("data") or []


def fetch_games_for_date(date_iso: str, season: int) -> list[dict]:
    return fetch_games_for_dates([date_iso], season)


def recent_date_strings(days: int = 14, today: date | None = None) -> list[str]:
    today = today or date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def _team_name(team: dict | None) -> str:
    if not team:
        return ""
    return (
        team.get("full_name")
        or team.get("display_name")
        or team.get("name")
        or ""
    )


def games_to_dataframe(raw_games: list[dict]) -> pd.DataFrame:
    """Normalize BallDontLie NHL game payloads into the shared Edge schema."""
    rows = []
    for g in raw_games:
        home = g.get("home_team") or {}
        away = g.get("away_team") or g.get("visitor_team") or {}
        status_state = (g.get("status_state") or "").lower()
        game_state = str(g.get("game_state") or g.get("status") or "")
        rows.append(
            {
                "game_id": g.get("id"),
                "game_date": str(g.get("game_date") or g.get("date") or "")[:10],
                "datetime_utc": g.get("start_time_utc") or g.get("datetime") or g.get("date"),
                "season": g.get("season"),
                "postseason": bool(g.get("postseason")),
                "status": game_state,
                "status_state": status_state or game_state.lower(),
                "home_team": _team_name(home),
                "away_team": _team_name(away),
                "home_abbreviation": (home.get("abbreviation") or "").upper(),
                "away_abbreviation": (away.get("abbreviation") or "").upper(),
                "home_points": g.get("home_score")
                if g.get("home_score") is not None
                else g.get("home_team_score"),
                "away_points": g.get("away_score")
                if g.get("away_score") is not None
                else g.get("visitor_team_score"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates("game_id")
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df["season"] = pd.to_numeric(df["season"], errors="coerce").astype("Int64")
    df["home_points"] = pd.to_numeric(df["home_points"], errors="coerce")
    df["away_points"] = pd.to_numeric(df["away_points"], errors="coerce")
    return df.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def is_final(row: pd.Series) -> bool:
    state = str(row.get("status_state") or "").lower()
    status = str(row.get("status") or "").lower()
    return state == "final" or status == "final" or "final" in status


def current_nhl_season(today: pd.Timestamp | None = None) -> int:
    """NHL season label = calendar year of the season start (Oct)."""
    today = today or pd.Timestamp.now(tz="America/New_York")
    if today.tzinfo is None:
        today = today.tz_localize("America/New_York")
    else:
        today = today.tz_convert("America/New_York")
    return today.year if today.month >= 10 else today.year - 1


# Back-compat alias used by copied scripts
current_nba_season = current_nhl_season
