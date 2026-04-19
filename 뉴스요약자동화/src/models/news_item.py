"""뉴스 아이템 데이터 모델 — NIAS v2.0"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TimeSlot(str, Enum):
    PRE_MARKET = "프리마켓"
    MARKET_HOURS = "장중"
    AFTER_MARKET = "애프터마켓"
    GLOBAL = "글로벌"


class Direction(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"


class MarketDomain(str, Enum):
    EQUITY = "주식"
    BOND = "채권"
    FX = "환율"
    COMMODITY = "원자재"
    MACRO = "매크로"
    CRYPTO = "암호화폐"
    GEOPOLITICAL = "지정학"


@dataclass
class StockImpact:
    stock_name: str
    direction: Direction
    intensity: float
    reason: str = ""
    sector: str = ""

    def to_dict(self) -> dict:
        return {
            "stock": self.stock_name,
            "direction": self.direction.value,
            "intensity": round(self.intensity, 2),
            "reason": self.reason,
            "sector": self.sector,
        }


@dataclass
class NewsItem:
    # 수집
    title: str
    source: str
    url: str
    source_type: str = "RSS"  # RSS, DART, FRED, BOK, SNS, INDICATOR, GEOPOLITICAL
    published_time: Optional[datetime] = None
    full_text: Optional[str] = None
    snippet: Optional[str] = None
    region: str = "KR"

    # 1차 필터
    keyword_tier: Optional[str] = None
    matched_keywords: list[str] = field(default_factory=list)

    # 영향도
    impact_score: float = 0.0
    urgency: float = 0.0
    scope: float = 0.0
    certainty: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    # 방향성
    direction: Optional[Direction] = None
    confidence: float = 0.0

    # 시장 분류
    time_slot: Optional[TimeSlot] = None
    market_domains: list[MarketDomain] = field(default_factory=list)

    # 종목 영향
    stock_impacts: list[StockImpact] = field(default_factory=list)
    tagged_stocks: list[str] = field(default_factory=list)

    # LLM 분석
    summary_1line: str = ""
    summary_3line: str = ""
    investment_signal: str = ""
    risk_factor: str = ""
    action_suggestion: str = ""
    impact_chain: str = ""

    # 지정학 (v2.0)
    geo_level: Optional[int] = None
    geo_region: str = ""
    geo_conflict_type: str = ""

    # 이벤트 Fallback (단기안 — 키워드 사전 miss 시 엔티티×액션 매트릭스로 승격)
    event_fallback: bool = False
    event_category: Optional[str] = None        # ACTION_CATEGORIES 중 하나
    event_entity_class: Optional[str] = None    # ENTITY_CLASSES 중 하나

    # 메타
    collected_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        import hashlib
        self._hash = hashlib.md5(self.url.encode()).hexdigest()

    @property
    def text_for_analysis(self) -> str:
        return self.full_text or self.snippet or self.title

    @property
    def is_high_impact(self) -> bool:
        return self.impact_score >= 5.0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "source_type": self.source_type,
            "url": self.url,
            "region": self.region,
            "impact_score": self.impact_score,
            "direction": self.direction.value if self.direction else None,
            "confidence": self.confidence,
            "market_domains": [d.value for d in self.market_domains],
            "stock_impacts": [si.to_dict() for si in self.stock_impacts],
            "summary_1line": self.summary_1line,
            "investment_signal": self.investment_signal,
            "action_suggestion": self.action_suggestion,
            "impact_chain": self.impact_chain,
            "geo_level": self.geo_level,
            "geo_region": self.geo_region,
        }
