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
    def __init__(self, rules: List[AlertRule] = None, max_daily_alerts: int = 10):  # QA 개선: 20→10
        self.rules = rules or self._default_rules()
        self.max_daily_alerts = max_daily_alerts
        self.cooldown_tracker: dict[str, datetime] = {}
        self.batch_queue: dict[str, dict] = {}
        self.daily_count = 0
        self.daily_reset_date = datetime.now().date()
        self.history_path = cfg.DATA_DIR / "alert_history.json"
        self.alert_history: list[dict] = []

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
        """뉴스 목록에 대해 알림 룰 평가"""
        self._check_daily_reset()
        alerts = []

        for item in items:
            for rule in self.rules:
                try:
                    if rule.condition(item):
                        if self._check_cooldown(rule, item) and self.daily_count < self.max_daily_alerts:
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
                                self._record_cooldown(rule, item)
                            else:
                                self._add_to_batch(rule, alert)
                except Exception:
                    pass

        return alerts

    def evaluate_indicators(self, indicators: List[MarketIndicator]) -> List[dict]:
        """시장지표에 대해 알림 룰 평가"""
        self._check_daily_reset()
        alerts = []

        for ind in indicators:
            if not ind.is_alert_worthy:
                continue

            for rule in self.rules:
                try:
                    if rule.condition(ind):
                        if self._check_cooldown(rule, ind) and self.daily_count < self.max_daily_alerts:
                            alert = {
                                "rule": rule.name,
                                "channels": rule.channels,
                                "template": rule.template,
                                "item": ind,
                                "timestamp": datetime.now().isoformat(),
                            }
                            alerts.append(alert)
                            self.daily_count += 1
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
        """일일 카운트 리셋"""
        today = datetime.now().date()
        if today != self.daily_reset_date:
            self.daily_count = 0
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
