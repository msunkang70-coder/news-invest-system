"""종목-기사 키워드 매칭"""


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    """텍스트에서 매칭된 키워드 리스트 반환"""
    text_lower = text.lower()
    matched = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw.lower() in text_lower:
            matched.append(kw)
    return matched
