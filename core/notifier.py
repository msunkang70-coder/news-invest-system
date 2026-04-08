"""Telegram 알림 발송"""

import io
import sys
import logging
import requests
from datetime import datetime

from core.models import get_conn, get_unnotified, mark_notified

logger = logging.getLogger(__name__)

DIRECTION_EMOJI = {
    "positive": "긍정(+)",
    "negative": "부정(-)",
    "neutral": "중립(=)",
    "mixed": "혼합(+-)",
}


def format_message(item: dict) -> str:
    """알림 메시지 포맷"""
    direction_text = DIRECTION_EMOJI.get(item["direction"], item["direction"])
    bar_filled = int(item["impact"] * 10)
    bar = "#" * bar_filled + "." * (10 - bar_filled)
    return (
        f"[{item['stock_name']}] 관련 뉴스\n"
        f"------------------------------\n"
        f"{item['title']}\n\n"
        f"방향: {direction_text}\n"
        f"영향도: [{bar}] {item['impact']:.2f}\n"
        f"관련도: {item['relevance']:.2f}\n\n"
        f"분석: {item['reasoning']}\n\n"
        f"링크: {item['url']}\n"
        f"출처: {item['source']} | {item.get('published', '')}"
    )


def format_telegram_message(item: dict) -> str:
    """Telegram HTML 포맷 메시지"""
    direction_emoji = {"positive": "🟢", "negative": "🔴",
                       "neutral": "⚪", "mixed": "🟡"}.get(item["direction"], "")
    return (
        f"📰 <b>[{item['stock_name']}]</b> 관련 뉴스\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 {item['title']}\n\n"
        f"{direction_emoji} 영향도: {item['impact']:.2f} | 관련도: {item['relevance']:.2f}\n\n"
        f"💬 {item['reasoning']}\n\n"
        f"🔗 <a href=\"{item['url']}\">원문 보기</a>\n"
        f"📡 {item['source']}"
    )


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Telegram 메시지 전송"""
    if not bot_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"[알림] Telegram 응답: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"[알림] Telegram 전송 실패: {e}")
        return False


def _check_cooldown(config: dict, stock_id: int, cooldown_min: int) -> bool:
    """동일 종목에 대해 cooldown 시간 내 알림이 있었는지 확인.
    True면 쿨다운 중(알림 보류)."""
    if cooldown_min <= 0:
        return False
    conn = get_conn(config)
    row = conn.execute("""
        SELECT COUNT(*) FROM notifications n
        JOIN analysis a ON n.analysis_id = a.id
        WHERE a.stock_id = ?
          AND n.status IN ('sent', 'console')
          AND n.sent_at >= datetime('now','localtime',?)
    """, (stock_id, f"-{cooldown_min} minutes")).fetchone()
    conn.close()
    return row[0] > 0


def should_alert(item: dict, config: dict) -> tuple[bool, str]:
    """알림 트리거 조건 확인. (통과여부, 사유) 반환."""
    alert_cfg = config.get("alert", {})
    min_rel = alert_cfg.get("min_relevance", 0.5)
    min_imp = alert_cfg.get("min_impact", 0.4)
    directions = alert_cfg.get("directions", ["positive", "negative", "mixed"])
    cooldown = alert_cfg.get("cooldown_minutes", 30)

    if item["relevance"] < min_rel:
        return False, f"관련도 부족({item['relevance']:.2f}<{min_rel})"
    if item["impact"] < min_imp:
        return False, f"영향도 부족({item['impact']:.2f}<{min_imp})"
    if item["direction"] not in directions:
        return False, f"방향 제외({item['direction']})"

    # 조용한 시간대 체크
    now_hour = datetime.now().hour
    quiet_start = alert_cfg.get("quiet_hours_start", 23)
    quiet_end = alert_cfg.get("quiet_hours_end", 7)
    if quiet_start > quiet_end:
        if now_hour >= quiet_start or now_hour < quiet_end:
            return False, "조용한 시간대"
    elif quiet_start <= now_hour < quiet_end:
        return False, "조용한 시간대"

    # 쿨다운 체크
    if _check_cooldown(config, item["stock_id"], cooldown):
        return False, f"쿨다운 중({cooldown}분)"

    return True, "조건 충족"


def notify_all(config: dict):
    """미발송 분석 결과 중 조건 충족 건 알림 발송"""
    tg_cfg = config.get("telegram", {})
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("chat_id", "")
    has_telegram = bool(bot_token and chat_id)

    items = get_unnotified(config)
    logger.info(f"[알림] 미발송 {len(items)}건 확인")

    sent_count = 0
    skip_reasons = {}

    for item in items:
        ok, reason = should_alert(item, config)
        if not ok:
            mark_notified(config, item["analysis_id"], status="skipped")
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        if has_telegram:
            msg = format_telegram_message(item)
            success = send_telegram(bot_token, chat_id, msg)
            status = "sent" if success else "failed"
        else:
            msg = format_message(item)
            try:
                out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                       errors="replace", line_buffering=True)
                out.write(f"\n{'='*50}\n{msg}\n{'='*50}\n\n")
                out.flush()
                out.detach()  # stdout.buffer 해제
            except Exception:
                print(msg)
            status = "console"

        mark_notified(config, item["analysis_id"], status=status)
        if status in ("sent", "console"):
            sent_count += 1

    # 스킵 사유 로그
    if skip_reasons:
        reasons_str = ", ".join(f"{k}:{v}건" for k, v in skip_reasons.items())
        logger.info(f"[알림] 스킵 사유: {reasons_str}")

    logger.info(f"[알림 완료] 발송 {sent_count}건 | 스킵 {sum(skip_reasons.values())}건")
