"""Google News RSS Fallback 수집기"""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

import config as cfg
from collectors.rss_collector import collect_rss

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def collect_google_news(queries: list[dict] | None = None) -> list:
    """Google News RSS로 뉴스 수집

    Args:
        queries: [{"name", "query", "region"}] 리스트

    Returns:
        NewsItem 리스트
    """
    if queries is None:
        queries = cfg.GOOGLE_NEWS_QUERIES

    sources = []
    for q in queries:
        url = GOOGLE_NEWS_RSS_TEMPLATE.format(query=quote_plus(q["query"]))
        sources.append({
            "name": q["name"],
            "url": url,
            "region": q.get("region", "GLOBAL"),
        })

    logger.info(f"[Google News] {len(sources)}개 쿼리 수집 시작")
    # RSS 수집기 재활용, 본문 추출은 스킵 (Google News redirect 이슈)
    items = collect_rss(sources, fetch_body=False)

    for item in items:
        if item.region == "GLOBAL" and not item.snippet:
            item.snippet = item.title

    logger.info(f"[Google News] 총 {len(items)}건 수집 완료")
    return items
