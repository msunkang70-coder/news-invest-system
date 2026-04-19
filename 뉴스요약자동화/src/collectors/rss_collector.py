"""RSS 피드 수집기 — 뉴스 + 지정학 소스"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime
from typing import List
from urllib.parse import urlparse

import feedparser

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)


def _resolve_google_news_url(gn_url: str) -> str:
    """Google News RSS URL → 브라우저에서 열 수 있는 URL로 변환

    /rss/articles/CBMi... → /articles/CBMi... 로 변환하면
    브라우저에서 클릭 시 원본 기사로 자동 리다이렉트됨.
    """
    if "news.google.com/rss/articles/" in gn_url:
        return gn_url.replace("/rss/articles/", "/articles/")
    return gn_url


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

            raw_url = entry.get("link", "")
            # Google News URL → 원본 URL 리다이렉트 추적
            url = _resolve_google_news_url(raw_url)

            item = NewsItem(
                title=entry.get("title", "").strip(),
                source=source["name"],
                url=url,
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
    """RSS 피드 수집 — 뉴스 + 지정학 + 한국어 Google News + 키워드 쿼리 + 핫스팟"""
    feeds = []
    if sources in ("all", "kr"):
        feeds.extend(cfg.RSS_SOURCES_KR)
        # 한국어 Google News (종목/섹터별 심화 수집)
        feeds.extend(getattr(cfg, "GOOGLE_NEWS_QUERIES_KR", []))

    if sources in ("all", "global"):
        feeds.extend(cfg.RSS_SOURCES_GLOBAL)
        # 단기안: 이전에는 정의만 되고 미연결 상태였던 쿼리들을 실제 파이프라인에 연결
        feeds.extend(getattr(cfg, "GOOGLE_NEWS_QUERIES", []))
        # 확장 준비: AP/BBC/Al Jazeera 등 직접 RSS (기본 OFF, ENABLE_EXTENDED_GLOBAL로 제어)
        if getattr(cfg, "ENABLE_EXTENDED_GLOBAL", False):
            feeds.extend(getattr(cfg, "RSS_SOURCES_GLOBAL_DIRECT", []))

    if sources in ("all", "geopolitical"):
        feeds.extend(cfg.RSS_SOURCES_GEOPOLITICAL)
        feeds.extend(getattr(cfg, "GOOGLE_NEWS_QUERIES_GEOPOLITICAL", []))
        # 단기안 신규: 지정학 핫스팟 (호르무즈·해상봉쇄·이란·대만·북한 등 전담)
        feeds.extend(getattr(cfg, "GOOGLE_NEWS_QUERIES_HOTSPOT", []))

    all_items = []
    for source in feeds:
        items = _parse_single_feed(source)
        all_items.extend(items)

    logger.info(f"[RSS] 전체 수집 완료: {len(all_items)}건 ({len(feeds)}개 피드)")
    return all_items
