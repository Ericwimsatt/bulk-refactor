from __future__ import annotations

from datetime import datetime


def format_timestamp(now: datetime | None = None) -> str:
    """Return a readable local timestamp.

    Format example: ``5.29.2026_4.32.12PM``
    Uses dots instead of colons because ``:`` is not valid in git ref names.
    """
    now = now or datetime.now().astimezone()
    hour_12 = now.hour % 12 or 12
    am_pm = "AM" if now.hour < 12 else "PM"
    return f"{now.month}.{now.day}.{now.year}_{hour_12}.{now.minute:02d}.{now.second:02d}{am_pm}"
