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

# ─── 헤더 ───
direction_emoji = "📈" if "강세" in market_direction else "📉"
st.markdown(f"## {direction_emoji} NIAS v2.0 — 실시간 뉴스 투자 알람 시스템")

col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns(5)
col_h1.metric("시장 방향", market_direction, f"확신도 {confidence:.0%}")
col_h2.metric("VIX 공포지수", vix_val)
col_h3.metric("원달러 환율", krw_val)
col_h4.metric("WTI 유가", wti_val)
col_h5.metric("미국 10년물", tnx_val)

st.caption(f"뉴스 {stats['news']}건 | 지표 {stats['indicators']}건 | BULL {bull_count} vs BEAR {bear_count} vs 미판정 {none_count} | 갱신: {datetime.now().strftime('%H:%M')}")
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
        # ── TOP 뉴스 카드 (펼치기 + 원문 링크) ──
        for i, item in enumerate(filtered[:20], 1):
            score = item.get("impact_score", 0)
            direction = item.get("direction")
            d_emoji = "🟢" if direction == "BULL" else "🔴" if direction == "BEAR" else "⚪"
            d_label = "강세" if direction == "BULL" else "약세" if direction == "BEAR" else "미판정"
            geo_tag = f" | 🌍 L{item['geo_level']} {item.get('geo_region', '')}" if item.get("geo_level") else ""
            source = item.get("source", "")
            title = item.get("title", "")
            url = item.get("url", "")

            # 헤더 라인
            header = f"**{d_emoji} [{score}점] {title[:80]}**"
            if url and url.startswith("http"):
                header += f" [🔗 원문 보기]({url})"

            with st.expander(f"{d_emoji} [{score}] {title[:70]}", expanded=(i <= 3)):
                st.markdown(header)
                st.caption(f"📌 소스: {source} ({item.get('source_type', 'RSS')}) {geo_tag}")

                # 본문 스니펫
                snippet = item.get("snippet", "")
                if snippet:
                    st.markdown(f"> {snippet[:200]}{'...' if len(snippet) > 200 else ''}")

                # 분석 결과
                col_a1, col_a2, col_a3 = st.columns(3)
                col_a1.markdown(f"**방향:** {d_emoji} {d_label}")
                col_a2.markdown(f"**행동 제안:** {item.get('action_suggestion', '-')}")
                col_a3.markdown(f"**확신도:** {item.get('confidence', 0):.0%}")

                signal = item.get("investment_signal", "")
                if signal and signal != "-":
                    st.info(f"💡 **투자 시그널:** {signal}")

                risk = item.get("risk_factor", "")
                if risk and risk != "-":
                    st.warning(f"⚠️ **리스크:** {risk}")

                chain = item.get("impact_chain", "")
                if chain:
                    st.success(f"🔗 **영향 체인:** {chain}")

                # 관련 종목
                stocks_raw = item.get("tagged_stocks", "[]")
                if isinstance(stocks_raw, str):
                    try:
                        stocks = json.loads(stocks_raw)
                    except Exception:
                        stocks = []
                else:
                    stocks = stocks_raw
                if stocks:
                    st.markdown(f"🏷️ **관련 종목:** {', '.join(stocks)}")

                # 원문 링크 버튼
                if url and url.startswith("http"):
                    st.link_button("📄 원본 기사 보기", url)
    else:
        st.info("조건에 맞는 뉴스가 없습니다. 필터를 조정해 보세요.")

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

        st.dataframe(df_stock, use_container_width=True, hide_index=True)

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

            with st.expander(f":{color}[**{bar} L{level} {region}**] — {name} ({data['count']}건)", expanded=(level >= 3)):
                for n in sorted(data["news"], key=lambda x: x.get("impact_score", 0), reverse=True)[:5]:
                    score = n.get("impact_score", 0)
                    title = n.get("title", "")
                    url = n.get("url", "")
                    conflict = n.get("geo_conflict_type", "")

                    link = f" [🔗 원문]({url})" if url and url.startswith("http") else ""
                    st.markdown(f"- **[{score}점]** {title[:70]}{link}")
                    if conflict:
                        st.caption(f"  분쟁 유형: {conflict}")

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
