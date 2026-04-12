"""DART 전자공시 수집기 — NIAS v2.0

금융감독원 전자공시시스템(DART)에서 주요 종목의 공시를 수집하여 NewsItem으로 변환.
라이브러리: OpenDartReader (https://github.com/FinanceData/OpenDartReader)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

# 주요 공시 유형 필터 (report_nm에 포함되면 수집)
IMPORTANT_REPORT_TYPES = [
    "사업보고서", "분기보고서", "반기보고서",
    "주요사항보고서", "공개매수",
    "유상증자", "무상증자", "전환사채", "신주인수권부사채",
    "합병", "분할", "영업양수도",
    "자기주식", "주식매수선택권",
    "최대주주변경", "임원ㆍ주요주주",
    "소송", "조회공시",
]


def collect_dart_disclosures(date: str = None) -> List[NewsItem]:
    """DART 전자공시 수집

    Args:
        date: 수집일 (YYYY-MM-DD). None이면 오늘.

    Returns:
        공시를 변환한 NewsItem 리스트
    """
    if not cfg.DART_API_KEY or cfg.DART_API_KEY.startswith("your_"):
        logger.debug("[DART] API 키 미설정 — 스킵")
        return []

    try:
        import opendartreader as odr

        dart = odr.OpenDartReader(cfg.DART_API_KEY)

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        # 당일 전체 공시 목록 조회
        disclosures = dart.list(start=date, end=date)

        if disclosures is None or disclosures.empty:
            logger.info(f"[DART] {date} 공시 없음")
            return []

        items = []
        for _, row in disclosures.iterrows():
            # 관심 종목 필터
            corp_name = str(row.get("corp_name", ""))
            is_watched = any(
                corp_name in keywords
                for keywords in cfg.STOCK_TAGS.values()
            )

            # 주요 공시 유형 필터
            report_nm = str(row.get("report_nm", ""))
            is_important = any(rt in report_nm for rt in IMPORTANT_REPORT_TYPES)

            if not (is_watched or is_important):
                continue

            rcept_no = str(row.get("rcept_no", ""))
            item = NewsItem(
                title=f"[공시] {corp_name}: {report_nm}",
                source="DART",
                source_type="DART",
                url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                published_time=_parse_date(row.get("rcept_dt")),
                snippet=f"{corp_name} {report_nm}",
                region="KR",
            )
            items.append(item)

        logger.info(f"[DART] {date}: {len(disclosures)}건 중 {len(items)}건 관심 공시")
        return items

    except Exception as e:
        logger.warning(f"[DART] 수집 실패: {e}")
        return []


def _parse_date(date_str) -> datetime | None:
    """DART 날짜 문자열 파싱 (YYYYMMDD)"""
    if not date_str:
        return None
    try:
        s = str(date_str).strip()
        if len(s) == 8:
            return datetime.strptime(s, "%Y%m%d")
        elif "-" in s:
            return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        pass
    return None
