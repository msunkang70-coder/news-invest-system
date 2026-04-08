"""RSS 피드 기반 뉴스 수집"""
from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests

import config as cfg
from models.news_item import NewsItem

# trafilatura 내부 경고 억제 ("discarding data: None")
logging.getLogger("trafilatura").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*discarding.*")

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _parse_published(entry) -> tuple[Optional[datetime], Optional[datetime]]:
    """published_parsed → UTC datetime + KST datetime"""
    pp = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pp:
        utc_now = datetime.now(timezone.utc)
        return utc_now, utc_now.astimezone(KST)
    try:
        from time import mktime
        utc_dt = datetime.fromtimestamp(mktime(pp), tz=timezone.utc)
        kst_dt = utc_dt.astimezone(KST)
        return utc_dt, kst_dt
    except Exception:
        utc_now = datetime.now(timezone.utc)
        return utc_now, utc_now.astimezone(KST)


def _extract_snippet(entry) -> str:
    """RSS 엔트리에서 snippet 추출"""
    for field in ("summary", "description", "content"):
        val = entry.get(field, "")
        if isinstance(val, list):
            val = val[0].get("value", "") if val else ""
        if val:
            # HTML 태그 간단 제거
            import re
            clean = re.sub(r"<[^>]+>", "", val).strip()
            if len(clean) > 20:
                return clean[:1000]
    return ""


def _fetch_full_text(url: str) -> str:
    """trafilatura로 본문 추출 (실패 시 빈 문자열)"""
    try:
        import trafilatura
        resp = requests.get(
            url,
            timeout=cfg.REQUEST_TIMEOUT,
            headers={"User-Agent": cfg.USER_AGENT},
        )
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_comments=False) or ""
        return text[:5000]
    except Exception as e:
        logger.debug(f"본문 추출 실패 [{url}]: {e}")
        return ""


def collect_rss(sources: list[dict] | None = None, fetch_body: bool = True) -> list[NewsItem]:
    """RSS 소스 목록에서 뉴스 수집

    Args:
        sources: [{"name", "url", "region"}] 리스트. None이면 config 기본값 사용
        fetch_body: True면 trafilatura로 본문 추출 시도

    Returns:
        NewsItem 리스트
    """
    if sources is None:
        sources = cfg.RSS_SOURCES_KR + cfg.RSS_SOURCES_GLOBAL

    items: list[NewsItem] = []

    for src in sources:
        name = src["name"]
        url = src["url"]
        region = src.get("region", "KR")

        logger.info(f"[RSS] {name} 수집 중...")

        try:
            resp = requests.get(
                url,
                timeout=cfg.REQUEST_TIMEOUT,
                headers={"User-Agent": cfg.USER_AGENT},
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            logger.warning(f"[RSS] {name} 수집 실패: {e}")
            continue

        count = 0
        for entry in feed.entries[:cfg.MAX_ARTICLES_PER_FEED]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            utc_dt, kst_dt = _parse_published(entry)
            snippet = _extract_snippet(entry)

            full_text = ""
            if fetch_body:
                full_text = _fetch_full_text(link)

            item = NewsItem(
                title=title,
                source=name,
                url=link,
                published_time=utc_dt,
                published_time_kst=kst_dt,
                full_text=full_text if full_text else None,
                snippet=snippet if snippet else None,
                region=region,
            )
            items.append(item)
            count += 1

        logger.info(f"[RSS] {name}: {count}건 수집")

    logger.info(f"[RSS] 총 {len(items)}건 수집 완료")
    return items
