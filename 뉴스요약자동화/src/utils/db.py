"""SQLite DB 유틸리티 — NIAS v2.0

뉴스, 시장지표, 알림 이력을 SQLite에 저장/조회.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import config as cfg
from models.news_item import NewsItem
from models.market_indicator import MarketIndicator

logger = logging.getLogger(__name__)

DB_PATH = cfg.DATA_DIR / "nias.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """DB 스키마 초기화"""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS news_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            source_type TEXT DEFAULT 'RSS',
            url TEXT UNIQUE NOT NULL,
            published_time TEXT,
            collected_time TEXT DEFAULT (datetime('now','localtime')),
            region TEXT DEFAULT 'KR',
            snippet TEXT,
            keyword_tier TEXT,
            matched_keywords TEXT,
            impact_score REAL DEFAULT 0,
            urgency REAL DEFAULT 0,
            scope REAL DEFAULT 0,
            certainty REAL DEFAULT 0,
            direction TEXT,
            confidence REAL DEFAULT 0,
            time_slot TEXT,
            market_domains TEXT,
            stock_impacts TEXT,
            tagged_stocks TEXT,
            summary_1line TEXT,
            investment_signal TEXT,
            action_suggestion TEXT,
            risk_factor TEXT,
            impact_chain TEXT,
            geo_level INTEGER,
            geo_region TEXT,
            geo_conflict_type TEXT,
            score_breakdown TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_news_published ON news_items(published_time);
        CREATE INDEX IF NOT EXISTS idx_news_score ON news_items(impact_score);
        CREATE INDEX IF NOT EXISTS idx_news_source_type ON news_items(source_type);

        CREATE TABLE IF NOT EXISTS market_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            current_value REAL,
            previous_close REAL,
            change_pct REAL,
            threshold_level TEXT,
            threshold_breached TEXT,
            market_implication TEXT,
            recorded_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_indicator_ticker ON market_indicators(ticker);
        CREATE INDEX IF NOT EXISTS idx_indicator_time ON market_indicators(recorded_at);

        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT NOT NULL,
            title TEXT,
            channels TEXT,
            status TEXT DEFAULT 'sent',
            sent_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()
    logger.info(f"[DB] 초기화 완료: {DB_PATH}")


def save_news_items(items: List[NewsItem]):
    """분석 완료된 뉴스 일괄 저장"""
    conn = get_connection()
    saved = 0
    for item in items:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO news_items (
                    id, title, source, source_type, url, published_time,
                    region, snippet, keyword_tier, matched_keywords,
                    impact_score, urgency, scope, certainty,
                    direction, confidence, market_domains,
                    stock_impacts, tagged_stocks,
                    summary_1line, investment_signal, action_suggestion,
                    risk_factor, impact_chain,
                    geo_level, geo_region, geo_conflict_type, score_breakdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item._hash, item.title, item.source, item.source_type, item.url,
                item.published_time.isoformat() if item.published_time else None,
                item.region, item.snippet, item.keyword_tier,
                json.dumps(item.matched_keywords, ensure_ascii=False),
                item.impact_score, item.urgency, item.scope, item.certainty,
                item.direction.value if item.direction else None, item.confidence,
                json.dumps([d.value for d in item.market_domains], ensure_ascii=False),
                json.dumps([si.to_dict() for si in item.stock_impacts], ensure_ascii=False),
                json.dumps(item.tagged_stocks, ensure_ascii=False),
                item.summary_1line, item.investment_signal, item.action_suggestion,
                item.risk_factor, item.impact_chain,
                item.geo_level, item.geo_region, item.geo_conflict_type,
                json.dumps(item.score_breakdown, ensure_ascii=False),
            ))
            saved += 1
        except Exception as e:
            logger.debug(f"[DB] 뉴스 저장 스킵: {e}")
    conn.commit()
    conn.close()
    if saved:
        logger.info(f"[DB] 뉴스 {saved}/{len(items)}건 저장")


def save_indicators(indicators: List[MarketIndicator]):
    """시장지표 히스토리 저장"""
    conn = get_connection()
    for ind in indicators:
        conn.execute("""
            INSERT INTO market_indicators (
                ticker, name, category, current_value, previous_close,
                change_pct, threshold_level, threshold_breached, market_implication
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ind.ticker, ind.name, ind.category.value,
            ind.current_value, ind.previous_close, ind.change_pct,
            ind.threshold_level.value,
            json.dumps(ind.threshold_breached, ensure_ascii=False),
            ind.market_implication,
        ))
    conn.commit()
    conn.close()
    if indicators:
        logger.info(f"[DB] 지표 {len(indicators)}건 저장")


def get_recent_news(hours: int = 24, limit: int = 100) -> List[dict]:
    """최근 N시간 내 고영향 뉴스 조회"""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT * FROM news_items
        WHERE collected_time >= ?
        ORDER BY impact_score DESC
        LIMIT ?
    """, (cutoff, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_indicator_history(ticker: str, days: int = 7) -> List[dict]:
    """특정 지표의 최근 N일 히스토리"""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT * FROM market_indicators
        WHERE ticker = ? AND recorded_at >= ?
        ORDER BY recorded_at ASC
    """, (ticker, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_db_stats() -> dict:
    """DB 통계"""
    conn = get_connection()
    news_count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    ind_count = conn.execute("SELECT COUNT(*) FROM market_indicators").fetchone()[0]
    alert_count = conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()[0]
    conn.close()
    return {"news": news_count, "indicators": ind_count, "alerts": alert_count}


# 모듈 로드 시 DB 자동 초기화
init_db()
