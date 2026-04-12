"""경제지표 수집기 — FRED + 한국은행 ECOS

주요 경제지표의 최근 발표값을 수집하여 변동 감지 시 NewsItem으로 변환.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import requests

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

# FRED 모니터링 대상
FRED_SERIES = {
    "FEDFUNDS": "미국 기준금리",
    "CPIAUCSL": "미국 소비자물가지수 (CPI)",
    "UNRATE":   "미국 실업률",
    "GDP":      "미국 GDP",
    "T10Y2Y":   "미국 장단기 금리차 (10Y-2Y)",
}

# 한국은행 ECOS 모니터링 대상
BOK_SERIES = {
    "722Y001/0101000": {"name": "한국 기준금리", "cycle": "M"},
    "901Y009/0":       {"name": "한국 소비자물가지수", "cycle": "M"},
}


def collect_fred_indicators() -> List[NewsItem]:
    """FRED 경제지표 최신 발표 수집"""
    if not cfg.FRED_API_KEY or cfg.FRED_API_KEY.startswith("your_"):
        logger.debug("[FRED] API 키 미설정 — 스킵")
        return []

    items = []
    for series_id, name in FRED_SERIES.items():
        try:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": cfg.FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            observations = data.get("observations", [])
            if len(observations) < 2:
                continue

            latest = observations[0]
            previous = observations[1]

            latest_val = _safe_float(latest.get("value"))
            prev_val = _safe_float(previous.get("value"))

            if latest_val is None or prev_val is None:
                continue

            change = latest_val - prev_val
            change_pct = (change / prev_val * 100) if prev_val != 0 else 0

            # 변동이 있을 때만 뉴스 생성
            if abs(change_pct) < 0.01 and latest["date"] == previous["date"]:
                continue

            direction = "상승" if change > 0 else "하락"
            item = NewsItem(
                title=f"[경제지표] {name}: {latest_val} ({direction} {abs(change):+.2f})",
                source="FRED",
                source_type="FRED",
                url=f"https://fred.stlouisfed.org/series/{series_id}",
                published_time=_parse_fred_date(latest.get("date")),
                snippet=f"{name} 최신: {latest_val} (이전: {prev_val}, 변동: {change:+.2f})",
                region="GLOBAL",
            )
            items.append(item)

        except Exception as e:
            logger.warning(f"[FRED] {series_id} 수집 실패: {e}")

    if items:
        logger.info(f"[FRED] {len(items)}건 경제지표 수집")
    return items


def collect_bok_indicators() -> List[NewsItem]:
    """한국은행 ECOS 경제지표 수집"""
    if not cfg.BOK_API_KEY or cfg.BOK_API_KEY.startswith("your_"):
        logger.debug("[한은] API 키 미설정 — 스킵")
        return []

    items = []
    for stat_code, meta in BOK_SERIES.items():
        try:
            # ECOS API v2
            parts = stat_code.split("/")
            table_code = parts[0]
            item_code = parts[1] if len(parts) > 1 else ""

            now = datetime.now()
            # 최근 6개월 데이터 조회
            start_date = f"{now.year - 1}{now.month:02d}"
            end_date = f"{now.year}{now.month:02d}"

            url = (
                f"https://ecos.bok.or.kr/api/StatisticSearch/"
                f"{cfg.BOK_API_KEY}/json/kr/1/2/{table_code}/{meta['cycle']}/"
                f"{start_date}/{end_date}/{item_code}"
            )

            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            rows = data.get("StatisticSearch", {}).get("row", [])
            if len(rows) < 2:
                continue

            latest = rows[-1]
            previous = rows[-2]

            latest_val = _safe_float(latest.get("DATA_VALUE"))
            prev_val = _safe_float(previous.get("DATA_VALUE"))

            if latest_val is None or prev_val is None:
                continue

            change = latest_val - prev_val
            direction = "상승" if change > 0 else "하락"

            item = NewsItem(
                title=f"[경제지표] {meta['name']}: {latest_val} ({direction})",
                source="한국은행",
                source_type="BOK",
                url="https://ecos.bok.or.kr/",
                published_time=datetime.now(),
                snippet=f"{meta['name']} 최신: {latest_val} (이전: {prev_val})",
                region="KR",
            )
            items.append(item)

        except Exception as e:
            logger.warning(f"[한은] {stat_code} 수집 실패: {e}")

    if items:
        logger.info(f"[한은] {len(items)}건 경제지표 수집")
    return items


def _safe_float(value) -> float | None:
    """안전한 float 변환"""
    if value is None or value == ".":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_fred_date(date_str: str) -> datetime | None:
    """FRED 날짜 파싱 (YYYY-MM-DD)"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None
