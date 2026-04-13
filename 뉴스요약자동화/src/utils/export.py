"""CSV 내보내기 — NIAS v2.0

DB 데이터를 CSV로 내보내어 Excel/구글시트에서 분석 가능.
Usage:
    python -c "from utils.export import export_all; export_all()"
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

import config as cfg
from utils.db import get_connection

logger = logging.getLogger(__name__)


def export_news_csv(days: int = 30, output_dir: Path = None) -> Path:
    """뉴스 히스토리 CSV 내보내기"""
    out = output_dir or cfg.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"news_export_{datetime.now().strftime('%Y%m%d')}.csv"

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT * FROM news_items
        WHERE collected_time >= datetime('now', '-{days} days', 'localtime')
        ORDER BY impact_score DESC
    """).fetchall()
    conn.close()

    if not rows:
        logger.info("[CSV] 내보낼 뉴스 없음")
        return path

    headers = [
        "제목", "출처", "유형", "영향도", "방향", "확신도",
        "행동제안", "투자시그널", "리스크",
        "관련종목", "키워드", "지정학L", "지역", "영향체인",
        "발행시각", "수집시각", "URL",
    ]

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            stocks = r["tagged_stocks"] or "[]"
            if isinstance(stocks, str):
                try:
                    stocks = ", ".join(json.loads(stocks))
                except Exception:
                    pass
            keywords = r["matched_keywords"] or "[]"
            if isinstance(keywords, str):
                try:
                    keywords = ", ".join(json.loads(keywords))
                except Exception:
                    pass

            writer.writerow([
                r["title"],
                r["source"],
                r["source_type"],
                r["impact_score"],
                r["direction"] or "",
                r["confidence"],
                r["action_suggestion"] or "",
                r["investment_signal"] or "",
                r["risk_factor"] or "",
                stocks,
                keywords,
                r["geo_level"] or "",
                r["geo_region"] or "",
                r["impact_chain"] or "",
                r["published_time"] or "",
                r["collected_time"] or "",
                r["url"],
            ])

    logger.info(f"[CSV] 뉴스 {len(rows)}건 → {path.name}")
    return path


def export_indicators_csv(days: int = 30, output_dir: Path = None) -> Path:
    """시장지표 히스토리 CSV 내보내기"""
    out = output_dir or cfg.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"indicators_export_{datetime.now().strftime('%Y%m%d')}.csv"

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT * FROM market_indicators
        WHERE recorded_at >= datetime('now', '-{days} days', 'localtime')
        ORDER BY recorded_at DESC
    """).fetchall()
    conn.close()

    if not rows:
        logger.info("[CSV] 내보낼 지표 없음")
        return path

    headers = ["티커", "지표명", "카테고리", "현재값", "전일종가", "변동률(%)", "상태", "기록시각"]

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([
                r["ticker"], r["name"], r["category"],
                r["current_value"], r["previous_close"], r["change_pct"],
                r["threshold_level"], r["recorded_at"],
            ])

    logger.info(f"[CSV] 지표 {len(rows)}건 → {path.name}")
    return path


def export_all(days: int = 30):
    """전체 데이터 CSV 내보내기"""
    p1 = export_news_csv(days)
    p2 = export_indicators_csv(days)
    print(f"뉴스: {p1}")
    print(f"지표: {p2}")
    return p1, p2
