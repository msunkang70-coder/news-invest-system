"""Streamlit 대시보드

실행: streamlit run app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
import yaml

from core.models import (
    init_db, sync_stocks, get_stocks, get_recent_articles,
    get_notification_history, get_stock_summary,
)
from core.collector import collect_all
from core.analyzer import analyze_articles
from core.notifier import notify_all

# --- 설정 로드 ---
@st.cache_resource
def load_config():
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()
init_db(config)
sync_stocks(config)

# --- 페이지 설정 ---
st.set_page_config(page_title="주식 뉴스 모니터", page_icon="📊", layout="wide")
st.title("📊 주식 뉴스 모니터")

# --- 사이드바 ---
with st.sidebar:
    st.header("필터")

    stocks = get_stocks(config)
    stock_names = ["전체"] + [s["name"] for s in stocks]
    selected_stock = st.selectbox("종목", stock_names)

    direction_options = ["전체", "positive", "negative", "neutral", "mixed"]
    direction_labels = ["전체", "🟢 긍정", "🔴 부정", "⚪ 중립", "🟡 혼합"]
    selected_dir_idx = st.selectbox(
        "방향", range(len(direction_options)),
        format_func=lambda i: direction_labels[i]
    )
    selected_direction = direction_options[selected_dir_idx]

    days = st.selectbox("기간", [1, 3, 7, 14, 30], index=2, format_func=lambda d: f"{d}일")

    st.divider()
    st.header("수동 실행")
    if st.button("수집+분석 실행", use_container_width=True):
        with st.spinner("수집 중..."):
            new_ids = collect_all(config)
            analyze_articles(config, article_ids=new_ids if new_ids else None)
            notify_all(config)
        st.success(f"완료! 신규 {len(new_ids)}건 수집")
        st.rerun()

# --- 탭 ---
tab1, tab2, tab3, tab4 = st.tabs(["📰 최신 기사", "📈 종목별 현황", "🔔 알림 이력", "⚙️ 종목 관리"])

# === 탭1: 최신 기사 ===
with tab1:
    stock_filter = None if selected_stock == "전체" else selected_stock
    articles = get_recent_articles(config, days=days, stock_name=stock_filter,
                                   direction=selected_direction)

    if not articles:
        st.info("해당 조건의 기사가 없습니다. 사이드바에서 '수집+분석 실행'을 눌러보세요.")
    else:
        st.caption(f"총 {len(articles)}건")
        for art in articles:
            dir_emoji = {"positive": "🟢", "negative": "🔴",
                         "neutral": "⚪", "mixed": "🟡"}.get(art["direction"], "")

            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
            with col1:
                st.markdown(f"**{art['title']}**")
                st.caption(f"{art['stock_name']} | {art['source']} | {art.get('published', '')}")
            with col2:
                st.markdown(f"{dir_emoji} **{art['direction']}**")
                st.progress(art["impact"], text=f"영향도 {art['impact']:.2f}")
            with col3:
                st.markdown(f"[원문 링크]({art['url']})")
                st.caption(f"관련도: {art['relevance']:.2f}")

            with st.expander("분석 근거"):
                st.write(art["reasoning"])
            st.divider()

# === 탭2: 종목별 현황 ===
with tab2:
    summary = get_stock_summary(config, days=days)
    if not summary:
        st.info("분석 데이터가 없습니다.")
    else:
        df = pd.DataFrame(summary)
        df.columns = ["종목", "기사수", "평균관련도", "평균영향도", "긍정", "부정", "중립"]

        st.subheader("종목별 기사 수")
        chart_df = df.set_index("종목")[["긍정", "부정", "중립"]]
        st.bar_chart(chart_df)

        st.subheader("종목별 요약")
        st.dataframe(df, width="stretch", hide_index=True)

# === 탭3: 알림 이력 ===
with tab3:
    history = get_notification_history(config, days=days)
    if not history:
        st.info("알림 이력이 없습니다.")
    else:
        for h in history:
            dir_emoji = {"positive": "🟢", "negative": "🔴",
                         "neutral": "⚪", "mixed": "🟡"}.get(h["direction"], "")
            status_map = {"sent": "✅발송", "console": "📋콘솔", "skipped": "⏭️스킵", "failed": "❌실패"}
            status_text = status_map.get(h["status"], h["status"])

            st.markdown(
                f"**[{h['stock_name']}]** {h['title'][:60]}... "
                f"{dir_emoji} 영향도:{h['impact']:.2f} "
                f"[링크]({h['url']})"
            )
            st.caption(f"{h['sent_at']} | {status_text}")
            st.divider()

# === 탭4: 종목 관리 ===
with tab4:
    st.subheader("등록된 종목")
    for s in stocks:
        col1, col2, col3 = st.columns([0.3, 0.5, 0.2])
        with col1:
            st.markdown(f"**{s['name']}** ({s['ticker']})")
        with col2:
            st.caption(f"키워드: {s['keywords']}")
        with col3:
            st.caption(f"섹터: {s['sector']}")

    st.divider()
    st.caption("종목 추가/수정은 config.yaml 파일을 편집한 후 앱을 재시작하세요.")
