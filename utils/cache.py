"""URL 캐시 — 24시간 TTL, JSON 파일 기반"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import config as cfg

logger = logging.getLogger(__name__)

CACHE_FILE = cfg.CACHE_DIR / "url_cache.json"


class URLCache:
    """단순 URL 캐시 — 이미 수집한 URL 재수집 방지"""

    def __init__(self):
        self._cache: dict[str, str] = {}  # url_hash → ISO timestamp
        self._load()

    def _load(self):
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save(self):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._cache, f)

    def is_cached(self, url_hash: str) -> bool:
        """URL이 캐시에 있고 TTL 내인지"""
        if url_hash not in self._cache:
            return False
        cached_at = datetime.fromisoformat(self._cache[url_hash])
        return datetime.utcnow() - cached_at < timedelta(hours=cfg.CACHE_TTL_HOURS)

    def add(self, url_hash: str):
        """URL을 캐시에 추가"""
        self._cache[url_hash] = datetime.utcnow().isoformat()

    def add_many(self, items):
        """NewsItem 리스트의 URL들을 캐시에 추가"""
        for item in items:
            self.add(item._hash)
        self._save()

    def filter_new(self, items) -> list:
        """캐시에 없는 새 뉴스만 반환"""
        new_items = [i for i in items if not self.is_cached(i._hash)]
        cached = len(items) - len(new_items)
        if cached > 0:
            logger.info(f"[캐시] {cached}건 캐시 히트, {len(new_items)}건 신규")
        return new_items

    def cleanup(self):
        """만료된 캐시 엔트리 정리"""
        now = datetime.utcnow()
        expired = [
            k for k, v in self._cache.items()
            if now - datetime.fromisoformat(v) > timedelta(hours=cfg.CACHE_TTL_HOURS)
        ]
        for k in expired:
            del self._cache[k]
        if expired:
            logger.info(f"[캐시] {len(expired)}건 만료 정리")
        self._save()
