"""RSS 피드 수집기 — 뉴스 + 지정학 소스"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import feedparser

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)


def _parse_single_feed(source: dict) -> List[NewsItem]:
    """단일 RSS 피드 파싱"""
    try:
        feed = feedparser.parse(
            source["url"],
            agent=cfg.USER_AGENT,
        )
        items = []
        for entry in feed.entries[:cfg.MAX_ARTICLES_PER_FEED]:
            pub_time = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_time = datetime(*entry.published_parsed[:6])

            item = NewsItem(
                title=entry.get("title", "").strip(),
                source=source["name"],
                url=entry.get("link", ""),
                source_type="RSS",
                published_time=pub_time,
                snippet=entry.get("summary", "")[:500],
                region=source.get("region", "KR"),
            )
            if item.title and item.url:
                items.append(item)

        logger.info(f"[RSS] {source['name']}: {len(items)}건 수집")
        return items

    except Exception as e:
        logger.warning(f"[RSS] {source['name']} 수집 실패: {e}")
        return []


def collect_rss_feeds(sources: str = "all") -> List[NewsItem]:
    """RSS 피드 수집 — 뉴스 + 지정학"""
    feeds = []
    if sources in ("all", "kr"):
        feeds.extend(cfg.RSS_SOURCES_KR)
    if sources in ("all", "global"):
        feeds.extend(cfg.RSS_SOURCES_GLOBAL)
    if sources in ("all", "geopolitical"):
        feeds.extend(cfg.RSS_SOURCES_GEOPOLITICAL)

    all_items = []
    for source in feeds:
        items = _parse_single_feed(source)
        all_items.extend(items)

    logger.info(f"[RSS] 전체 수집 완료: {len(all_items)}건 ({len(feeds)}개 피드)")
    return all_items
