"""시간대 분류 — KST 기준 프리마켓/장중/애프터마켓/글로벌"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from models.news_item import NewsItem, TimeSlot

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _classify_one(item: NewsItem) -> TimeSlot:
    """단일 뉴스의 시간대 분류"""

    # 해외 뉴스는 기본적으로 GLOBAL
    if item.region == "GLOBAL":
        # 단, KST 기준 장중 시간이면 해당 슬롯으로
        if item.published_time_kst:
            h = item.published_time_kst.hour
            m = item.published_time_kst.minute
            if 9 <= h < 15 or (h == 15 and m <= 30):
                return TimeSlot.MARKET_HOURS
        return TimeSlot.GLOBAL

    # 국내 뉴스 — KST 시간 기준
    if item.published_time_kst:
        h = item.published_time_kst.hour
        m = item.published_time_kst.minute
        t = h * 60 + m  # 분 단위

        if 360 <= t <= 539:       # 06:00 ~ 08:59
            return TimeSlot.PRE_MARKET
        elif 540 <= t <= 930:     # 09:00 ~ 15:30
            return TimeSlot.MARKET_HOURS
        elif 931 <= t <= 1439:    # 15:31 ~ 23:59
            return TimeSlot.AFTER_MARKET
        else:                     # 00:00 ~ 05:59
            return TimeSlot.GLOBAL

    # 시간 정보 없으면 장중으로 기본값
    return TimeSlot.MARKET_HOURS


def classify_timeslots(items: list[NewsItem]) -> list[NewsItem]:
    """전체 뉴스에 시간대 분류 태깅"""
    counts = {slot: 0 for slot in TimeSlot}

    for item in items:
        item.time_slot = _classify_one(item)
        counts[item.time_slot] += 1

    slot_summary = " / ".join(f"{s.emoji}{s.value}:{c}" for s, c in counts.items())
    logger.info(f"[시간대] {len(items)}건 분류: {slot_summary}")

    return items
