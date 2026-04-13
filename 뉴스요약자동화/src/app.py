"""NIAS v2.0 — Fintech Dashboard

Bloomberg / TradingView 스타일 대시보드
로직 변경 없음 — UI/UX 전면 리디자인
"""
from __future__ import annotations
import sys, json
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import config as cfg
from utils.db import get_recent_news, get_indicator_history, get_db_stats, get_connection
from utils.freshness import relative_time, is_stale

st.set_page_config(page_title="NIAS", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")

# ═══════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ═══════════════════════════════════════════════════════════
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* ══ GLOBAL — Toss-style clean ══ */
    .block-container { padding: 2rem 2.5rem 3rem; max-width: 1100px; }
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, 'Noto Sans KR', sans-serif; color: #191F28; }
    h1, h2, h3 { font-family: 'Inter', sans-serif !important; color: #191F28; }

    /* ══ VERDICT ══ */
    .verdict-banner {
        display: flex; align-items: center; gap: 12px;
        padding: 16px 22px; border-radius: 16px; margin-bottom: 24px;
        font-size: 15px; font-weight: 600; line-height: 1.5;
        border: none;
    }
    .verdict-bull  { background: #F2FBF5; color: #1B7D3A; }
    .verdict-bear  { background: #FFF0F0; color: #C73333; }
    .verdict-mixed { background: #FFF9EB; color: #8B6914; }

    /* ══ KPI GRID ══ */
    .kpi-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
        gap: 14px; margin-bottom: 24px;
    }
    .kpi-card {
        background: #FFFFFF; border: none; border-radius: 16px;
        padding: 20px; transition: all 0.2s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .kpi-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); transform: translateY(-2px); }
    .kpi-card.alert { background: #FFF5F5; box-shadow: 0 1px 3px rgba(220,38,38,0.1); }
    .kpi-label { font-size: 11px; color: #8B95A1; font-weight: 600; margin-bottom: 8px; letter-spacing: 0.5px; }
    .kpi-value { font-size: 26px; font-weight: 800; color: #191F28; line-height: 1.1; letter-spacing: -0.5px; }
    .kpi-delta { font-size: 13px; font-weight: 600; margin-top: 6px; }
    .kpi-delta.up { color: #16A34A; }
    .kpi-delta.down { color: #DC2626; }
    .kpi-delta.flat { color: #B0B8C1; }

    /* ══ NEWS CARD ══ */
    .news-card {
        background: #FFFFFF; border: none; border-radius: 14px;
        padding: 18px 20px; margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: all 0.2s ease;
        border-left: 3px solid transparent;
    }
    .news-card:hover { box-shadow: 0 4px 20px rgba(0,0,0,0.07); transform: translateY(-1px); }
    .news-card.bull { border-left-color: #22C55E; }
    .news-card.bear { border-left-color: #EF4444; }
    .news-title { font-size: 14px; font-weight: 600; color: #191F28; line-height: 1.55; margin-bottom: 8px; word-break: keep-all; }
    .news-meta { font-size: 12px; color: #B0B8C1; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .news-meta a { color: #8B95A1; text-decoration: none; font-weight: 500; }
    .news-meta a:hover { color: #191F28; }

    /* ══ PILL ══ */
    .pill {
        display: inline-flex; align-items: center; justify-content: center;
        padding: 3px 10px; border-radius: 20px;
        font-size: 11px; font-weight: 700; letter-spacing: 0.2px;
    }
    .pill-high  { background: #FEE2E2; color: #DC2626; }
    .pill-mid   { background: #FEF3C7; color: #D97706; }
    .pill-low   { background: #F3F4F6; color: #6B7280; }
    .pill-action { background: #EFF6FF; color: #2563EB; }
    .pill-geo   { background: #F3E8FF; color: #7C3AED; }
    .pill-green { background: #DCFCE7; color: #16A34A; }
    .pill-red   { background: #FEE2E2; color: #DC2626; }

    /* ══ STOCK CARD ══ */
    .stock-card {
        background: #FFFFFF; border: none; border-radius: 14px;
        padding: 16px 20px; margin-bottom: 8px;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: all 0.2s ease;
    }
    .stock-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.07); }
    .stock-name { font-weight: 700; font-size: 15px; color: #191F28; }
    .stock-bar { height: 6px; border-radius: 3px; background: #F3F4F6; flex: 1; margin: 0 16px; min-width: 60px; }
    .stock-bar-fill { height: 6px; border-radius: 3px; }

    /* ══ INDICATOR ROW ══ */
    .ind-row {
        background: #FFFFFF; border: none; border-radius: 14px;
        padding: 16px 20px; margin-bottom: 8px;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: all 0.2s ease;
    }
    .ind-row:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.07); }
    .ind-row.alert-row { background: #FFF5F5; box-shadow: 0 1px 3px rgba(220,38,38,0.08); }
    .ind-name { font-size: 13px; color: #4E5968; font-weight: 500; min-width: 130px; }
    .ind-val { font-size: 22px; font-weight: 800; color: #191F28; letter-spacing: -0.5px; }

    /* ══ GEO CARD ══ */
    .geo-card {
        border-left: 4px solid #D1D5DB; border-radius: 14px; padding: 16px 20px;
        margin-bottom: 10px; background: #FFFFFF;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: all 0.2s ease;
    }
    .geo-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.07); }
    .geo-card.l4 { border-left-color: #EF4444; background: #FFFAFA; }
    .geo-card.l3 { border-left-color: #F59E0B; background: #FFFDF7; }
    .geo-title { font-weight: 700; font-size: 15px; color: #191F28; }
    .geo-sub { font-size: 12px; color: #8B95A1; margin-top: 6px; line-height: 1.6; }
    .geo-sub a { color: #6B7280; text-decoration: none; }
    .geo-sub a:hover { color: #191F28; }

    /* ══ UTILITY ══ */
    .section-gap { margin-top: 28px; }
    .meta-bar { font-size: 12px; color: #B0B8C1; margin-bottom: 20px; font-weight: 500; }
    .stale { opacity: 0.35; }
    .old { opacity: 0.55; }

    /* ══ STREAMLIT OVERRIDES ══ */
    .stDeployButton { display: none; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stTabs [data-baseweb="tab"] { font-size: 14px; font-weight: 600; color: #8B95A1; padding: 12px 4px; }
    .stTabs [aria-selected="true"] { color: #191F28 !important; }
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; }
    .stSlider > div { padding: 0 !important; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def load_news(hours=48):
    return get_recent_news(hours=hours, limit=200)

@st.cache_data(ttl=300)
def load_indicators():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM market_indicators ORDER BY recorded_at DESC").fetchall()
    conn.close()
    seen, result = set(), []
    for r in [dict(r) for r in rows]:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            result.append(r)
    return result

stats = get_db_stats()
news_data = load_news(48)
indicators = load_indicators()

bull = sum(1 for n in news_data if n.get("direction") == "BULL")
bear = sum(1 for n in news_data if n.get("direction") == "BEAR")
total_dir = bull + bear
ratio = bull / total_dir if total_dir > 0 else 0.5
is_bull = ratio > 0.5
geo_count = sum(1 for n in news_data if n.get("geo_level"))

# ═══════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════
st.markdown('<p style="font-size:11px;color:#9ca3af;margin:0;">NIAS v2.0 · News-Invest Alert System</p>', unsafe_allow_html=True)

# Verdict Banner
if is_bull:
    v_cls = "verdict-mixed" if geo_count >= 3 else "verdict-bull"
    v_text = "강세 우위 · 추세 추종 매수 유효" + (" · 지정학 리스크 병존" if geo_count >= 3 else "")
    v_icon = "📈"
else:
    v_cls = "verdict-bear"
    v_text = "약세 흐름 · 신규 매수 보류" + (" · 지정학 리스크 확대" if geo_count >= 3 else " · 반등 확인 전 관망")
    v_icon = "📉"
st.markdown(f'<div class="verdict-banner {v_cls}">{v_icon} {v_text}</div>', unsafe_allow_html=True)

# KPI Grid
kpi_html = '<div class="kpi-grid">'
for ind in indicators[:8]:
    chg = ind.get("change_pct", 0) or 0
    level = ind.get("threshold_level", "정상")
    alert_cls = "alert" if level in ("위험", "극단", "경고") else ""
    delta_cls = "up" if chg > 0.01 else "down" if chg < -0.01 else "flat"
    delta_sign = "+" if chg > 0 else ""
    kpi_html += f'''
    <div class="kpi-card {alert_cls}">
        <div class="kpi-label">{ind["name"]}</div>
        <div class="kpi-value">{ind["current_value"]}</div>
        <div class="kpi-delta {delta_cls}">{delta_sign}{chg:.1f}%</div>
    </div>'''
kpi_html += '</div>'
st.markdown(kpi_html, unsafe_allow_html=True)

st.markdown(f'<div class="meta-bar">BULL {bull} · BEAR {bear} · 뉴스 {stats["news"]} · 지표 {stats["indicators"]} · {datetime.now().strftime("%H:%M")}</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs(["뉴스", "종목", "지표", "지정학", "히스토리"])

# ─── TAB 1: NEWS ───
with tab1:
    col1, col2 = st.columns([1, 1])
    with col1:
        min_score = st.slider("최소 점수", 1.0, 10.0, 5.0, 0.5, key="ns")
    with col2:
        dir_filter = st.selectbox("방향", ["전체", "BULL", "BEAR"], key="nd")

    filtered = [n for n in news_data if n.get("impact_score", 0) >= min_score]
    if dir_filter != "전체":
        filtered = [n for n in filtered if n.get("direction") == dir_filter]

    for idx, item in enumerate(filtered[:25]):
        score = item.get("impact_score", 0)
        direction = item.get("direction", "")
        title = item.get("title", "")[:70]
        action = item.get("action_suggestion", "")
        source = item.get("source", "")
        url = item.get("url", "")
        pub = item.get("published_time", "")
        signal = item.get("investment_signal", "")
        chain = item.get("impact_chain", "")
        geo_lv = item.get("geo_level")
        geo_rg = item.get("geo_region", "")
        age = relative_time(pub)

        card_cls = "bull" if direction == "BULL" else "bear" if direction == "BEAR" else ""
        fade = "stale" if is_stale(pub, 48) else "old" if is_stale(pub, 24) else ""
        pill_cls = "pill-high" if score >= 8 else "pill-mid" if score >= 6.5 else "pill-low"

        action_pill = f'<span class="pill pill-action">{action}</span>' if action and action != "관망" else ""
        geo_pill = f'<span class="pill pill-geo">L{geo_lv}</span>' if geo_lv else ""
        link_html = f'<a href="{url}" target="_blank">원문↗</a>' if url and url.startswith("http") else ""

        st.markdown(f'''
        <div class="news-card {card_cls} {fade}">
            <div class="news-title">
                <span class="pill {pill_cls}">{score}</span> {title} {action_pill} {geo_pill}
            </div>
            <div class="news-meta">
                <span>{source}</span><span>{age}</span>{link_html}
            </div>
        </div>''', unsafe_allow_html=True)

        if idx < 5 and (signal or chain):
            with st.expander("상세 분석", expanded=False):
                if signal and "키워드 감지" not in signal:
                    st.markdown(f"**💡 시그널:** {signal}")
                if chain:
                    st.markdown(f"**🔗 영향 체인:** {chain.replace('->', ' → ')}")
                if url and url.startswith("http"):
                    st.link_button("원문 보기", url)

# ─── TAB 2: STOCKS ───
with tab2:
    stock_scores = {}
    for n in news_data:
        raw = n.get("stock_impacts", "[]")
        try: impacts = json.loads(raw) if isinstance(raw, str) else raw
        except: continue
        for si in impacts:
            name = si.get("stock", "")
            if not name: continue
            if name not in stock_scores:
                stock_scores[name] = {"bull": 0, "bear": 0, "count": 0}
            w = si.get("intensity", 0.5) * n.get("impact_score", 5) / 10
            if si.get("direction") == "BULL":
                stock_scores[name]["bull"] += w
            else:
                stock_scores[name]["bear"] += w
            stock_scores[name]["count"] += 1

    if stock_scores:
        for name, s in sorted(stock_scores.items(), key=lambda x: abs(x[1]["bull"] - x[1]["bear"]), reverse=True):
            net = round(s["bull"] - s["bear"], 2)
            pill_cls = "pill-green" if net >= 1.5 else "pill-red" if net <= -1.5 else "pill-low"
            label = "매수" if net >= 1.5 else "축소" if net <= -1.5 else "관망"
            bar_w = min(100, abs(net) * 12)
            bar_c = "#22c55e" if net > 0 else "#ef4444"

            st.markdown(f'''
            <div class="stock-card">
                <div>
                    <span class="stock-name">{name}</span>
                    <span class="pill {pill_cls}" style="margin-left:8px;">{label}</span>
                </div>
                <div class="stock-bar"><div class="stock-bar-fill" style="background:{bar_c};width:{bar_w}%;"></div></div>
                <div style="text-align:right;min-width:90px;">
                    <span style="color:#22c55e;font-size:12px;">▲{s["bull"]:.1f}</span>
                    <span style="color:#ef4444;font-size:12px;margin-left:4px;">▼{s["bear"]:.1f}</span>
                    <div style="font-size:11px;color:#9ca3af;">{s["count"]}건</div>
                </div>
            </div>''', unsafe_allow_html=True)
    else:
        st.info("종목 데이터 없음")

# ─── TAB 3: INDICATORS ───
with tab3:
    if indicators:
        for ind in indicators:
            level = ind.get("threshold_level", "정상")
            chg = ind.get("change_pct", 0) or 0
            alert_cls = "alert-row" if level in ("위험", "극단", "경고") else ""
            delta_c = "#16a34a" if chg > 0 else "#dc2626" if chg < 0 else "#9ca3af"

            st.markdown(f'''
            <div class="ind-row {alert_cls}">
                <span class="ind-name">{ind["name"]}</span>
                <span class="ind-val">{ind["current_value"]}</span>
                <span style="color:{delta_c};font-size:13px;font-weight:600;min-width:60px;text-align:right;">{chg:+.1f}%</span>
                <span style="font-size:11px;color:#9ca3af;min-width:40px;text-align:right;">{level}</span>
            </div>''', unsafe_allow_html=True)

        st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)
        sel = st.selectbox("지표 추이", [i["ticker"] for i in indicators],
                           format_func=lambda t: next((i["name"] for i in indicators if i["ticker"] == t), t))
        hist = get_indicator_history(sel, 7)
        if hist:
            df = pd.DataFrame(hist)
            fig = px.line(df, x="recorded_at", y="current_value")
            fig.update_traces(line_color="#2563eb", line_width=2)
            fig.update_layout(
                height=220, margin=dict(l=0, r=0, t=8, b=0),
                xaxis=dict(showgrid=False, title=""), yaxis=dict(showgrid=True, gridcolor="#f3f4f6", title=""),
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)

# ─── TAB 4: GEOPOLITICS ───
with tab4:
    geo_news = [n for n in news_data if n.get("geo_level")]
    if geo_news:
        regions = {}
        for n in geo_news:
            r = n.get("geo_region", "기타")
            if r not in regions:
                regions[r] = {"level": 0, "news": []}
            regions[r]["level"] = max(regions[r]["level"], n.get("geo_level", 0))
            regions[r]["news"].append(n)

        level_name = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}

        for region, data in sorted(regions.items(), key=lambda x: x[1]["level"], reverse=True):
            lv = data["level"]
            geo_cls = "l4" if lv >= 4 else "l3" if lv >= 3 else ""
            color = "#dc2626" if lv >= 4 else "#d97706" if lv >= 3 else "#374151"

            news_html = ""
            for n in sorted(data["news"], key=lambda x: x.get("impact_score", 0), reverse=True)[:3]:
                url = n.get("url", "")
                link = f' <a href="{url}" target="_blank">원문↗</a>' if url and url.startswith("http") else ""
                news_html += f'<div class="geo-sub">[{n.get("impact_score",0)}] {n["title"][:55]}{link}</div>'

            st.markdown(f'''
            <div class="geo-card {geo_cls}">
                <div class="geo-title" style="color:{color};">L{lv} {region} <span style="font-weight:400;font-size:12px;color:#6b7280;">— {level_name.get(lv, "")} · {len(data["news"])}건</span></div>
                {news_html}
            </div>''', unsafe_allow_html=True)
    else:
        st.info("지정학 뉴스 없음")

# ─── TAB 5: HISTORY ───
with tab5:
    hist_days = st.selectbox("기간", [7, 14, 30], format_func=lambda d: f"최근 {d}일")
    conn_h = get_connection()
    hist_news = [dict(r) for r in conn_h.execute(
        f"SELECT * FROM news_items WHERE collected_time >= datetime('now','-{hist_days} days','localtime') ORDER BY collected_time DESC"
    ).fetchall()]
    conn_h.close()

    if hist_news:
        kw_counter = Counter()
        for n in hist_news:
            raw = n.get("matched_keywords", "[]")
            try: kws = json.loads(raw) if isinstance(raw, str) else raw
            except: kws = []
            kw_counter.update(kws)

        if kw_counter:
            kw_df = pd.DataFrame(kw_counter.most_common(12), columns=["키워드", "빈도"])
            fig = px.bar(kw_df, x="키워드", y="빈도")
            fig.update_traces(marker_color="#2563eb")
            fig.update_layout(
                height=220, margin=dict(l=0, r=0, t=8, b=0),
                xaxis=dict(title=""), yaxis=dict(title="", showgrid=True, gridcolor="#f3f4f6"),
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            csv = pd.DataFrame(hist_news).to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV 다운로드", csv, f"nias_{hist_days}d.csv", "text/csv")
        with col2:
            st.metric("수집 뉴스", len(hist_news))

# ─── FOOTER ───
st.markdown('<div style="height:40px"></div>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;font-size:10px;color:#d1d5db;">NIAS v2.0 · 자동 생성된 참고 정보 · 투자 판단의 최종 책임은 사용자에게 있습니다</p>', unsafe_allow_html=True)
