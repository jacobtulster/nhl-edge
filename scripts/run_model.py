#!/usr/bin/env python3
"""Train/score Model B, join odds, write docs/ev_board.json."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from zoneinfo import ZoneInfo

from nhl_edge.balldontlie import (
    current_nba_season,
    fetch_games_for_date,
    games_to_dataframe,
    is_final,
)
from nhl_edge.config import (
    DOCS_DIR,
    EV_BOARD_PATH,
    GAMES_PATH,
    MODEL_B_FEATURES,
    TEAM_STATE_PATH,
)
from nhl_edge.picks import sync_board_picks
from nhl_edge.features import build_team_state, build_training_frame, features_for_matchup
from nhl_edge.model import predict_home_win_prob, train_model_b
from nhl_edge.odds import (
    american_or_decimal_to_implied,
    best_h2h_prices,
    expected_value,
    fetch_h2h_odds,
    team_key,
)


def _completed_games(games: pd.DataFrame) -> pd.DataFrame:
    mask = games.apply(is_final, axis=1)
    out = games[mask].copy()
    out = out.dropna(
        subset=[
            "home_abbreviation",
            "away_abbreviation",
            "home_points",
            "away_points",
            "season",
        ]
    )
    out = out[~out["postseason"].fillna(False).astype(bool)]
    return out.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def main() -> int:
    if not GAMES_PATH.exists():
        raise FileNotFoundError(
            f"{GAMES_PATH} missing. Run scripts/refresh_database.py first."
        )

    now_et = datetime.now(ZoneInfo("America/New_York"))
    today = now_et.date().isoformat()
    season = current_nba_season(pd.Timestamp(now_et))

    games = pd.read_csv(GAMES_PATH)
    games["game_date"] = pd.to_datetime(games["game_date"], errors="coerce")
    completed = _completed_games(games)
    print(f"Training on {len(completed)} completed regular-season games")

    frame = build_training_frame(completed)
    bundle = train_model_b(frame)
    print(
        f"Model B trained on {bundle['training_games']} games "
        f"(seasons {bundle['training_seasons']})"
    )

    state = build_team_state(completed)
    state.to_csv(TEAM_STATE_PATH, index=False)

    # Today's slate from BallDontLie
    raw_today = fetch_games_for_date(today, season)
    today_df = games_to_dataframe(raw_today)
    upcoming = []
    for _, g in today_df.iterrows():
        state_name = str(g.get("status_state") or "").lower()
        status = str(g.get("status") or "").lower()
        if g.get("postseason"):
            continue
        if state_name in {"final", "in progress", "halftime"}:
            continue
        if status == "final":
            continue
        upcoming.append(g)

    print(f"Scheduled/upcoming games for {today}: {len(upcoming)}")

    odds_events, odds_meta = fetch_h2h_odds()
    odds_rows = best_h2h_prices(odds_events)
    odds_lookup = {
        (r["home_abbreviation"], r["away_abbreviation"]): r for r in odds_rows
    }

    board_rows = []
    for g in upcoming:
        home = str(g["home_abbreviation"]).upper()
        away = str(g["away_abbreviation"]).upper()
        try:
            feats = features_for_matchup(home, away, state)
        except KeyError as exc:
            print(f"Skip {away} @ {home}: {exc}")
            continue

        feat_df = pd.DataFrame([feats])
        home_prob = predict_home_win_prob(bundle, feat_df)[0]
        away_prob = 1.0 - home_prob

        odds = odds_lookup.get((home, away))
        if odds is None:
            # Try reverse key match via team_key on full names
            for key, row in odds_lookup.items():
                if key[0] == team_key(home) and key[1] == team_key(away):
                    odds = row
                    break

        home_dec = odds["home_decimal"] if odds else None
        away_dec = odds["away_decimal"] if odds else None

        home_implied = (
            american_or_decimal_to_implied(home_dec) if home_dec else None
        )
        away_implied = (
            american_or_decimal_to_implied(away_dec) if away_dec else None
        )
        home_ev = (
            expected_value(home_prob, home_dec) if home_dec else None
        )
        away_ev = (
            expected_value(away_prob, away_dec) if away_dec else None
        )

        best_side = None
        best_ev = None
        if home_ev is not None and away_ev is not None:
            if home_ev >= away_ev:
                best_side, best_ev = "home", home_ev
            else:
                best_side, best_ev = "away", away_ev
        elif home_ev is not None:
            best_side, best_ev = "home", home_ev
        elif away_ev is not None:
            best_side, best_ev = "away", away_ev

        board_rows.append(
            {
                "game_id": int(g["game_id"]) if pd.notna(g["game_id"]) else None,
                "date": today,
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "home_abbreviation": home,
                "away_abbreviation": away,
                "home_win_probability": round(home_prob, 4),
                "away_win_probability": round(away_prob, 4),
                "home_decimal": home_dec,
                "away_decimal": away_dec,
                "home_implied_prob": round(home_implied, 4) if home_implied else None,
                "away_implied_prob": round(away_implied, 4) if away_implied else None,
                "home_ev": round(home_ev, 4) if home_ev is not None else None,
                "away_ev": round(away_ev, 4) if away_ev is not None else None,
                "best_side": best_side,
                "best_ev": round(best_ev, 4) if best_ev is not None else None,
                "home_book": odds.get("home_book") if odds else None,
                "away_book": odds.get("away_book") if odds else None,
                "features": {k: round(float(feats[k]), 4) for k in MODEL_B_FEATURES},
            }
        )

    # Sort by best EV descending (value first)
    board_rows.sort(
        key=lambda r: (r["best_ev"] is not None, r["best_ev"] or -999),
        reverse=True,
    )

    payload = {
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "date": today,
        "season": season,
        "model": "Model B (logistic moneyline)",
        "sport": "NHL",
        "market": "h2h",
        "training_games": bundle["training_games"],
        "odds_quota": odds_meta,
        "game_count": len(board_rows),
        "games": board_rows,
        "note": (
            "NHL moneylines only. Probabilities are model likelihoods, not guarantees. "
            "EV is model_prob × decimal_odds − 1 using best available US book price."
        ),
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    EV_BOARD_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(board_rows)} games → {EV_BOARD_PATH}")

    # Persist +EV recommendations and auto-grade finished games for ROI
    sync_board_picks(payload, games)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
