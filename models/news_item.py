"""뉴스 아이템 데이터 모델 — 투자 의사결정 시스템 v2"""
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

    @property
    def emoji(self) -> str:
        return {"프리마켓": "🌅", "장중": "🕘", "애프터마켓": "🌆", "글로벌": "🌙"}[self.value]


class Direction(str, Enum):
    """시장 방향 — NEUTRAL 없음. 반드시 한쪽으로 기울어야 한다."""
    BULL = "BULL"
    BEAR = "BEAR"

    @property
    def emoji(self) -> str:
        return "🟢" if self == Direction.BULL else "🔴"

    @property
    def label_kr(self) -> str:
        return "상승" if self == Direction.BULL else "하락"


class MarketDomain(str, Enum):
    """뉴스가 영향을 미치는 시장 영역"""
    EQUITY = "주식"
    BOND = "채권"
    FX = "환율"
    COMMODITY = "원자재"
    MACRO = "매크로"
    CRYPTO = "암호화폐"

    @property
    def emoji(self) -> str:
        return {
            "주식": "📈", "채권": "📉", "환율": "💱",
            "원자재": "🛢️", "매크로": "🏛️", "암호화폐": "₿",
        }[self.value]


@dataclass
class StockImpact:
    """개별 종목에 대한 영향 분석"""
    stock_name: str
    direction: Direction           # BULL / BEAR
    intensity: float               # 0.0 ~ 1.0 (영향 강도)
    reason: str = ""               # "HBM 수요 증가 수혜"
    sector: str = ""               # "반도체"

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
    """뉴스 아이템 — 투자 의사결정 파이프라인 전용"""

    # ─── 수집 ───
    title: str
    source: str
    url: str
    published_time: Optional[datetime] = None
    published_time_kst: Optional[datetime] = None
    full_text: Optional[str] = None
    snippet: Optional[str] = None
    region: str = "KR"

    # ─── 1차 필터 ───
    keyword_tier: Optional[str] = None
    matched_keywords: list[str] = field(default_factory=list)

    # ─── 영향도 (v2: 다차원) ───
    impact_score: float = 0.0          # 최종 1~10
    urgency: float = 0.0               # 긴급도 (0~1)
    scope: float = 0.0                 # 파급 범위 (0~1)
    certainty: float = 0.0             # 확실성 (0~1)
    score_breakdown: dict = field(default_factory=dict)

    # ─── 방향성 (v2: NEUTRAL 없음) ───
    direction: Optional[Direction] = None
    confidence: float = 0.0            # 방향 확신도 (0.5~1.0)

    # ─── 시장 분류 ───
    time_slot: Optional[TimeSlot] = None
    market_domains: list[MarketDomain] = field(default_factory=list)  # 복수 가능

    # ─── 종목 영향 매핑 ───
    stock_impacts: list[StockImpact] = field(default_factory=list)
    tagged_stocks: list[str] = field(default_factory=list)

    # ─── LLM 분석 ───
    summary_1line: str = ""
    summary_3line: str = ""
    investment_signal: str = ""        # "반도체 섹터 매수 신호" 형태
    risk_factor: str = ""              # 리스크 요인
    action_suggestion: str = ""        # "관망" / "분할매수" / "비중축소" 등

    # ─── 메타 ───
    collected_at: datetime = field(default_factory=datetime.utcnow)
    _hash: str = ""

    def __post_init__(self):
        import hashlib
        self._hash = hashlib.md5(self.url.encode()).hexdigest()

    @property
    def text_for_analysis(self) -> str:
        return self.full_text or self.snippet or self.title

    @property
    def is_high_impact(self) -> bool:
        return self.impact_score >= 5.0

    @property
    def primary_domain(self) -> Optional[MarketDomain]:
        return self.market_domains[0] if self.market_domains else None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_time_kst": self.published_time_kst.isoformat() if self.published_time_kst else None,
            "region": self.region,
            "impact_score": self.impact_score,
            "urgency": self.urgency,
            "scope": self.scope,
            "certainty": self.certainty,
            "direction": self.direction.value if self.direction else None,
            "confidence": self.confidence,
            "market_domains": [d.value for d in self.market_domains],
            "stock_impacts": [si.to_dict() for si in self.stock_impacts],
            "summary_1line": self.summary_1line,
            "investment_signal": self.investment_signal,
            "action_suggestion": self.action_suggestion,
        }
