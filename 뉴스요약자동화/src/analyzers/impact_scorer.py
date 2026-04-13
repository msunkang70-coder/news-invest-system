"""영향도 점수 — 다차원 스코어링 (긴급도 x 파급범위 x 확실성)

기존 뉴스정보/filters/impact_scorer.py에서 이식 + 지정학 승수 확장
"""
from __future__ import annotations

import logging
import math
from typing import List

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

# ─── 긴급도 키워드 ───
URGENCY_HIGH = [
    "속보", "긴급", "breaking", "just in", "flash",
    "서킷브레이커", "circuit breaker", "폭락", "급등", "급락",
    "전쟁", "war", "제재", "sanctions", "봉쇄",
    "crash", "surge", "plunge", "halt",
    "금리인상", "금리인하", "rate hike", "rate cut",
    "FOMC", "연준", "Fed",
    "ICBM", "미사일 발사", "핵실험", "교전", "공습",
]
URGENCY_MID = [
    "발표", "announce", "결정", "확정", "승인",
    "실적", "earnings", "guidance", "가이던스",
    "CPI", "PPI", "고용", "nonfarm", "GDP",
    "관세", "tariff", "수출", "수입",
    "VIX", "공포지수", "야간선물",
]

# ─── 파급범위 키워드 ───
SCOPE_GLOBAL = [
    "글로벌", "global", "세계", "world", "미국", "중국", "유럽",
    "연준", "Fed", "ECB", "BOJ", "FOMC",
    "유가", "oil", "crude", "달러", "dollar", "환율",
    "전쟁", "war", "무역전쟁", "trade war",
    "인플레이션", "inflation", "경기침체", "recession",
    "대만", "Taiwan", "NATO", "나토",
]
SCOPE_SECTOR = [
    "반도체", "semiconductor", "AI", "자동차", "EV",
    "배터리", "battery", "바이��", "제약",
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
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(1.0, hits / max(3, len(keywords) * 0.15))


def _calculate_urgency(text: str) -> float:
    high = _keyword_hit_ratio(text, URGENCY_HIGH)
    mid = _keyword_hit_ratio(text, URGENCY_MID)
    return min(1.0, high * 0.7 + mid * 0.3)


def _calculate_scope(text: str) -> float:
    g = _keyword_hit_ratio(text, SCOPE_GLOBAL)
    s = _keyword_hit_ratio(text, SCOPE_SECTOR)
    i = _keyword_hit_ratio(text, SCOPE_SINGLE)
    return min(1.0, g * 0.5 + s * 0.35 + i * 0.15)


def _calculate_certainty(text: str) -> float:
    high = _keyword_hit_ratio(text, CERTAINTY_HIGH)
    low = _keyword_hit_ratio(text, CERTAINTY_LOW)
    base = 0.5 + high * 0.4 - low * 0.3
    return max(0.1, min(1.0, base))


def _tier_multiplier(tier: str | None) -> float:
    return {"STRONG": 1.3, "MEDIUM": 1.0, "WEAK": 0.7}.get(tier or "WEAK", 0.7)


def _composite_to_10(urgency: float, scope: float, certainty: float, tier_mult: float) -> float:
    raw = (urgency * 0.4 + scope * 0.35 + certainty * 0.25) * tier_mult
    x = (raw - 0.35) * 6
    sigmoid = 1 / (1 + math.exp(-x))
    score = 1.0 + sigmoid * 9.0
    return round(max(1.0, min(10.0, score)), 1)


def score_impact(items: List[NewsItem]) -> List[NewsItem]:
    """다차원 영향도 스코어링 + 지정학 승수 + 임계값 필터링"""
    for item in items:
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}"

        item.urgency = round(_calculate_urgency(text), 3)
        item.scope = round(_calculate_scope(text), 3)
        item.certainty = round(_calculate_certainty(text), 3)

        tier_mult = _tier_multiplier(item.keyword_tier)
        base_score = _composite_to_10(item.urgency, item.scope, item.certainty, tier_mult)

        # 지정학 승수 적용 (v2.0)
        geo_mult = {1: 1.0, 2: 1.2, 3: 1.5, 4: 2.0, 5: 3.0}.get(item.geo_level or 0, 1.0)

        # 소스 신뢰도 가중치 (Tier 1=1.0, Tier 2=0.9, Tier 3=0.7)
        source_name = (item.source or "").lower()
        if any(s in source_name for s in ["reuters", "bloomberg", "연합뉴스", "한국경제", "매일경제"]):
            source_mult = 1.0   # Tier 1: 주요 통신사/경제지
        elif any(s in source_name for s in ["cnbc", "wsj", "ft via", "조선", "sbs", "gn-kr"]):
            source_mult = 0.95  # Tier 2: 방송/일간지/Google News 국내
        elif any(s in source_name for s in ["gn -", "investing", "google", "sns"]):
            source_mult = 0.85  # Tier 3: Google News 영문/SNS
        elif any(s in source_name for s in ["war on", "diplomat", "38 north", "defense"]):
            source_mult = 0.7   # Tier 4: 분석 블로그/싱크탱크
        else:
            source_mult = 0.9

        item.impact_score = round(min(10.0, base_score * geo_mult * source_mult), 1)

        item.score_breakdown = {
            "urgency": item.urgency,
            "scope": item.scope,
            "certainty": item.certainty,
            "tier_mult": tier_mult,
            "geo_mult": geo_mult,
            "source_mult": source_mult,
        }

    # 임계값 필터
    high = [i for i in items if i.impact_score >= cfg.IMPACT_THRESHOLD]
    low = len(items) - len(high)
    high.sort(key=lambda x: x.impact_score, reverse=True)

    if items:
        scores = [i.impact_score for i in items]
        avg = sum(scores) / len(scores)
        logger.info(
            f"[스코어] {len(items)}건 → 고영향 {len(high)}건 / 저영향 {low}건 (평균:{avg:.1f})"
        )

    return high
