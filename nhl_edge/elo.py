from __future__ import annotations

import pandas as pd

from nhl_edge.config import BASE_ELO, HOME_ADVANTAGE, K_FACTOR, SEASON_CARRYOVER


def build_pregame_elo(completed: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Chronological Elo with same-day batch updates (no same-day leakage).
    Returns per-game pregame Elo rows and final team ratings.
    """
    games = completed.copy()
    games = games.sort_values(["game_date", "game_id"]).reset_index(drop=True)

    ratings: dict[str, float] = {}
    current_season: int | None = None
    records: list[dict] = []

    for game_date, day_games in games.groupby("game_date", sort=True):
        daily_updates: dict[str, float] = {}

        for game in day_games.itertuples(index=False):
            season = int(game.season)
            home = str(game.home_abbreviation).upper()
            away = str(game.away_abbreviation).upper()

            if current_season is not None and season != current_season:
                ratings = {
                    team: BASE_ELO + SEASON_CARRYOVER * (rating - BASE_ELO)
                    for team, rating in ratings.items()
                }
            current_season = season

            rh = ratings.get(home, BASE_ELO)
            ra = ratings.get(away, BASE_ELO)
            expected = 1.0 / (1.0 + 10 ** (-(rh - ra + HOME_ADVANTAGE) / 400.0))
            actual = 1.0 if float(game.home_points) > float(game.away_points) else 0.0
            change = K_FACTOR * (actual - expected)

            records.append(
                {
                    "game_id": game.game_id,
                    "game_date": game_date,
                    "season": season,
                    "home_abbreviation": home,
                    "away_abbreviation": away,
                    "home_elo_pre": rh,
                    "away_elo_pre": ra,
                    "home_elo_difference": rh - ra,
                    "home_elo_probability": expected,
                    "home_points": game.home_points,
                    "away_points": game.away_points,
                }
            )

            daily_updates[home] = daily_updates.get(home, 0.0) + change
            daily_updates[away] = daily_updates.get(away, 0.0) - change

        for team, change in daily_updates.items():
            ratings[team] = ratings.get(team, BASE_ELO) + change

    return pd.DataFrame(records), ratings
