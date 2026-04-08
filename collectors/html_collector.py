"""HTML 크롤링 Fallback 수집기

RSS 실패 시 직접 HTML 페이지에서 뉴스 링크 추출
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# HTML fallback 대상 사이트 정의
HTML_SOURCES = [
    {
        "name": "한국은행 보도자료",
        "url": "https://www.bok.or.kr/portal/bbs/P0000559/list.do?menuNo=200761",
        "selector": "a.link",
        "base_url": "https://www.bok.or.kr",
        "region": "KR",
    },
    {
        "name": "기획재정부 보도자료",
        "url": "https://www.moef.go.kr/nw/nes/nesdta.do?menuNo=4010100",
        "selector": "td.tit a",
        "base_url": "https://www.moef.go.kr",
        "region": "KR",
    },
    {
        "name": "KOTRA 해외시장뉴스",
        "url": "https://dream.kotra.or.kr/kotranews/cms/news/actionKotraBoardList.do?MENU_ID=70",
        "selector": "a.title",
        "base_url": "https://dream.kotra.or.kr",
        "region": "KR",
    },
]


def _fetch_full_text(url: str) -> str:
    """trafilatura로 본문 추출"""
    try:
        import trafilatura
        resp = requests.get(url, timeout=cfg.REQUEST_TIMEOUT, headers={"User-Agent": cfg.USER_AGENT})
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_comments=False) or ""
        return text[:5000]
    except Exception:
        return ""


def collect_html_fallback(sources: list[dict] | None = None) -> list[NewsItem]:
    """HTML 페이지에서 뉴스 링크 크롤링

    Args:
        sources: HTML_SOURCES 형식 리스트. None이면 기본값

    Returns:
        NewsItem 리스트
    """
    if sources is None:
        sources = HTML_SOURCES

    items: list[NewsItem] = []

    for src in sources:
        name = src["name"]
        logger.info(f"[HTML] {name} 크롤링 중...")

        try:
            resp = requests.get(
                src["url"],
                timeout=cfg.REQUEST_TIMEOUT,
                headers={"User-Agent": cfg.USER_AGENT},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.warning(f"[HTML] {name} 크롤링 실패: {e}")
            continue

        links = soup.select(src["selector"])
        count = 0
        for link in links[:cfg.MAX_ARTICLES_PER_FEED]:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue

            # 상대 URL 처리
            if href.startswith("/"):
                href = src.get("base_url", "") + href

            if not href.startswith("http"):
                continue

            full_text = _fetch_full_text(href)

            item = NewsItem(
                title=title,
                source=name,
                url=href,
                published_time=datetime.now(timezone.utc),
                published_time_kst=datetime.now(KST),
                full_text=full_text if full_text else None,
                region=src.get("region", "KR"),
            )
            items.append(item)
            count += 1

        logger.info(f"[HTML] {name}: {count}건 수집")

    logger.info(f"[HTML] 총 {len(items)}건 수집 완료")
    return items
