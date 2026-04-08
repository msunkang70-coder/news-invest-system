"""중복 뉴스 제거 — URL 해시 + 제목 유사도"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)


def _title_similarity(a: str, b: str) -> float:
    """두 제목의 유사도 (0~1)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def deduplicate(items: list[NewsItem]) -> list[NewsItem]:
    """중복 제거 — URL 해시 + 제목 유사도 기반

    Returns:
        중복 제거된 NewsItem 리스트
    """
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    unique: list[NewsItem] = []
    dup_count = 0

    for item in items:
        # 1) URL 중복
        if item._hash in seen_urls:
            dup_count += 1
            continue

        # 2) 제목 유사도 중복
        is_dup = False
        for seen_t in seen_titles:
            if _title_similarity(item.title, seen_t) >= cfg.TITLE_SIMILARITY_THRESHOLD:
                is_dup = True
                dup_count += 1
                break

        if not is_dup:
            seen_urls.add(item._hash)
            seen_titles.append(item.title)
            unique.append(item)

    logger.info(f"[중복제거] {len(items)}건 → {len(unique)}건 (중복 {dup_count}건 제거)")
    return unique
