"""SQLite 데이터베이스 모델 및 헬퍼 함수"""

import sqlite3
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    ticker      TEXT,
    keywords    TEXT,
    sector      TEXT,
    active      INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    source       TEXT,
    published    TEXT,
    body         TEXT,
    collected_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS analysis (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  INTEGER NOT NULL REFERENCES articles(id),
    stock_id    INTEGER NOT NULL REFERENCES stocks(id),
    relevance   REAL,
    direction   TEXT,
    impact      REAL,
    reasoning   TEXT,
    notified    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(article_id, stock_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analysis(id),
    channel     TEXT DEFAULT 'telegram',
    sent_at     TEXT DEFAULT (datetime('now','localtime')),
    status      TEXT DEFAULT 'sent'
);
"""


def get_db_path(config: dict) -> str:
    db_rel = config.get("db_path", "data/news.db")
    return str(BASE_DIR / db_rel)


def get_conn(config: dict) -> sqlite3.Connection:
    db_path = get_db_path(config)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(config: dict):
    conn = get_conn(config)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def sync_stocks(config: dict):
    """config.yaml의 종목 목록을 DB에 동기화"""
    conn = get_conn(config)
    for s in config.get("stocks", []):
        keywords_str = ",".join(s.get("keywords", []))
        existing = conn.execute(
            "SELECT id FROM stocks WHERE name = ?", (s["name"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE stocks SET ticker=?, keywords=?, sector=?, active=1 WHERE id=?",
                (s.get("ticker"), keywords_str, s.get("sector"), existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO stocks (name, ticker, keywords, sector) VALUES (?,?,?,?)",
                (s["name"], s.get("ticker"), keywords_str, s.get("sector")),
            )
    conn.commit()
    conn.close()


def get_stocks(config: dict) -> list[dict]:
    conn = get_conn(config)
    rows = conn.execute("SELECT * FROM stocks WHERE active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_article(config: dict, title: str, url: str, source: str,
                   published: str, body: str) -> int | None:
    """기사 삽입. 중복 URL이면 None 반환."""
    conn = get_conn(config)
    try:
        cur = conn.execute(
            "INSERT INTO articles (title, url, source, published, body) VALUES (?,?,?,?,?)",
            (title, url, source, published, body),
        )
        conn.commit()
        article_id = cur.lastrowid
    except sqlite3.IntegrityError:
        article_id = None
    conn.close()
    return article_id


def insert_analysis(config: dict, article_id: int, stock_id: int,
                    relevance: float, direction: str, impact: float,
                    reasoning: str) -> int | None:
    conn = get_conn(config)
    try:
        cur = conn.execute(
            """INSERT INTO analysis (article_id, stock_id, relevance, direction, impact, reasoning)
               VALUES (?,?,?,?,?,?)""",
            (article_id, stock_id, relevance, direction, impact, reasoning),
        )
        conn.commit()
        analysis_id = cur.lastrowid
    except sqlite3.IntegrityError:
        analysis_id = None
    conn.close()
    return analysis_id


def get_unnotified(config: dict) -> list[dict]:
    """알림 미발송 분석 결과 조회"""
    conn = get_conn(config)
    rows = conn.execute("""
        SELECT a.id as analysis_id, a.relevance, a.direction, a.impact, a.reasoning,
               a.stock_id, a.article_id,
               ar.title, ar.url, ar.source, ar.published,
               s.name as stock_name, s.ticker
        FROM analysis a
        JOIN articles ar ON a.article_id = ar.id
        JOIN stocks s ON a.stock_id = s.id
        WHERE a.notified = 0
        ORDER BY a.impact DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notified(config: dict, analysis_id: int, status: str = "sent"):
    conn = get_conn(config)
    conn.execute("UPDATE analysis SET notified=1 WHERE id=?", (analysis_id,))
    conn.execute(
        "INSERT INTO notifications (analysis_id, status) VALUES (?,?)",
        (analysis_id, status),
    )
    conn.commit()
    conn.close()


def get_recent_articles(config: dict, days: int = 7, stock_name: str = None,
                        direction: str = None) -> list[dict]:
    """대시보드용: 최근 기사+분석 결과 조회"""
    conn = get_conn(config)
    query = """
        SELECT ar.title, ar.url, ar.source, ar.published, ar.collected_at,
               a.relevance, a.direction, a.impact, a.reasoning,
               s.name as stock_name, s.ticker
        FROM analysis a
        JOIN articles ar ON a.article_id = ar.id
        JOIN stocks s ON a.stock_id = s.id
        WHERE ar.collected_at >= datetime('now','localtime',?)
    """
    params: list = [f"-{days} days"]

    if stock_name:
        query += " AND s.name = ?"
        params.append(stock_name)
    if direction and direction != "전체":
        query += " AND a.direction = ?"
        params.append(direction)

    query += " ORDER BY ar.collected_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_notification_history(config: dict, days: int = 7) -> list[dict]:
    conn = get_conn(config)
    rows = conn.execute("""
        SELECT n.sent_at, n.status, n.channel,
               a.relevance, a.direction, a.impact, a.reasoning,
               ar.title, ar.url, ar.source,
               s.name as stock_name
        FROM notifications n
        JOIN analysis a ON n.analysis_id = a.id
        JOIN articles ar ON a.article_id = ar.id
        JOIN stocks s ON a.stock_id = s.id
        WHERE n.sent_at >= datetime('now','localtime',?)
        ORDER BY n.sent_at DESC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stock_summary(config: dict, days: int = 7) -> list[dict]:
    """종목별 기사 수/평균 점수 요약"""
    conn = get_conn(config)
    rows = conn.execute("""
        SELECT s.name as stock_name,
               COUNT(a.id) as article_count,
               ROUND(AVG(a.relevance), 2) as avg_relevance,
               ROUND(AVG(a.impact), 2) as avg_impact,
               SUM(CASE WHEN a.direction='positive' THEN 1 ELSE 0 END) as pos_count,
               SUM(CASE WHEN a.direction='negative' THEN 1 ELSE 0 END) as neg_count,
               SUM(CASE WHEN a.direction='neutral' THEN 1 ELSE 0 END) as neu_count
        FROM analysis a
        JOIN stocks s ON a.stock_id = s.id
        JOIN articles ar ON a.article_id = ar.id
        WHERE ar.collected_at >= datetime('now','localtime',?)
        GROUP BY s.name
        ORDER BY article_count DESC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
