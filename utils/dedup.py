"""중복 기사 제거 유틸리티"""

import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "ref", "source", "mc_cid", "mc_eid",
}


def normalize_url(url: str) -> str:
    """트래킹 파라미터 제거 후 URL 정규화"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=False)
    clean = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    clean_query = urlencode(clean, doseq=True) if clean else ""
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        parsed.params,
        clean_query,
        "",
    ))
    return normalized


def _normalize_title(title: str) -> str:
    """제목 정규화: 공백/특수문자 제거, 소문자"""
    t = re.sub(r"[\s\[\]()【】「」''\"\"·…\-_|/]", "", title)
    t = re.sub(r"[^\w가-힣a-zA-Z0-9]", "", t)
    return t.lower()


def title_similarity(a: str, b: str) -> float:
    """두 제목의 bigram 기반 유사도 (0.0~1.0)"""
    na = _normalize_title(a)
    nb = _normalize_title(b)

    if not na or not nb:
        return 0.0

    # 길이 차이가 너무 크면 다른 기사
    if len(na) > 2 * len(nb) or len(nb) > 2 * len(na):
        return 0.0

    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1))

    ba = bigrams(na)
    bb = bigrams(nb)

    if not ba or not bb:
        return 1.0 if na == nb else 0.0

    intersection = len(ba & bb)
    union = len(ba | bb)
    return intersection / union if union > 0 else 0.0


def is_title_duplicate(new_title: str, existing_titles: list[str],
                       threshold: float = 0.7) -> bool:
    """기존 제목 리스트에서 유사 제목이 있으면 True"""
    for t in existing_titles:
        if title_similarity(new_title, t) >= threshold:
            return True
    return False
