"""교차 자산 영향 체인 분석기 — NIAS v2.0

하나의 이벤트가 다중 자산에 순차적으로 미치는 연쇄 영향을 추적.
예: 중동 분쟁 -> 유가 상승 -> 인플레 우려 -> 금리 인상 기대 -> 성장주 하락
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from models.news_item import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class ImpactChainLink:
    asset: str
    direction: str
    confidence: float
    affected_stocks: list[str] = field(default_factory=list)
    affected_sectors: list[str] = field(default_factory=list)


@dataclass
class ImpactChain:
    name: str
    trigger: str
    chain: list[ImpactChainLink] = field(default_factory=list)
    total_confidence: float = 0.0

    @property
    def summary(self) -> str:
        parts = [f"{link.asset}{link.direction}" for link in self.chain]
        return " -> ".join(parts)


CHAIN_TEMPLATES = {
    "oil_inflation": {
        "trigger_keywords": ["유가 상승", "oil price surge", "OPEC 감산", "중동 분쟁",
                             "호르무즈", "원유 공급", "crude oil", "유가 급등",
                             "유가", "에너지", "중동", "이란", "석유", "원유",
                             "oil", "energy", "Iran", "Middle East", "OPEC"],
        "chain": [
            ImpactChainLink("유가", "상승", 0.9,
                           affected_sectors=["정유(+)", "항공(-)", "해운(-)"]),
            ImpactChainLink("운송비", "상승", 0.8,
                           affected_sectors=["물류(-)", "소비재(-)"]),
            ImpactChainLink("인플레이션", "상승 압력", 0.7),
            ImpactChainLink("금리", "인상 기대", 0.6,
                           affected_sectors=["성장주(-)", "기술주(-)", "금융(+)"]),
        ],
    },
    "dollar_strength": {
        "trigger_keywords": ["달러 강세", "DXY 상승", "dollar strength", "강달러",
                             "금리 인상", "rate hike", "Fed hawkish", "매파",
                             "달러", "환율", "원달러", "dollar", "금리", "FOMC", "연준"],
        "chain": [
            ImpactChainLink("달러", "강세", 0.9),
            ImpactChainLink("원달러 환율", "상승 (원화 약세)", 0.85,
                           affected_sectors=["수출주(+)", "내수주(-)"]),
            ImpactChainLink("신흥국 자금", "유출 압력", 0.7,
                           affected_sectors=["코스피(-)"]),
            ImpactChainLink("원자재", "하락 압력", 0.65,
                           affected_sectors=["철강(-)", "비철금속(-)"]),
        ],
    },
    "taiwan_crisis": {
        "trigger_keywords": ["대만 해협", "Taiwan strait", "중국 대만", "대만 봉쇄",
                             "중국 군사훈련 대만",
                             "대만", "Taiwan", "반도체 공급", "TSMC"],
        "chain": [
            ImpactChainLink("반도체 공급망", "리스크 급등", 0.95,
                           affected_stocks=["TSMC", "삼성전자", "SK하이닉스"],
                           affected_sectors=["반도체(-)"]),
            ImpactChainLink("글로벌 기술주", "하락 압력", 0.85,
                           affected_stocks=["NVIDIA", "애플", "마이크로소프트"],
                           affected_sectors=["빅테크(-)", "AI(-)"]),
            ImpactChainLink("안전자산", "상승", 0.8,
                           affected_sectors=["금(+)", "미국 국채(+)"]),
        ],
    },
    "rate_shock": {
        "trigger_keywords": ["금리 인상", "rate hike", "FOMC 매파", "hawkish",
                             "인플레이션 지속", "CPI 서프라이즈", "CPI surprise",
                             "금리", "기준금리", "인플레", "CPI", "Fed", "연준"],
        "chain": [
            ImpactChainLink("단기 금리", "상승", 0.9),
            ImpactChainLink("성장주", "밸류에이션 하락", 0.85,
                           affected_sectors=["기술주(-)", "바이오(-)"]),
            ImpactChainLink("부동산/리츠", "하락 압력", 0.75,
                           affected_sectors=["건설(-)", "부동산(-)"]),
            ImpactChainLink("은행주", "수혜 (NIM 확대)", 0.7,
                           affected_sectors=["금융(+)"]),
        ],
    },
    "korea_peninsula": {
        "trigger_keywords": ["북한 미사일", "ICBM", "핵실험", "한반도 긴장",
                             "North Korea missile", "북한 도발",
                             "북한", "North Korea", "한반도", "Korean Peninsula"],
        "chain": [
            ImpactChainLink("코스피", "급락", 0.85,
                           affected_sectors=["코스피 전체(-)"]),
            ImpactChainLink("원화", "급락 (원달러 급등)", 0.8),
            ImpactChainLink("방산주", "상승", 0.75,
                           affected_stocks=["한화에어로스페이스", "LIG넥스원"],
                           affected_sectors=["방산(+)"]),
            ImpactChainLink("외국인 자금", "유출", 0.7,
                           affected_sectors=["대형주(-)"]),
        ],
    },
}


def analyze_impact_chains(item: NewsItem) -> List[ImpactChain]:
    """뉴스에서 교차 자산 영향 체인 탐지"""
    text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}".lower()
    matched_chains = []

    for chain_name, template in CHAIN_TEMPLATES.items():
        hits = sum(1 for kw in template["trigger_keywords"] if kw.lower() in text)
        if hits >= 2:
            total_conf = 1.0
            for link in template["chain"]:
                total_conf *= link.confidence

            chain = ImpactChain(
                name=chain_name,
                trigger=chain_name,
                chain=template["chain"],
                total_confidence=round(total_conf, 3),
            )
            matched_chains.append(chain)

            # NewsItem에 체인 정보 기록
            item.impact_chain = chain.summary

            logger.info(
                f"[영향체인] {chain_name} 매칭 (확신도: {total_conf:.1%}): {item.title[:40]}"
            )

    return matched_chains
