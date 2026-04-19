"""이벤트 액션·엔티티 분류 — 단기안 Fallback 레이어

설계 철학:
  - 엔티티(무엇이: 호르무즈, Fed, 삼성 ...)는 계속 바뀐다
  - 액션(무슨 일: 봉쇄, 공격, 제재, 경고 ...)은 반복된다
  → 지명이 키워드 사전에 없어도 (엔티티 클래스 × 액션 카테고리) 조합으로
     provisional 이벤트 레벨을 산출하여 geopolitical_classifier의 miss를 보완.

이 모듈은 중기안 event_type_classifier 의 Tier 1 규칙 레이어로도 재사용된다.
"""
from __future__ import annotations

from typing import Optional


# ─────────────────────────────────────────────────────────────
# 액션 카테고리 — 사건의 성격(반복되는 패턴)
# 특정 지명/기관명은 여기에 넣지 않는다. 순수 '무슨 일' 동사·명사만.
# ─────────────────────────────────────────────────────────────
ACTION_CATEGORIES: dict[str, list[str]] = {
    "blockade": [
        # 영어
        "blockade", "close the", "closed", "closure", "shut", "stays shut",
        "cut off", "blocked", "seal off", "sealed off", "denied access",
        "exclusion zone", "no-sail", "cordon",
        # 한국어
        "봉쇄", "폐쇄", "차단", "통제", "접근 금지", "진입 금지",
    ],
    "supply_disruption": [
        "halt production", "halted", "suspend production", "suspended",
        "plunges", "collapse", "shortage", "disruption", "cut supply",
        "stops shipping", "stops exports", "output falls", "production drop",
        "scaled back", "curbed", "curtailed",
        "생산 중단", "공급 차질", "공급 부족", "출하 중단", "선적 중단",
        "가동 중단", "감산",
    ],
    "attack": [
        "strike", "attacked", "attacks", "hits", "struck", "retaliation",
        "raid", "bombing", "bombed", "missile attack", "drone attack",
        "targets", "targeted", "fired at", "opened fire", "shelled",
        "공격", "타격", "피격", "공습", "보복", "폭격", "미사일 발사",
    ],
    "sanction": [
        "sanction", "sanctions", "embargo", "ban exports", "ban imports",
        "freeze assets", "blacklist", "blacklisted", "restrict exports",
        "export control", "trade ban", "cut off from",
        "제재", "금수", "동결", "수출 금지", "수출 통제", "거래 중단",
    ],
    "official_warning": [
        "announces", "threatens", "threatened", "warns", "warned",
        "official notice", "declares", "issues warning", "ultimatum",
        "vows to", "pledges retaliation", "red line",
        "공식 통보", "공식 경고", "최후통첩", "선언", "성명", "천명",
    ],
    "policy_shock": [
        "emergency rate", "surprise hike", "surprise cut", "unscheduled",
        "intervention", "currency intervention", "shock",
        "quantitative easing", "quantitative tightening",
        "긴급 금리", "깜짝 인상", "깜짝 인하", "긴급 인하", "외환 개입",
    ],
    "major_incident": [
        "crisis", "collapse", "bankruptcy", "default", "explosion",
        "disaster", "catastrophe", "contagion", "meltdown",
        "위기", "붕괴", "파산", "디폴트", "폭발", "재난",
    ],
}


# ─────────────────────────────────────────────────────────────
# 엔티티 클래스 — 시장 충격 민감도가 다른 대상 그룹
# dict 순서 = 우선순위 (먼저 매칭되는 클래스 채택).
# shipping_lane을 맨 앞에 두는 이유: 호르무즈·수에즈급은 지리·상품 둘 다 해당되나
# 사건 성격상 '해상로 이벤트'가 가장 시장 파급이 직접적.
# ─────────────────────────────────────────────────────────────
ENTITY_CLASSES: dict[str, list[str]] = {
    "shipping_lane": [
        "strait of hormuz", "hormuz", "호르무즈",
        "suez canal", "suez", "수에즈",
        "panama canal", "panama", "파나마",
        "strait of malacca", "malacca", "말라카",
        "bosphorus", "보스포러스",
        "red sea", "홍해", "bab el-mandeb", "bab-el-mandeb",
        "persian gulf", "페르시아만",
        "해협", "운하",
    ],
    "strategic_geography": [
        "middle east", "중동",
        "iran", "이란", "israel", "이스라엘",
        "gaza", "가자", "west bank", "서안지구",
        "syria", "시리아", "yemen", "예멘",
        "taiwan", "대만", "taiwan strait", "대만해협",
        "north korea", "북한", "korean peninsula", "한반도",
        "ukraine", "우크라이나", "russia", "러시아",
        "south china sea", "남중국해",
        "kashmir", "카슈미르",
    ],
    "commodity": [
        "oil", "crude", "원유", "petroleum", "석유", "brent", "wti",
        "natural gas", "lng", "천연가스",
        "chip", "chips", "semiconductor", "반도체", "wafer",
        "rare earth", "희토류",
        "wheat", "grain", "곡물", "food", "식량",
        "lithium", "리튬", "nickel", "니켈", "cobalt", "copper",
        "gold", "금 선물",
    ],
    "institution": [
        "federal reserve", "fed", "연준", "fomc",
        "ecb", "european central bank", "유럽중앙은행",
        "boj", "bank of japan", "일본은행",
        "bok", "한국은행", "한은",
        "opec", "석유수출국기구", "imf", "world bank",
        "treasury", "재무부",
    ],
    "major_corporate": [
        "tsmc", "samsung", "삼성전자", "sk hynix", "sk하이닉스",
        "aramco", "아람코",
        "apple", "애플", "nvidia", "엔비디아", "microsoft",
        "jpmorgan", "tesla", "테슬라",
    ],
}


# ─────────────────────────────────────────────────────────────
# (엔티티 클래스 × 액션 카테고리) → provisional level 매트릭스
# 값: 1 (관심) / 2 (경계) / 3 (심각)
# 매트릭스에 없는 조합은 기본값 1.
# ─────────────────────────────────────────────────────────────
_LEVEL_MATRIX: dict[tuple[str, str], int] = {
    # 해상로: 봉쇄·공급차질·공격은 즉시 L3 (호르무즈·수에즈·말라카급)
    ("shipping_lane", "blockade"): 3,
    ("shipping_lane", "supply_disruption"): 3,
    ("shipping_lane", "attack"): 3,
    ("shipping_lane", "major_incident"): 3,
    ("shipping_lane", "official_warning"): 2,
    ("shipping_lane", "sanction"): 2,

    # 전략 지역: 공격·봉쇄는 L3, 공급차질·제재·경고는 L2
    ("strategic_geography", "attack"): 3,
    ("strategic_geography", "blockade"): 3,
    ("strategic_geography", "major_incident"): 3,
    ("strategic_geography", "supply_disruption"): 2,
    ("strategic_geography", "sanction"): 2,
    ("strategic_geography", "official_warning"): 2,

    # 원자재: 공급차질·봉쇄가 시장 직접 영향
    ("commodity", "supply_disruption"): 3,
    ("commodity", "blockade"): 3,
    ("commodity", "attack"): 2,
    ("commodity", "sanction"): 2,
    ("commodity", "major_incident"): 2,

    # 중앙은행·국제기구: 정책 충격이 핵심
    ("institution", "policy_shock"): 3,
    ("institution", "major_incident"): 3,
    ("institution", "official_warning"): 2,
    ("institution", "sanction"): 2,

    # 글로벌 대기업: 사고·공급차질·제재
    ("major_corporate", "major_incident"): 2,
    ("major_corporate", "supply_disruption"): 2,
    ("major_corporate", "sanction"): 2,
    ("major_corporate", "attack"): 2,
}

_DEFAULT_FALLBACK_LEVEL = 1


# ─────────────────────────────────────────────────────────────
# 탐지 함수
# ─────────────────────────────────────────────────────────────

def detect_action_category(text: str) -> Optional[str]:
    """첫 매칭 액션 카테고리 반환 (우선순위는 dict 삽입 순서)."""
    if not text:
        return None
    lower = text.lower()
    for category, keywords in ACTION_CATEGORIES.items():
        if any(kw in lower for kw in keywords):
            return category
    return None


def detect_entity_class(text: str) -> Optional[str]:
    """첫 매칭 엔티티 클래스 반환 (dict 순서: shipping_lane 최우선)."""
    if not text:
        return None
    lower = text.lower()
    for entity_class, keywords in ENTITY_CLASSES.items():
        if any(kw in lower for kw in keywords):
            return entity_class
    return None


def resolve_event_level(entity_class: str, action: str) -> int:
    """(엔티티 × 액션) 매트릭스로 provisional level 결정"""
    return _LEVEL_MATRIX.get((entity_class, action), _DEFAULT_FALLBACK_LEVEL)


def compute_impact_boost(entity_class: Optional[str], action: Optional[str]) -> float:
    """impact_score 에 더할 추가 부스트.

    - shipping_lane + (blockade | supply_disruption | attack): +2.5 (critical)
    - 그 외 fallback 성립: +1.5
    - fallback 미성립: 0.0
    """
    if entity_class is None or action is None:
        return 0.0
    if entity_class == "shipping_lane" and action in ("blockade", "supply_disruption", "attack"):
        return 2.5
    return 1.5
