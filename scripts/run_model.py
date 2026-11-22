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
from nhl_edge.ats import cover_probability
from nhl_edge.picks import sync_board_picks
from nhl_edge.features import build_team_state, build_training_frame, features_for_matchup
from nhl_edge.model import predict_home_win_prob, train_model_b
from nhl_edge.odds import (
    american_or_decimal_to_implied,
    best_h2h_prices,
    collect_spread_quotes,
    expected_value,
    fetch_odds,
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

    odds_events, odds_meta = fetch_odds("h2h,spreads")
    odds_rows = best_h2h_prices(odds_events)
    odds_lookup = {
        (r["home_abbreviation"], r["away_abbreviation"]): r for r in odds_rows
    }
    spread_quotes = collect_spread_quotes(odds_events)

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
            for key, row in odds_lookup.items():
                if key[0] == team_key(home) and key[1] == team_key(away):
                    odds = row
                    break

        home_dec = odds["home_decimal"] if odds else None
        away_dec = odds["away_decimal"] if odds else None
        home_ml_ev = expected_value(home_prob, home_dec) if home_dec else None
        away_ml_ev = expected_value(away_prob, away_dec) if away_dec else None

        best_ml_side = None
        best_ml_ev = None
        if home_ml_ev is not None and away_ml_ev is not None:
            if home_ml_ev >= away_ml_ev:
                best_ml_side, best_ml_ev = "home", home_ml_ev
            else:
                best_ml_side, best_ml_ev = "away", away_ml_ev
        elif home_ml_ev is not None:
            best_ml_side, best_ml_ev = "home", home_ml_ev
        elif away_ml_ev is not None:
            best_ml_side, best_ml_ev = "away", away_ml_ev

        # ATS / puck line — pick the quote with highest model EV per side
        best_home_ats = None
        best_away_ats = None
        for q in spread_quotes.get((home, away), []):
            try:
                point = float(q["point"])
                dec = float(q["decimal"])
            except (TypeError, ValueError, KeyError):
                continue
            cprob = cover_probability(home_prob, side=q["side"], point=point)
            ev = expected_value(cprob, dec)
            packed = {
                "point": point,
                "decimal": dec,
                "book": q.get("book"),
                "cover_prob": cprob,
                "ev": ev,
            }
            if q["side"] == "home":
                if best_home_ats is None or ev > best_home_ats["ev"]:
                    best_home_ats = packed
            elif q["side"] == "away":
                if best_away_ats is None or ev > best_away_ats["ev"]:
                    best_away_ats = packed

        best_ats_side = None
        best_ats_ev = None
        if best_home_ats and best_away_ats:
            if best_home_ats["ev"] >= best_away_ats["ev"]:
                best_ats_side, best_ats_ev = "home", best_home_ats["ev"]
            else:
                best_ats_side, best_ats_ev = "away", best_away_ats["ev"]
        elif best_home_ats:
            best_ats_side, best_ats_ev = "home", best_home_ats["ev"]
        elif best_away_ats:
            best_ats_side, best_ats_ev = "away", best_away_ats["ev"]

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
                # Primary: ATS / puck line
                "primary_market": "spread",
                "home_spread": best_home_ats["point"] if best_home_ats else None,
                "away_spread": best_away_ats["point"] if best_away_ats else None,
                "home_spread_decimal": best_home_ats["decimal"] if best_home_ats else None,
                "away_spread_decimal": best_away_ats["decimal"] if best_away_ats else None,
                "home_spread_book": best_home_ats["book"] if best_home_ats else None,
                "away_spread_book": best_away_ats["book"] if best_away_ats else None,
                "home_cover_prob": round(best_home_ats["cover_prob"], 4) if best_home_ats else None,
                "away_cover_prob": round(best_away_ats["cover_prob"], 4) if best_away_ats else None,
                "home_ats_ev": round(best_home_ats["ev"], 4) if best_home_ats else None,
                "away_ats_ev": round(best_away_ats["ev"], 4) if best_away_ats else None,
                "best_ats_side": best_ats_side,
                "best_ats_ev": round(best_ats_ev, 4) if best_ats_ev is not None else None,
                "best_side": best_ats_side,
                "best_ev": round(best_ats_ev, 4) if best_ats_ev is not None else None,
                # Bonus: moneyline
                "home_decimal": home_dec,
                "away_decimal": away_dec,
                "home_implied_prob": (
                    round(american_or_decimal_to_implied(home_dec), 4) if home_dec else None
                ),
                "away_implied_prob": (
                    round(american_or_decimal_to_implied(away_dec), 4) if away_dec else None
                ),
                "home_ev": round(home_ml_ev, 4) if home_ml_ev is not None else None,
                "away_ev": round(away_ml_ev, 4) if away_ml_ev is not None else None,
                "best_ml_side": best_ml_side,
                "best_ml_ev": round(best_ml_ev, 4) if best_ml_ev is not None else None,
                "home_book": odds.get("home_book") if odds else None,
                "away_book": odds.get("away_book") if odds else None,
                "features": {k: round(float(feats[k]), 4) for k in MODEL_B_FEATURES},
            }
        )

    # Sort by best ATS EV descending (primary book)
    board_rows.sort(
        key=lambda r: (r["best_ats_ev"] is not None, r["best_ats_ev"] or -999),
        reverse=True,
    )

    payload = {
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "date": today,
        "season": season,
        "model": "Model B (win prob → puck-line cover)",
        "sport": "NHL",
        "market": "spreads",
        "bonus_market": "h2h",
        "primary_market": "spread",
        "training_games": bundle["training_games"],
        "odds_quota": odds_meta,
        "game_count": len(board_rows),
        "games": board_rows,
        "note": (
            "Primary book is ATS / puck line. Cover probs come from the win model’s "
            "implied margin; EV = cover_prob × decimal − 1 at the best US book quote. "
            "Moneyline EV is tracked as a separate bonus ledger."
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
