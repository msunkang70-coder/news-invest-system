"""전쟁·지정학 에스컬레이션 5단계 분류기 — NIAS v2.0

레벨 정의:
  L1 (긴장):     외교 갈등, 성명 발표, 경제 보복 예고
  L2 (긴장 고조): 군사훈련 확대, 제재 발동, 군사력 전개
  L3 (무력 시위): 미사일 시험, 영공/영해 침범, 제한적 군사행동
  L4 (무력 충돌): 실제 교전, 군사기지 공격, 인명 피해
  L5 (전면 위기): 전면전, 핵 위협, 주요 해상로 봉쇄
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from models.news_item import NewsItem
from analyzers.event_actions import (
    detect_action_category,
    detect_entity_class,
    resolve_event_level,
)

logger = logging.getLogger(__name__)


class EscalationLevel(IntEnum):
    L1_TENSION = 1
    L2_HEIGHTENED = 2
    L3_SHOW_OF_FORCE = 3
    L4_ARMED_CONFLICT = 4
    L5_FULL_CRISIS = 5


@dataclass
class GeopoliticalAssessment:
    level: EscalationLevel
    conflict_type: str
    region: str
    impact_multiplier: float
    market_channels: list[str] = field(default_factory=list)
    description: str = ""


ESCALATION_KEYWORDS = {
    EscalationLevel.L5_FULL_CRISIS: [
        "전면전", "all-out war", "full-scale invasion", "핵 공격", "nuclear strike",
        "해상봉쇄", "naval blockade", "대만해협 봉쇄", "계엄령", "martial law",
        "DEFCON", "전시상태", "전면 침공", "nuclear launch", "핵 발사",
        "총동원령", "general mobilization", "전쟁 선포", "declaration of war",
        "수에즈 봉쇄", "Suez blocked", "말라카 봉쇄", "Malacca blocked",
    ],
    EscalationLevel.L4_ARMED_CONFLICT: [
        "교전", "combat", "공습", "airstrike", "미사일 공격", "missile attack",
        "포격", "shelling", "사망자", "casualties", "군사기지 공격",
        "침공", "invasion", "drone strike", "드론 공격",
        "ground offensive", "지상 공격", "retaliatory strike", "보복 공격",
        "killed in action", "전사", "civilian casualties", "민간인 피해",
        "air defense", "방공", "intercept", "요격",
    ],
    EscalationLevel.L3_SHOW_OF_FORCE: [
        "미사일 발사", "missile launch", "ICBM", "핵실험", "nuclear test",
        "영공 침범", "airspace violation", "영해 침범", "군사훈련",
        "항공모함 전개", "carrier strike group", "군사력 과시",
        "missile test", "weapons test", "무기 실험", "hypersonic",
        "naval exercise", "해상 훈련", "joint military drill", "합동 훈련",
        "no-fly zone", "비행금지구역", "military buildup", "군사력 증강",
    ],
    EscalationLevel.L2_HEIGHTENED: [
        "긴장 고조", "tensions rise", "escalation", "에스컬레이션",
        "제재 발동", "sanctions imposed", "대사 소환", "ambassador recalled",
        "군병력 증강", "troops buildup", "경고 발령",
        "trade embargo", "수출 금지", "export ban", "asset freeze", "자산 동결",
        "military alert", "경계 태세", "travel ban", "입국 금지",
        "diplomatic expulsion", "외교관 추방", "arms deal", "무기 거래",
    ],
    EscalationLevel.L1_TENSION: [
        "외교 갈등", "diplomatic dispute", "비난 성명", "condemnation",
        "제재 검토", "considering sanctions", "우려 표명", "concern",
        "diplomatic protest", "외교적 항의", "summoned ambassador",
        "trade dispute", "무역 분쟁", "territorial claim", "영유권 주장",
        "warning issued", "경고 발령", "military posture", "군사적 태세",
    ],
}

LEVEL_MULTIPLIERS = {
    EscalationLevel.L1_TENSION: 1.0,
    EscalationLevel.L2_HEIGHTENED: 1.2,
    EscalationLevel.L3_SHOW_OF_FORCE: 1.5,
    EscalationLevel.L4_ARMED_CONFLICT: 2.0,
    EscalationLevel.L5_FULL_CRISIS: 3.0,
}

REGION_KEYWORDS = {
    "중동": ["Middle East", "중동", "이란", "Iran", "이스라엘", "Israel",
             "Hamas", "하마스", "Hezbollah", "헤즈볼라", "호르무즈", "Hormuz",
             "Gaza", "가자", "West Bank", "시리아", "Syria", "Yemen", "예멘",
             "Houthi", "후티", "Red Sea", "홍해", "Persian Gulf", "페르시아만",
             "Baghdad", "바그다드", "Tehran", "테헤란", "Tel Aviv", "텔아비브"],
    "대만해협": ["Taiwan strait", "대만", "대만해협", "중국 통일", "하나의 중국",
                "Taiwan", "Taipei", "타이페이", "Chinese military", "중국군",
                "PLA", "인민해방군", "One China", "대만 독립"],
    "한반도": ["North Korea", "북한", "ICBM", "핵실험", "nuclear test", "DMZ",
              "비핵화", "denuclearization", "미사일 발사",
              "Pyongyang", "평양", "Kim Jong", "김정은", "38th parallel",
              "Korean Peninsula", "한반도", "THAAD", "사드"],
    "우크라이나": ["Ukraine", "우크라이나", "러시아", "Russia", "크림반도",
                  "Crimea", "NATO", "나토", "Kyiv", "키이우", "Zelensky",
                  "젤렌스키", "Putin", "푸틴", "Donbas", "돈바스",
                  "Black Sea", "흑해", "Nord Stream"],
    "남중국해": ["South China Sea", "남중국해", "9단선", "영유권", "territorial"],
}

REGION_MARKET_CHANNELS = {
    "중동": ["유가 급등", "안전자산(금) 상승", "항공/해운주 하락", "방산주 상승"],
    "대만해협": ["반도체 공급망 리스크", "TSMC 직격", "글로벌 기술주 하락", "안전자산 상승"],
    "한반도": ["코스피 급락", "원화 약세", "방산주 상승", "외국인 자금 유출"],
    "우크라이나": ["유럽 에너지 위기", "천연가스 급등", "유럽주 하락", "방산주 상승"],
    "남중국해": ["해상운송 리스크", "물류 비용 상승", "중국 관련주 하락"],
}


def classify_geopolitical(item: NewsItem) -> Optional[GeopoliticalAssessment]:
    """뉴스의 지정학 에스컬레이션 레벨 분류"""
    text = f"{item.title} {item.snippet or ''} {(item.full_text or '')[:500]}".lower()

    # 에스컬레이션 레벨 판정 (높은 레벨부터)
    detected_level = None
    for level in sorted(EscalationLevel, reverse=True):
        keywords = ESCALATION_KEYWORDS.get(level, [])
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits >= 1:
            detected_level = level
            break

    # Fallback: 기존 에스컬레이션 키워드 miss 시 (엔티티 × 액션) 매트릭스로 provisional 승격
    # 목적: 'Hormuz stays shut', 'Closed Strait'처럼 정확한 봉쇄 키워드가 없어도
    #       해상로+봉쇄/공급차질 조합이면 L3로 자동 판정.
    if detected_level is None:
        entity_class = detect_entity_class(text)
        action = detect_action_category(text)
        if entity_class and action:
            provisional = resolve_event_level(entity_class, action)
            detected_level = EscalationLevel(provisional)
            item.event_fallback = True
            item.event_category = action
            item.event_entity_class = entity_class
            logger.info(
                f"[지정학-Fallback] L{provisional} ({entity_class}+{action}): {item.title[:50]}"
            )

    if detected_level is None:
        return None

    # 지역 판정
    detected_region = "기타"
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            detected_region = region
            break

    assessment = GeopoliticalAssessment(
        level=detected_level,
        conflict_type=_detect_conflict_type(text),
        region=detected_region,
        impact_multiplier=LEVEL_MULTIPLIERS[detected_level],
        market_channels=REGION_MARKET_CHANNELS.get(detected_region, []),
        description=f"{detected_region} (Level {detected_level.value})",
    )

    # NewsItem에 지정학 정보 기록
    item.geo_level = detected_level.value
    item.geo_region = detected_region
    item.geo_conflict_type = assessment.conflict_type

    logger.info(
        f"[지정학] L{detected_level.value} {detected_region}: {item.title[:50]}"
    )
    return assessment


def _detect_conflict_type(text: str) -> str:
    """분쟁 유형 판정"""
    type_keywords = {
        "전면전": ["전면전", "full-scale war", "전면 침공", "total war"],
        "무력충돌": ["교전", "combat", "공습", "airstrike", "포격"],
        "군사행동": ["미사일 발사", "missile launch", "ICBM", "핵실험"],
        "제재": ["제재", "sanctions", "embargo", "수출통제"],
        "긴장고조": ["긴장 고조", "tensions", "escalation"],
    }
    for ctype, keywords in type_keywords.items():
        if any(kw.lower() in text for kw in keywords):
            return ctype
    return "긴장"
