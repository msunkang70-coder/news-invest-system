"""영향도 점수 v2 — 다차원 스코어링 (긴급도×파급범위×확실성) + 정규분포 재배치

기존: 키워드 히트 수 단순 합산 → 대부분 4~5점 밀집
개선: 차원별 독립 측정 → 정규분포 매핑 → 1~10 고르게 분산
"""
from __future__ import annotations

import logging
import math
import re

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

# ─── 긴급도 키워드 (속보/즉시 영향) ───
URGENCY_HIGH = [
    "속보", "긴급", "breaking", "just in", "flash",
    "서킷브레이커", "circuit breaker", "폭락", "급등", "급락",
    "전쟁", "war", "제재", "sanctions", "봉쇄",
    "crash", "surge", "plunge", "halt",
    "금리인상", "금리인하", "rate hike", "rate cut",
    "FOMC", "연준", "Fed",
]
URGENCY_MID = [
    "발표", "announce", "결정", "확정", "승인",
    "실적", "earnings", "guidance", "가이던스",
    "CPI", "PPI", "고용", "nonfarm", "GDP",
    "관세", "tariff", "수출", "수입",
]

# ─── 파급범위 키워드 ───
SCOPE_GLOBAL = [
    "글로벌", "global", "세계", "world", "미국", "중국", "유럽",
    "연준", "Fed", "ECB", "BOJ", "FOMC",
    "유가", "oil", "crude", "달러", "dollar", "환율",
    "전쟁", "war", "무역전쟁", "trade war",
    "인플레이션", "inflation", "경기침체", "recession",
]
SCOPE_SECTOR = [
    "반도체", "semiconductor", "AI", "자동차", "EV",
    "배터리", "battery", "바이오", "제약",
    "금융", "은행", "보험", "부동산",
    "에너지", "신재생", "원자력", "조선",
    "공급망", "supply chain",
]
SCOPE_SINGLE = [
    "실적", "earnings", "자사주", "배당", "buyback",
    "CEO", "대표이사", "인수", "합병", "M&A", "IPO",
]

# ─── 확실성 키워드 ───
CERTAINTY_HIGH = [
    "확정", "결정", "발표", "공시", "signed", "approved", "confirmed",
    "실적", "earnings", "보고서", "report",
    "통계", "지표", "data", "공식",
]
CERTAINTY_LOW = [
    "전망", "예상", "관측", "speculation", "rumor",
    "가능성", "우려", "concerns", "may", "might", "could",
    "검토", "논의", "considering", "reportedly",
    "칼럼", "의견", "opinion", "analysis",
]


def _keyword_hit_ratio(text: str, keywords: list[str]) -> float:
    """키워드 매칭 비율 (0~1)"""
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(1.0, hits / max(3, len(keywords) * 0.15))


def _calculate_urgency(text: str) -> float:
    """긴급도 (0~1): 속보/즉시 시장 영향 여부"""
    high = _keyword_hit_ratio(text, URGENCY_HIGH)
    mid = _keyword_hit_ratio(text, URGENCY_MID)
    return min(1.0, high * 0.7 + mid * 0.3)


def _calculate_scope(text: str) -> float:
    """파급범위 (0~1): 글로벌 > 섹터 > 개별종목"""
    g = _keyword_hit_ratio(text, SCOPE_GLOBAL)
    s = _keyword_hit_ratio(text, SCOPE_SECTOR)
    i = _keyword_hit_ratio(text, SCOPE_SINGLE)
    return min(1.0, g * 0.5 + s * 0.35 + i * 0.15)


def _calculate_certainty(text: str) -> float:
    """확실성 (0~1): 확정 사실 vs 추측/전망"""
    high = _keyword_hit_ratio(text, CERTAINTY_HIGH)
    low = _keyword_hit_ratio(text, CERTAINTY_LOW)
    base = 0.5 + high * 0.4 - low * 0.3
    return max(0.1, min(1.0, base))


def _tier_multiplier(tier: str | None) -> float:
    """키워드 티어 가중치"""
    return {"STRONG": 1.3, "MEDIUM": 1.0, "WEAK": 0.7}.get(tier or "WEAK", 0.7)


def _composite_to_10(urgency: float, scope: float, certainty: float, tier_mult: float) -> float:
    """3차원 합성 → 1~10 정규분포 매핑

    공식: raw = (urgency×0.4 + scope×0.35 + certainty×0.25) × tier_mult
    매핑: sigmoid 스트레칭으로 중앙 밀집 방지
    """
    raw = (urgency * 0.4 + scope * 0.35 + certainty * 0.25) * tier_mult

    # Sigmoid 스트레칭: 0~1.3 → 1~10
    # 중앙(0.4~0.6)에서도 차이가 벌어지도록
    x = (raw - 0.35) * 6  # 센터 시프트 + 스케일
    sigmoid = 1 / (1 + math.exp(-x))
    score = 1.0 + sigmoid * 9.0

    return round(max(1.0, min(10.0, score)), 1)


def score_impact(items: list[NewsItem]) -> list[NewsItem]:
    """다차원 영향도 스코어링 + 임계값 필터링"""

    for item in items:
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}"

        item.urgency = round(_calculate_urgency(text), 3)
        item.scope = round(_calculate_scope(text), 3)
        item.certainty = round(_calculate_certainty(text), 3)

        tier_mult = _tier_multiplier(item.keyword_tier)
        item.impact_score = _composite_to_10(item.urgency, item.scope, item.certainty, tier_mult)

        item.score_breakdown = {
            "urgency": item.urgency,
            "scope": item.scope,
            "certainty": item.certainty,
            "tier_mult": tier_mult,
        }

    # 임계값 필터
    high = [i for i in items if i.impact_score >= cfg.IMPACT_THRESHOLD]
    low = len(items) - len(high)
    high.sort(key=lambda x: x.impact_score, reverse=True)

    # 분포 로깅
    if items:
        scores = [i.impact_score for i in items]
        avg = sum(scores) / len(scores)
        bins = {f"{b}-{b+1}": sum(1 for s in scores if b <= s < b+1) for b in range(1, 10)}
        logger.info(
            f"[스코어] {len(items)}건 → 고영향 {len(high)}건 / 저영향 {low}건 "
            f"(평균:{avg:.1f}, 분포:{bins})"
        )

    return high
