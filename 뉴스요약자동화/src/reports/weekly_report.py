"""주간 성과 리포트 — NIAS v2.0

지난 7일간의 알림/뉴스/지표를 종합하여 주간 성과를 평가.
매주 월요일 08:00 자동 발송 (스케줄러 등록) 또는 수동 실행.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import List

import config as cfg
from utils.db import get_connection

logger = logging.getLogger(__name__)


def generate_weekly_report(days: int = 7) -> dict:
    """주간 성과 데이터 수집 + 분석"""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # 뉴스 통계
    news = [dict(r) for r in conn.execute(
        "SELECT * FROM news_items WHERE collected_time >= ? ORDER BY impact_score DESC", (cutoff,)
    ).fetchall()]

    # 지표 통계
    indicators = [dict(r) for r in conn.execute(
        "SELECT * FROM market_indicators WHERE recorded_at >= ? ORDER BY recorded_at DESC", (cutoff,)
    ).fetchall()]

    conn.close()

    # 알림 이력
    alerts = []
    alert_path = cfg.DATA_DIR / "alert_history.json"
    if alert_path.exists():
        try:
            with open(alert_path, "r", encoding="utf-8") as f:
                all_alerts = json.load(f)
            cutoff_str = cutoff[:10]
            alerts = [a for a in all_alerts if a.get("timestamp", "")[:10] >= cutoff_str]
        except Exception:
            pass

    # ── 분석 ──

    # 뉴스 방향 분포
    directions = Counter(n.get("direction") for n in news)
    bull = directions.get("BULL", 0)
    bear = directions.get("BEAR", 0)
    none_dir = directions.get(None, 0)

    # 스코어 분포
    scores = [n.get("impact_score", 0) for n in news]
    avg_score = sum(scores) / len(scores) if scores else 0
    high_impact = sum(1 for s in scores if s >= 7)

    # 키워드 트렌드
    keyword_counter = Counter()
    for n in news:
        raw = n.get("matched_keywords", "[]")
        try:
            kws = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            kws = []
        keyword_counter.update(kws)
    top_keywords = keyword_counter.most_common(10)

    # 종목 언급 빈도
    stock_counter = Counter()
    for n in news:
        raw = n.get("tagged_stocks", "[]")
        try:
            stocks = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            stocks = []
        stock_counter.update(stocks)
    top_stocks = stock_counter.most_common(10)

    # 지정학
    geo_news = [n for n in news if n.get("geo_level")]
    geo_regions = Counter(n.get("geo_region") for n in geo_news)
    max_geo_level = max((n.get("geo_level", 0) for n in geo_news), default=0)

    # 지표 변동 요약
    latest_by_ticker = {}
    for ind in indicators:
        t = ind["ticker"]
        if t not in latest_by_ticker:
            latest_by_ticker[t] = ind

    # 알림 통계
    alert_rules = Counter(a.get("rule") for a in alerts)

    report = {
        "period": f"{(datetime.now() - timedelta(days=days)).strftime('%m/%d')} ~ {datetime.now().strftime('%m/%d')}",
        "total_news": len(news),
        "bull": bull, "bear": bear, "none_direction": none_dir,
        "avg_score": round(avg_score, 1),
        "high_impact": high_impact,
        "top_keywords": top_keywords,
        "top_stocks": top_stocks,
        "geo_count": len(geo_news),
        "geo_regions": dict(geo_regions),
        "max_geo_level": max_geo_level,
        "indicator_count": len(latest_by_ticker),
        "indicators": latest_by_ticker,
        "alert_count": len(alerts),
        "alert_rules": dict(alert_rules),
        "top5_news": news[:5],
    }
    return report


def build_weekly_email(report: dict) -> tuple[str, str]:
    """주간 성과 리포트 이메일 HTML"""
    period = report["period"]
    total = report["total_news"]
    bull = report["bull"]
    bear = report["bear"]
    avg = report["avg_score"]
    high = report["high_impact"]

    # 키워드 트렌드
    kw_html = ""
    for kw, cnt in report["top_keywords"][:7]:
        kw_html += f'<span style="display:inline-block;background:#e0e7ff;padding:3px 10px;border-radius:12px;margin:3px;font-size:13px;">{kw} ({cnt})</span>'

    # 종목 순위
    stock_html = ""
    for name, cnt in report["top_stocks"][:5]:
        stock_html += f"<tr><td style='padding:6px;'>{name}</td><td style='padding:6px; text-align:right;'>{cnt}건</td></tr>"

    # TOP 5 뉴스
    top_html = ""
    for n in report["top5_news"][:5]:
        d = "📈" if n.get("direction") == "BULL" else "📉" if n.get("direction") == "BEAR" else "⚪"
        top_html += f"<tr><td style='padding:6px;text-align:center;'>{n.get('impact_score',0)}</td><td style='padding:6px;'>{d} {n['title'][:55]}</td></tr>"

    # 알림 통계
    alert_html = ""
    for rule, cnt in sorted(report["alert_rules"].items(), key=lambda x: x[1], reverse=True):
        alert_html += f"<tr><td style='padding:6px;'>{rule}</td><td style='padding:6px;text-align:right;'>{cnt}건</td></tr>"

    # 지정학
    geo_text = ""
    if report["geo_count"]:
        geo_text = f"지정학 뉴스 {report['geo_count']}건 (최대 L{report['max_geo_level']})"

    ratio = bull / (bull + bear) * 100 if (bull + bear) > 0 else 50
    mood = "강세 우위" if ratio > 60 else "약세 우위" if ratio < 40 else "혼조"

    subject = f"📋 [NIAS 주간] {period} | {mood}, 고영향 {high}건"
    preheader = f'<span style="display:none!important;opacity:0;color:transparent;height:0;width:0;max-height:0;max-width:0;overflow:hidden;">뉴스 {total}건 분석. BULL {bull} vs BEAR {bear}. 키워드: {", ".join(k for k,_ in report["top_keywords"][:3])}</span>'

    html = f"""
    {preheader}
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', Arial, sans-serif; max-width: 620px; margin: 0 auto;">
      <div style="background: #4338ca; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0; font-size:20px;">📋 NIAS 주간 성과 리포트</h2>
        <p style="margin:6px 0 0; opacity:0.9; font-size:13px;">{period} | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
      </div>
      <div style="padding: 20px; border: 1px solid #ddd; border-top: none;">

        <div style="display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap;">
          <div style="flex:1; min-width:120px; background:#f0f4ff; padding:14px; border-radius:8px; text-align:center;">
            <div style="font-size:24px; font-weight:bold;">{total}</div>
            <div style="font-size:12px; color:#666;">분석 뉴스</div>
          </div>
          <div style="flex:1; min-width:120px; background:#ecfdf5; padding:14px; border-radius:8px; text-align:center;">
            <div style="font-size:24px; font-weight:bold; color:#22c55e;">{bull}</div>
            <div style="font-size:12px; color:#666;">BULL</div>
          </div>
          <div style="flex:1; min-width:120px; background:#fef2f2; padding:14px; border-radius:8px; text-align:center;">
            <div style="font-size:24px; font-weight:bold; color:#ef4444;">{bear}</div>
            <div style="font-size:12px; color:#666;">BEAR</div>
          </div>
          <div style="flex:1; min-width:120px; background:#fffbeb; padding:14px; border-radius:8px; text-align:center;">
            <div style="font-size:24px; font-weight:bold; color:#f59e0b;">{high}</div>
            <div style="font-size:12px; color:#666;">고영향 (7+)</div>
          </div>
        </div>

        <h3 style="margin:20px 0 8px;">🔑 주간 키워드 트렌드</h3>
        <div style="margin-bottom:16px;">{kw_html}</div>

        {'<h3 style="margin:20px 0 8px;">🏆 TOP 5 뉴스</h3><table style="width:100%%; border-collapse:collapse; font-size:13px;"><tr style="background:#f8f9fa;"><th style="padding:6px;width:40px;">점수</th><th style="padding:6px;">뉴스</th></tr>' + top_html + '</table>' if top_html else ''}

        {'<h3 style="margin:20px 0 8px;">🏷️ 종목 언급 TOP 5</h3><table style="width:100%%; border-collapse:collapse; font-size:13px;">' + stock_html + '</table>' if stock_html else ''}

        {'<h3 style="margin:20px 0 8px;">🔔 알림 발송 통계</h3><table style="width:100%%; border-collapse:collapse; font-size:13px;">' + alert_html + '</table>' if alert_html else '<p style="color:#999; font-size:13px;">이번 주 발송된 알림 없음</p>'}

        {f'<div style="background:#fff3cd; padding:12px; border-radius:6px; margin:16px 0; font-size:13px;">🌍 {geo_text}</div>' if geo_text else ''}

        <div style="background:#f1f5f9; padding:14px; border-radius:8px; margin:16px 0; font-size:13px;">
          <strong>📊 요약:</strong> 평균 영향도 {avg}, BULL 비율 {ratio:.0f}% ({mood})
          {'| 알림 ' + str(report["alert_count"]) + '건 발송' if report["alert_count"] else ''}
        </div>

        <hr style="margin:20px 0; border:none; border-top:1px solid #eee;">
        <p style="color: #999; font-size: 11px;">
          NIAS v2.0 주간 리포트 | 투자 판단의 최종 책임은 사용자에게 있습니다.
        </p>
      </div>
    </div>
    """
    return subject, html


def send_weekly_report(days: int = 7):
    """주간 리포트 생성 + 이메일 발송"""
    from notifiers.email_notifier import GmailNotifier

    report = generate_weekly_report(days)
    if report["total_news"] == 0:
        logger.info("[주간] 뉴스 없음 — 리포트 스킵")
        return

    subject, html = build_weekly_email(report)

    if cfg.ALERT_EMAIL_TO:
        notifier = GmailNotifier()
        result = notifier.send(cfg.ALERT_EMAIL_TO, subject, html)
        if result:
            logger.info(f"[주간] 리포트 발송: {subject[:50]}")

    logger.info(f"[주간] 분석: {report['total_news']}건, BULL {report['bull']} vs BEAR {report['bear']}, 고영향 {report['high_impact']}건")
