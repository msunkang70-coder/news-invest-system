"""한국어 번역 유틸리티 — NIAS v2.0

영어 뉴스 제목/본문을 한국어로 번역.
Google Translate 무료 API 사용 (LLM 할당량 미소모).
번역 실패 시 원문 그대로 반환.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# 캐시: 동일 텍스트 반복 번역 방지 (최대 500건)
_cache: dict[str, str] = {}


def _is_korean(text: str) -> bool:
    """텍스트가 이미 한국어인지 판별 (한글 비율 30% 이상)"""
    if not text:
        return True
    korean_chars = sum(1 for c in text if '\uAC00' <= c <= '\uD7A3')
    return korean_chars / len(text) > 0.3


def translate_to_kr(text: str) -> str:
    """영어 텍스트를 한국어로 번역. 이미 한국어면 그대로 반환."""
    if not text or _is_korean(text):
        return text

    # 캐시 확인
    cache_key = text[:100]
    if cache_key in _cache:
        return _cache[cache_key]

    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='en', target='ko').translate(text[:500])
        if translated:
            _cache[cache_key] = translated
            return translated
    except Exception as e:
        logger.debug(f"[번역] 실패 → 원문 유지: {e}")

    return text


def translate_title(title: str) -> str:
    """뉴스 제목 번역 (짧은 텍스트 최적화)"""
    if not title or _is_korean(title):
        return title

    # "Title - Source" 형식에서 소스 분리
    parts = title.rsplit(" - ", 1)
    main_title = parts[0]
    source = parts[1] if len(parts) > 1 else ""

    translated = translate_to_kr(main_title)
    if source:
        return f"{translated} - {source}"
    return translated
