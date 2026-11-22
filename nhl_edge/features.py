from __future__ import annotations

import numpy as np
import pandas as pd

from nhl_edge.elo import build_pregame_elo


def _team_game_log(completed: pd.DataFrame) -> pd.DataFrame:
    home = completed[
        [
            "game_id",
            "game_date",
            "season",
            "home_abbreviation",
            "away_abbreviation",
            "home_points",
            "away_points",
        ]
    ].copy()
    home.columns = [
        "game_id",
        "game_date",
        "season",
        "team",
        "opponent",
        "points_for",
        "points_against",
    ]
    home["is_home"] = 1

    away = completed[
        [
            "game_id",
            "game_date",
            "season",
            "away_abbreviation",
            "home_abbreviation",
            "away_points",
            "home_points",
        ]
    ].copy()
    away.columns = [
        "game_id",
        "game_date",
        "season",
        "team",
        "opponent",
        "points_for",
        "points_against",
    ]
    away["is_home"] = 0

    log = pd.concat([home, away], ignore_index=True)
    log["team"] = log["team"].str.upper()
    log["opponent"] = log["opponent"].str.upper()
    log["margin"] = log["points_for"] - log["points_against"]
    log = log.sort_values(["team", "game_date", "game_id"]).reset_index(drop=True)

    # Past-only rolling windows (shift so current game is excluded)
    log["avg_margin_5"] = log.groupby("team")["margin"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )
    log["avg_margin_10"] = log.groupby("team")["margin"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=1).mean()
    )
    return log


def build_training_frame(completed: pd.DataFrame) -> pd.DataFrame:
    """One row per completed game with Model B features (point-in-time)."""
    elo_df, _ = build_pregame_elo(completed)
    team_log = _team_game_log(completed)

    home_form = team_log[team_log["is_home"] == 1][
        ["game_id", "avg_margin_5", "avg_margin_10"]
    ].rename(
        columns={
            "avg_margin_5": "home_avg_margin_5",
            "avg_margin_10": "home_avg_margin_10",
        }
    )
    away_form = team_log[team_log["is_home"] == 0][
        ["game_id", "avg_margin_5", "avg_margin_10"]
    ].rename(
        columns={
            "avg_margin_5": "away_avg_margin_5",
            "avg_margin_10": "away_avg_margin_10",
        }
    )

    frame = elo_df.merge(home_form, on="game_id", how="left")
    frame = frame.merge(away_form, on="game_id", how="left")
    frame["home_recent_form_advantage"] = (
        frame["home_avg_margin_10"] - frame["away_avg_margin_10"]
    )
    frame["target"] = (frame["home_points"] > frame["away_points"]).astype(int)
    return frame


def build_team_state(completed: pd.DataFrame) -> pd.DataFrame:
    """Current Elo + form snapshot for every team (after all completed games)."""
    _, ratings = build_pregame_elo(completed)
    team_log = _team_game_log(completed)

    # Trailing form including the latest completed game
    rows = []
    for team, hist in team_log.groupby("team"):
        hist = hist.sort_values(["game_date", "game_id"])
        margins = hist["margin"]
        rows.append(
            {
                "team": team,
                "current_elo": ratings.get(team, 1500.0),
                "avg_margin_5": float(margins.tail(5).mean()) if len(margins) else np.nan,
                "avg_margin_10": float(margins.tail(10).mean()) if len(margins) else np.nan,
                "games_played": int(len(hist)),
                "last_game_date": hist["game_date"].iloc[-1] if len(hist) else pd.NaT,
            }
        )
    state = pd.DataFrame(rows).sort_values("team").reset_index(drop=True)
    return state


def features_for_matchup(home: str, away: str, state: pd.DataFrame) -> dict[str, float]:
    state = state.set_index("team")
    home = home.upper()
    away = away.upper()
    if home not in state.index or away not in state.index:
        raise KeyError(f"Missing team state for {away} @ {home}")
    h = state.loc[home]
    a = state.loc[away]
    return {
        "home_elo_difference": float(h["current_elo"] - a["current_elo"]),
        "home_recent_form_advantage": float(h["avg_margin_10"] - a["avg_margin_10"]),
        "home_avg_margin_5": float(h["avg_margin_5"]),
        "away_avg_margin_5": float(a["avg_margin_5"]),
        "home_avg_margin_10": float(h["avg_margin_10"]),
        "away_avg_margin_10": float(a["avg_margin_10"]),
    }
