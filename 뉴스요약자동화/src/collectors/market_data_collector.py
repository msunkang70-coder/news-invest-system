"""시장지표 수집기 — yfinance + FinanceDataReader

글로벌: VIX, DXY, WTI, Brent, Gold, US10Y, S&P500
국내: 코스피, 원달러 환율, VKOSPI
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from models.market_indicator import MarketIndicator, IndicatorCategory, ThresholdLevel
import config as cfg

logger = logging.getLogger(__name__)

YFINANCE_TICKERS = {
    "^VIX":     {"name": "VIX 공포지수",      "category": IndicatorCategory.VOLATILITY},
    "DX-Y.NYB": {"name": "달러인덱스 (DXY)",  "category": IndicatorCategory.FX},
    "CL=F":     {"name": "WTI 원유",          "category": IndicatorCategory.COMMODITY},
    "BZ=F":     {"name": "브렌트유",           "category": IndicatorCategory.COMMODITY},
    "GC=F":     {"name": "금 선물",            "category": IndicatorCategory.COMMODITY},
    "^TNX":     {"name": "미국 10년물 금리",   "category": IndicatorCategory.BOND},
    "^GSPC":    {"name": "S&P 500",           "category": IndicatorCategory.EQUITY_INDEX},
}


def _check_thresholds(indicator: MarketIndicator) -> None:
    """임계값 검사 (절대값 + 변동률)"""
    thresholds = cfg.INDICATOR_THRESHOLDS.get(indicator.ticker, {})
    if not thresholds:
        thresholds = cfg.INDICATOR_THRESHOLDS_KR.get(indicator.ticker, {})
    if not thresholds:
        return

    # 절대값 임계값
    for threshold_value, level_str, message in thresholds.get("absolute", []):
        if indicator.current_value >= threshold_value:
            level = ThresholdLevel({"WARNING": "경고", "CRITICAL": "위험", "EXTREME": "극단"}.get(level_str, "경고"))
            if level.priority > indicator.threshold_level.priority:
                indicator.threshold_level = level
            indicator.threshold_breached.append(
                f"{indicator.name} {indicator.current_value:.2f} >= {threshold_value}: {message}"
            )

    # 변동률 임계값
    change_threshold = thresholds.get("change_pct")
    if change_threshold and abs(indicator.change_pct) >= change_threshold:
        level = ThresholdLevel.WARNING
        if level.priority > indicator.threshold_level.priority:
            indicator.threshold_level = level
        direction = "급등" if indicator.change_pct > 0 else "급락"
        indicator.threshold_breached.append(
            f"{indicator.name} {indicator.change_pct:+.1f}% {direction}"
        )


def collect_global_indicators() -> List[MarketIndicator]:
    """yfinance로 글로벌 시장지표 수집"""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance 미설치. pip install yfinance")
        return []

    indicators = []
    for ticker_symbol, meta in YFINANCE_TICKERS.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="2d")

            if hist.empty:
                continue

            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
            change_pct = ((current - prev) / prev * 100) if prev != 0 else 0.0

            indicator = MarketIndicator(
                ticker=ticker_symbol,
                name=meta["name"],
                category=meta["category"],
                current_value=round(current, 2),
                previous_close=round(prev, 2),
                change_pct=round(change_pct, 2),
                timestamp=datetime.now(),
            )
            _check_thresholds(indicator)
            indicators.append(indicator)

        except Exception as e:
            logger.warning(f"[지표] {ticker_symbol} 수집 실패: {e}")

    logger.info(f"[지표] 글로벌 {len(indicators)}개 수집 완료")
    return indicators


def collect_kr_indicators() -> List[MarketIndicator]:
    """FinanceDataReader로 국내 시장지표 수집"""
    try:
        import FinanceDataReader as fdr
    except ImportError:
        logger.error("FinanceDataReader 미설치. pip install finance-datareader")
        return []

    indicators = []

    # 원달러 환율
    try:
        df = fdr.DataReader("USD/KRW")
        if not df.empty:
            current = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else current
            change_pct = ((current - prev) / prev * 100) if prev != 0 else 0.0

            ind = MarketIndicator(
                ticker="KRW/USD",
                name="원달러 환율",
                category=IndicatorCategory.FX,
                current_value=round(current, 2),
                previous_close=round(prev, 2),
                change_pct=round(change_pct, 2),
            )
            _check_thresholds(ind)
            indicators.append(ind)
    except Exception as e:
        logger.warning(f"[지표] 원달러 수집 실패: {e}")

    logger.info(f"[지표] 국내 {len(indicators)}개 수집 완료")
    return indicators
