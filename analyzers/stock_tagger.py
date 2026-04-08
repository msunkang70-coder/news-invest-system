"""종목 태깅 — 뉴스 본문에서 관련 종목 자동 매칭 (강화)"""
from __future__ import annotations

import logging
import re

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

# config의 STOCK_TAGS를 기반으로 컴파일된 패턴 생성
_COMPILED_PATTERNS: dict[str, list[re.Pattern]] = {}


def _get_patterns() -> dict[str, list[re.Pattern]]:
    """키워드별 정규식 패턴 캐시"""
    if not _COMPILED_PATTERNS:
        for stock_name, keywords in cfg.STOCK_TAGS.items():
            patterns = []
            for kw in keywords:
                # 대소문자 무시, 한글은 그대로 매칭
                try:
                    patterns.append(re.compile(re.escape(kw), re.IGNORECASE))
                except re.error:
                    pass
            _COMPILED_PATTERNS[stock_name] = patterns
    return _COMPILED_PATTERNS


def tag_stocks(items: list[NewsItem]) -> list[NewsItem]:
    """뉴스에 관련 종목 태깅 (정규식 기반, 대소문자 무시)"""
    patterns = _get_patterns()

    for item in items:
        # 제목 + snippet + 본문 앞부분을 합쳐서 검색
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:1000]}"
        tags = []

        for stock_name, stock_patterns in patterns.items():
            for pat in stock_patterns:
                if pat.search(text):
                    tags.append(stock_name)
                    break  # 하나만 매칭되면 다음 종목으로

        item.tagged_stocks = list(set(tags))

    tagged_count = sum(1 for i in items if i.tagged_stocks)
    if items:
        logger.info(f"[태깅] {tagged_count}/{len(items)}건 종목 태깅 완료")
        # 태깅 0건이면 디버그 정보
        if tagged_count == 0:
            sample_titles = [i.title[:40] for i in items[:3]]
            logger.debug(f"[태깅] 샘플 제목: {sample_titles}")

    return items
