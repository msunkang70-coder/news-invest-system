"""데이터 신선도 유틸리티 — NIAS v2.0

뉴스 발행시간을 "방금 전" / "2시간 전" / "3일 전" 등 상대 시간으로 변환.
24시간 이상 된 뉴스에 "과거" 태그 부여.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def relative_time(dt) -> str:
    """발행시간 → 상대 시간 문자열"""
    if not dt:
        return ""
    now = datetime.now()
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00").replace("+00:00", ""))
        except Exception:
            return ""
    try:
        diff = now - dt
    except Exception:
        return ""

    secs = int(diff.total_seconds())
    if secs < 0:
        return "방금"
    if secs < 60:
        return "방금 전"
    if secs < 3600:
        return f"{secs // 60}분 전"
    if secs < 86400:
        return f"{secs // 3600}시간 전"
    days = secs // 86400
    if days == 1:
        return "어제"
    if days < 7:
        return f"{days}일 전"
    return f"{days}일 전"


def freshness_badge(dt) -> str:
    """신선도 뱃지 HTML"""
    if not dt:
        return ""
    now = datetime.now()
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00").replace("+00:00", ""))
        except Exception:
            return ""
    try:
        diff = now - dt
    except Exception:
        return ""

    hours = diff.total_seconds() / 3600
    if hours < 1:
        return '<span style="background:#22c55e;color:white;padding:1px 6px;border-radius:8px;font-size:10px;">방금</span>'
    if hours < 6:
        return f'<span style="background:#3b82f6;color:white;padding:1px 6px;border-radius:8px;font-size:10px;">{int(hours)}시간 전</span>'
    if hours < 24:
        return f'<span style="background:#f59e0b;color:white;padding:1px 6px;border-radius:8px;font-size:10px;">{int(hours)}시간 전</span>'
    days = int(hours / 24)
    return f'<span style="background:#94a3b8;color:white;padding:1px 6px;border-radius:8px;font-size:10px;">⏳ {days}일 전</span>'


def is_stale(dt, hours: int = 24) -> bool:
    """24시간 이상 된 뉴스인지"""
    if not dt:
        return False
    now = datetime.now()
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00").replace("+00:00", ""))
        except Exception:
            return False
    try:
        return (now - dt).total_seconds() > hours * 3600
    except Exception:
        return False
