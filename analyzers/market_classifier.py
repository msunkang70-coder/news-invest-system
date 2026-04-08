"""시장 영역 분류 — 뉴스가 영향을 미치는 시장 도메인 태깅

하나의 뉴스가 복수 시장에 영향 가능 (예: "금리 인상" → 채권 + 주식 + 환율)
"""
from __future__ import annotations

import logging

from models.news_item import NewsItem, MarketDomain

logger = logging.getLogger(__name__)

# 시장 영역별 키워드 매핑
_DOMAIN_KEYWORDS: dict[MarketDomain, list[str]] = {
    MarketDomain.EQUITY: [
        "주식", "코스피", "코스닥", "KOSPI", "KOSDAQ", "나스닥", "NASDAQ",
        "S&P", "다우", "Dow", "니케이", "상해", "실적", "earnings",
        "IPO", "M&A", "주가", "시가총액", "PER", "EPS",
        "삼성전자", "SK하이닉스", "현대차", "NVIDIA", "Apple", "Tesla",
        "반도체", "AI", "배터리", "바이오", "자동차", "은행주",
    ],
    MarketDomain.BOND: [
        "국채", "금리", "채권", "bond", "treasury", "yield",
        "10년물", "2년물", "스프레드", "spread",
        "금리인상", "금리인하", "rate hike", "rate cut",
        "통화정책", "monetary policy",
    ],
    MarketDomain.FX: [
        "환율", "달러", "USD", "원달러", "dollar", "엔화", "유로",
        "EUR", "JPY", "CNY", "위안", "강달러", "약달러",
        "외환", "forex", "FX", "원화",
    ],
    MarketDomain.COMMODITY: [
        "유가", "oil", "crude", "WTI", "브렌트", "Brent", "OPEC",
        "금", "gold", "은", "silver", "구리", "copper",
        "천연가스", "natural gas", "철광석", "석탄",
        "원자재", "commodity", "곡물", "소맥", "대두",
    ],
    MarketDomain.MACRO: [
        "FOMC", "연준", "Fed", "ECB", "BOJ", "한국은행",
        "GDP", "CPI", "PPI", "PMI", "ISM", "고용",
        "인플레이션", "inflation", "경기침체", "recession",
        "재정정책", "fiscal", "기준금리", "양적완화", "QE", "QT",
        "관세", "tariff", "무역", "trade", "제재", "sanctions",
        "전쟁", "war", "지정학", "geopolitical",
    ],
    MarketDomain.CRYPTO: [
        "비트코인", "Bitcoin", "BTC", "이더리움", "Ethereum", "ETH",
        "암호화폐", "crypto", "블록체인", "blockchain",
        "코인", "디지털자산", "CBDC", "스테이블코인",
    ],
}


def classify_markets(items: list[NewsItem]) -> list[NewsItem]:
    """뉴스에 시장 영역(MarketDomain) 태깅 — 복수 매칭 가능"""
    domain_counts = {d: 0 for d in MarketDomain}

    for item in items:
        text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}".lower()
        domains = []

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw.lower() in text)
            if hits >= 2:  # 2개 이상 매칭 시 해당 영역
                domains.append((domain, hits))

        if not domains:
            # fallback: 1개라도 매칭되는 것 중 최고
            for domain, keywords in _DOMAIN_KEYWORDS.items():
                hits = sum(1 for kw in keywords if kw.lower() in text)
                if hits >= 1:
                    domains.append((domain, hits))

        if not domains:
            domains = [(MarketDomain.MACRO, 0)]  # 최종 fallback

        # 히트 수 내림차순 정렬 후 태깅
        domains.sort(key=lambda x: x[1], reverse=True)
        item.market_domains = [d for d, _ in domains[:3]]  # 최대 3개

        for d in item.market_domains:
            domain_counts[d] += 1

    summary = " / ".join(f"{d.emoji}{d.value}:{c}" for d, c in domain_counts.items() if c > 0)
    logger.info(f"[시장분류] {len(items)}건: {summary}")

    return items
