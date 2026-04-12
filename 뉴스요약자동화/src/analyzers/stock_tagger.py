"""종목 태깅 — NIAS v2.0

뉴스 텍스트에서 관심 종목을 매칭하고 tagged_stocks, stock_impacts에 기록.
config.py의 STOCK_TAGS 사전 기반 매칭 + 섹터 간접 매핑.
"""
from __future__ import annotations

import logging
import re
from typing import List

import config as cfg
from models.news_item import NewsItem, Direction, StockImpact

logger = logging.getLogger(__name__)

BULL_SIGNALS = [
    "호실적", "매출 증가", "수주", "상향", "흑자", "성장", "확대",
    "수요 증가", "양산", "공급 계약", "수출 호조", "점유율 확대",
    "surge", "beat", "upgrade", "growth", "record", "outperform",
    "투자 확대", "신모델", "출시", "공개", "협력", "파트너십",
]
BEAR_SIGNALS = [
    "적자", "매출 감소", "하향", "손실", "부진", "둔화", "축소",
    "리콜", "소송", "규제", "벌금", "파업", "감산", "철수",
    "plunge", "downgrade", "decline", "loss", "miss", "underperform",
    "경쟁 심화", "점유율 하락", "지연", "취소", "중단",
]

SECTOR_STOCKS = {
    "반도체": ["삼성전자", "SK하이닉스", "NVIDIA", "TSMC"],
    "AI": ["NVIDIA", "마이크로소프트", "구글", "메타"],
    "자동차": ["현대차", "테슬라"],
    "배터리": ["LG에너지솔루션"],
    "인터넷": ["네이버", "카카오", "구글"],
    "빅테크": ["애플", "마이크로소프트", "구글", "아마존", "메타"],
}

SECTOR_KEYWORDS = {
    "반도체": ["반도체", "semiconductor", "chip", "메모리", "DRAM", "HBM", "낸드"],
    "AI": ["AI", "인공지능", "artificial intelligence", "LLM", "GPT", "데이터센터"],
    "자동차": ["자동차", "EV", "전기차", "automotive"],
    "배터리": ["배터리", "battery", "2차전지", "리튬"],
    "인터넷": ["플랫폼", "검색", "광고", "이커머스"],
    "빅테크": ["빅테크", "big tech", "FAANG", "매그니피센트"],
}

# 컴파일된 패턴 캐시
_PATTERNS: dict[str, list[re.Pattern]] = {}


def _get_patterns() -> dict[str, list[re.Pattern]]:
    if not _PATTERNS:
        for stock, keywords in cfg.STOCK_TAGS.items():
            _PATTERNS[stock] = [re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords]
    return _PATTERNS


def _detect_direction(text: str) -> tuple[Direction, float]:
    text_lower = text.lower()
    bull = sum(1 for kw in BULL_SIGNALS if kw.lower() in text_lower)
    bear = sum(1 for kw in BEAR_SIGNALS if kw.lower() in text_lower)
    total = bull + bear
    if total == 0:
        return Direction.BULL, 0.5
    if bull > bear:
        return Direction.BULL, round(0.5 + min(0.5, (bull - bear) / max(total, 1) * 0.5), 2)
    elif bear > bull:
        return Direction.BEAR, round(0.5 + min(0.5, (bear - bull) / max(total, 1) * 0.5), 2)
    return Direction.BULL, 0.55


def tag_stocks(items: List[NewsItem]) -> List[NewsItem]:
    """뉴스 목록에 종목 태깅 (직접 + 섹터 간접)"""
    patterns = _get_patterns()
    total_tagged = 0

    for item in items:
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}"
        impacts: dict[str, StockImpact] = {}

        # 1) 직접 종목 매칭
        for stock_name, stock_patterns in patterns.items():
            for pat in stock_patterns:
                if pat.search(text):
                    direction, confidence = _detect_direction(text)
                    intensity = round(min(1.0, 0.7 * 0.6 + (item.impact_score / 10) * 0.4), 2)

                    sector = ""
                    for sec, stocks in SECTOR_STOCKS.items():
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

        # 2) 섹터 키워드 → 간접 매핑
        text_lower = text.lower()
        for sector, keywords in SECTOR_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw.lower() in text_lower)
            if hits >= 2:
                direction, confidence = _detect_direction(text)
                for stock_name in SECTOR_STOCKS.get(sector, []):
                    if stock_name not in impacts:
                        intensity = round(min(1.0, 0.3 * 0.6 + (item.impact_score / 10) * 0.4), 2)
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
            total_tagged += 1

    logger.info(f"[종목태깅] {total_tagged}/{len(items)}건 종목 매핑 완료")
    return items
