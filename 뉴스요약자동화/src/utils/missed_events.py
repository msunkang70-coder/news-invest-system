"""누락 이벤트 로거 — 중기안 학습 데이터 수집용

목적:
  impact_score가 임계값을 넘었음에도 모든 알림 룰에서 탈락한 뉴스를 기록.
  향후 event_type_classifier(중기안)의 튜닝 데이터로 활용.
  주간 리포트에서 "놓친 뉴스 TOP N"로도 노출 가능.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import config as cfg

logger = logging.getLogger(__name__)

MISSED_EVENTS_PATH = cfg.DATA_DIR / "missed_events.json"
MAX_ENTRIES = 2000  # 롤링 보관 상한
_MIN_IMPACT_TO_LOG = 5.0  # 이 이상인 뉴스만 '놓친 사례'로 기록


def log_missed_event(item, rule_check_results: dict) -> None:
    """모든 알림 룰에 탈락한 뉴스 기록.

    Parameters:
        item: NewsItem
        rule_check_results: {rule_name: bool} — 각 룰 조건 매칭 여부
    """
    try:
        impact = getattr(item, "impact_score", 0.0) or 0.0
        if impact < _MIN_IMPACT_TO_LOG:
            return

        reasons = []
        if impact < 8.0:
            reasons.append(f"impact_score {impact:.1f} < 8.0 (긴급속보 미달)")
        geo = getattr(item, "geo_level", None) or 0
        if geo < 3:
            reasons.append(f"geo_level={geo} < 3 (지정학 룰 미달)")
        if not getattr(item, "tagged_stocks", None):
            reasons.append("tagged_stocks 없음 (관심종목 미매칭)")
        source_type = getattr(item, "source_type", "")
        if source_type not in ("FRED", "BOK"):
            reasons.append(f"source_type={source_type} (경제지표 미해당)")
        if impact < 6.0:
            reasons.append(f"impact_score {impact:.1f} < 6.0 (고영향뉴스 미달)")
        if not getattr(item, "event_fallback", False):
            reasons.append("event_fallback=False (이벤트후보 미매칭)")

        direction_val = None
        d = getattr(item, "direction", None)
        if d is not None and hasattr(d, "value"):
            direction_val = d.value

        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "title": (getattr(item, "title", "") or "")[:200],
            "source": getattr(item, "source", ""),
            "source_type": source_type,
            "url": (getattr(item, "url", "") or "")[:300],
            "impact_score": impact,
            "geo_level": getattr(item, "geo_level", None),
            "geo_region": getattr(item, "geo_region", None),
            "event_fallback": getattr(item, "event_fallback", False),
            "event_category": getattr(item, "event_category", None),
            "event_entity_class": getattr(item, "event_entity_class", None),
            "direction": direction_val,
            "tagged_stocks": getattr(item, "tagged_stocks", []),
            "rule_checks": rule_check_results,
            "reasons": reasons,
        }

        existing = []
        if MISSED_EVENTS_PATH.exists():
            try:
                with open(MISSED_EVENTS_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []

        existing.append(entry)
        if len(existing) > MAX_ENTRIES:
            existing = existing[-MAX_ENTRIES:]

        MISSED_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MISSED_EVENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[missed_events] 기록: [{impact:.1f}] {entry['title'][:60]} "
            f"— 사유: {', '.join(reasons[:2])}"
        )
    except Exception as e:
        logger.warning(f"[missed_events] 저장 실패: {e}")


def get_missed_events(limit: int = 100) -> list[dict]:
    """최근 누락 이벤트 조회 (대시보드/리포트용)"""
    if not MISSED_EVENTS_PATH.exists():
        return []
    try:
        with open(MISSED_EVENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[-limit:]
    except Exception:
        pass
    return []
