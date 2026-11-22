"""ATS / puck-line cover probabilities from the moneyline win model."""

from __future__ import annotations

import math


# Logistic margin scale (goals). Calibrated so P(margin>0) ≈ home win prob.
MARGIN_SCALE = 0.85


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def expected_home_margin(home_win_prob: float, scale: float = MARGIN_SCALE) -> float:
    """Implied E[home_goals − away_goals] from the win model."""
    return scale * _logit(home_win_prob)


def cover_probability(
    home_win_prob: float,
    *,
    side: str,
    point: float,
    scale: float = MARGIN_SCALE,
) -> float:
    """
    P(side covers) with logistic home-margin model.

    Odds API `point` is the spread on that side (home -1.5, away +1.5).
    Cover when side_score + point > opponent_score.
    """
    mu = expected_home_margin(home_win_prob, scale=scale)
    s = float(scale) if scale else MARGIN_SCALE
    side_l = str(side).lower()
    pt = float(point)
    if side_l == "home":
        # home_margin + point > 0  ⇒  margin > -point
        t = -pt
        return 1.0 / (1.0 + math.exp((t - mu) / s))
    # away_margin + point > 0  ⇒  -home_margin + point > 0  ⇒  margin < point
    t = pt
    return 1.0 / (1.0 + math.exp((mu - t) / s))


def grade_spread(side: str, point: float, away_score: float, home_score: float) -> str | None:
    try:
        a = float(away_score)
        h = float(home_score)
        pt = float(point)
    except (TypeError, ValueError):
        return None
    if str(side).lower() == "away":
        margin = a + pt - h
    else:
        margin = h + pt - a
    if abs(margin) < 1e-9:
        return "P"
    return "W" if margin > 0 else "L"
