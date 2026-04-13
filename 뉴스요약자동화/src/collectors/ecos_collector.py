"""한국은행 ECOS API 수집기 — NIAS v2.0

60sec_econ_signal/core/ecos.py 아키텍처를 기반으로 이식.
환율(일별), CPI, 수출증가율, 기준금리, GDP 등 거시지표 자동 수집.

API 키: .env의 BOK_API_KEY 또는 환경변수 ECOS_API_KEY
무료 발급: https://ecos.bok.or.kr → 오픈 API → 인증키 신청
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

import requests

import config as cfg
from models.news_item import NewsItem
from models.market_indicator import MarketIndicator, IndicatorCategory, ThresholdLevel

logger = logging.getLogger(__name__)

ECOS_BASE = "https://ecos.bok.or.kr/api"
_TIMEOUT = 10
_MAX_RETRY = 2
_RETRY_WAIT = 2

# ─── ECOS 지표 정의 (60sec_econ_signal에서 검증된 코드) ───
ECOS_SPEC = {
    "환율(원/$)": {
        "stat_code": "731Y003", "item_code": "0000003",
        "period": "D", "yoy": False,
        "unit": "원/$", "category": IndicatorCategory.FX,
        "nias_ticker": "KRW/USD_ECOS",
        "thresholds": [(1400, "WARNING"), (1450, "CRITICAL")],
    },
    "소비자물가(CPI)": {
        "stat_code": "901Y009", "item_code": "0",
        "period": "M", "yoy": True,
        "unit": "%", "category": IndicatorCategory.MACRO,
        "nias_ticker": "KR_CPI",
        "thresholds": [(3.0, "WARNING"), (4.0, "CRITICAL")],
    },
    "수출증가율": {
        "stat_code": "403Y001", "item_code": "*AA",
        "period": "M", "yoy": True,
        "unit": "%", "category": IndicatorCategory.MACRO,
        "nias_ticker": "KR_EXPORT",
        "thresholds": [],  # 양방향 (음수도 의미)
    },
    "기준금리": {
        "stat_code": "722Y001", "item_code": "0101000",
        "period": "M", "yoy": False,
        "unit": "%", "category": IndicatorCategory.BOND,
        "nias_ticker": "KR_BASE_RATE",
        "thresholds": [],
    },
    "경상수지(억달러)": {
        "stat_code": "056Y001", "item_code": "10101",
        "period": "M", "yoy": False, "scale": 0.01,
        "unit": "억달러", "category": IndicatorCategory.MACRO,
        "nias_ticker": "KR_CA",
        "thresholds": [],
    },
}


def _get_api_key() -> Optional[str]:
    """BOK_API_KEY 또는 ECOS_API_KEY에서 키 조회"""
    import os
    for env_var in ("BOK_API_KEY", "ECOS_API_KEY"):
        key = os.environ.get(env_var, "").strip()
        if key and not key.startswith("your_"):
            return key
    return None


def _date_range(period: str, lookback: int = 30) -> tuple:
    today = datetime.today()
    if period == "D":
        start = today - timedelta(days=lookback)
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    if period == "Q":
        cur_q = (today.month - 1) // 3 + 1
        total_q = today.year * 4 + cur_q - lookback
        sy = (total_q - 1) // 4
        sq = (total_q - 1) % 4 + 1
        return f"{sy}Q{sq}", f"{today.year}Q{cur_q}"
    # Monthly
    n = lookback + 2
    total = today.year * 12 + (today.month - 1) - n
    sy, sm = divmod(total, 12)
    sm += 1
    return f"{sy}{sm:02d}", today.strftime("%Y%m")


def _fetch_rows(api_key: str, stat_code: str, item_code: str, period: str) -> list:
    """ECOS API 호출 (재시도 포함)"""
    start, end = _date_range(period)
    url = (
        f"{ECOS_BASE}/StatisticSearch"
        f"/{api_key}/json/kr/1/100"
        f"/{stat_code}/{period}/{start}/{end}/{item_code}"
    )

    for attempt in range(_MAX_RETRY + 1):
        try:
            resp = requests.get(url, timeout=_TIMEOUT,
                                headers={"User-Agent": "NIAS/2.0"})
            resp.raise_for_status()
            body = resp.json()
            break
        except Exception as e:
            if attempt < _MAX_RETRY:
                time.sleep(_RETRY_WAIT)
            else:
                logger.warning(f"[ECOS] 요청 실패 ({stat_code}): {e}")
                return []
    else:
        return []

    if "RESULT" in body:
        msg = body["RESULT"].get("MESSAGE", "")
        logger.warning(f"[ECOS] API 오류 ({stat_code}): {msg}")
        return []

    rows = body.get("StatisticSearch", {}).get("row", [])
    return [r for r in rows if r.get("DATA_VALUE") not in (None, "", "-")]


def _calc_yoy(rows: list) -> tuple:
    """전년동월 대비 YoY 계산"""
    rows_s = sorted(rows, key=lambda r: r["TIME"])
    if len(rows_s) < 14:
        return None, None
    try:
        def pct(a, b):
            fa, fb = float(a), float(b)
            return round((fa / fb - 1) * 100, 1) if fb != 0 else None
        cur = pct(rows_s[-2]["DATA_VALUE"], rows_s[-14]["DATA_VALUE"])
        prev = pct(rows_s[-3]["DATA_VALUE"], rows_s[-15]["DATA_VALUE"]) if len(rows_s) >= 15 else None
        return (str(cur) if cur is not None else None,
                str(prev) if prev is not None else None)
    except Exception:
        return None, None


def collect_ecos_indicators() -> List[MarketIndicator]:
    """ECOS API로 한국 거시지표 수집 → MarketIndicator 리스트"""
    api_key = _get_api_key()
    if not api_key:
        logger.debug("[ECOS] API 키 미설정 — 스킵")
        return []

    indicators = []
    for label, spec in ECOS_SPEC.items():
        try:
            rows = _fetch_rows(api_key, spec["stat_code"], spec["item_code"], spec["period"])
            if not rows:
                continue

            rows_s = sorted(rows, key=lambda r: r["TIME"])
            scale = spec.get("scale", 1.0)

            if spec["period"] == "D":
                # 일별 (환율)
                val = round(float(rows_s[-1]["DATA_VALUE"]) * scale, 1)
                prev = round(float(rows_s[-2]["DATA_VALUE"]) * scale, 1) if len(rows_s) >= 2 else val
                as_of = rows_s[-1]["TIME"]
            elif spec.get("yoy"):
                # YoY 계산
                yoy_val, yoy_prev = _calc_yoy(rows_s)
                if yoy_val is None:
                    continue
                val = float(yoy_val)
                prev = float(yoy_prev) if yoy_prev else val
                as_of = rows_s[-2]["TIME"]
            else:
                # 절댓값 (기준금리 등)
                val = round(float(rows_s[-1]["DATA_VALUE"]) * scale, 2)
                prev = round(float(rows_s[-2]["DATA_VALUE"]) * scale, 2) if len(rows_s) >= 2 else val
                as_of = rows_s[-1]["TIME"]

            change_pct = round((val - prev) / abs(prev) * 100, 2) if prev != 0 else 0

            ind = MarketIndicator(
                ticker=spec["nias_ticker"],
                name=label,
                category=spec["category"],
                current_value=val,
                previous_close=prev,
                change_pct=change_pct,
                timestamp=datetime.now(),
            )

            # 임계값 검사
            for threshold_val, level_str in spec.get("thresholds", []):
                if val >= threshold_val:
                    level = {"WARNING": ThresholdLevel.WARNING, "CRITICAL": ThresholdLevel.CRITICAL}.get(level_str, ThresholdLevel.WARNING)
                    if level.priority > ind.threshold_level.priority:
                        ind.threshold_level = level
                    ind.threshold_breached.append(f"{label} {val} >= {threshold_val}")

            indicators.append(ind)
            logger.info(f"[ECOS] {label}: {val} {spec['unit']} (전기 대비 {change_pct:+.1f}%)")

        except Exception as e:
            logger.warning(f"[ECOS] {label} 수집 실패: {e}")

    if indicators:
        logger.info(f"[ECOS] {len(indicators)}개 지표 수집 완료")

    return indicators


def collect_ecos_news() -> List[NewsItem]:
    """ECOS 지표 변동을 뉴스 형태로 변환 (경제지표 발표 알림용)"""
    indicators = collect_ecos_indicators()
    items = []

    for ind in indicators:
        if not ind.threshold_breached:
            continue

        direction = "상승" if ind.change_pct > 0 else "하락"
        item = NewsItem(
            title=f"[경제지표] {ind.name}: {ind.current_value}{'' if ind.category == IndicatorCategory.FX else '%'} ({direction})",
            source="한국은행 ECOS",
            source_type="BOK",
            url="https://ecos.bok.or.kr/",
            published_time=datetime.now(),
            snippet=f"{ind.name} {ind.current_value} (전기 대비 {ind.change_pct:+.1f}%). {', '.join(ind.threshold_breached)}",
            region="KR",
        )
        items.append(item)

    return items
