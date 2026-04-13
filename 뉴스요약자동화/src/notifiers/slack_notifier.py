"""Slack 웹훅 알림 — NIAS v2.0

Incoming Webhook으로 Slack 채널에 알림 전송.
Block Kit 포맷 + 시간 + 행동 제안 + 핵심 시나리오 포함.
"""
from __future__ import annotations

import logging
from datetime import datetime

import requests

import config as cfg
from models.news_item import NewsItem
from models.market_indicator import MarketIndicator

logger = logging.getLogger(__name__)


def _fmt_time(dt) -> str:
    """발행 시간 포맷"""
    if not dt:
        return "시간 미상"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt[:16]
    try:
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return str(dt)[:16]


def _now_str() -> str:
    return datetime.now().strftime("%m/%d %H:%M")


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
    """긴급 뉴스 Slack 알림 (시간 + 행동 + 시나리오)"""
    score = getattr(item, "impact_score", 0)
    direction = item.direction.value if item.direction else "?"
    d_emoji = ":chart_with_upwards_trend:" if direction == "BULL" else ":chart_with_downwards_trend:"
    signal = getattr(item, "investment_signal", "") or ""
    action = getattr(item, "action_suggestion", "") or "관망"
    risk = getattr(item, "risk_factor", "") or ""
    url = getattr(item, "url", "")
    pub_time = _fmt_time(getattr(item, "published_time", None))

    # 관련 종목
    import json
    stocks = getattr(item, "tagged_stocks", [])
    if isinstance(stocks, str):
        try:
            stocks = json.loads(stocks)
        except Exception:
            stocks = []
    stocks_str = ", ".join(stocks[:4]) if stocks else ""

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":rotating_light: [{score}점] ({pub_time}) {item.title[:45]}", "emoji": True}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f":clock1: *발행 {pub_time}* | 알림 {_now_str()} | 출처: {item.source}"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*방향:* {d_emoji} {direction} ({getattr(item, 'confidence', 0):.0%})"},
                {"type": "mrkdwn", "text": f"*행동:* *{action}*"},
            ]
        },
    ]

    # 시그널 + 리스크 (핵심 1줄씩)
    insight_parts = []
    if signal and signal not in ("강세 키워드 감지", "약세 키워드 감지", "분석 대기"):
        insight_parts.append(f":bulb: {signal[:80]}")
    if risk and risk != "키워드 기반 분석 — LLM 분석 불가 상태":
        insight_parts.append(f":warning: {risk[:80]}")
    if insight_parts:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(insight_parts)}
        })

    # 관련 종목
    if stocks_str:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":label: 관련 종목: {stocks_str}"}]
        })

    # 원문 버튼
    if url and url.startswith("http"):
        blocks.append({
            "type": "actions",
            "elements": [{"type": "button", "text": {"type": "plain_text", "text": ":newspaper: 원문 보기", "emoji": True}, "url": url}]
        })

    return send_slack(f":rotating_light: [{score}점] ({pub_time}) {item.title[:45]}", blocks)


def notify_indicator_alert(indicator: MarketIndicator) -> bool:
    """시장지표 Slack 알림 (시간 + 행동 + 시나리오)"""
    level_emoji = {
        "정상": ":large_green_circle:", "주의": ":large_yellow_circle:",
        "경고": ":large_orange_circle:", "위험": ":red_circle:", "극단": ":bangbang:",
    }.get(indicator.threshold_level.value, ":white_circle:")

    chg_emoji = ":small_red_triangle:" if indicator.change_pct > 0 else ":small_red_triangle_down:"

    # 이메일과 동일한 한줄 해석
    from notifiers.email_notifier import _indicator_oneliner
    oneliner = _indicator_oneliner(indicator)

    # 지표별 핵심 행동 1줄
    ticker = indicator.ticker
    val = indicator.current_value
    if ticker == "^VIX":
        if val >= 30: action_line = ":octagonal_sign: 위험자산 비중 축소. 추격 매도 금지"
        elif val >= 25: action_line = ":hand: 신규 매수 보류. 스톱로스 점검"
        else: action_line = ":white_check_mark: 정상 매매 가능"
    elif ticker in ("KRW/USD", "KRW/USD_ECOS"):
        if val >= 1450: action_line = ":hand: 내수주 매수 보류. 수출주 보유 유지"
        elif val >= 1400: action_line = ":eyes: 외국인 수급 주시. 수출�� 비중 확대"
        else: action_line = ":white_check_mark: 환율 중립"
    elif ticker in ("CL=F", "BZ=F"):
        if abs(indicator.change_pct) >= 5:
            action_line = f":hand: 에너지 관련 종목 추격 {'매수' if indicator.change_pct > 0 else '매도'} 금지"
        else: action_line = ":white_check_mark: 현 전략 유지"
    elif ticker == "^TNX":
        if val >= 5.0: action_line = ":octagonal_sign: 성장주/기술주 비중 축소"
        else: action_line = ":eyes: 금리 민감 섹터 모니터링"
    elif ticker == "KR_CPI":
        if val >= 3.0: action_line = ":hand: 금리 민감주 매수 보류"
        else: action_line = ":white_check_mark: 물가 안정. 금리 인하 수혜주 관심"
    elif ticker == "KR_EXPORT":
        if val >= 10: action_line = ":rocket: 수출주(반도체, 자동차) 비중 확대"
        elif val < 0: action_line = ":hand: 수출주 매수 보류. 방어주 관심"
        else: action_line = ":eyes: 수출주 선별적 접근"
    else:
        action_line = ":eyes: 모니터링 ���속"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{level_emoji} {indicator.name} {indicator.current_value} ({indicator.change_pct:+.1f}%)", "emoji": True}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f":clock1: {_now_str()} | 전일 {indicator.previous_close} | 상태: {indicator.threshold_level.value}"}
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{oneliner}*"}
        },
    ]

    # 임계값 돌파
    if indicator.threshold_breached:
        breached_text = "\n".join(f"• {b}" for b in indicator.threshold_breached[:2])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":warning: *임계값:*\n{breached_text}"}
        })

    # 행동 제안
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f":point_right: *행동:* {action_line}"}
    })

    # 시장 영향
    if indicator.market_implication:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":pushpin: {indicator.market_implication}"}]
        })

    return send_slack(
        f"{level_emoji} {indicator.name} {indicator.current_value} ({indicator.change_pct:+.1f}%) | {oneliner}",
        blocks,
    )


def notify_geopolitical(item: NewsItem) -> bool:
    """지정학 Slack 알림 (시간 + 행동 + 영향 체인)"""
    level = item.geo_level or 0
    region = item.geo_region or "미확인"
    level_names = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}
    level_bar = {1: ":green_square:", 2: ":yellow_square:", 3: ":orange_square:", 4: ":red_square:", 5: ":black_large_square:"}

    pub_time = _fmt_time(getattr(item, "published_time", None))
    chain = getattr(item, "impact_chain", "") or ""

    # 레벨별 행동 제안
    if level >= 5:
        action_line = ":octagonal_sign: 현금 비중 극대화. 위험자산 즉시 축소"
    elif level >= 4:
        action_line = ":hand: 위험자산 비중 축소. 방산주/안전자산 관심"
    elif level >= 3:
        action_line = ":eyes: 포트폴리오 헷지 검토. 해당 지역 관련주 주시"
    else:
        action_line = ":memo: 모니터링 지속"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":earth_asia: [L{level}] ({pub_time}) {region} — {item.title[:35]}", "emoji": True}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f":clock1: *발행 {pub_time}* | 알림 {_now_str()} | 출처: {item.source}"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*레벨:* {level_bar.get(level, '')} L{level} {level_names.get(level, '')}"},
                {"type": "mrkdwn", "text": f"*영향도:* {item.impact_score}/10"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":point_right: *행동:* {action_line}"}
        },
    ]

    if chain:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":link: *영향 체인:* {chain}"}
        })

    url = getattr(item, "url", "")
    if url and url.startswith("http"):
        blocks.append({
            "type": "actions",
            "elements": [{"type": "button", "text": {"type": "plain_text", "text": ":newspaper: 원문 보기", "emoji": True}, "url": url}]
        })

    return send_slack(f":earth_asia: [L{level}] ({pub_time}) {region} {item.title[:35]}", blocks)
