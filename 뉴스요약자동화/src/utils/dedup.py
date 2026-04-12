"""중복 제거 — URL 해시 + 제목 유사도"""
from __future__ import annotations

import hashlib
import logging
from difflib import SequenceMatcher
from typing import List

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)


def deduplicate(items: List[NewsItem]) -> List[NewsItem]:
    """2-Pass 중복 제거: URL 해시 → 제목 유사도"""
    # Pass 1: URL 해시
    seen_urls = set()
    url_deduped = []
    for item in items:
        url_hash = hashlib.md5(item.url.encode()).hexdigest()
        if url_hash not in seen_urls:
            seen_urls.add(url_hash)
            url_deduped.append(item)

    # Pass 2: 제목 유사도
    threshold = cfg.TITLE_SIMILARITY_THRESHOLD
    title_deduped = []
    for item in url_deduped:
        is_dup = False
        for existing in title_deduped:
            ratio = SequenceMatcher(None, item.title, existing.title).ratio()
            if ratio >= threshold:
                is_dup = True
                break
        if not is_dup:
            title_deduped.append(item)

    removed = len(items) - len(title_deduped)
    if removed:
        logger.info(f"[Dedup] {len(items)}건 → {len(title_deduped)}건 ({removed}건 중복 제거)")

    return title_deduped
