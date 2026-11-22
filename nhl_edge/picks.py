"""Track +EV board recommendations, auto-grade finals, publish ROI ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_edge.balldontlie import is_final
from nhl_edge.config import MIN_EV_TO_TRACK, PICKS_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_store() -> dict[str, Any]:
    return {"updatedAt": None, "picks": [], "summary": {}}


def load_picks(path: Path | None = None) -> dict[str, Any]:
    path = path or PICKS_PATH
    if not path.exists():
        return empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_store()
    if not isinstance(data, dict):
        return empty_store()
    if not isinstance(data.get("picks"), list):
        data["picks"] = []
    return data


def pick_key(game_id: Any, side: str) -> str:
    return f"{game_id}|{str(side).lower()}"


def matchup_id(date: str, away: str, home: str, side: str) -> str:
    return "|".join(
        [
            str(date or ""),
            str(away or "").upper(),
            "at",
            str(home or "").upper(),
            str(side or "").lower(),
            "ml",
        ]
    )


def decimal_to_american(decimal: float | None) -> float | None:
    if decimal is None:
        return None
    try:
        d = float(decimal)
    except (TypeError, ValueError):
        return None
    if d <= 1:
        return None
    if d >= 2:
        return round((d - 1) * 100)
    return round(-100 / (d - 1))


def profit_units(result: str, decimal: float | None) -> float:
    r = str(result or "").upper()
    if r == "P":
        return 0.0
    if r == "L":
        return -1.0
    try:
        d = float(decimal) if decimal is not None else 2.0
    except (TypeError, ValueError):
        d = 2.0
    if d <= 1:
        d = 2.0
    return round(d - 1.0, 4)


def grade_moneyline(side: str, away_score: float, home_score: float) -> str | None:
    try:
        a = float(away_score)
        h = float(home_score)
    except (TypeError, ValueError):
        return None
    if a == h:
        return "P"
    pick_is_away = str(side).lower() == "away"
    won = (a > h) if pick_is_away else (h > a)
    return "W" if won else "L"


def summarize(picks: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(picks)
    graded = [p for p in picks if str(p.get("result") or "").upper() in {"W", "L", "P"}]
    w = sum(1 for p in graded if str(p.get("result")).upper() == "W")
    l = sum(1 for p in graded if str(p.get("result")).upper() == "L")
    psh = sum(1 for p in graded if str(p.get("result")).upper() == "P")
    profit = 0.0
    for p in graded:
        try:
            profit += float(p.get("profit") or 0)
        except (TypeError, ValueError):
            pass
    decided = w + l
    return {
        "picks": n,
        "graded": len(graded),
        "w": w,
        "l": l,
        "p": psh,
        "win_pct": round(w / decided, 4) if decided else None,
        "profit_u": round(profit, 4),
        "roi": round(profit / len(graded), 4) if graded else None,
    }


def equity_curve(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    graded = [
        p
        for p in picks
        if str(p.get("result") or "").upper() in {"W", "L", "P"}
    ]
    graded.sort(
        key=lambda p: (
            str(p.get("gradedAt") or p.get("loggedAt") or ""),
            str(p.get("pickKey") or ""),
        )
    )
    cum = 0.0
    out = []
    for i, p in enumerate(graded, start=1):
        try:
            profit = float(p.get("profit") or 0)
        except (TypeError, ValueError):
            profit = -1.0 if str(p.get("result")).upper() == "L" else 0.0
        cum = round(cum + profit, 4)
        out.append(
            {
                "n": i,
                "when": p.get("gradedAt") or p.get("loggedAt"),
                "matchup": f"{p.get('away_abbreviation') or p.get('away')} @ {p.get('home_abbreviation') or p.get('home')}",
                "side": p.get("takeSide") or p.get("side"),
                "team": p.get("takeTeam") or p.get("team"),
                "result": p.get("result"),
                "profit": profit,
                "cum": cum,
                "pos": cum if cum > 0 else 0,
                "neg": cum if cum < 0 else 0,
            }
        )
    return out


def upsert_from_board(
    board: dict[str, Any],
    *,
    min_ev: float | None = None,
    store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log +EV top-side recommendations once per game/side."""
    min_ev = MIN_EV_TO_TRACK if min_ev is None else float(min_ev)
    store = store or load_picks()
    by_key = {
        str(p.get("pickKey")): p
        for p in store.get("picks") or []
        if p and p.get("pickKey")
    }
    inserted = 0

    for game in board.get("games") or []:
        best_ev = game.get("best_ev")
        best_side = game.get("best_side")
        if best_side not in {"home", "away"}:
            continue
        try:
            ev = float(best_ev)
        except (TypeError, ValueError):
            continue
        if ev < min_ev:
            continue

        game_id = game.get("game_id")
        if game_id is None:
            continue
        key = pick_key(game_id, best_side)
        if key in by_key:
            continue

        is_home = best_side == "home"
        decimal = game.get("home_decimal") if is_home else game.get("away_decimal")
        book = game.get("home_book") if is_home else game.get("away_book")
        team = (
            game.get("home_abbreviation") if is_home else game.get("away_abbreviation")
        )
        model_p = (
            game.get("home_win_probability")
            if is_home
            else game.get("away_win_probability")
        )

        pick = {
            "pickKey": key,
            "matchupId": matchup_id(
                str(game.get("date") or ""),
                str(game.get("away_abbreviation") or ""),
                str(game.get("home_abbreviation") or ""),
                best_side,
            ),
            "loggedAt": _now_iso(),
            "sport": "NHL",
            "league": "NHL",
            "date": game.get("date"),
            "game_id": game_id,
            "away": game.get("away_team"),
            "home": game.get("home_team"),
            "away_abbreviation": game.get("away_abbreviation"),
            "home_abbreviation": game.get("home_abbreviation"),
            "takeSide": best_side,
            "takeTeam": team,
            "side": best_side,
            "team": team,
            "market": "ml",
            "decimal": decimal,
            "price": decimal_to_american(decimal),
            "line": decimal_to_american(decimal),
            "lineSource": "odds-api",
            "lineBook": book,
            "model_prob": model_p,
            "ev": ev,
            "bucket": "pos_ev" if ev > 0 else "best_side",
            "result": None,
            "profit": None,
            "gradedAt": None,
            "gradeSource": None,
            "awayScore": None,
            "homeScore": None,
        }
        by_key[key] = pick
        inserted += 1

    store["picks"] = list(by_key.values())
    store["_inserted"] = inserted
    return store


def _build_game_lookup(games: pd.DataFrame) -> dict[Any, pd.Series]:
    lookup: dict[Any, pd.Series] = {}
    if games is None or games.empty:
        return lookup
    for _, row in games.iterrows():
        gid = row.get("game_id")
        if pd.isna(gid):
            continue
        try:
            lookup[int(gid)] = row
        except (TypeError, ValueError):
            lookup[gid] = row
        away = str(row.get("away_abbreviation") or "").upper()
        home = str(row.get("home_abbreviation") or "").upper()
        date = str(row.get("game_date") or "")[:10]
        if away and home and date:
            lookup[f"{date}|{away}|{home}"] = row
    return lookup


def _lookup_pick_row(pick: dict[str, Any], lookup: dict[Any, pd.Series]) -> pd.Series | None:
    gid = pick.get("game_id")
    try:
        gid_i = int(gid)
    except (TypeError, ValueError):
        gid_i = gid
    row = lookup.get(gid_i)
    if row is None:
        row = lookup.get(gid)
    if row is None:
        date = str(pick.get("date") or "")[:10]
        away = str(pick.get("away_abbreviation") or pick.get("away") or "").upper()
        home = str(pick.get("home_abbreviation") or pick.get("home") or "").upper()
        row = lookup.get(f"{date}|{away}|{home}")
    return row


def grade_open_picks(
    store: dict[str, Any],
    games: pd.DataFrame,
) -> dict[str, Any]:
    """Fill W/L/P + profit when a game is marked final."""
    lookup = _build_game_lookup(games)
    graded = 0
    for pick in store.get("picks") or []:
        if not pick:
            continue
        if str(pick.get("result") or "").upper() in {"W", "L", "P"}:
            continue
        row = _lookup_pick_row(pick, lookup)
        if row is None or not is_final(row):
            continue
        away_pts = row.get("away_points")
        home_pts = row.get("home_points")
        if pd.isna(away_pts) or pd.isna(home_pts):
            continue
        result = grade_moneyline(pick.get("takeSide") or pick.get("side"), away_pts, home_pts)
        if not result:
            continue
        pick["result"] = result
        pick["profit"] = profit_units(result, pick.get("decimal"))
        pick["awayScore"] = float(away_pts)
        pick["homeScore"] = float(home_pts)
        pick["gradedAt"] = _now_iso()
        pick["gradeSource"] = str(row.get("grade_source") or "balldontlie")
        graded += 1

    store["_graded"] = graded
    return store


def save_picks(store: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    path = path or PICKS_PATH
    picks = store.get("picks") or []
    # Stable order: newest logged first for humans; equity built chronologically in UI/helpers
    picks_sorted = sorted(
        picks,
        key=lambda p: str(p.get("loggedAt") or ""),
        reverse=True,
    )
    summary = summarize(picks_sorted)
    payload = {
        "updatedAt": _now_iso(),
        "minEv": MIN_EV_TO_TRACK,
        "summary": summary,
        "equity": equity_curve(picks_sorted),
        "picks": picks_sorted,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def sync_board_picks(board: dict[str, Any], games: pd.DataFrame) -> dict[str, Any]:
    from nhl_edge.balldontlie import current_nhl_season, refresh_scores_for_dates

    store = load_picks()
    store = upsert_from_board(board, store=store)

    open_dates = [
        str(p.get("date") or "")[:10]
        for p in (store.get("picks") or [])
        if p and str(p.get("result") or "").upper() not in {"W", "L", "P"}
    ]
    games_for_grade = games
    if open_dates:
        try:
            games_for_grade = refresh_scores_for_dates(
                games.copy() if games is not None else pd.DataFrame(),
                open_dates,
                current_nhl_season(),
            )
        except Exception as exc:  # noqa: BLE001 — grading must not kill the board publish
            print(f"Open-pick score refresh failed: {exc}")

    store = grade_open_picks(store, games_for_grade)
    payload = save_picks(store)
    print(
        f"Picks ledger: +{store.get('_inserted', 0)} new, "
        f"graded {store.get('_graded', 0)}, "
        f"total {payload['summary'].get('picks', 0)} → {PICKS_PATH}"
    )
    return payload
