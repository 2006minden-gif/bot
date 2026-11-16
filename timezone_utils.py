# -*- coding: utf-8 -*-
"""Время в часовом поясе проекта (Europe/Moscow по умолчанию)."""
from datetime import datetime

import config

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(config.TIMEZONE)
except Exception:  # noqa: BLE001
    _TZ = None


def now_str() -> str:
    dt = datetime.now(_TZ) if _TZ else datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S") + f" ({config.TIMEZONE})"
