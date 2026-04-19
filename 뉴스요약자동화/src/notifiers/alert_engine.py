"""룰 기반 알림 엔진 — NIAS v2.0

13종 알림 룰 (뉴스 5 + 지표 6 + 지정학 2)
쿨다운, 배치 큐, 일일 상한 관리
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from models.news_item import NewsItem
from models.market_indicator import MarketIndicator
import config as cfg

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    name: str
    condition: Callable
    channels: List[str]
    template: str
    cooldown_minutes: int = 30
    batch_window_minutes: int = 0  # 0 = 즉시

    def __repr__(self):
        return f"AlertRule({self.name})"


class AlertEngine:
    # 한 뉴스가 여러 룰에 매칭되면 상위 1개만 발송 (지정학 템플릿이 정보량 많으므로 우선)
    # 이벤트후보는 긴급속보 아래, 관심종목 위 — 키워드 miss 된 이벤트 fallback 경로
    NEWS_RULE_PRIORITY = [
        "지정학_L4", "지정학_L3", "긴급속보", "이벤트후보",
        "관심종목", "경제지표", "고영향뉴스",
    ]

    # 룰 이름 → 카테고리 매핑 (카테고리별 일일 상한용)
    _RULE_TO_CATEGORY: dict[str, str] = {
        "긴급속보": "urgent",
        "고영향뉴스": "high_impact",
        "관심종목": "watchlist",
        "경제지표": "indicator",
        "지정학_L3": "geopolitical",
        "지정학_L4": "geopolitical",
        "이벤트후보": "event_candidate",
        "VIX_경고": "market_alert",
        "VIX_패닉": "market_alert",
        "환율_급변": "market_alert",
        "유가_급변": "market_alert",
        "국채_급변": "market_alert",
        "야간선물_급변": "market_alert",
    }

    # 카테고리별 일일 상한 — 한 카테고리 소진이 다른 카테고리를 막지 않음
    # 총합 51건이지만 전체 차단 없음. max_daily_alerts는 fallback 통계용으로만 유지.
    CATEGORY_LIMITS: dict[str, int] = {
        "urgent": 6,
        "high_impact": 5,
        "watchlist": 5,
        "indicator": 5,
        "geopolitical": 10,
        "event_candidate": 5,
        "market_alert": 10,
        "other": 5,
    }

    def __init__(self, rules: List[AlertRule] = None, max_daily_alerts: int = 20):
        # max_daily_alerts 는 fallback 통계·로그용 상한 (차단에는 사용 안 함, 카테고리별 상한이 주 기준)
        self.rules = rules or self._default_rules()
        self.max_daily_alerts = max_daily_alerts
        self.cooldown_tracker: dict[str, datetime] = {}
        self.batch_queue: dict[str, dict] = {}
        self.daily_count = 0  # 전체 누적 카운터 (fallback 통계)
        self.category_counts: dict[str, int] = {}  # 카테고리별 카운터 (차단 기준)
        self.daily_reset_date = datetime.now().date()
        self.history_path = cfg.DATA_DIR / "alert_history.json"
        self.alert_history: list[dict] = []

    def _category_of(self, rule: AlertRule) -> str:
        """룰 → 카테고리 이름"""
        return self._RULE_TO_CATEGORY.get(rule.name, "other")

    def _check_category_limit(self, rule: AlertRule) -> bool:
        """해당 카테고리의 일일 상한 여유가 있으면 True"""
        cat = self._category_of(rule)
        limit = self.CATEGORY_LIMITS.get(cat, 5)
        return self.category_counts.get(cat, 0) < limit

    def _bump_category(self, rule: AlertRule) -> None:
        """발동 성공 시 카테고리 카운터 증가"""
        cat = self._category_of(rule)
        self.category_counts[cat] = self.category_counts.get(cat, 0) + 1

    def _default_rules(self) -> List[AlertRule]:
        """13종 기본 알림 룰"""
        return [
            # 뉴스 룰 (5종)
            AlertRule("긴급속보", lambda n: isinstance(n, NewsItem) and n.impact_score >= 8.0,
                     ["email", "telegram"], "urgent", cooldown_minutes=30),
            AlertRule("고영향뉴스", lambda n: isinstance(n, NewsItem) and n.impact_score >= 6.0,
                     ["email"], "high_impact", cooldown_minutes=60, batch_window_minutes=60),
            AlertRule("관심종목", lambda n: isinstance(n, NewsItem) and bool(n.tagged_stocks),
                     ["email"], "watchlist", cooldown_minutes=30, batch_window_minutes=30),
            # 이벤트후보 (단기안 Fallback) — 키워드 miss 되었으나 (엔티티×액션)로 승격된 뉴스
            AlertRule("이벤트후보",
                     lambda n: isinstance(n, NewsItem)
                               and getattr(n, "event_fallback", False)
                               and (n.impact_score or 0) >= 5.5,
                     ["email"], "urgent", cooldown_minutes=60, batch_window_minutes=0),
            AlertRule("경제지표", lambda n: isinstance(n, NewsItem) and n.source_type in ("FRED", "BOK"),
                     ["email"], "indicator", cooldown_minutes=0),
            # 일일리포트는 스케줄러에서 직접 트리거

            # 지표 룰 (6종)
            AlertRule("VIX_경고", lambda n: isinstance(n, MarketIndicator) and n.ticker == "^VIX" and n.current_value >= 25,
                     ["email"], "market_alert", cooldown_minutes=120),
            AlertRule("VIX_패닉", lambda n: isinstance(n, MarketIndicator) and n.ticker == "^VIX" and n.current_value >= 30,
                     ["email", "telegram"], "market_alert", cooldown_minutes=60),
            AlertRule("환율_급변", lambda n: isinstance(n, MarketIndicator) and n.ticker == "KRW/USD" and n.is_alert_worthy,
                     ["email"], "market_alert", cooldown_minutes=60),
            AlertRule("유가_급변", lambda n: isinstance(n, MarketIndicator) and n.ticker in ("CL=F", "BZ=F") and abs(n.change_pct) >= 5,
                     ["email"], "market_alert", cooldown_minutes=120),
            AlertRule("국채_급변", lambda n: isinstance(n, MarketIndicator) and n.ticker == "^TNX" and n.is_alert_worthy,
                     ["email"], "market_alert", cooldown_minutes=120),
            AlertRule("야간선물_급변", lambda n: isinstance(n, MarketIndicator) and n.ticker == "KOSPI200N" and n.is_alert_worthy,
                     ["email", "telegram"], "market_alert", cooldown_minutes=60),

            # 지정학 룰 (2종)
            AlertRule("지정학_L3", lambda n: isinstance(n, NewsItem) and (n.geo_level or 0) >= 3,
                     ["email", "telegram"], "geopolitical", cooldown_minutes=60),
            AlertRule("지정학_L4", lambda n: isinstance(n, NewsItem) and (n.geo_level or 0) >= 4,
                     ["email", "telegram"], "geopolitical", cooldown_minutes=30),
        ]

    def evaluate_news(self, items: List[NewsItem]) -> List[dict]:
        """뉴스 목록에 대해 알림 룰 평가 — 아이템당 최상위 우선순위 룰 1개만 발송

        조건 매칭이 전무한 뉴스 중 impact_score가 임계값 이상인 건은
        data/missed_events.json 에 기록되어 중기안 튜닝 입력으로 재사용됨.
        """
        self._check_daily_reset()
        alerts = []

        rule_map = {r.name: r for r in self.rules}
        prioritized = [rule_map[n] for n in self.NEWS_RULE_PRIORITY if n in rule_map]

        for item in items:
            any_condition_matched = False
            for rule in prioritized:
                try:
                    if not rule.condition(item):
                        continue
                    any_condition_matched = True
                    if not self._check_cooldown(rule, item):
                        break  # 쿨다운 중이면 하위 룰로 폴스루하지 않음 (중복 알림 방지)
                    # 전체 차단 로직 제거 — 카테고리별 상한 초과 시 하위 룰(다른 카테고리)로 fallthrough
                    if not self._check_category_limit(rule):
                        cat = self._category_of(rule)
                        logger.info(
                            f"[알림] 카테고리 '{cat}' 일일 상한 {self.CATEGORY_LIMITS.get(cat, 5)} 도달 "
                            f"— 하위 룰(다른 카테고리)로 fallthrough"
                        )
                        continue
                    alert = {
                        "rule": rule.name,
                        "channels": rule.channels,
                        "template": rule.template,
                        "item": item,
                        "timestamp": datetime.now().isoformat(),
                    }
                    if rule.batch_window_minutes == 0:
                        alerts.append(alert)
                        self.daily_count += 1
                        self._bump_category(rule)
                        self._record_cooldown(rule, item)
                    else:
                        self._add_to_batch(rule, alert)
                    break
                except Exception:
                    continue

            # 어떤 룰 조건도 매칭 안 된 경우 — 놓친 중요 뉴스로 의심. 별도 로그에 기록.
            if not any_condition_matched:
                try:
                    from utils.missed_events import log_missed_event
                    def _safe_match(rule, it):
                        try:
                            return bool(rule.condition(it))
                        except Exception:
                            return False
                    rule_checks = {r.name: _safe_match(r, item) for r in prioritized}
                    log_missed_event(item, rule_checks)
                except Exception:
                    pass

        return alerts

    def evaluate_indicators(self, indicators: List[MarketIndicator]) -> List[dict]:
        """시장지표에 대해 알림 룰 평가 — 카테고리별 상한 적용, 전체 차단 없음"""
        self._check_daily_reset()
        alerts = []

        for ind in indicators:
            if not ind.is_alert_worthy:
                continue

            for rule in self.rules:
                try:
                    if not rule.condition(ind):
                        continue
                    if not self._check_cooldown(rule, ind):
                        continue
                    if not self._check_category_limit(rule):
                        cat = self._category_of(rule)
                        logger.info(
                            f"[알림] 카테고리 '{cat}' 일일 상한 {self.CATEGORY_LIMITS.get(cat, 5)} 도달 "
                            f"— {rule.name} 차단 (같은 카테고리만 막힘)"
                        )
                        continue
                    alert = {
                        "rule": rule.name,
                        "channels": rule.channels,
                        "template": rule.template,
                        "item": ind,
                        "timestamp": datetime.now().isoformat(),
                    }
                    alerts.append(alert)
                    self.daily_count += 1
                    self._bump_category(rule)
                    self._record_cooldown(rule, ind)
                except Exception:
                    pass

        return alerts

    def flush_batches(self) -> List[dict]:
        """배치 윈도우 경과한 큐 발송"""
        now = datetime.now()
        flushed = []

        for rule_name in list(self.batch_queue.keys()):
            queue = self.batch_queue[rule_name]
            if now - queue["first_added"] >= timedelta(minutes=queue["window"]):
                flushed.extend(queue["items"])
                del self.batch_queue[rule_name]

        return flushed

    def _check_cooldown(self, rule: AlertRule, item) -> bool:
        """쿨다운 검사"""
        if rule.cooldown_minutes == 0:
            return True

        key = f"{rule.name}"
        if hasattr(item, "tagged_stocks") and item.tagged_stocks:
            key += f"_{item.tagged_stocks[0]}"
        elif hasattr(item, "ticker"):
            key += f"_{item.ticker}"

        last = self.cooldown_tracker.get(key)
        if last and (datetime.now() - last) < timedelta(minutes=rule.cooldown_minutes):
            return False
        return True

    def _record_cooldown(self, rule: AlertRule, item) -> None:
        """쿨다운 기록"""
        key = f"{rule.name}"
        if hasattr(item, "tagged_stocks") and item.tagged_stocks:
            key += f"_{item.tagged_stocks[0]}"
        elif hasattr(item, "ticker"):
            key += f"_{item.ticker}"
        self.cooldown_tracker[key] = datetime.now()

    def _add_to_batch(self, rule: AlertRule, alert: dict) -> None:
        """배치 큐에 추가"""
        if rule.name not in self.batch_queue:
            self.batch_queue[rule.name] = {
                "first_added": datetime.now(),
                "window": rule.batch_window_minutes,
                "items": [],
            }
        self.batch_queue[rule.name]["items"].append(alert)

    def _check_daily_reset(self):
        """일일 카운트 리셋 — 전체 합계 + 카테고리별 카운터 모두 리셋"""
        today = datetime.now().date()
        if today != self.daily_reset_date:
            self.daily_count = 0
            self.category_counts = {}
            self.daily_reset_date = today

    def save_history(self, alerts: List[dict]) -> None:
        """알림 이력 저장"""
        for alert in alerts:
            entry = {
                "rule": alert["rule"],
                "channels": alert["channels"],
                "timestamp": alert["timestamp"],
                "title": getattr(alert["item"], "title", "") or getattr(alert["item"], "name", ""),
            }
            self.alert_history.append(entry)

        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self.alert_history[-500:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"알림 이력 저장 실패: {e}")
