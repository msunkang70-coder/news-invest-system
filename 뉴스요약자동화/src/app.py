"""NIAS v2.0 — Streamlit 대시보드

실시간 뉴스 + 시장지표 + 지정학 통합 대시보드 (한국어)
Usage: streamlit run src/app.py
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
import pandas as pd
import plotly.express as px

import config as cfg
from utils.db import get_recent_news, get_indicator_history, get_db_stats, get_connection

st.set_page_config(
    page_title="NIAS v2.0 — 투자 알람",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── 데이터 로드 ───
@st.cache_data(ttl=300)
def load_news(hours=48):
    return get_recent_news(hours=hours, limit=200)

@st.cache_data(ttl=300)
def load_all_indicators():
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM market_indicators
        WHERE recorded_at >= datetime('now', '-24 hours', 'localtime')
        ORDER BY recorded_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=300)
def load_alerts():
    path = cfg.DATA_DIR / "alert_history.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# ─── 데이터 준비 ───
stats = get_db_stats()
news_data = load_news(48)
indicators_data = load_all_indicators()

latest_indicators = {}
for ind in indicators_data:
    t = ind["ticker"]
    if t not in latest_indicators:
        latest_indicators[t] = ind

bull_count = sum(1 for n in news_data if n.get("direction") == "BULL")
bear_count = sum(1 for n in news_data if n.get("direction") == "BEAR")
none_count = sum(1 for n in news_data if not n.get("direction"))
total_dir = bull_count + bear_count
bull_ratio = bull_count / total_dir if total_dir > 0 else 0.5
market_direction = "강세(BULL)" if bull_ratio > 0.5 else "약세(BEAR)"
confidence = abs(bull_ratio - 0.5) * 2

vix_val = latest_indicators.get("^VIX", {}).get("current_value", "-")
krw_val = latest_indicators.get("KRW/USD", {}).get("current_value", "-")
wti_val = latest_indicators.get("CL=F", {}).get("current_value", "-")
tnx_val = latest_indicators.get("^TNX", {}).get("current_value", "-")

# ─── 커스텀 CSS ───
st.markdown("""
<style>
.summary-card {
    padding: 16px; border-radius: 10px; margin-bottom: 8px;
    border-left: 5px solid; font-size: 14px;
}
.card-bull { background: #f0fdf4; border-color: #22c55e; }
.card-bear { background: #fef2f2; border-color: #ef4444; }
.card-geo  { background: #fffbeb; border-color: #f59e0b; }
.card-neutral { background: #f8fafc; border-color: #94a3b8; }
.score-badge {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-weight: bold; font-size: 12px; color: white; margin-right: 6px;
}
.score-high { background: #ef4444; }
.score-mid  { background: #f59e0b; }
.score-low  { background: #94a3b8; }
</style>
""", unsafe_allow_html=True)

# ─── 헤더 ───
direction_emoji = "📈" if "강세" in market_direction else "📉"
st.markdown(f"## {direction_emoji} NIAS v2.0 — 실시간 투자 알람")

# ═══ 요약 대시보드 (첫 화면, 한눈에 파악) ═══

# 행 1: 시장 판단 + 핵심 지표 6개
col_m, col_v, col_fx, col_oil, col_bond, col_fg = st.columns(6)

# 시장 방향
dir_color = "🟢" if "강세" in market_direction else "🔴"
col_m.metric("시장 방향", f"{dir_color} {market_direction}", f"BULL {bull_count} / BEAR {bear_count}")

# VIX
vix_ind = latest_indicators.get("^VIX", {})
vix_chg = vix_ind.get("change_pct", 0)
col_v.metric("VIX 공포지수", vix_val, f"{vix_chg:+.1f}%" if vix_chg else None,
             delta_color="inverse")

# 환율
krw_ind = latest_indicators.get("KRW/USD", latest_indicators.get("KRW/USD_ECOS", {}))
krw_chg = krw_ind.get("change_pct", 0)
col_fx.metric("원달러", krw_val, f"{krw_chg:+.1f}%" if krw_chg else None,
              delta_color="inverse")

# 유가
wti_ind = latest_indicators.get("CL=F", {})
wti_chg = wti_ind.get("change_pct", 0)
col_oil.metric("WTI 유가", wti_val, f"{wti_chg:+.1f}%" if wti_chg else None)

# 국채
tnx_ind = latest_indicators.get("^TNX", {})
tnx_chg = tnx_ind.get("change_pct", 0)
col_bond.metric("US 10Y", tnx_val, f"{tnx_chg:+.1f}%" if tnx_chg else None,
                delta_color="inverse")

# 공포/탐욕
fg_ind = latest_indicators.get("CRYPTO_FG", {})
fg_val = fg_ind.get("current_value", "-")
col_fg.metric("Crypto F&G", fg_val)

# 행 2: TOP 3 뉴스 카드 + 지정학 요약
st.markdown("---")

top3 = sorted(news_data, key=lambda x: x.get("impact_score", 0), reverse=True)[:3]
geo_news_all = [n for n in news_data if n.get("geo_level")]

col_news, col_geo = st.columns([3, 1])

with col_news:
    st.markdown("##### 🏆 핵심 뉴스 TOP 3")
    for rank, n in enumerate(top3, 1):
        score = n.get("impact_score", 0)
        direction = n.get("direction", "")
        title = n.get("title", "")[:70]
        action = n.get("action_suggestion", "")
        source = n.get("source", "")
        url = n.get("url", "")
        signal = n.get("investment_signal", "") or ""
        risk = n.get("risk_factor", "") or ""
        pub = n.get("published_time", "") or ""
        geo_lv = n.get("geo_level")
        geo_rg = n.get("geo_region", "")
        chain = n.get("impact_chain", "") or ""

        # 종목
        stocks_raw = n.get("tagged_stocks", "[]")
        try:
            stocks = json.loads(stocks_raw) if isinstance(stocks_raw, str) else stocks_raw
        except Exception:
            stocks = []
        stocks_str = ", ".join(stocks[:3]) if stocks else ""

        # 발행일
        pub_str = ""
        if pub:
            try:
                pub_str = pub[:10] if len(str(pub)) >= 10 else str(pub)
            except Exception:
                pass

        # 카드 색상
        if direction == "BULL":
            border = "#22c55e"; bg = "#f0fdf4"; d_icon = "📈"; d_label = "강세"
        elif direction == "BEAR":
            border = "#ef4444"; bg = "#fef2f2"; d_icon = "📉"; d_label = "약세"
        else:
            border = "#94a3b8"; bg = "#f8fafc"; d_icon = "⚪"; d_label = "미판정"

        badge_bg = "#ef4444" if score >= 8 else "#f59e0b" if score >= 6.5 else "#94a3b8"

        # 행동 뱃지
        action_color = "#22c55e" if action in ("적극매수", "분할매수") else "#ef4444" if action in ("비중축소", "매도검토") else "#64748b"

        # 시그널 (fallback 기본값 필터)
        signal_html = ""
        if signal and "키워드 감지" not in signal:
            signal_html = f'<div style="margin-top:6px;font-size:12px;">💡 {signal[:60]}</div>'

        # 종목 + 지정학
        meta_parts = []
        if stocks_str:
            meta_parts.append(f"🏷 {stocks_str}")
        if geo_lv:
            meta_parts.append(f"🌍 L{geo_lv} {geo_rg}")
        if chain:
            meta_parts.append(f"🔗 {chain[:40]}")
        meta_html = " &nbsp;|&nbsp; ".join(meta_parts)

        link_html = f'<a href="{url}" target="_blank" style="color:{border};font-size:11px;text-decoration:none;">원문 보기 →</a>' if url and url.startswith("http") else ""

        st.markdown(
            f'<div style="background:{bg}; border-left:5px solid {border}; padding:14px 16px; border-radius:10px; margin-bottom:10px;">'
            # 1행: 점수 + 제목
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<span style="background:{badge_bg};color:white;padding:3px 10px;border-radius:14px;font-weight:bold;font-size:13px;">{score}</span>'
            f'<span style="font-size:15px;font-weight:bold;line-height:1.3;">{d_icon} {title}</span>'
            f'</div>'
            # 2행: 방향 + 행동 + 출처 + 일자
            f'<div style="margin-top:6px;font-size:12px;color:#555;">'
            f'<span style="background:{action_color};color:white;padding:1px 8px;border-radius:10px;font-size:11px;">{d_label} → {action or "관망"}</span>'
            f' &nbsp; {source} &nbsp; {pub_str} &nbsp; {link_html}'
            f'</div>'
            # 3행: 시그널
            f'{signal_html}'
            # 4행: 종목/지정학/체인
            f'{"<div style=margin-top:4px;font-size:11px;color:#888;>" + meta_html + "</div>" if meta_html else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

with col_geo:
    st.markdown("##### 🌍 지정학 리스크")
    if geo_news_all:
        region_max = {}
        for n in geo_news_all:
            r = n.get("geo_region", "기타")
            region_max[r] = max(region_max.get(r, 0), n.get("geo_level", 0))

        level_bar = {1: "■□□□□", 2: "■■□□□", 3: "■■■□□", 4: "■■■■□", 5: "■■■■■"}
        level_color = {1: "#22c55e", 2: "#eab308", 3: "#f97316", 4: "#ef4444", 5: "#991b1b"}

        for region, level in sorted(region_max.items(), key=lambda x: x[1], reverse=True):
            bar = level_bar.get(level, "?")
            color = level_color.get(level, "#666")
            st.markdown(
                f'<span style="color:{color};font-weight:bold;font-size:13px;">{bar} L{level} {region}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("분류된 지정학 뉴스 없음")

st.caption(f"뉴스 {stats['news']}건 | 지표 {stats['indicators']}건 | 갱신: {datetime.now().strftime('%H:%M')}")
st.divider()

# ─── 탭 ───
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📰 실시간 뉴스", "📈 종목 시그널", "📊 시장지표", "🌍 지정학 리스크", "🔔 알림 이력", "📋 히스토리"]
)

# ═══════════════ 탭 1: 실시간 뉴스 ═══════════════
with tab1:
    st.subheader("📰 실시간 뉴스 피드")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        min_score = st.slider("최소 영향도 점수", 1.0, 10.0, 5.0, 0.5, key="news_score")
    with col_f2:
        direction_filter = st.selectbox("방향 필터", ["전체", "BULL (강세)", "BEAR (약세)", "미판정"], key="news_dir")
    with col_f3:
        source_filter = st.selectbox("소스 유형", ["전체", "RSS", "SNS", "DART", "FRED", "BOK"], key="news_src")

    filtered = [n for n in news_data if n.get("impact_score", 0) >= min_score]
    if "BULL" in direction_filter:
        filtered = [n for n in filtered if n.get("direction") == "BULL"]
    elif "BEAR" in direction_filter:
        filtered = [n for n in filtered if n.get("direction") == "BEAR"]
    elif "미판정" in direction_filter:
        filtered = [n for n in filtered if not n.get("direction")]
    if source_filter != "전체":
        filtered = [n for n in filtered if n.get("source_type") == source_filter]

    st.caption(f"총 {len(filtered)}건 (필터 적용)")

    if filtered:
        for i, item in enumerate(filtered[:20], 1):
            score = item.get("impact_score", 0)
            direction = item.get("direction")
            d_emoji = "🟢" if direction == "BULL" else "🔴" if direction == "BEAR" else "⚪"
            d_label = "강세" if direction == "BULL" else "약세" if direction == "BEAR" else "미판정"
            geo_tag = f" | 🌍 L{item['geo_level']} {item.get('geo_region', '')}" if item.get("geo_level") else ""
            source = item.get("source", "")
            title = item.get("title", "")
            url = item.get("url", "")
            action = item.get("action_suggestion", "")

            # 색상 코딩
            if direction == "BULL":
                card_class = "card-bull"
            elif direction == "BEAR":
                card_class = "card-bear"
            elif item.get("geo_level"):
                card_class = "card-geo"
            else:
                card_class = "card-neutral"

            if score >= 8:
                badge_class = "score-high"
            elif score >= 6.5:
                badge_class = "score-mid"
            else:
                badge_class = "score-low"

            action_html = f" → <b>{action}</b>" if action and action not in ("관망", "-", "") else ""
            link_html = f' <a href="{url}" target="_blank" style="font-size:11px;">원문</a>' if url and url.startswith("http") else ""

            # 카드 형태로 표시
            st.markdown(
                f'<div class="summary-card {card_class}">'
                f'<span class="score-badge {badge_class}">{score}</span>'
                f'{d_emoji} {title[:75]}{action_html}{geo_tag}'
                f'<br><span style="color:#888;font-size:11px;">{source} ({item.get("source_type","RSS")}){link_html}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # 상세 펼치기 (상위 5건만)
            if i <= 5:
                with st.expander(f"상세 보기 — {title[:40]}", expanded=False):
                    snippet = item.get("snippet", "")
                    if snippet:
                        st.markdown(f"> {snippet[:200]}")

                    col_a1, col_a2, col_a3 = st.columns(3)
                    col_a1.markdown(f"**방향:** {d_emoji} {d_label}")
                    col_a2.markdown(f"**행동:** {action or '관망'}")
                    col_a3.markdown(f"**확신도:** {item.get('confidence', 0):.0%}")

                    signal = item.get("investment_signal", "")
                    if signal and "키워드 감지" not in signal:
                        st.info(f"💡 {signal}")

                    risk = item.get("risk_factor", "")
                    if risk and "키워드 기반" not in risk:
                        st.warning(f"⚠️ {risk}")

                    chain = item.get("impact_chain", "")
                    if chain:
                        st.success(f"🔗 {chain}")

                    stocks_raw = item.get("tagged_stocks", "[]")
                    if isinstance(stocks_raw, str):
                        try: stocks = json.loads(stocks_raw)
                        except: stocks = []
                    else: stocks = stocks_raw
                    if stocks:
                        st.markdown(f"🏷️ {', '.join(stocks)}")

                    if url and url.startswith("http"):
                        st.link_button("📄 원본 기사", url)
    else:
        st.info("조건에 맞는 뉴스가 없습니다.")

# ═══════════════ 탭 2: 종목 시그널 ═══════════════
with tab2:
    st.subheader("📈 종목별 투자 시그널")

    stock_scores = {}
    for n in news_data:
        impacts_raw = n.get("stock_impacts", "[]")
        if isinstance(impacts_raw, str):
            try:
                impacts = json.loads(impacts_raw)
            except Exception:
                continue
        else:
            impacts = impacts_raw

        for si in impacts:
            name = si.get("stock", "")
            if not name:
                continue
            if name not in stock_scores:
                stock_scores[name] = {"bull": 0, "bear": 0, "count": 0, "reasons": []}
            score_weight = si.get("intensity", 0.5) * n.get("impact_score", 5) / 10
            if si.get("direction") == "BULL":
                stock_scores[name]["bull"] += score_weight
            else:
                stock_scores[name]["bear"] += score_weight
            stock_scores[name]["count"] += 1
            reason = si.get("reason", "")
            if reason and len(stock_scores[name]["reasons"]) < 3:
                stock_scores[name]["reasons"].append(f"{si.get('direction','?')}: {reason}")

    if stock_scores:
        rows = []
        for name, s in stock_scores.items():
            net = round(s["bull"] - s["bear"], 2)
            if net >= 3.0: action = "🟢 적극매수"
            elif net >= 1.5: action = "🟢 분할매수"
            elif net >= 0.5: action = "🔵 관심 유지"
            elif net >= -0.5: action = "⚪ 관망"
            elif net >= -1.5: action = "🟠 리스크 주의"
            elif net >= -3.0: action = "🔴 비중축소"
            else: action = "🔴 매도 검토"
            rows.append({
                "종목": name,
                "강세 점수": round(s["bull"], 1),
                "약세 점수": round(s["bear"], 1),
                "순점수": net,
                "뉴스 수": s["count"],
                "행동 제안": action,
            })

        df_stock = pd.DataFrame(rows).sort_values("순점수", ascending=False)

        fig = px.bar(df_stock, x="종목", y=["강세 점수", "약세 점수"],
                     barmode="group",
                     color_discrete_map={"강세 점수": "#22c55e", "약세 점수": "#ef4444"},
                     title="종목별 강세/약세 시그널")
        fig.update_layout(yaxis_title="시그널 점수", legend_title="방향")
        st.plotly_chart(fig, use_container_width=True)

        # 종목별 카드 (색상 코딩)
        for _, row in df_stock.iterrows():
            net = row["순점수"]
            if net >= 1.5:
                card_class = "card-bull"
            elif net <= -1.5:
                card_class = "card-bear"
            else:
                card_class = "card-neutral"

            st.markdown(
                f'<div class="summary-card {card_class}" style="padding:10px;">'
                f'<b>{row["종목"]}</b> &nbsp; {row["행동 제안"]} &nbsp; '
                f'<span style="color:#22c55e;">▲{row["강세 점수"]}</span> / '
                f'<span style="color:#ef4444;">▼{row["약세 점수"]}</span> &nbsp; '
                f'순점수: <b>{net:+.1f}</b> &nbsp; 뉴스 {row["뉴스 수"]}건'
                f'</div>',
                unsafe_allow_html=True,
            )

        # 종목별 상세
        for name, s in sorted(stock_scores.items(), key=lambda x: abs(x[1]["bull"] - x[1]["bear"]), reverse=True)[:5]:
            if s["reasons"]:
                with st.expander(f"🏷️ {name} — 근거 뉴스"):
                    for r in s["reasons"]:
                        st.markdown(f"- {r}")
    else:
        st.info("종목 시그널 데이터가 없습니다. 파이프라인 실행 후 확인해 주세요.")

# ═══════════════ 탭 3: 시장지표 ═══════════════
with tab3:
    st.subheader("📊 시장지표 현황")

    if latest_indicators:
        cols = st.columns(4)
        for i, (ticker, ind) in enumerate(latest_indicators.items()):
            col = cols[i % 4]
            chg = ind.get("change_pct", 0)
            level = ind.get("threshold_level", "정상")
            emoji = {"정상": "🟢", "주의": "🟡", "경고": "🟠", "위험": "🔴", "극단": "🚨"}.get(level, "⚪")
            col.metric(
                label=f"{emoji} {ind['name']}",
                value=f"{ind['current_value']}",
                delta=f"{chg:+.1f}%",
            )

        # 임계값 돌파 현황
        breached = []
        for ticker, ind in latest_indicators.items():
            raw = ind.get("threshold_breached", "[]")
            if isinstance(raw, str):
                try:
                    items = json.loads(raw)
                except Exception:
                    items = []
            else:
                items = raw
            if items:
                for b in items:
                    breached.append({"지표": ind["name"], "상태": ind.get("threshold_level", ""), "내용": b})

        if breached:
            st.subheader("⚠️ 임계값 돌파 현황")
            st.dataframe(pd.DataFrame(breached), use_container_width=True, hide_index=True)

        # 히스토리 차트
        st.subheader("📈 지표 추이")
        selected_ticker = st.selectbox(
            "지표 선택",
            list(latest_indicators.keys()),
            format_func=lambda t: latest_indicators[t]["name"],
            key="ind_select",
        )
        history = get_indicator_history(selected_ticker, days=7)
        if history:
            df_hist = pd.DataFrame(history)
            fig = px.line(df_hist, x="recorded_at", y="current_value",
                          title=f"{latest_indicators[selected_ticker]['name']} 추이",
                          labels={"recorded_at": "시간", "current_value": "값"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("히스토리 데이터가 부족합니다. 파이프라인을 여러 번 실행하면 차트가 생성됩니다.")
    else:
        st.info("시장지표 데이터가 없습니다. `python src/main.py` 를 먼저 실행해 주세요.")

# ═══════════════ 탭 4: 지정학 리스크 ═══════════════
with tab4:
    st.subheader("🌍 지정학 리스크 현황")

    geo_news = [n for n in news_data if n.get("geo_level")]

    if geo_news:
        # 지역별 에스컬레이션 요약
        region_data = {}
        for n in geo_news:
            region = n.get("geo_region", "기타")
            level = n.get("geo_level", 0)
            if region not in region_data:
                region_data[region] = {"max_level": 0, "count": 0, "news": []}
            region_data[region]["max_level"] = max(region_data[region]["max_level"], level)
            region_data[region]["count"] += 1
            region_data[region]["news"].append(n)

        level_bar = {1: "■□□□□", 2: "■■□□□", 3: "■■■□□", 4: "■■■■□", 5: "■■■■■"}
        level_name = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}
        level_color = {1: "green", 2: "orange", 3: "orange", 4: "red", 5: "darkred"}

        for region, data in sorted(region_data.items(), key=lambda x: x[1]["max_level"], reverse=True):
            level = data["max_level"]
            bar = level_bar.get(level, "?")
            name = level_name.get(level, "?")
            color = level_color.get(level, "gray")

            level_bg = {1: "#f0fdf4", 2: "#fffbeb", 3: "#fff7ed", 4: "#fef2f2", 5: "#fef2f2"}
            level_border = {1: "#22c55e", 2: "#eab308", 3: "#f97316", 4: "#ef4444", 5: "#991b1b"}

            # 지역 카드
            st.markdown(
                f'<div style="background:{level_bg.get(level,"#f8f8f8")}; border-left:5px solid {level_border.get(level,"#ccc")}; '
                f'padding:12px; border-radius:8px; margin-bottom:8px;">'
                f'<b style="font-size:15px;">{bar} L{level} {region}</b> — {name} ({data["count"]}건)'
                f'</div>',
                unsafe_allow_html=True,
            )

            with st.expander(f"L{level} {region} 뉴스 상세", expanded=(level >= 4)):
                for n in sorted(data["news"], key=lambda x: x.get("impact_score", 0), reverse=True)[:5]:
                    score = n.get("impact_score", 0)
                    title = n.get("title", "")
                    url = n.get("url", "")
                    conflict = n.get("geo_conflict_type", "")

                    badge = "score-high" if score >= 8 else "score-mid" if score >= 6.5 else "score-low"
                    link = f' <a href="{url}" target="_blank" style="font-size:11px;">원문</a>' if url and url.startswith("http") else ""

                    st.markdown(
                        f'<span class="score-badge {badge}">{score}</span> {title[:65]}'
                        f'{"  <span style=color:#888;font-size:11px;>" + conflict + "</span>" if conflict else ""}'
                        f'{link}',
                        unsafe_allow_html=True,
                    )

                chain = n.get("impact_chain", "")
                if chain:
                    st.info(f"🔗 영향 체인: {chain}")
    else:
        st.info("지정학 분류된 뉴스가 없습니다. 지정학 전문 RSS에서 수집된 뉴스가 표시됩니다.")

# ═══════════════ 탭 5: 알림 이력 ═══════════════
with tab5:
    st.subheader("🔔 알림 발송 이력")

    alerts = load_alerts()
    if alerts:
        df_alerts = pd.DataFrame(alerts)
        df_alerts = df_alerts.rename(columns={
            "rule": "알림 룰",
            "channels": "채널",
            "timestamp": "발송 시간",
            "title": "제목",
        })
        st.dataframe(df_alerts.tail(50).iloc[::-1], use_container_width=True, hide_index=True)

        # 룰별 통계
        st.subheader("📊 룰별 알림 통계")
        rule_counts = {}
        for a in alerts:
            r = a.get("rule", "?")
            rule_counts[r] = rule_counts.get(r, 0) + 1
        if rule_counts:
            fig = px.bar(
                x=list(rule_counts.keys()),
                y=list(rule_counts.values()),
                labels={"x": "알림 룰", "y": "발송 건수"},
                title="알림 룰별 발송 현황",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.metric("총 알림 건수", len(alerts))
    else:
        st.info("알림 이력이 없습니다. 파이프라인 실행 시 알림이 기록됩니다.")

# ═══════════════ 탭 6: 히스토리 ═══════════════
with tab6:
    st.subheader("📋 데이터 히스토리 + 트렌드")

    hist_days = st.selectbox("기간 선택", [7, 14, 30], format_func=lambda d: f"최근 {d}일", key="hist_days")

    # 키워드 트렌드
    conn_h = get_connection()
    hist_news = [dict(r) for r in conn_h.execute(f"""
        SELECT * FROM news_items
        WHERE collected_time >= datetime('now', '-{hist_days} days', 'localtime')
        ORDER BY collected_time DESC
    """).fetchall()]
    conn_h.close()

    if hist_news:
        from collections import Counter

        # 키워드 트렌드
        kw_counter = Counter()
        for n in hist_news:
            raw = n.get("matched_keywords", "[]")
            try:
                kws = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                kws = []
            kw_counter.update(kws)

        if kw_counter:
            st.subheader("🔑 키워드 트렌드")
            kw_df = pd.DataFrame(kw_counter.most_common(15), columns=["키워드", "빈도"])
            fig_kw = px.bar(kw_df, x="키워드", y="빈도", title=f"최근 {hist_days}일 키워드 빈도",
                           color="빈도", color_continuous_scale="Blues")
            st.plotly_chart(fig_kw, use_container_width=True)

        # 종목 언급 빈도
        stock_counter = Counter()
        for n in hist_news:
            raw = n.get("tagged_stocks", "[]")
            try:
                stocks = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                stocks = []
            stock_counter.update(stocks)

        if stock_counter:
            st.subheader("🏷️ 종목 언급 빈도")
            st_df = pd.DataFrame(stock_counter.most_common(10), columns=["종목", "언급 수"])
            fig_st = px.bar(st_df, x="종목", y="언급 수", title=f"최근 {hist_days}일 종목 언급",
                           color="언급 수", color_continuous_scale="Greens")
            st.plotly_chart(fig_st, use_container_width=True)

        # 일별 뉴스 수
        st.subheader("📊 일별 뉴스 수집량")
        daily = Counter()
        for n in hist_news:
            day = (n.get("collected_time") or "")[:10]
            if day:
                daily[day] += 1
        if daily:
            daily_df = pd.DataFrame(sorted(daily.items()), columns=["날짜", "건수"])
            fig_daily = px.bar(daily_df, x="날짜", y="건수", title=f"최근 {hist_days}일 일별 수집량")
            st.plotly_chart(fig_daily, use_container_width=True)

        # 스코어 분포
        st.subheader("📈 영향도 분포")
        score_bins = Counter()
        for n in hist_news:
            s = int(n.get("impact_score", 0))
            score_bins[f"{s}-{s+1}"] = score_bins.get(f"{s}-{s+1}", 0) + 1
        if score_bins:
            sb_df = pd.DataFrame(sorted(score_bins.items()), columns=["점수 구간", "건수"])
            fig_sb = px.bar(sb_df, x="점수 구간", y="건수", title="영향도 스코어 분포")
            st.plotly_chart(fig_sb, use_container_width=True)

        # CSV 내보내기 버튼
        st.subheader("📥 데이터 내보내기")
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            csv_news = pd.DataFrame(hist_news).to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 뉴스 CSV 다운로드", csv_news,
                               f"nias_news_{hist_days}d.csv", "text/csv")
        with col_exp2:
            conn_i = get_connection()
            ind_data = [dict(r) for r in conn_i.execute(f"""
                SELECT * FROM market_indicators
                WHERE recorded_at >= datetime('now', '-{hist_days} days', 'localtime')
            """).fetchall()]
            conn_i.close()
            if ind_data:
                csv_ind = pd.DataFrame(ind_data).to_csv(index=False).encode("utf-8-sig")
                st.download_button("📥 지표 CSV 다운로드", csv_ind,
                                   f"nias_indicators_{hist_days}d.csv", "text/csv")

        st.metric("총 뉴스", len(hist_news))
    else:
        st.info("히스토리 데이터가 없습니다. 파이프라인 운영 후 데이터가 축적됩니다.")

# ─── 푸터 ───
st.divider()
st.caption(
    f"NIAS v2.0 | 마지막 갱신: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
    f"⚠️ 본 대시보드는 자동 생성된 참고 정보입니다. 투자 판단의 최종 책임은 사용자에게 있습니다."
)
