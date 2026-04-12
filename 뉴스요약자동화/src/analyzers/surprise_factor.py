"""경제지표 서프라이즈 팩터 — NIAS v2.0

실제 발표값과 시장 컨센서스의 괴리를 정량화.
서프라이즈가 클수록 시장 영향이 크다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def calculate_surprise(indicator_name: str, actual: float, expected: float) -> dict:
    """서프라이즈 팩터 계산

    Returns:
        dict with: actual, expected, surprise, surprise_pct, grade, impact_boost, direction
    """
    if expected == 0:
        return _default_result(actual, expected)

    surprise = actual - expected
    surprise_pct = surprise / abs(expected) * 100

    abs_pct = abs(surprise_pct)
    if abs_pct >= 10:
        grade = "MEGA_SURPRISE"
        impact_boost = 2.0
    elif abs_pct >= 5:
        grade = "BIG_SURPRISE"
        impact_boost = 1.5
    elif abs_pct >= 2:
        grade = "MODERATE_SURPRISE"
        impact_boost = 1.2
    else:
        grade = "IN_LINE"
        impact_boost = 1.0

    # CPI/인플레 기준: 실제 > 예상 → HAWKISH (금리 인상 방향)
    direction = "HAWKISH" if surprise > 0 else "DOVISH"

    result = {
        "indicator": indicator_name,
        "actual": actual,
        "expected": expected,
        "surprise": round(surprise, 4),
        "surprise_pct": round(surprise_pct, 2),
        "grade": grade,
        "impact_boost": impact_boost,
        "direction": direction,
        "description": (
            f"{indicator_name}: {actual} (예상 {expected}, "
            f"서프라이즈 {surprise:+.2f}, {grade})"
        ),
    }

    if grade != "IN_LINE":
        logger.info(f"[서프라이즈] {result['description']}")

    return result


def _default_result(actual: float, expected: float) -> dict:
    return {
        "actual": actual,
        "expected": expected,
        "surprise": 0,
        "surprise_pct": 0,
        "grade": "IN_LINE",
        "impact_boost": 1.0,
        "direction": "NEUTRAL",
        "description": f"expected=0, 계산 불가",
    }
