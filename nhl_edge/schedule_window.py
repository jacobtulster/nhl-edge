from __future__ import annotations

from datetime import datetime

from zoneinfo import ZoneInfo

from nhl_edge.config import RUN_HOUR_END_ET, RUN_HOUR_START_ET


def within_run_window(now: datetime | None = None) -> tuple[bool, str]:
    """Return whether we should run (8am–11pm Eastern, inclusive)."""
    now = now or datetime.now(ZoneInfo("America/New_York"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("America/New_York"))
    else:
        now = now.astimezone(ZoneInfo("America/New_York"))

    hour = now.hour
    ok = RUN_HOUR_START_ET <= hour <= RUN_HOUR_END_ET
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")
    if ok:
        return True, f"Inside run window ({stamp})."
    return False, f"Outside run window 8am–11pm ET ({stamp}). Skipping."
