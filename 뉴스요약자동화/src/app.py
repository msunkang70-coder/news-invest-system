"""NIAS v2.0 — 대시보드 (클린 리디자인)

금융 대시보드 스타일: 절제된 색상, 여백, 1줄 요약 + 펼치기 상세
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
from utils.freshness import relative_time, is_stale

st.set_page_config(page_title="NIAS", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

# ─── 클린 CSS ───
st.markdown("""
<style>
    /* 전체 톤 다운 */
    .block-container { padding-top: 1.5rem; }
    h2 { font-size: 1.4rem !important; margin-bottom: 0 !important; }

    /* 카드 공통 */
    .n-card {
        padding: 10px 14px; border-radius: 6px; margin-bottom: 6px;
        border-left: 4px solid; font-size: 13px; line-height: 1.5;
    }
    .n-bull { background: #f8fdf8; border-color: #16a34a; }
    .n-bear { background: #fef8f8; border-color: #dc2626; }
    .n-neutral { background: #f9fafb; border-color: #d1d5db; }

    /* 뱃지 */
    .b { display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px; font-weight:600; color:white; margin-right:4px; }
    .b-red { background:#dc2626; }
    .b-amber { background:#d97706; }
    .b-gray { background:#9ca3af; }
    .b-green { background:#16a34a; }
    .b-action { background:#1d4ed8; }

    /* 한줄 판단 바 */
    .verdict { padding:8px 14px; border-radius:6px; font-size:14px; font-weight:600; margin-bottom:10px; }

    /* 체인 */
    .chain { background:#fffbeb; border:1px solid #fde68a; border-radius:4px; padding:4px 10px; font-size:11px; margin-top:4px; display:inline-block; }

    /* 흐린 카드 */
    .stale { opacity:0.45; }
    .old { opacity:0.65; }

    /* 서브텍스트 */
    .sub { color:#6b7280; font-size:11px; }
</style>
""", unsafe_allow_html=True)

# ─── 데이터 ───
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

# ─── 헤더: 한줄 판단 ───
st.markdown("## 📊 NIAS")

geo_count = sum(1 for n in news_data if n.get("geo_level"))
if is_bull:
    v_text = "강세 우위. 추세 추종 매수 유효" + (", 지정학 리스크 병존" if geo_count >= 3 else "")
    v_bg = "#dcfce7" if geo_count < 3 else "#fef9c3"
else:
    v_text = "약세 흐름. 신규 매수 보류" + (", 지정학 리스크 확대" if geo_count >= 3 else ", 반등 확인 전 관망")
    v_bg = "#fee2e2"
st.markdown(f'<div class="verdict" style="background:{v_bg};">{"📈" if is_bull else "📉"} {v_text}</div>', unsafe_allow_html=True)

# ─── 지표 요약 (이상 있는 것만 강조) ───
alert_inds = [i for i in indicators if i.get("threshold_level") not in ("정상", None)]
normal_inds = [i for i in indicators if i.get("threshold_level") in ("정상", None)]

if alert_inds:
    cols = st.columns(min(len(alert_inds), 4))
    for idx, ind in enumerate(alert_inds[:4]):
        with cols[idx]:
            emoji = "🔴" if ind["threshold_level"] == "위험" else "🟠"
            st.metric(f"{emoji} {ind['name']}", ind["current_value"], f"{ind.get('change_pct',0):+.1f}%", delta_color="inverse")

# 정상 지표는 한줄로
if normal_inds:
    normal_str = " · ".join(f"{i['name']} {i['current_value']}" for i in normal_inds[:6])
    st.caption(f"정상: {normal_str}")

st.caption(f"B{bull}/R{bear} | 뉴스 {stats['news']} | 지표 {stats['indicators']} | {datetime.now().strftime('%H:%M')}")
st.divider()

# ─── 탭 ───
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📰 뉴스", "📈 종목", "📊 지표", "🌍 지정학", "📋 히스토리"])

# ═══ 탭 1: 뉴스 ═══
with tab1:
    col_f1, col_f2 = st.columns([1, 1])
    with col_f1:
        min_score = st.slider("최소 점수", 1.0, 10.0, 5.0, 0.5, key="s")
    with col_f2:
        dir_filter = st.selectbox("방향", ["전체", "BULL", "BEAR"], key="d")

    filtered = [n for n in news_data if n.get("impact_score", 0) >= min_score]
    if dir_filter != "전체":
        filtered = [n for n in filtered if n.get("direction") == dir_filter]

    for item in filtered[:25]:
        score = item.get("impact_score", 0)
        direction = item.get("direction", "")
        title = item.get("title", "")
        action = item.get("action_suggestion", "")
        source = item.get("source", "")
        url = item.get("url", "")
        pub = item.get("published_time", "")
        signal = item.get("investment_signal", "")
        chain = item.get("impact_chain", "")
        geo_lv = item.get("geo_level")
        geo_rg = item.get("geo_region", "")

        # 스타일
        if direction == "BULL":
            card = "n-bull"
        elif direction == "BEAR":
            card = "n-bear"
        else:
            card = "n-neutral"

        badge = "b-red" if score >= 8 else "b-amber" if score >= 6.5 else "b-gray"
        fade = "stale" if is_stale(pub, 48) else "old" if is_stale(pub, 24) else ""
        age = relative_time(pub)

        # 유형 아이콘
        tl = title.lower()
        if geo_lv:
            icon = "🌍"
        elif any(k in tl for k in ["금리", "rate", "fed", "cpi"]):
            icon = "🏛️"
        elif any(k in tl for k in ["유가", "oil", "opec"]):
            icon = "🛢️"
        elif any(k in tl for k in ["환율", "달러", "dollar"]):
            icon = "💱"
        else:
            icon = "💼" if direction == "BULL" else "📉" if direction == "BEAR" else "📰"

        action_html = f' <span class="b b-action">{action}</span>' if action and action != "관망" else ""
        geo_html = f' <span class="b b-amber">L{geo_lv} {geo_rg}</span>' if geo_lv else ""
        link = f' <a href="{url}" target="_blank" style="color:#6b7280;font-size:10px;">원문↗</a>' if url and url.startswith("http") else ""

        st.markdown(
            f'<div class="n-card {card} {fade}">'
            f'<span class="b {badge}">{score}</span> {icon} {title[:65]}{action_html}{geo_html}'
            f'<br><span class="sub">{source} · {age}{link}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 상위 5건만 펼치기
        if filtered.index(item) < 5 and (signal or chain):
            with st.expander("상세", expanded=False):
                if signal and "키워드 감지" not in signal:
                    st.markdown(f"💡 {signal}")
                if chain:
                    parts = chain.replace("->", "→").split("→")
                    st.markdown(f"🔗 {'  →  '.join(p.strip() for p in parts)}")
                if url and url.startswith("http"):
                    st.link_button("원문 보기", url)

# ═══ 탭 2: 종목 ═══
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
            if net >= 1.5:
                card, action = "n-bull", "매수"
            elif net <= -1.5:
                card, action = "n-bear", "축소"
            else:
                card, action = "n-neutral", "관망"

            bar_w = min(100, abs(net) * 15)
            bar_c = "#16a34a" if net > 0 else "#dc2626"

            st.markdown(
                f'<div class="n-card {card}">'
                f'<b>{name}</b> &nbsp; <span class="b {"b-green" if net > 0 else "b-red"}">{action}</span> &nbsp; '
                f'<span style="color:#16a34a;">▲{s["bull"]:.1f}</span> / '
                f'<span style="color:#dc2626;">▼{s["bear"]:.1f}</span> &nbsp; '
                f'<span class="sub">순 {net:+.1f} · {s["count"]}건</span>'
                f'<div style="background:#e5e7eb;border-radius:2px;height:4px;margin-top:4px;">'
                f'<div style="background:{bar_c};width:{bar_w}%;height:4px;border-radius:2px;"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("종목 데이터 없음")

# ═══ 탭 3: 지표 ═══
with tab3:
    if indicators:
        for ind in indicators:
            level = ind.get("threshold_level", "정상")
            if level in ("위험", "극단"):
                card = "n-bear"
            elif level in ("경고", "주의"):
                card = "n-neutral"
                card = f'n-card' # amber styling inline
            else:
                card = "n-neutral"

            chg = ind.get("change_pct", 0)
            st.markdown(
                f'<div class="n-card {"n-bear" if level in ("위험","극단") else "n-neutral"}">'
                f'<b>{ind["name"]}</b> &nbsp; '
                f'<span style="font-size:16px;font-weight:700;">{ind["current_value"]}</span> '
                f'<span style="color:{"#16a34a" if chg > 0 else "#dc2626"};">{chg:+.1f}%</span> &nbsp; '
                f'<span class="sub">{level}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.subheader("추이")
        sel = st.selectbox("지표", [i["ticker"] for i in indicators], format_func=lambda t: next((i["name"] for i in indicators if i["ticker"] == t), t))
        hist = get_indicator_history(sel, 7)
        if hist:
            df = pd.DataFrame(hist)
            fig = px.line(df, x="recorded_at", y="current_value", labels={"recorded_at": "", "current_value": ""})
            fig.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("지표 없음")

# ═══ 탭 4: 지정학 ═══
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
            color = "#dc2626" if lv >= 4 else "#d97706" if lv >= 3 else "#6b7280"
            border = "#dc2626" if lv >= 4 else "#fbbf24" if lv >= 3 else "#d1d5db"

            st.markdown(
                f'<div style="border-left:4px solid {border};padding:8px 12px;margin-bottom:8px;border-radius:4px;">'
                f'<span style="color:{color};font-weight:700;">L{lv} {region}</span> '
                f'<span class="sub">— {level_name.get(lv, "")} ({len(data["news"])}건)</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            for n in sorted(data["news"], key=lambda x: x.get("impact_score", 0), reverse=True)[:3]:
                sc = n.get("impact_score", 0)
                url = n.get("url", "")
                link = f' <a href="{url}" target="_blank" style="color:#6b7280;font-size:10px;">원문↗</a>' if url and url.startswith("http") else ""
                st.markdown(f'<span class="sub">&nbsp;&nbsp;[{sc}] {n["title"][:55]}{link}</span>', unsafe_allow_html=True)
    else:
        st.info("지정학 뉴스 없음")

# ═══ 탭 5: 히스토리 ═══
with tab5:
    from collections import Counter
    hist_days = st.selectbox("기간", [7, 14, 30], format_func=lambda d: f"{d}일", key="hd")
    conn_h = get_connection()
    hist_news = [dict(r) for r in conn_h.execute(f"SELECT * FROM news_items WHERE collected_time >= datetime('now','-{hist_days} days','localtime') ORDER BY collected_time DESC").fetchall()]
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
            fig = px.bar(kw_df, x="키워드", y="빈도", color="빈도", color_continuous_scale="Blues")
            fig.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            csv = pd.DataFrame(hist_news).to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 뉴스 CSV", csv, f"news_{hist_days}d.csv", "text/csv")
        with col_e2:
            st.metric("총 뉴스", len(hist_news))
    else:
        st.info("데이터 없음")

# ─── 푸터 ───
st.divider()
st.caption("NIAS v2.0 | 자동 생성된 참고 정보입니다. 투자 판단의 최종 책임은 사용자에게 있습니다.")
