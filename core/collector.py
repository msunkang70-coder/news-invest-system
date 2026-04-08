"""RSS 피드 수집기 (국내 + 글로벌)"""

import re
import feedparser
import logging
from datetime import datetime
from time import mktime
from urllib.parse import quote_plus

from core.models import get_conn, insert_article
from utils.dedup import normalize_url, is_title_duplicate
from utils.text_extract import extract_body

logger = logging.getLogger(__name__)


def parse_published(entry) -> str:
    """피드 항목에서 발행일시 추출"""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            return val[:30]
    return ""


def get_entry_link(entry) -> str:
    """피드 항목에서 링크 추출"""
    if hasattr(entry, "link") and entry.link:
        return entry.link
    for link_obj in getattr(entry, "links", []):
        if link_obj.get("href"):
            return link_obj["href"]
    return ""


def build_global_feeds(config: dict) -> list[dict]:
    """종목별 keywords_en + sector_queries + macro_feeds로 Google News RSS URL 생성"""
    global_cfg = config.get("global_news", {})
    if not global_cfg.get("enabled", False):
        return []

    feeds = []
    sector_queries = global_cfg.get("sector_queries", {})

    # 종목별 영문 키워드로 Google News RSS
    for stock in config.get("stocks", []):
        en_keywords = stock.get("keywords_en", [])
        if not en_keywords:
            continue
        # 주요 키워드(첫 번째)로 피드 생성
        main_kw = en_keywords[0]
        query = quote_plus(f"{main_kw} stock")
        feeds.append({
            "name": f"Google:{stock['name']}",
            "url": f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en",
        })

        # 섹터 쿼리도 추가
        sector = stock.get("sector", "")
        for sq in sector_queries.get(sector, [])[:1]:  # 섹터당 1개만
            query = quote_plus(f"{main_kw} {sq}")
            feeds.append({
                "name": f"Google:{stock['name']}/{sq}",
                "url": f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en",
            })

    # 거시경제 공통 피드
    for mf in global_cfg.get("macro_feeds", []):
        query = quote_plus(mf["query"])
        feeds.append({
            "name": f"Google:{mf['name']}",
            "url": f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en",
        })

    return feeds


def _get_recent_titles(config: dict, hours: int = 48) -> list[str]:
    """최근 N시간 이내 기사 제목 조회 (제목 유사도 dedup용)"""
    conn = get_conn(config)
    rows = conn.execute(
        "SELECT title FROM articles WHERE collected_at >= datetime('now','localtime',?)",
        (f"-{hours} hours",)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def collect_feed(config: dict, feed_info: dict, recent_titles: list[str]) -> dict:
    """단일 RSS 피드에서 기사 수집.
    반환: {'new': [ids], 'dup_url': int, 'dup_title': int, 'filtered': int, 'errors': int}
    """
    feed_name = feed_info["name"]
    feed_url = feed_info["url"]
    collector_cfg = config.get("collector", {})
    max_articles = collector_cfg.get("max_articles_per_feed", 30)
    timeout = collector_cfg.get("request_timeout", 15)
    user_agent = collector_cfg.get("user_agent", "")
    do_extract = collector_cfg.get("extract_body", True)
    body_max = collector_cfg.get("body_max_chars", 3000)
    min_title_len = collector_cfg.get("min_title_length", 10)
    min_body_len = collector_cfg.get("min_body_length", 50)
    sim_threshold = collector_cfg.get("title_similarity_threshold", 0.7)

    stats = {"new": [], "dup_url": 0, "dup_title": 0, "filtered": 0, "errors": 0}

    logger.info(f"[수집] {feed_name}")

    try:
        feed = feedparser.parse(feed_url, agent=user_agent)
    except Exception as e:
        logger.error(f"[수집] {feed_name} 파싱 실패: {e}")
        stats["errors"] = 1
        return stats

    if feed.bozo and not feed.entries:
        logger.warning(f"[수집] {feed_name} 피드 오류: {getattr(feed, 'bozo_exception', 'unknown')}")
        stats["errors"] = 1
        return stats

    entries = feed.entries[:max_articles]
    logger.info(f"[수집] {feed_name}: {len(entries)}건 항목")

    for entry in entries:
        title = getattr(entry, "title", "").strip().lstrip("\ufeff")
        link = get_entry_link(entry)
        if not title or not link:
            continue

        # 품질 필터: 제목 너무 짧음
        if len(title) < min_title_len:
            stats["filtered"] += 1
            continue

        # 제목 유사도 dedup
        if is_title_duplicate(title, recent_titles, threshold=sim_threshold):
            stats["dup_title"] += 1
            continue

        url = normalize_url(link)
        published = parse_published(entry)

        # 본문 추출
        body = ""
        summary = getattr(entry, "summary", "") or ""
        if summary:
            body = re.sub(r"<[^>]+>", "", summary).strip()[:body_max]

        if do_extract and len(body) < 200:
            extracted = extract_body(link, timeout=timeout, max_chars=body_max,
                                     user_agent=user_agent)
            if extracted:
                body = extracted

        # 품질 필터: 본문 너무 짧음 (제목+본문 합쳐서 판단)
        if len(body) < min_body_len and len(title) < 30:
            stats["filtered"] += 1
            continue

        article_id = insert_article(
            config, title=title, url=url,
            source=f"RSS:{feed_name}", published=published, body=body
        )
        if article_id:
            stats["new"].append(article_id)
            recent_titles.append(title)  # 이후 항목의 dedup에도 활용
            logger.info(f"  + {title[:60]}")
        else:
            stats["dup_url"] += 1

    return stats


def collect_all(config: dict) -> list[int]:
    """국내 + 글로벌 전체 피드 수집. 새로 삽입된 article_id 리스트 반환."""
    dedup_hours = config.get("collector", {}).get("title_dedup_hours", 48)
    recent_titles = _get_recent_titles(config, hours=dedup_hours)
    logger.info(f"[수집] 제목 dedup 풀: 최근 {dedup_hours}h 내 {len(recent_titles)}건")

    # 국내 피드
    domestic_feeds = config.get("feeds", [])
    # 글로벌 피드
    global_feeds = build_global_feeds(config)

    all_feeds = domestic_feeds + global_feeds
    logger.info(f"[수집] 전체 피드 {len(all_feeds)}개 (국내 {len(domestic_feeds)} + 글로벌 {len(global_feeds)})")

    total_new = []
    total_dup_url = 0
    total_dup_title = 0
    total_filtered = 0
    total_errors = 0

    for feed_info in all_feeds:
        try:
            stats = collect_feed(config, feed_info, recent_titles)
            total_new.extend(stats["new"])
            total_dup_url += stats["dup_url"]
            total_dup_title += stats["dup_title"]
            total_filtered += stats["filtered"]
            total_errors += stats["errors"]
        except Exception as e:
            logger.error(f"[수집] {feed_info['name']} 전체 실패: {e}")
            total_errors += 1

    logger.info(
        f"[수집 완료] 신규 {len(total_new)}건 | "
        f"URL중복 {total_dup_url} | 제목중복 {total_dup_title} | "
        f"품질필터 {total_filtered} | 오류 {total_errors}"
    )
    return total_new
