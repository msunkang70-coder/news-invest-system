"""종목 영향 매핑 — 뉴스 → 종목별 방향+강도+사유 매핑

기존 stock_tagger: 단순 키워드 매칭 → "삼성전자" 태깅
개선: 종목 + 방향(BULL/BEAR) + 강도(0~1) + 영향 사유 추출
"""
from __future__ import annotations

import logging
import re

import config as cfg
from models.news_item import NewsItem, Direction, StockImpact

logger = logging.getLogger(__name__)

# 종목별 센티먼트 키워드 (해당 종목 맥락에서)
_BULL_SIGNALS = [
    "호실적", "매출 증가", "수주", "상향", "흑자", "성장", "확대",
    "수요 증가", "양산", "공급 계약", "수출 호조", "점유율 확대",
    "surge", "beat", "upgrade", "growth", "record", "outperform",
    "투자 확대", "신모델", "출시", "공개", "협력", "파트너십",
]
_BEAR_SIGNALS = [
    "적자", "매출 감소", "하향", "손실", "부진", "둔화", "축소",
    "리콜", "소송", "규제", "벌금", "파업", "감산", "철수",
    "plunge", "downgrade", "decline", "loss", "miss", "underperform",
    "경쟁 심화", "점유율 하락", "지연", "취소", "중단",
]

# 섹터-종목 매핑 (섹터 키워드 히트 시 관련 종목에 간접 영향)
_SECTOR_STOCKS = {
    "반도체": ["삼성전자", "SK하이닉스", "NVIDIA", "TSMC"],
    "AI": ["NVIDIA", "마이크로소프트", "구글", "메타"],
    "자동차": ["현대차", "테슬라"],
    "배터리": ["LG에너지솔루션"],
    "인터넷": ["네이버", "카카오", "구글"],
    "빅테크": ["애플", "마이크로소프트", "구글", "아마존", "메타"],
}

_SECTOR_KEYWORDS = {
    "반도체": ["반도체", "semiconductor", "chip", "메모리", "DRAM", "HBM", "낸드"],
    "AI": ["AI", "인공지능", "artificial intelligence", "LLM", "GPT", "데이터센터"],
    "자동차": ["자동차", "EV", "전기차", "automotive"],
    "배터리": ["배터리", "battery", "2차전지", "리튬"],
    "인터넷": ["플랫폼", "검색", "광고", "이커머스"],
    "빅테크": ["빅테크", "big tech", "FAANG", "매그니피센트"],
}

# 컴파일된 종목 패턴 캐시
_STOCK_PATTERNS: dict[str, list[re.Pattern]] = {}


def _get_patterns() -> dict[str, list[re.Pattern]]:
    if not _STOCK_PATTERNS:
        for stock, keywords in cfg.STOCK_TAGS.items():
            _STOCK_PATTERNS[stock] = [
                re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords
            ]
    return _STOCK_PATTERNS


def _detect_direction(text: str) -> tuple[Direction, float]:
    """텍스트의 방향성 + 확신도"""
    text_lower = text.lower()
    bull = sum(1 for kw in _BULL_SIGNALS if kw.lower() in text_lower)
    bear = sum(1 for kw in _BEAR_SIGNALS if kw.lower() in text_lower)

    total = bull + bear
    if total == 0:
        return Direction.BULL, 0.5  # 기본: 약한 BULL

    if bull > bear:
        confidence = 0.5 + min(0.5, (bull - bear) / max(total, 1) * 0.5)
        return Direction.BULL, round(confidence, 2)
    elif bear > bull:
        confidence = 0.5 + min(0.5, (bear - bull) / max(total, 1) * 0.5)
        return Direction.BEAR, round(confidence, 2)
    else:
        # 동점이면 제목 키워드로 판단
        title_lower = text.split("\n")[0].lower() if "\n" in text else text_lower[:100]
        title_bull = sum(1 for kw in _BULL_SIGNALS[:10] if kw.lower() in title_lower)
        title_bear = sum(1 for kw in _BEAR_SIGNALS[:10] if kw.lower() in title_lower)
        if title_bull >= title_bear:
            return Direction.BULL, 0.55
        return Direction.BEAR, 0.55


def _calculate_intensity(item: NewsItem, is_direct: bool) -> float:
    """종목에 대한 영향 강도 (0~1)"""
    base = 0.7 if is_direct else 0.3  # 직접 언급 vs 섹터 간접
    # impact_score 반영
    score_factor = item.impact_score / 10.0
    return round(min(1.0, base * 0.6 + score_factor * 0.4), 2)


def map_stock_impacts(items: list[NewsItem]) -> list[NewsItem]:
    """종목 영향 매핑 — 직접 언급 + 섹터 간접 영향"""
    patterns = _get_patterns()
    total_mapped = 0

    for item in items:
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:1000]}"
        impacts: dict[str, StockImpact] = {}

        # 1) 직접 종목 언급 매칭
        for stock_name, stock_patterns in patterns.items():
            for pat in stock_patterns:
                if pat.search(text):
                    direction, confidence = _detect_direction(text)
                    intensity = _calculate_intensity(item, is_direct=True)

                    # 종목별 섹터 찾기
                    sector = ""
                    for sec, stocks in _SECTOR_STOCKS.items():
                        if stock_name in stocks:
                            sector = sec
                            break

                    impacts[stock_name] = StockImpact(
                        stock_name=stock_name,
                        direction=direction,
                        intensity=intensity,
                        reason=f"직접 언급 ({pat.pattern})",
                        sector=sector,
                    )
                    break

        # 2) 섹터 키워드 → 간접 영향
        text_lower = text.lower()
        for sector, keywords in _SECTOR_KEYWORDS.items():
            sector_hits = sum(1 for kw in keywords if kw.lower() in text_lower)
            if sector_hits >= 2:
                direction, confidence = _detect_direction(text)
                for stock_name in _SECTOR_STOCKS.get(sector, []):
                    if stock_name not in impacts:
                        intensity = _calculate_intensity(item, is_direct=False)
                        impacts[stock_name] = StockImpact(
                            stock_name=stock_name,
                            direction=direction,
                            intensity=intensity,
                            reason=f"섹터 간접 ({sector})",
                            sector=sector,
                        )

        item.stock_impacts = list(impacts.values())
        item.tagged_stocks = [si.stock_name for si in item.stock_impacts]
        if item.stock_impacts:
            total_mapped += 1

    logger.info(f"[종목매핑] {total_mapped}/{len(items)}건 종목 영향 매핑 완료")
    return items
