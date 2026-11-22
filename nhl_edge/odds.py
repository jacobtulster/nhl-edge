from __future__ import annotations

import re
from typing import Any

import requests

from nhl_edge.config import ODDS_API_KEY, ODDS_URL

# Full name / nickname → abbreviation
TEAM_ALIASES = {
    "anaheim ducks": "ANA",
    "arizona coyotes": "ARI",
    "utah hockey club": "UTA",
    "utah mammoth": "UTA",
    "boston bruins": "BOS",
    "buffalo sabres": "BUF",
    "calgary flames": "CGY",
    "carolina hurricanes": "CAR",
    "chicago blackhawks": "CHI",
    "colorado avalanche": "COL",
    "columbus blue jackets": "CBJ",
    "dallas stars": "DAL",
    "detroit red wings": "DET",
    "edmonton oilers": "EDM",
    "florida panthers": "FLA",
    "los angeles kings": "LAK",
    "minnesota wild": "MIN",
    "montreal canadiens": "MTL",
    "montréal canadiens": "MTL",
    "nashville predators": "NSH",
    "new jersey devils": "NJD",
    "new york islanders": "NYI",
    "new york rangers": "NYR",
    "ottawa senators": "OTT",
    "philadelphia flyers": "PHI",
    "pittsburgh penguins": "PIT",
    "san jose sharks": "SJS",
    "seattle kraken": "SEA",
    "st louis blues": "STL",
    "st. louis blues": "STL",
    "tampa bay lightning": "TBL",
    "toronto maple leafs": "TOR",
    "vancouver canucks": "VAN",
    "vegas golden knights": "VGK",
    "washington capitals": "WSH",
    "winnipeg jets": "WPG",
}


def team_key(name: str) -> str:
    raw = str(name).strip()
    lower = raw.lower()
    if lower in TEAM_ALIASES:
        return TEAM_ALIASES[lower]
    if len(raw) <= 3:
        return raw.upper()
    return re.sub(r"[^a-z0-9]", "", lower)


def american_or_decimal_to_implied(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        return 0.0
    return 1.0 / decimal_odds


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """EV per $1 stake at decimal odds."""
    return model_prob * decimal_odds - 1.0


def fetch_odds(markets: str = "h2h,spreads") -> tuple[list[dict[str, Any]], dict[str, str]]:
    if not ODDS_API_KEY:
        raise ValueError("Missing ODDS_API_KEY. Set it in .env or GitHub Actions secrets.")

    response = requests.get(
        ODDS_URL,
        params={
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        },
        timeout=30,
    )
    response.raise_for_status()
    meta = {
        "requests_remaining": response.headers.get("x-requests-remaining", ""),
        "requests_used": response.headers.get("x-requests-used", ""),
    }
    return response.json(), meta


# Back-compat alias
fetch_h2h_odds = fetch_odds


def _side_for_outcome(name: str, home_name: str, away_name: str, home_abbr: str, away_abbr: str) -> str | None:
    if team_key(name) == home_abbr or name == home_name:
        return "home"
    if team_key(name) == away_abbr or name == away_name:
        return "away"
    return None


def best_h2h_prices(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events or []:
        home_name = event.get("home_team") or ""
        away_name = event.get("away_team") or ""
        home_abbr = team_key(home_name)
        away_abbr = team_key(away_name)
        best_home = None
        best_away = None
        home_book = None
        away_book = None
        for book in event.get("bookmakers") or []:
            title = book.get("title") or book.get("key") or ""
            for market in book.get("markets") or []:
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes") or []:
                    name = outcome.get("name") or ""
                    price = outcome.get("price")
                    if price is None:
                        continue
                    try:
                        price_f = float(price)
                    except (TypeError, ValueError):
                        continue
                    side = _side_for_outcome(name, home_name, away_name, home_abbr, away_abbr)
                    if side == "home" and (best_home is None or price_f > best_home):
                        best_home = price_f
                        home_book = title
                    elif side == "away" and (best_away is None or price_f > best_away):
                        best_away = price_f
                        away_book = title
        rows.append(
            {
                "home_abbreviation": home_abbr,
                "away_abbreviation": away_abbr,
                "home_team": home_name,
                "away_team": away_name,
                "home_decimal": best_home,
                "away_decimal": best_away,
                "home_book": home_book,
                "away_book": away_book,
            }
        )
    return rows


def collect_spread_quotes(events: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """All US-book puck-line quotes keyed by (home_abbr, away_abbr)."""
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events or []:
        home_name = event.get("home_team") or ""
        away_name = event.get("away_team") or ""
        home_abbr = team_key(home_name)
        away_abbr = team_key(away_name)
        key = (home_abbr, away_abbr)
        quotes = out.setdefault(key, [])
        for book in event.get("bookmakers") or []:
            title = book.get("title") or book.get("key") or ""
            for market in book.get("markets") or []:
                if market.get("key") != "spreads":
                    continue
                for outcome in market.get("outcomes") or []:
                    point = outcome.get("point")
                    price = outcome.get("price")
                    if point is None or price is None:
                        continue
                    try:
                        point_f = float(point)
                        price_f = float(price)
                    except (TypeError, ValueError):
                        continue
                    side = _side_for_outcome(
                        outcome.get("name") or "",
                        home_name,
                        away_name,
                        home_abbr,
                        away_abbr,
                    )
                    if not side:
                        continue
                    quotes.append(
                        {
                            "side": side,
                            "point": point_f,
                            "decimal": price_f,
                            "book": title,
                        }
                    )
    return out
