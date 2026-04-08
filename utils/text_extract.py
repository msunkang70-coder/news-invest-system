"""URL에서 기사 본문 추출"""

import requests
import logging

logger = logging.getLogger(__name__)


def extract_body(url: str, timeout: int = 15, max_chars: int = 3000,
                 user_agent: str = "") -> str:
    """trafilatura로 본문 추출. 실패 시 빈 문자열 반환."""
    try:
        import trafilatura
    except ImportError:
        logger.warning("trafilatura 미설치 — 본문 추출 건너뜀")
        return ""

    try:
        headers = {"User-Agent": user_agent} if user_agent else {}
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text) or ""
        return text[:max_chars]
    except Exception as e:
        logger.debug(f"본문 추출 실패: {url} — {e}")
        return ""
