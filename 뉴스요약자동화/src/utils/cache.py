"""URL 캐시 — 24시간 TTL 기반 중복 방지"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import config as cfg
from models.news_item import NewsItem

logger = logging.getLogger(__name__)


class UrlCache:
    def __init__(self, cache_file: Path = None, ttl_hours: int = None):
        self.cache_file = cache_file or (cfg.CACHE_DIR / "url_cache.json")
        self.ttl = timedelta(hours=ttl_hours or cfg.CACHE_TTL_HOURS)
        self.cache: dict[str, str] = self._load()

    def _load(self) -> dict:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False)

    def is_cached(self, url: str) -> bool:
        ts = self.cache.get(url)
        if not ts:
            return False
        cached_time = datetime.fromisoformat(ts)
        return (datetime.now() - cached_time) < self.ttl

    def add(self, url: str):
        self.cache[url] = datetime.now().isoformat()

    def filter_new(self, items: List[NewsItem]) -> List[NewsItem]:
        new_items = [i for i in items if not self.is_cached(i.url)]
        for item in new_items:
            self.add(item.url)
        self._save()
        logger.info(f"[캐시] {len(items)}건 → {len(new_items)}건 (신규)")
        return new_items

    def cleanup(self):
        now = datetime.now()
        expired = [url for url, ts in self.cache.items()
                   if (now - datetime.fromisoformat(ts)) > self.ttl]
        for url in expired:
            del self.cache[url]
        self._save()
        logger.info(f"[캐시] {len(expired)}건 만료 정리")
