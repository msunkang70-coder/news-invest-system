"""코스피200 야간선물 모니터링 — NIAS v2.0

KRX 자체운영 (2025.06~). 거래시간: 18:00 ~ 익일 06:00 (KST)
야간선물은 익일 코스피 방향의 강력한 선행 지표.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from models.market_indicator import MarketIndicator, IndicatorCategory, ThresholdLevel
import config as cfg

logger = logging.getLogger(__name__)


def is_night_session() -> bool:
    """현재 야간선물 거래시간인지 확인 (18:00~06:00 KST)"""
    hour = datetime.now().hour
    return hour >= 18 or hour < 6


def collect_night_futures() -> Optional[MarketIndicator]:
    """야간선물 데이터 수집

    방법 1 (권장): 한국투자증권 KIS Open API
    방법 2 (대안): yfinance 코스피200 선물 (거래시간 제한)
    방법 3 (최소): 야간선물 전문 사이트 스크래핑
    """
    if not is_night_session():
        logger.debug("[야간선물] 거래시간 아님 — 스킵")
        return None

    # KIS Open API 사용 시
    if cfg.KIS_APP_KEY and cfg.KIS_APP_SECRET:
        return _collect_via_kis_api()

    # fallback: yfinance로 최근 종가 기반 추정
    return _collect_via_yfinance_fallback()


def _collect_via_kis_api() -> Optional[MarketIndicator]:
    """한국투자증권 Open API를 통한 야간선물 수집"""
    try:
        # TODO: 실제 KIS API 연동 구현
        # from mojito2 import KoreaInvestment
        # broker = KoreaInvestment(cfg.KIS_APP_KEY, cfg.KIS_APP_SECRET)
        # quote = broker.fetch_futures_price("KOSPI200_NIGHT")

        logger.info("[야간선물] KIS API 연동 대기중 (구현 필요)")
        return None

    except Exception as e:
        logger.warning(f"[야간선물] KIS API 실패: {e}")
        return None


def _collect_via_yfinance_fallback() -> Optional[MarketIndicator]:
    """yfinance로 KOSPI200 선물 최근 데이터 fallback"""
    try:
        import yfinance as yf

        ticker = yf.Ticker("^KS200")  # KOSPI 200 Index
        hist = ticker.history(period="2d")

        if hist.empty:
            return None

        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        change_pct = ((current - prev) / prev * 100) if prev != 0 else 0.0

        indicator = MarketIndicator(
            ticker="KOSPI200N",
            name="코스피200 야간선물 (추정)",
            category=IndicatorCategory.NIGHT_FUTURES,
            current_value=round(current, 2),
            previous_close=round(prev, 2),
            change_pct=round(change_pct, 2),
        )

        # 임계값 검사
        if abs(change_pct) >= 2.0:
            indicator.threshold_level = ThresholdLevel.CRITICAL
            direction = "급락" if change_pct < 0 else "급등"
            indicator.threshold_breached.append(
                f"야간선물 {change_pct:+.1f}% {direction} — 익일 코스피 {direction} 가능성"
            )
            indicator.market_implication = f"익일 코스피 갭{'다운' if change_pct < 0 else '업'} 예상"
        elif abs(change_pct) >= 1.5:
            indicator.threshold_level = ThresholdLevel.WARNING
            indicator.threshold_breached.append(f"야간선물 {change_pct:+.1f}% 변동")

        return indicator

    except Exception as e:
        logger.warning(f"[야간선물] yfinance fallback 실패: {e}")
        return None
