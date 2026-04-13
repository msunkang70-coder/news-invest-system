"""시장지표 데이터 모델 — NIAS v2.0"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IndicatorCategory(str, Enum):
    VOLATILITY = "변동성"
    FX = "환율"
    COMMODITY = "원자재"
    BOND = "채권"
    EQUITY_INDEX = "주가지수"
    NIGHT_FUTURES = "야간선물"
    SENTIMENT = "심리지표"
    MACRO = "매크로"


class ThresholdLevel(str, Enum):
    NORMAL = "정상"
    WATCH = "주의"
    WARNING = "경고"
    CRITICAL = "위험"
    EXTREME = "극단"

    @property
    def priority(self) -> int:
        return {"정상": 0, "주의": 1, "경고": 2, "위험": 3, "극단": 4}[self.value]


@dataclass
class MarketIndicator:
    ticker: str
    name: str
    category: IndicatorCategory
    current_value: float
    previous_close: float
    change_pct: float
    timestamp: datetime = field(default_factory=datetime.now)

    threshold_level: ThresholdLevel = ThresholdLevel.NORMAL
    threshold_breached: list[str] = field(default_factory=list)
    market_implication: str = ""
    affected_assets: list[str] = field(default_factory=list)

    @property
    def is_alert_worthy(self) -> bool:
        return self.threshold_level.priority >= ThresholdLevel.WARNING.priority

    @property
    def direction_emoji(self) -> str:
        if self.change_pct > 0.5:
            return "🟢"
        elif self.change_pct < -0.5:
            return "🔴"
        return "⚪"

    @property
    def level_emoji(self) -> str:
        return {
            "정상": "🟢", "주의": "🟡", "경고": "🟠", "위험": "🔴", "극단": "🚨",
        }[self.threshold_level.value]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "category": self.category.value,
            "current_value": self.current_value,
            "previous_close": self.previous_close,
            "change_pct": round(self.change_pct, 2),
            "threshold_level": self.threshold_level.value,
            "threshold_breached": self.threshold_breached,
            "market_implication": self.market_implication,
        }
