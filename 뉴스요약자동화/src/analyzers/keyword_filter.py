"""키워��� 기반 1차 필터링 — STRONG / MEDIUM / WEAK 티어 분류

기존 뉴스정보/filters/keyword_filter.py에서 이식 + NIAS v2.0 키워드 확장 적용
"""
from __future__ import annotations

import logging
import re
from typing import List

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    """텍스트에서 매칭되는 키워드 목록 반환 (대���문자 무시)"""
    text_lower = text.lower()
    matched = []
    for kw in keywords:
        if len(kw) <= 2:
            pattern = r'\b' + re.escape(kw.lower()) + r'\b'
            if re.search(pattern, text_lower):
                matched.append(kw)
        else:
            if kw.lower() in text_lower:
                matched.append(kw)
    return matched


def filter_by_keywords(items: List[NewsItem]) -> List[NewsItem]:
    """키워드 기반 뉴스 ��어 분류 + 매칭 키워드 태깅

    Returns:
        티어가 태깅�� NewsItem 리스트 (매칭 없는 건 제외)
    """
    filtered: List[NewsItem] = []
    excluded = 0

    for item in items:
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}"

        strong = _match_keywords(text, cfg.KEYWORDS_STRONG)
        medium = _match_keywords(text, cfg.KEYWORDS_MEDIUM)
        weak = _match_keywords(text, cfg.KEYWORDS_WEAK)

        all_matched = strong + medium + weak

        if strong:
            item.keyword_tier = "STRONG"
            item.matched_keywords = list(set(all_matched))
            filtered.append(item)
        elif medium:
            item.keyword_tier = "MEDIUM"
            item.matched_keywords = list(set(all_matched))
            filtered.append(item)
        elif weak:
            item.keyword_tier = "WEAK"
            item.matched_keywords = list(set(all_matched))
            filtered.append(item)
        else:
            excluded += 1

    logger.info(
        f"[필터] {len(items)}건 → {len(filtered)}건 통과 "
        f"(STRONG:{sum(1 for i in filtered if i.keyword_tier=='STRONG')}, "
        f"MEDIUM:{sum(1 for i in filtered if i.keyword_tier=='MEDIUM')}, "
        f"WEAK:{sum(1 for i in filtered if i.keyword_tier=='WEAK')}, "
        f"제외:{excluded})"
    )
    return filtered
