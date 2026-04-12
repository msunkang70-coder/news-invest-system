"""NIAS v2.0 — Streamlit 대시보드

실시간 뉴스 + 시장지표 + 지정학 통합 대시보드
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
import plotly.graph_objects as go

import config as cfg
from utils.db import get_recent_news, get_indicator_history, get_db_stats, get_connection

st.set_page_config(
    page_title="NIAS v2.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── 데이터 로드 ───
@st.cache_data(ttl=300)
def load_news(hours=24):
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

# ─── 헤더 ───
stats = get_db_stats()
news_data = load_news(48)
indicators_data = load_all_indicators()

# 최신 지표값 (티커별 가장 최근)
latest_indicators = {}
for ind in indicators_data:
    t = ind["ticker"]
    if t not in latest_indicators:
        latest_indicators[t] = ind

# 시장 종합 판단
bull_count = sum(1 for n in news_data if n.get("direction") == "BULL")
bear_count = sum(1 for n in news_data if n.get("direction") == "BEAR")
total = bull_count + bear_count
bull_ratio = bull_count / total if total > 0 else 0.5
market_direction = "BULL" if bull_ratio > 0.5 else "BEAR"
confidence = abs(bull_ratio - 0.5) * 2

vix_val = latest_indicators.get("^VIX", {}).get("current_value", "-")
krw_val = latest_indicators.get("KRW/USD", {}).get("current_value", "-")
wti_val = latest_indicators.get("CL=F", {}).get("current_value", "-")
tnx_val = latest_indicators.get("^TNX", {}).get("current_value", "-")

direction_emoji = "📈" if market_direction == "BULL" else "📉"
st.markdown(f"""
## {direction_emoji} NIAS v2.0 — 실시간 뉴스 투자 알람 시스템
**시장: {market_direction}** (확신도 {confidence:.0%}) | BULL {bull_count} vs BEAR {bear_count} |
VIX: **{vix_val}** | 원달러: **{krw_val}** | WTI: **{wti_val}** | US10Y: **{tnx_val}** |
DB: 뉴스 {stats['news']}건 / 지표 {stats['indicators']}건
""")

st.divider()

# ─── 탭 ───
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📰 실시간 뉴스", "📈 종목 시그널", "📊 시장지표", "🌍 지정학", "🔔 알림 이력"]
)

# ─── 탭 1: 실시간 뉴스 ───
with tab1:
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        min_score = st.slider("최소 영향도", 1.0, 10.0, 5.0, 0.5)
    with col_f2:
        direction_filter = st.selectbox("방향", ["전체", "BULL", "BEAR"])
    with col_f3:
        source_filter = st.selectbox("소스 유형", ["전체", "RSS", "DART", "FRED", "SNS", "GEOPOLITICAL"])

    filtered = news_data
    filtered = [n for n in filtered if n.get("impact_score", 0) >= min_score]
    if direction_filter != "전체":
        filtered = [n for n in filtered if n.get("direction") == direction_filter]
    if source_filter != "전체":
        filtered = [n for n in filtered if n.get("source_type") == source_filter]

    if filtered:
        df = pd.DataFrame(filtered)
        display_cols = ["impact_score", "title", "direction", "source", "source_type", "geo_level", "geo_region"]
        available = [c for c in display_cols if c in df.columns]
        df_display = df[available].head(30)
        df_display = df_display.rename(columns={
            "impact_score": "점수", "title": "제목", "direction": "방향",
            "source": "소스", "source_type": "유형", "geo_level": "지정학L", "geo_region": "지역"
        })
        st.dataframe(df_display, use_container_width=True, height=400)

        # TOP 5 상세
        st.subheader("🏆 TOP 5 뉴스")
        for i, item in enumerate(filtered[:5], 1):
            score = item.get("impact_score", 0)
            d = "🟢" if item.get("direction") == "BULL" else "🔴"
            geo = f" | L{item['geo_level']} {item.get('geo_region', '')}" if item.get("geo_level") else ""
            st.markdown(f"""
            **{i}. [{score}] {d} {item['title'][:70]}**
            > 소스: {item['source']} | {item.get('source_type', 'RSS')}{geo}
            > 시그널: {item.get('investment_signal', '-')} | 행동: {item.get('action_suggestion', '-')}
            """)
    else:
        st.info("조건에 맞는 뉴스가 없습니다.")

# ─── 탭 2: 종목 시그널 ───
with tab2:
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
                stock_scores[name] = {"bull": 0, "bear": 0, "count": 0}
            score_weight = si.get("intensity", 0.5) * n.get("impact_score", 5) / 10
            if si.get("direction") == "BULL":
                stock_scores[name]["bull"] += score_weight
            else:
                stock_scores[name]["bear"] += score_weight
            stock_scores[name]["count"] += 1

    if stock_scores:
        rows = []
        for name, s in stock_scores.items():
            net = round(s["bull"] - s["bear"], 2)
            if net >= 3.0: action = "적극매수"
            elif net >= 1.5: action = "분할매수"
            elif net >= 0.5: action = "관심 유지"
            elif net >= -0.5: action = "관망"
            elif net >= -1.5: action = "리스크 주의"
            elif net >= -3.0: action = "비중축소"
            else: action = "매도 검토"
            rows.append({"종목": name, "BULL": round(s["bull"], 1), "BEAR": round(s["bear"], 1),
                         "순점수": net, "뉴스수": s["count"], "행동": action})

        df_stock = pd.DataFrame(rows).sort_values("순점수", ascending=False)

        fig = px.bar(df_stock, x="종목", y=["BULL", "BEAR"],
                     barmode="group", color_discrete_map={"BULL": "#22c55e", "BEAR": "#ef4444"},
                     title="종목별 시그널")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_stock, use_container_width=True)
    else:
        st.info("종목 시그널 데이터가 없습니다.")

# ─── 탭 3: 시장지표 ───
with tab3:
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

        # 지표별 히스토리 차트
        st.subheader("📊 지표 히스토리 (24시간)")
        selected_ticker = st.selectbox("지표 선택", list(latest_indicators.keys()),
                                        format_func=lambda t: latest_indicators[t]["name"])
        history = get_indicator_history(selected_ticker, days=7)
        if history:
            df_hist = pd.DataFrame(history)
            fig = px.line(df_hist, x="recorded_at", y="current_value",
                          title=f"{latest_indicators[selected_ticker]['name']} 추이")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("시장지표 데이터가 없습니다. 파이프라인을 먼저 실행해주세요.")

# ─── 탭 4: 지정학 ───
with tab4:
    geo_news = [n for n in news_data if n.get("geo_level")]

    if geo_news:
        # 지역별 에스컬레이션 현황
        st.subheader("지역별 에스컬레이션 현황")
        region_max_level = {}
        for n in geo_news:
            region = n.get("geo_region", "기타")
            level = n.get("geo_level", 0)
            region_max_level[region] = max(region_max_level.get(region, 0), level)

        level_bar = {1: "■□□□□", 2: "■■□□□", 3: "■■■□□", 4: "■■■■□", 5: "■■■■■"}
        level_name = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}
        level_color = {1: "green", 2: "orange", 3: "orange", 4: "red", 5: "darkred"}

        for region, level in sorted(region_max_level.items(), key=lambda x: x[1], reverse=True):
            bar = level_bar.get(level, "?")
            name = level_name.get(level, "?")
            color = level_color.get(level, "gray")
            count = sum(1 for n in geo_news if n.get("geo_region") == region)
            st.markdown(f":{color}[**{bar} L{level} {region}**] — {name} ({count}건)")

        # 지정학 뉴스 목록
        st.subheader("최근 지정학 뉴스")
        for n in sorted(geo_news, key=lambda x: x.get("impact_score", 0), reverse=True)[:10]:
            level = n.get("geo_level", 0)
            score = n.get("impact_score", 0)
            st.markdown(f"- **[{score}] L{level} {n.get('geo_region', '')}** — {n['title'][:60]}")
    else:
        st.info("지정학 분류된 뉴스가 없습니다.")

# ─── 탭 5: 알림 이력 ───
with tab5:
    alerts = load_alerts()
    if alerts:
        df_alerts = pd.DataFrame(alerts)
        st.dataframe(df_alerts.tail(50).iloc[::-1], use_container_width=True)
        st.metric("총 알림 건수", len(alerts))
    else:
        st.info("알림 이력이 없습니다.")

# ─── 푸터 ───
st.divider()
st.caption(f"NIAS v2.0 | 마지막 갱신: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
           f"⚠️ 자동 생성된 참고 정보입니다. 투자 판단의 최종 책임은 사용자에게 있습니다.")
