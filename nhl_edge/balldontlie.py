"""NHL game feed.

BallDontLie NHL is preferred when the key has access; otherwise we fall back to
the same public NHL web API used in the research Colab (`api-web.nhle.com`).
Odds still come from The Odds API (moneyline).
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from nhl_edge.config import BALLDONTLIE_API_KEY, BALLDONTLIE_GAMES_URL

# NHL public web API is much more permissive than BallDontLie free tier.
REQUEST_DELAY = float(os.environ.get("NHL_EDGE_REQUEST_DELAY", "0.2"))
NHL_WEB = "https://api-web.nhle.com/v1"
NHL_TEAMS = [
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL",
    "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH",
    "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
    "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
    "ARI",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 NHL-Edge"})


def _sleep() -> None:
    if REQUEST_DELAY > 0:
        time.sleep(REQUEST_DELAY)


def _headers() -> dict[str, str]:
    if not BALLDONTLIE_API_KEY:
        return {}
    return {"Authorization": BALLDONTLIE_API_KEY}


def _bdl_get(params: list[tuple[str, Any]], max_retries: int = 6) -> dict | None:
    if not BALLDONTLIE_API_KEY:
        return None
    for attempt in range(max_retries):
        response = SESSION.get(
            BALLDONTLIE_GAMES_URL,
            headers=_headers(),
            params=params,
            timeout=30,
        )
        if response.status_code in {401, 403}:
            print("BallDontLie NHL unauthorized — using NHL public API fallback.")
            return None
        if response.status_code == 429:
            wait = min(int(response.headers.get("Retry-After", 20)), 30)
            print(f"Rate limited (attempt {attempt + 1}/{max_retries}); waiting {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        _sleep()
        return response.json()
    raise RuntimeError("BallDontLie rate limit exceeded after retries.")


def season_code(start_year: int) -> str:
    return f"{int(start_year)}{int(start_year) + 1}"


def current_nhl_season(today: pd.Timestamp | None = None) -> int:
    today = today or pd.Timestamp.now(tz="America/New_York")
    if today.tzinfo is None:
        today = today.tz_localize("America/New_York")
    else:
        today = today.tz_convert("America/New_York")
    return today.year if today.month >= 10 else today.year - 1


current_nba_season = current_nhl_season


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
        or team.get("abbrev")
        or ""
    )


def _localized(obj: Any, key: str = "default") -> str:
    if isinstance(obj, dict):
        return str(obj.get(key) or obj.get("default") or "")
    return str(obj or "")


def _status_from_nhl(game_state: str) -> tuple[str, str]:
    state = str(game_state or "").upper()
    if state in {"OFF", "FINAL"}:
        return "Final", "final"
    if state in {"LIVE", "CRIT"}:
        return state, "in progress"
    if state in {"FUT", "PRE"}:
        return state, "scheduled"
    return state or "unknown", (state or "unknown").lower()


def games_to_dataframe(raw_games: list[dict]) -> pd.DataFrame:
    rows = []
    for g in raw_games:
        # BallDontLie-shaped
        if "home_team" in g and isinstance(g.get("home_team"), dict) and "abbreviation" in (g.get("home_team") or {}):
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
            continue

        # Already normalized / NHL web shaped
        if "home_abbreviation" in g:
            rows.append(g)
            continue

        home = g.get("homeTeam") or {}
        away = g.get("awayTeam") or {}
        status, status_state = _status_from_nhl(g.get("gameState") or g.get("game_state"))
        season_raw = g.get("season")
        season = None
        if season_raw is not None:
            s = str(season_raw)
            season = int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else season_raw
        game_type = g.get("gameType") or g.get("game_type")
        rows.append(
            {
                "game_id": g.get("id") or g.get("game_id"),
                "game_date": str(g.get("gameDate") or g.get("game_date") or "")[:10],
                "datetime_utc": g.get("startTimeUTC") or g.get("start_time_utc"),
                "season": season,
                "postseason": bool(game_type in {3, "3", 4, "4"}),
                "status": status,
                "status_state": status_state,
                "home_team": _localized(home.get("placeName")) + " " + _localized(home.get("commonName"))
                if home.get("placeName") or home.get("commonName")
                else (home.get("abbrev") or g.get("home_team")),
                "away_team": _localized(away.get("placeName")) + " " + _localized(away.get("commonName"))
                if away.get("placeName") or away.get("commonName")
                else (away.get("abbrev") or g.get("away_team")),
                "home_abbreviation": (home.get("abbrev") or g.get("home_team") or "").upper(),
                "away_abbreviation": (away.get("abbrev") or g.get("away_team") or "").upper(),
                "home_points": home.get("score") if home.get("score") is not None else g.get("home_score"),
                "away_points": away.get("score") if away.get("score") is not None else g.get("away_score"),
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
    df["home_abbreviation"] = df["home_abbreviation"].astype(str).str.upper()
    df["away_abbreviation"] = df["away_abbreviation"].astype(str).str.upper()
    return df.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def is_final(row: pd.Series) -> bool:
    state = str(row.get("status_state") or "").lower()
    status = str(row.get("status") or "").lower()
    return state == "final" or status == "final" or "final" in status or status == "off"


def fetch_games(seasons: list[int], label: str = "games") -> list[dict]:
    """Try BallDontLie first; return raw list or empty to signal fallback."""
    games: list[dict] = []
    cursor: int | None = None
    seen_cursors: set[int] = set()
    page = 0
    while page < 80:
        page += 1
        params: list[tuple[str, Any]] = [("per_page", 100)]
        for season in seasons:
            params.append(("seasons[]", season))
        if cursor is not None:
            params.append(("cursor", cursor))
        payload = _bdl_get(params)
        if payload is None:
            return []
        batch = payload.get("data") or []
        games.extend(batch)
        meta = payload.get("meta") or {}
        next_cursor = meta.get("next_cursor")
        print(f"  {label} page {page}: +{len(batch)} (total {len(games)})")
        if not next_cursor or not batch:
            break
        if next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return games


def _nhl_get(url: str) -> dict:
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    _sleep()
    return response.json()


def fetch_season_games_nhl_web(season_start: int) -> list[dict]:
    """
    Walk weekly NHL schedule pages (fast) instead of 32 club-season pulls.
    Same spirit as NBA Edge free-tier tweak: fewer calls, save-as-you-go upstream.
    """
    code = season_code(season_start)
    print(f"  NHL web API season {code} (weekly schedule)")
    by_id: dict[Any, dict] = {}
    # NHL season roughly mid-Oct → mid-Jun; step 7 days
    start = date(int(season_start), 10, 1)
    end = date(int(season_start) + 1, 6, 30)
    cursor = start
    weeks = 0
    while cursor <= end:
        weeks += 1
        url = f"{NHL_WEB}/schedule/{cursor.isoformat()}"
        try:
            payload = _nhl_get(url)
        except Exception as exc:
            print(f"  skip week {cursor}: {exc}")
            cursor = cursor + timedelta(days=7)
            continue
        # Payload shape: { gameWeek: [ { date, games: [...] }, ... ] } or games at top
        weeks_list = payload.get("gameWeek") or payload.get("gameWeeks") or []
        if weeks_list:
            for day in weeks_list:
                for game in day.get("games") or []:
                    gid = game.get("id")
                    if gid is not None:
                        by_id[gid] = game
        else:
            for game in payload.get("games") or []:
                gid = game.get("id")
                if gid is not None:
                    by_id[gid] = game
        if weeks % 6 == 0:
            print(f"    through {cursor}: {len(by_id)} unique games")
        cursor = cursor + timedelta(days=7)
    print(f"  season {code}: {len(by_id)} games across {weeks} weeks")
    return list(by_id.values())


def fetch_season_games(season: int) -> list[dict]:
    raw = fetch_games([season], label=f"season {season}")
    if raw:
        return raw
    return fetch_season_games_nhl_web(season)


def fetch_games_for_dates_nhl_web(dates: list[str]) -> list[dict]:
    by_id: dict[Any, dict] = {}
    for d in dates:
        url = f"{NHL_WEB}/score/{d}"
        try:
            payload = _nhl_get(url)
        except Exception as exc:
            print(f"  score {d}: {exc}")
            continue
        for game in payload.get("games") or []:
            gid = game.get("id")
            if gid is not None:
                by_id[gid] = game
    return list(by_id.values())


def fetch_games_for_dates(dates: list[str], season: int) -> list[dict]:
    params: list[tuple[str, Any]] = [
        ("seasons[]", season),
        ("per_page", 100),
    ]
    for d in dates:
        params.append(("dates[]", d))
    payload = _bdl_get(params)
    if payload is not None:
        return payload.get("data") or []
    return fetch_games_for_dates_nhl_web(dates)


def fetch_games_for_date(date_iso: str, season: int) -> list[dict]:
    return fetch_games_for_dates([date_iso], season)
