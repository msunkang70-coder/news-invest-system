"""심리지표 수집기 — NIAS v2.0

Crypto Fear & Greed Index (Alternative.me API)
CNN Fear & Greed Index (웹 스크래핑 또는 대안)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import requests

import config as cfg
from models.market_indicator import MarketIndicator, IndicatorCategory, ThresholdLevel

logger = logging.getLogger(__name__)


def collect_crypto_fear_greed() -> MarketIndicator | None:
    """Crypto Fear & Greed Index (Alternative.me API)

    0 = Extreme Fear, 100 = Extreme Greed
    """
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=2",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            return None

        current = int(data[0]["value"])
        previous = int(data[1]["value"]) if len(data) >= 2 else current
        change = current - previous
        classification = data[0].get("value_classification", "")

        indicator = MarketIndicator(
            ticker="CRYPTO_FG",
            name=f"Crypto F&G ({classification})",
            category=IndicatorCategory.SENTIMENT,
            current_value=float(current),
            previous_close=float(previous),
            change_pct=float(change),  # 절대값 변화 (% 아님)
            timestamp=datetime.now(),
        )

        # 임계값 검사
        thresholds = cfg.SENTIMENT_THRESHOLDS.get("crypto_fear_greed", {})
        if current <= thresholds.get("low_critical", 10):
            indicator.threshold_level = ThresholdLevel.CRITICAL
            indicator.threshold_breached.append(f"Crypto F&G {current} — 극도 공포")
            indicator.market_implication = "암호화폐 시장 극도 공포 — 역발상 매수 기회 가능"
        elif current <= thresholds.get("low_warning", 15):
            indicator.threshold_level = ThresholdLevel.WARNING
            indicator.threshold_breached.append(f"Crypto F&G {current} — 공포")
        elif current >= thresholds.get("high_critical", 90):
            indicator.threshold_level = ThresholdLevel.CRITICAL
            indicator.threshold_breached.append(f"Crypto F&G {current} — 극도 탐욕")
            indicator.market_implication = "암호화폐 시장 극도 탐욕 — 조정 리스크"
        elif current >= thresholds.get("high_warning", 85):
            indicator.threshold_level = ThresholdLevel.WARNING
            indicator.threshold_breached.append(f"Crypto F&G {current} — 탐욕")

        logger.info(f"[심리] Crypto F&G: {current} ({classification})")
        return indicator

    except Exception as e:
        logger.warning(f"[심리] Crypto F&G 수집 실패: {e}")
        return None


def collect_sentiment_indicators() -> List[MarketIndicator]:
    """모든 심리지표 수집"""
    indicators = []

    crypto = collect_crypto_fear_greed()
    if crypto:
        indicators.append(crypto)

    # CNN Fear & Greed — 별도 API/스크래핑 필요 (향후 추가)
    # cnn = collect_cnn_fear_greed()
    # if cnn: indicators.append(cnn)

    return indicators
