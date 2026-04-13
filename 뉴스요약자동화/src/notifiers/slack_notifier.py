"""Slack 웹훅 알림 — NIAS v2.0

Incoming Webhook으로 Slack 채널에 알림 전송.
Block Kit 포맷으로 구조화된 메시지 전송.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

import config as cfg
from models.news_item import NewsItem
from models.market_indicator import MarketIndicator

logger = logging.getLogger(__name__)


def send_slack(text: str, blocks: list = None) -> bool:
    """Slack 웹훅으로 메시지 전송"""
    url = cfg.SLACK_WEBHOOK_URL
    if not url or not url.startswith("https://hooks.slack.com"):
        return False

    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.text == "ok":
            logger.info(f"[Slack] 발송 성공: {text[:40]}")
            return True
        else:
            logger.warning(f"[Slack] 발송 실패: {resp.status_code} {resp.text[:50]}")
            return False
    except Exception as e:
        logger.warning(f"[Slack] 발송 에러: {e}")
        return False


def notify_urgent_news(item: NewsItem) -> bool:
    """긴급 뉴스 Slack 알림"""
    score = getattr(item, "impact_score", 0)
    direction = item.direction.value if item.direction else "?"
    d_emoji = ":chart_with_upwards_trend:" if direction == "BULL" else ":chart_with_downwards_trend:"
    geo = f" | L{item.geo_level} {item.geo_region}" if item.geo_level else ""
    signal = getattr(item, "investment_signal", "") or ""
    action = getattr(item, "action_suggestion", "") or ""
    url = getattr(item, "url", "")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":rotating_light: [{score}점] {item.title[:50]}", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*방향:* {d_emoji} {direction}"},
                {"type": "mrkdwn", "text": f"*출처:* {item.source}"},
                {"type": "mrkdwn", "text": f"*행동:* {action or '관망'}"},
                {"type": "mrkdwn", "text": f"*영향도:* {score}/10{geo}"},
            ]
        },
    ]

    if signal:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":bulb: *시그널:* {signal}"}
        })

    if url and url.startswith("http"):
        blocks.append({
            "type": "actions",
            "elements": [{"type": "button", "text": {"type": "plain_text", "text": ":newspaper: 원문 보기"}, "url": url}]
        })

    return send_slack(f":rotating_light: [{score}점] {item.title[:50]}", blocks)


def notify_indicator_alert(indicator: MarketIndicator) -> bool:
    """시장지표 임계값 Slack 알림"""
    level_emoji = {
        "정상": ":large_green_circle:", "주의": ":large_yellow_circle:",
        "경고": ":large_orange_circle:", "위험": ":red_circle:", "극단": ":bangbang:",
    }.get(indicator.threshold_level.value, ":white_circle:")

    chg_emoji = ":small_red_triangle:" if indicator.change_pct > 0 else ":small_red_triangle_down:"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{level_emoji} {indicator.name} {indicator.current_value}", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*변동률:* {chg_emoji} {indicator.change_pct:+.1f}%"},
                {"type": "mrkdwn", "text": f"*전일:* {indicator.previous_close}"},
                {"type": "mrkdwn", "text": f"*상태:* {indicator.threshold_level.value}"},
            ]
        },
    ]

    if indicator.threshold_breached:
        breached_text = "\n".join(f"• {b}" for b in indicator.threshold_breached)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":warning: *임계값 돌파:*\n{breached_text}"}
        })

    if indicator.market_implication:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":pushpin: *시장 영향:* {indicator.market_implication}"}
        })

    return send_slack(
        f"{level_emoji} {indicator.name} {indicator.current_value} ({indicator.change_pct:+.1f}%)",
        blocks,
    )


def notify_geopolitical(item: NewsItem) -> bool:
    """지정학 Slack 알림"""
    level = item.geo_level or 0
    region = item.geo_region or "미확인"
    level_bar = {1: ":green_square:", 2: ":yellow_square:", 3: ":orange_square:", 4: ":red_square:", 5: ":black_large_square:"}.get(level, "")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":earth_asia: [L{level}] {region} — {item.title[:40]}", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*레벨:* {level_bar} L{level}"},
                {"type": "mrkdwn", "text": f"*지역:* {region}"},
                {"type": "mrkdwn", "text": f"*영향도:* {item.impact_score}/10"},
            ]
        },
    ]

    chain = getattr(item, "impact_chain", "")
    if chain:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":link: *영향 체인:* {chain}"}
        })

    return send_slack(f":earth_asia: [L{level}] {region} {item.title[:40]}", blocks)
