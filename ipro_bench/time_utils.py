from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    BRASILIA = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:
    # Brazil has observed UTC-03:00 without daylight saving time since 2019.
    BRASILIA = timezone(timedelta(hours=-3), "BRT")


def brasilia_datetime(value: str | datetime | None = None) -> datetime:
    if value is None:
        parsed = datetime.now(BRASILIA)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BRASILIA)
    return parsed.astimezone(BRASILIA)


def brasilia_text(value: str | datetime | None) -> str:
    return brasilia_datetime(value).strftime("%d/%m/%Y %H:%M:%S %Z")
