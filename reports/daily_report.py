"""투자 의사결정 리포트 v2 — 뉴스 요약이 아닌 "투자 판단 보고서"

구조:
1. 시장 판결 (전체 방향 + 확신도)
2. 섹터별 시그널 대시보드
3. 종목별 투자 신호표
4. 시간대별 주요 이벤트
5. TOP 뉴스 상세 분석
6. 리스크/기회 매트릭스
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import config as cfg
from models.news_item import NewsItem, TimeSlot, Direction, MarketDomain
from analyzers.signal_aggregator import MarketVerdict

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def generate_report(
    items: list[NewsItem],
    verdict: MarketVerdict,
    date_str: str | None = None,
) -> str:
    """투자 의사결정 리포트 생성"""
    if date_str is None:
        date_str = datetime.now(KST).strftime("%Y%m%d")

    today = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    bulls = verdict.total_bull
    bears = verdict.total_bear
    total = bulls + bears

    md = []

    # ═══════════════════ 1. 시장 판결 ═══════════════════
    md.append(f"# 📊 투자 의사결정 리포트 ({today})")
    md.append("")
    md.append(f"> {now_str} 기준 | 분석 대상 **{total}건**")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 🎯 오늘의 시장 판결")
    md.append("")

    dir_emoji = verdict.overall_direction.emoji
    dir_label = verdict.overall_direction.label_kr
    conf_pct = int(verdict.overall_confidence * 100)

    md.append(f"### {dir_emoji} {verdict.market_mood}")
    md.append("")
    md.append(f"| 항목 | 값 |")
    md.append(f"|------|------|")
    md.append(f"| 전체 방향 | **{dir_label}** ({conf_pct}% 확신) |")
    md.append(f"| BULL 뉴스 | 🟢 {bulls}건 ({bulls/total*100:.0f}%) |" if total > 0 else "| BULL | 0건 |")
    md.append(f"| BEAR 뉴스 | 🔴 {bears}건 ({bears/total*100:.0f}%) |" if total > 0 else "| BEAR | 0건 |")
    md.append("")

    # ═══════════════════ 2. 섹터 대시보드 ═══════════════════
    md.append("---")
    md.append("")
    md.append("## 📡 섹터별 시그널")
    md.append("")

    if verdict.sector_signals:
        md.append("| 섹터 | 방향 | 강도 | 뉴스수 | 관련 종목 |")
        md.append("|------|------|------|--------|-----------|")

        for sec in sorted(verdict.sector_signals.values(), key=lambda x: abs(x.net_score), reverse=True):
            dir_e = sec.direction.emoji
            mood = sec.mood
            stocks = ", ".join(sec.stocks[:4])
            net = f"{sec.net_score:+.1f}"
            md.append(f"| {sec.sector} | {dir_e} {mood} | {net} | {sec.news_count} | {stocks} |")
        md.append("")

    # ═══════════════════ 3. 종목별 투자 신호 ═══════════════════
    md.append("---")
    md.append("")
    md.append("## 📋 종목별 투자 신호")
    md.append("")

    if verdict.stock_signals:
        md.append("| 종목 | 방향 | 순점수 | 강도 | 행동제안 | 뉴스수 |")
        md.append("|------|------|--------|------|----------|--------|")

        for ss in sorted(verdict.stock_signals.values(), key=lambda x: abs(x.net_score), reverse=True):
            dir_e = ss.direction.emoji
            strength = ss.strength
            net = f"{ss.net_score:+.1f}"
            md.append(f"| {ss.stock_name} | {dir_e} {ss.direction.label_kr} | {net} | {strength} | **{ss.action}** | {ss.news_count} |")

        md.append("")

        # 종목별 상세 근거 (상위 5개)
        top_stocks = sorted(verdict.stock_signals.values(), key=lambda x: abs(x.net_score), reverse=True)[:5]
        for ss in top_stocks:
            if ss.top_reasons:
                md.append(f"**{ss.stock_name}** ({ss.sector})")
                for reason in ss.top_reasons:
                    md.append(f"  - {reason}")
                md.append("")

    # ═══════════════════ 4. 시간대별 이벤트 ═══════════════════
    md.append("---")
    md.append("")
    md.append("## ⏰ 시간대별 주요 이벤트")
    md.append("")

    slots = {slot: [] for slot in TimeSlot}
    for item in items:
        slot = item.time_slot or TimeSlot.MARKET_HOURS
        slots[slot].append(item)

    for slot in TimeSlot:
        slot_items = slots[slot]
        md.append(f"### {slot.emoji} {slot.value} ({len(slot_items)}건)")
        md.append("")
        if not slot_items:
            md.append("_해당 시간대 주요 뉴스 없음_")
        else:
            slot_items.sort(key=lambda x: x.impact_score, reverse=True)
            for item in slot_items[:8]:
                d = item.direction
                de = d.emoji if d else "⚪"
                dv = d.value if d else "?"
                tags = f" `{', '.join(item.tagged_stocks[:3])}`" if item.tagged_stocks else ""
                act = f" → **{item.action_suggestion}**" if item.action_suggestion else ""
                md.append(f"- [{dv}] {item.summary_1line or item.title[:50]} (영향도:{item.impact_score}){tags}{act}")
        md.append("")

    # ═══════════════════ 5. TOP 5 상세 분석 ═══════════════════
    md.append("---")
    md.append("")
    md.append("## 🔥 TOP 5 영향 뉴스 — 상세 분석")
    md.append("")

    top5 = sorted(items, key=lambda x: x.impact_score, reverse=True)[:5]
    for rank, item in enumerate(top5, 1):
        d = item.direction
        de = d.emoji if d else "⚪"
        dv = d.value if d else "N/A"
        conf_str = f"{int(item.confidence*100)}%" if item.confidence else "N/A"

        md.append(f"### {rank}위 — {de} {item.title}")
        md.append("")
        md.append(f"| 항목 | 값 |")
        md.append(f"|------|------|")
        md.append(f"| 영향도 | **{item.impact_score}/10** (긴급도:{item.urgency:.2f} 범위:{item.scope:.2f} 확실성:{item.certainty:.2f}) |")
        md.append(f"| 방향 | {de} **{dv}** ({conf_str} 확신) |")
        md.append(f"| 시장 영역 | {', '.join(d.emoji + d.value for d in item.market_domains)} |" if item.market_domains else "")
        md.append(f"| 출처 | {item.source} |")
        md.append(f"| 투자 시그널 | {item.investment_signal} |" if item.investment_signal else "")
        md.append(f"| 행동 제안 | **{item.action_suggestion}** |" if item.action_suggestion else "")
        md.append(f"| 리스크 | {item.risk_factor} |" if item.risk_factor else "")
        md.append("")

        if item.summary_3line:
            md.append("**분석:**")
            for line in item.summary_3line.split("\n"):
                md.append(f"> {line}")
            md.append("")

        if item.stock_impacts:
            md.append("**종목 영향:**")
            for si in item.stock_impacts[:5]:
                md.append(f"- {si.direction.emoji} **{si.stock_name}** (강도:{si.intensity}) — {si.reason}")
            md.append("")

        md.append(f"[원문]({item.url})")
        md.append("")

    # ═══════════════════ 6. 리스크/기회 매트릭스 ═══════════════════
    md.append("---")
    md.append("")
    md.append("## ⚖️ 리스크 / 기회 매트릭스")
    md.append("")

    md.append("### 🔴 핵심 리스크")
    if verdict.key_risks:
        for r in verdict.key_risks:
            md.append(f"- {r}")
    else:
        md.append("- 특이 리스크 없음")
    md.append("")

    md.append("### 🟢 핵심 기회")
    if verdict.key_opportunities:
        for o in verdict.key_opportunities:
            md.append(f"- {o}")
    else:
        md.append("- 특이 기회 없음")
    md.append("")

    # ═══════════════════ 시장 영역별 뉴스 분포 ═══════════════════
    domain_counts: dict[MarketDomain, int] = {}
    for item in items:
        for d in item.market_domains:
            domain_counts[d] = domain_counts.get(d, 0) + 1

    if domain_counts:
        md.append("---")
        md.append("")
        md.append("## 🗂️ 시장 영역별 뉴스 분포")
        md.append("")
        for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * min(20, count)
            md.append(f"- {domain.emoji} **{domain.value}**: {count}건 {bar}")
        md.append("")

    # 면책
    md.append("---")
    md.append("")
    md.append("*본 리포트는 뉴스 기반 자동 분석 결과이며, 투자 권유가 아닙니다. 투자 판단은 본인의 책임하에 이루어져야 합니다.*")

    # 파일 저장
    content = "\n".join(md)
    output_path = cfg.OUTPUT_DIR / f"daily_report_{date_str}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"[리포트] {output_path} 생성 ({len(items)}건, {len(content)}bytes)")
    return str(output_path)
