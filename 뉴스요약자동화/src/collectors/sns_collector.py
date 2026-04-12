"""SNS/X 수집기 — NIAS v2.0

금융 인플루언서 및 공식 계정의 포스트를 수집.
방법 1: X API v2 (Basic tier, 유료)
방법 2: Google News RSS로 대체 (무료 fallback)
"""
from __future__ import annotations

import logging
from typing import List

import config as cfg
from models.news_item import NewsItem
from collectors.rss_collector import _parse_single_feed

logger = logging.getLogger(__name__)

# X API를 사용할 수 없는 경우, Google News RSS로 금융 인플루언서 발언을 검색
SNS_FALLBACK_FEEDS = [
    {
        "name": "GN - Fed/경제 발언",
        "url": "https://news.google.com/rss/search?q=Federal+Reserve+statement+OR+Fed+chair&hl=en-US&gl=US&ceid=US:en",
        "region": "GLOBAL",
    },
    {
        "name": "GN - 증시 전문가 의견",
        "url": "https://news.google.com/rss/search?q=stock+market+analyst+opinion+forecast&hl=en-US&gl=US&ceid=US:en",
        "region": "GLOBAL",
    },
]


def collect_sns_posts() -> List[NewsItem]:
    """SNS/전문가 발언 수집

    X API가 설정되지 않은 경우 Google News RSS fallback 사용.
    """
    # TODO: X API v2 연동 (KIS_APP_KEY와 별개로 X_BEARER_TOKEN 필요)
    # X API가 없으면 Google News RSS fallback
    return _collect_via_google_news_fallback()


def _collect_via_google_news_fallback() -> List[NewsItem]:
    """Google News RSS를 통한 전문가 발언/SNS 대체 수집"""
    items = []
    for feed in SNS_FALLBACK_FEEDS:
        result = _parse_single_feed(feed)
        for item in result:
            item.source_type = "SNS"
        items.extend(result)

    if items:
        logger.info(f"[SNS] Google News fallback: {len(items)}건 수집")
    return items
