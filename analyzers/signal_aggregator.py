"""시그널 집계기 — 종목/섹터별 뉴스 시그널 합산 → 투자 판단

핵심: 개별 뉴스의 방향+강도를 종목/섹터 단위로 합산하여
최종 투자 점수(bull_score vs bear_score)와 행동 제안 생성
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from models.news_item import NewsItem, Direction, StockImpact

logger = logging.getLogger(__name__)


@dataclass
class StockSignal:
    """종목별 합산 시그널"""
    stock_name: str
    sector: str = ""
    bull_score: float = 0.0
    bear_score: float = 0.0
    news_count: int = 0
    top_reasons: list[str] = field(default_factory=list)

    @property
    def net_score(self) -> float:
        """순 점수: 양수=BULL, 음수=BEAR"""
        return round(self.bull_score - self.bear_score, 2)

    @property
    def direction(self) -> Direction:
        return Direction.BULL if self.net_score >= 0 else Direction.BEAR

    @property
    def strength(self) -> str:
        """시그널 강도"""
        abs_net = abs(self.net_score)
        if abs_net >= 3.0:
            return "강한"
        elif abs_net >= 1.5:
            return "보통"
        return "약한"

    @property
    def action(self) -> str:
        """행동 제안"""
        net = self.net_score
        if net >= 3.0:
            return "적극매수"
        elif net >= 1.5:
            return "분할매수"
        elif net >= 0.5:
            return "관심 유지"
        elif net >= -0.5:
            return "관망"
        elif net >= -1.5:
            return "리스크 주의"
        elif net >= -3.0:
            return "비중축소"
        return "매도 검토"


@dataclass
class SectorSignal:
    """섹터별 합산 시그널"""
    sector: str
    bull_score: float = 0.0
    bear_score: float = 0.0
    news_count: int = 0
    stocks: list[str] = field(default_factory=list)

    @property
    def net_score(self) -> float:
        return round(self.bull_score - self.bear_score, 2)

    @property
    def direction(self) -> Direction:
        return Direction.BULL if self.net_score >= 0 else Direction.BEAR

    @property
    def mood(self) -> str:
        net = self.net_score
        if net >= 2.0:
            return "강세"
        elif net >= 0.5:
            return "약세 회복"
        elif net >= -0.5:
            return "혼조"
        elif net >= -2.0:
            return "약세"
        return "급약세"


@dataclass
class MarketVerdict:
    """최종 시장 판단"""
    stock_signals: dict[str, StockSignal] = field(default_factory=dict)
    sector_signals: dict[str, SectorSignal] = field(default_factory=dict)
    total_bull: int = 0
    total_bear: int = 0
    overall_direction: Direction = Direction.BULL
    overall_confidence: float = 0.5
    market_mood: str = ""
    key_risks: list[str] = field(default_factory=list)
    key_opportunities: list[str] = field(default_factory=list)


def aggregate_signals(items: list[NewsItem]) -> MarketVerdict:
    """전체 뉴스 시그널 → 종목/섹터/시장 종합 판단"""
    verdict = MarketVerdict()

    # 1) 종목별 시그널 합산
    for item in items:
        for si in item.stock_impacts:
            name = si.stock_name
            if name not in verdict.stock_signals:
                verdict.stock_signals[name] = StockSignal(
                    stock_name=name, sector=si.sector
                )
            ss = verdict.stock_signals[name]

            weight = si.intensity * (item.impact_score / 10.0)
            if si.direction == Direction.BULL:
                ss.bull_score += weight
            else:
                ss.bear_score += weight
            ss.news_count += 1

            reason = f"[{si.direction.value}] {item.summary_1line[:30]} ({si.reason})"
            if len(ss.top_reasons) < 3:
                ss.top_reasons.append(reason)

    # 2) 섹터별 시그널 합산
    for name, ss in verdict.stock_signals.items():
        sector = ss.sector or "기타"
        if sector not in verdict.sector_signals:
            verdict.sector_signals[sector] = SectorSignal(sector=sector)
        sec = verdict.sector_signals[sector]
        sec.bull_score += ss.bull_score
        sec.bear_score += ss.bear_score
        sec.news_count += ss.news_count
        if name not in sec.stocks:
            sec.stocks.append(name)

    # 3) 전체 시장 방향
    verdict.total_bull = sum(1 for i in items if i.direction == Direction.BULL)
    verdict.total_bear = sum(1 for i in items if i.direction == Direction.BEAR)

    total = verdict.total_bull + verdict.total_bear
    if total > 0:
        bull_ratio = verdict.total_bull / total
        if bull_ratio > 0.5:
            verdict.overall_direction = Direction.BULL
            verdict.overall_confidence = round(0.5 + (bull_ratio - 0.5) * 1.0, 2)
        else:
            verdict.overall_direction = Direction.BEAR
            verdict.overall_confidence = round(0.5 + (0.5 - bull_ratio) * 1.0, 2)

    # 4) 시장 분위기
    if verdict.total_bull > verdict.total_bear * 2:
        verdict.market_mood = "📈 강세장"
    elif verdict.total_bull > verdict.total_bear * 1.3:
        verdict.market_mood = "📈 약세 회복"
    elif verdict.total_bear > verdict.total_bull * 2:
        verdict.market_mood = "📉 급락 경고"
    elif verdict.total_bear > verdict.total_bull * 1.3:
        verdict.market_mood = "📉 약세 전환"
    else:
        verdict.market_mood = "↔️ 혼조세"

    # 5) 핵심 리스크 / 기회
    for item in sorted(items, key=lambda x: x.impact_score, reverse=True)[:10]:
        if item.direction == Direction.BEAR and len(verdict.key_risks) < 5:
            verdict.key_risks.append(item.summary_1line or item.title[:40])
        elif item.direction == Direction.BULL and len(verdict.key_opportunities) < 5:
            verdict.key_opportunities.append(item.summary_1line or item.title[:40])

    logger.info(
        f"[시그널] 종목 {len(verdict.stock_signals)}개 / 섹터 {len(verdict.sector_signals)}개 | "
        f"BULL:{verdict.total_bull} BEAR:{verdict.total_bear} → {verdict.market_mood}"
    )

    return verdict
