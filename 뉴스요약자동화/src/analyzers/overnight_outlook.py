"""야간선물 + 글로벌 지표 → 익일 코스피 전망 — NIAS v2.0

야간선물 세션(18:00~06:00) 데이터와 글로벌 지표를 종합하여
익일 코스피 방향을 예측.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from models.news_item import NewsItem, Direction
from models.market_indicator import MarketIndicator

logger = logging.getLogger(__name__)


def generate_overnight_outlook(
    night_futures: Optional[MarketIndicator],
    global_indicators: List[MarketIndicator],
    overnight_news: List[NewsItem] = None,
) -> dict:
    """익일 코스피 전망 생성

    Returns:
        dict: outlook, signals, summary, factors
    """
    factors = []
    bull_signals = 0
    bear_signals = 0

    # 1) 야간선물 신호
    if night_futures:
        chg = night_futures.change_pct
        if chg > 0.5:
            bull_signals += 2
            factors.append(f"야간선물 {chg:+.1f}% 상승")
        elif chg < -0.5:
            bear_signals += 2
            factors.append(f"야간선물 {chg:+.1f}% 하락")
        else:
            factors.append(f"야간선물 {chg:+.1f}% 보합")

    # 2) S&P 500
    sp500 = next((i for i in global_indicators if i.ticker == "^GSPC"), None)
    if sp500:
        if sp500.change_pct > 0.5:
            bull_signals += 1
            factors.append(f"S&P500 {sp500.change_pct:+.1f}% 상승")
        elif sp500.change_pct < -0.5:
            bear_signals += 1
            factors.append(f"S&P500 {sp500.change_pct:+.1f}% 하락")

    # 3) VIX
    vix = next((i for i in global_indicators if i.ticker == "^VIX"), None)
    if vix:
        if vix.current_value >= 30:
            bear_signals += 2
            factors.append(f"VIX {vix.current_value:.1f} 공포 구간")
        elif vix.current_value >= 25:
            bear_signals += 1
            factors.append(f"VIX {vix.current_value:.1f} 불안")
        elif vix.current_value < 18:
            bull_signals += 1
            factors.append(f"VIX {vix.current_value:.1f} 안정")

    # 4) 원달러 (DXY 대용)
    dxy = next((i for i in global_indicators if i.ticker == "DX-Y.NYB"), None)
    if dxy:
        if dxy.change_pct > 0.5:
            bear_signals += 1  # 달러 강세 → 코스피 약세
            factors.append(f"DXY {dxy.change_pct:+.1f}% 달러 강세")
        elif dxy.change_pct < -0.5:
            bull_signals += 1
            factors.append(f"DXY {dxy.change_pct:+.1f}% 달러 약세")

    # 5) 야간 뉴스 심리
    if overnight_news:
        news_bull = sum(1 for n in overnight_news if n.direction == Direction.BULL)
        news_bear = sum(1 for n in overnight_news if n.direction == Direction.BEAR)
        if news_bull > news_bear * 1.5:
            bull_signals += 1
            factors.append(f"야간 뉴스 강세 (BULL {news_bull} vs BEAR {news_bear})")
        elif news_bear > news_bull * 1.5:
            bear_signals += 1
            factors.append(f"야간 뉴스 약세 (BULL {news_bull} vs BEAR {news_bear})")

    # 종합 판단
    if bull_signals > bear_signals + 1:
        outlook = "강세"
        outlook_detail = "익일 코스피 상승 전망"
    elif bear_signals > bull_signals + 1:
        outlook = "약세"
        outlook_detail = "익일 코스피 하락 전망"
    elif bull_signals > bear_signals:
        outlook = "약한 강세"
        outlook_detail = "익일 코스피 소폭 상승 전망"
    elif bear_signals > bull_signals:
        outlook = "약한 약세"
        outlook_detail = "익일 코스피 소폭 하락 전망"
    else:
        outlook = "보합"
        outlook_detail = "익일 코스피 보합 전망"

    result = {
        "outlook": outlook,
        "outlook_detail": outlook_detail,
        "bull_signals": bull_signals,
        "bear_signals": bear_signals,
        "factors": factors,
        "night_futures_change": f"{night_futures.change_pct:+.2f}%" if night_futures else "N/A",
        "sp500_change": f"{sp500.change_pct:+.2f}%" if sp500 else "N/A",
        "vix_level": f"{vix.current_value:.1f}" if vix else "N/A",
        "generated_at": datetime.now().isoformat(),
        "summary": f"{outlook_detail} | 근거: {', '.join(factors[:3])}",
    }

    logger.info(f"[전망] {result['summary']}")
    return result
