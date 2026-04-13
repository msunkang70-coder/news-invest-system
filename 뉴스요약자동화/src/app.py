"""NIAS v2.0 — Premium Decision Dashboard

Toss-level design: white cards, shadow depth, number hierarchy, minimal color.
Logic unchanged — visual only.
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

import config as cfg
from utils.db import get_recent_news, get_indicator_history, get_db_stats, get_connection
from utils.freshness import relative_time, is_stale

st.set_page_config(page_title="NIAS", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")

# ═══════════════════════════════════════════════════════════
# STYLE
# ═══════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; background: #111318 !important; color: #D1D5DB; }
h1,h2,h3 { font-family: 'Inter', sans-serif !important; color: #F3F4F6 !important; }
.block-container { padding: 2rem 2.5rem 3rem; max-width: 1060px; background: #111318 !important; }
[data-testid="stAppViewContainer"] { background: #111318 !important; }
[data-testid="stHeader"] { background: #111318 !important; }

/* ── verdict ── */
.vd { padding: 14px 20px; border-radius: 12px; font-size: 14px; font-weight: 600; margin-bottom: 24px; }
.vd-g { background: rgba(34,197,94,0.1); color: #4ADE80; border: 1px solid rgba(34,197,94,0.15); }
.vd-r { background: rgba(239,68,68,0.1); color: #FCA5A5; border: 1px solid rgba(239,68,68,0.15); }
.vd-y { background: rgba(234,179,8,0.1); color: #FDE68A; border: 1px solid rgba(234,179,8,0.15); }

/* ── kpi grid (동일 크기) ── */
.kgrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.kcard {
    background: #1A1D24; border-radius: 14px; padding: 18px 16px;
    border: 1px solid #25292F;
    transition: all 0.2s ease;
}
.kcard:hover { border-color: #3B3F47; transform: translateY(-2px); }
.kl { font-size: 10.5px; color: #7D8590; font-weight: 600; letter-spacing: 0.4px; margin-bottom: 6px; }
.kv { font-size: 22px; font-weight: 800; color: #F3F4F6; letter-spacing: -0.4px; }
.kd { font-size: 12px; font-weight: 600; margin-top: 4px; }

/* ── news (통일 카드 — hero/regular 구분 제거) ── */
.nc {
    background: #1A1D24; border-radius: 12px; padding: 16px 20px;
    border: 1px solid #25292F;
    margin-bottom: 8px; transition: all 0.2s ease;
}
.nc:hover { border-color: #3B3F47; transform: translateY(-1px); }
.nc-t { font-size: 14px; font-weight: 600; color: #E5E7EB; line-height: 1.5; margin-bottom: 6px; }
.nc-m { font-size: 12px; color: #7D8590; display: flex; align-items: center; gap: 8px; }
.nc-m a { color: #6CA4E0; text-decoration: none; font-weight: 500; }
.nc-m a:hover { color: #93C5FD; }

/* ── 시간 뱃지 (opacity 대신 명시적 뱃지) ── */
.t-new { display:inline-block; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:600; background:rgba(34,197,94,0.15); color:#4ADE80; }
.t-old { display:inline-block; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:600; background:rgba(107,114,128,0.15); color:#6B7280; }

/* ── pill ── */
.p { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; margin-right: 5px; }
.p-s { background: #25292F; color: #9CA3AF; }
.p-a { background: rgba(59,130,246,0.15); color: #6CA4E0; }

/* ── stock ── */
.sc {
    background: #1A1D24; border-radius: 12px; padding: 16px 20px;
    border: 1px solid #25292F;
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px; transition: all 0.2s ease;
}
.sc:hover { border-color: #3B3F47; transform: translateY(-1px); }
.sc-n { font-weight: 700; font-size: 14px; color: #E5E7EB; }
.sc-bar { height: 4px; border-radius: 2px; background: #25292F; flex: 1; margin: 0 16px; }
.sc-fill { height: 4px; border-radius: 2px; }

/* ── indicator ── */
.ir {
    background: #1A1D24; border-radius: 12px; padding: 14px 20px;
    border: 1px solid #25292F;
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px; transition: all 0.2s ease;
}
.ir:hover { border-color: #3B3F47; transform: translateY(-1px); }
.ir.alert-row { border-color: rgba(239,68,68,0.3); }
.ir-n { font-size: 13px; color: #9CA3AF; font-weight: 500; }
.ir-v { font-size: 20px; font-weight: 800; color: #F3F4F6; letter-spacing: -0.3px; }

/* ── geo ── */
.gc {
    background: #1A1D24; border-radius: 12px; padding: 18px 22px; border-left: 3px solid #25292F;
    border-top: 1px solid #25292F; border-right: 1px solid #25292F; border-bottom: 1px solid #25292F;
    margin-bottom: 10px; transition: all 0.2s ease;
}
.gc:hover { border-color: #3B3F47; transform: translateY(-1px); }
.gc.g4 { border-left-color: #F87171; }
.gc.g3 { border-left-color: #FBBF24; }
.gc-t { font-weight: 700; font-size: 14px; color: #E5E7EB; }
.gc-s { font-size: 12px; color: #7D8590; margin-top: 6px; line-height: 1.7; }
.gc-s a { color: #6CA4E0; text-decoration: none; }
.gc-s a:hover { color: #93C5FD; }

/* ── util ── */
.cap { font-size: 11.5px; color: #6B7280; font-weight: 500; margin-bottom: 20px; }
.gap { height: 24px; }

/* ── tab 디자인 (탭 모양) ── */
.stDeployButton, #MainMenu, footer { display: none !important; visibility: hidden !important; }
.stTabs [data-baseweb="tab-list"] {
    background: #1A1D24 !important; border-radius: 10px; padding: 4px;
    border: 1px solid #25292F; gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 13px; font-weight: 600; color: #6B7280;
    border-radius: 8px; padding: 8px 16px !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #F3F4F6 !important; background: #25292F !important;
    border-radius: 8px;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-border"] { display: none !important; }
div[data-testid="stExpander"] { border: none !important; background: transparent !important; }
[data-testid="stMetricValue"] { color: #F3F4F6 !important; }
[data-testid="stMetricLabel"] { color: #7D8590 !important; }

/* 5. 슬라이더/셀렉트 라벨 가독성 */
label, .stSlider label, .stSelectbox label { color: #D1D5DB !important; font-size: 13px !important; font-weight: 600 !important; }
.stSlider [data-testid="stTickBarMin"], .stSlider [data-testid="stTickBarMax"] { color: #9CA3AF !important; }

/* 셀렉트박스 + 모든 폼 요소 다크 스타일 */
[data-baseweb="select"],
[data-baseweb="select"] > div,
.stSelectbox > div > div,
.stSelectbox [data-baseweb="select"] > div {
    background: #1E2330 !important; background-color: #1E2330 !important;
    border: 1px solid #334155 !important; border-radius: 10px !important;
    color: #E2E8F0 !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] div,
[data-baseweb="select"] p,
.stSelectbox span,
.stSelectbox div[data-baseweb] span {
    color: #E2E8F0 !important;
}
[data-baseweb="select"] svg { fill: #94A3B8 !important; }
[data-baseweb="popover"],
[data-baseweb="popover"] ul,
[data-baseweb="menu"] { background: #1E2330 !important; border: 1px solid #334155 !important; border-radius: 10px !important; }
[data-baseweb="popover"] li,
[data-baseweb="menu"] li,
[role="option"] { color: #E2E8F0 !important; background: transparent !important; }
[data-baseweb="popover"] li:hover,
[role="option"]:hover,
[aria-selected="true"][role="option"] { background: #2D3748 !important; }
[data-baseweb="input"],
.stTextInput input { background: #1E2330 !important; color: #E2E8F0 !important; border-color: #334155 !important; }

/* 슬라이더 다크 */
.stSlider [data-baseweb="slider"] div { background: #334155 !important; }
.stSlider [role="slider"] { background: #6CA4E0 !important; border-color: #6CA4E0 !important; }
[data-testid="stThumbValue"] { color: #E2E8F0 !important; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def load_news(h=48): return get_recent_news(hours=h, limit=200)

@st.cache_data(ttl=300)
def load_inds():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM market_indicators ORDER BY recorded_at DESC").fetchall()
    conn.close()
    seen, out = set(), []
    for r in [dict(r) for r in rows]:
        if r["ticker"] not in seen: seen.add(r["ticker"]); out.append(r)
    return out

stats = get_db_stats()
news = load_news(48)
inds = load_inds()
bull = sum(1 for n in news if n.get("direction") == "BULL")
bear = sum(1 for n in news if n.get("direction") == "BEAR")
td = bull + bear
is_bull = (bull / td if td else 0.5) > 0.5
gc = sum(1 for n in news if n.get("geo_level"))

# ═══════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════
# ─── 1. 제목 1.5배 ───
st.markdown('<h1 style="font-size:28px;font-weight:800;color:#F3F4F6;margin:0 0 4px;letter-spacing:-0.5px;">◆ NIAS</h1>', unsafe_allow_html=True)
st.markdown('<p style="font-size:12px;color:#7D8590;margin:0 0 16px;">News-Invest Alert System v2.0</p>', unsafe_allow_html=True)

vc = "vd-y" if gc >= 3 and is_bull else "vd-g" if is_bull else "vd-r"
vt = ("강세 우위 · 추세 매수 유효" + (" · 지정학 리스크 병존" if gc >= 3 else "")) if is_bull else ("약세 흐름 · 신규 매수 보류" + (" · 지정학 확대" if gc >= 3 else ""))
st.markdown(f'<div class="vd {vc}">{"📈" if is_bull else "📉"} {vt}</div>', unsafe_allow_html=True)

# ─── 2. 지표 2줄 (4+4) + 기준일자 ───
if inds:
    h = '<div class="kgrid">'
    for i in inds[:8]:
        c = i.get("change_pct", 0) or 0
        lv = i.get("threshold_level", "정상")
        dc = "#3FB950" if c > 0.01 else "#F85149" if c < -0.01 else "#6B7280"
        ds = "+" if c > 0 else ""
        alert = lv in ("위험", "극단", "경고")
        bg = "#1F1214" if alert else "#1A1D24"
        rec = i.get("recorded_at", "")
        date_str = rec[:10] if rec and len(str(rec)) >= 10 else ""
        h += (
            f'<div class="kcard" style="background:{bg};">'
            f'<div class="kl">{i["name"]}</div>'
            f'<div class="kv">{i["current_value"]}</div>'
            f'<div class="kd" style="color:{dc};">{ds}{c:.1f}%</div>'
            f'<div style="font-size:9.5px;color:#4B5563;margin-top:3px;">{date_str}</div>'
            f'</div>'
        )
    h += '</div>'
    st.markdown(h, unsafe_allow_html=True)

st.markdown(f'<div class="cap">강세(BULL) {bull}건 · 약세(BEAR) {bear}건 · 총 뉴스 {stats["news"]}건 · 갱신 {datetime.now().strftime("%H:%M")}</div>', unsafe_allow_html=True)

# ─── 3. 탭 (아이콘 + 명칭) ───
t1, t2, t3, t4, t5 = st.tabs(["📰 뉴스", "📈 종목", "📊 지표", "🌍 지정학", "📋 히스토리"])

# ── NEWS (카테고리별 분류) ──
with t1:
    c1, c2 = st.columns([1, 1])
    with c1: ms = st.slider("최소 영향도 점수", 1.0, 10.0, 5.0, 0.5, key="ms")
    with c2: df = st.selectbox("시장 방향 필터", ["전체", "📈 강세 (BULL)", "📉 약세 (BEAR)"], key="df")

    fl = [n for n in news if n.get("impact_score", 0) >= ms]
    if "BULL" in df: fl = [n for n in fl if n.get("direction") == "BULL"]
    elif "BEAR" in df: fl = [n for n in fl if n.get("direction") == "BEAR"]

    # 카테고리 분류 로직
    def _categorize(item):
        t = (item.get("title", "") + " " + (item.get("snippet", "") or "")).lower()
        kw = " ".join(item.get("matched_keywords", []) if isinstance(item.get("matched_keywords"), list) else [])
        t = t + " " + kw.lower()
        if item.get("geo_level"):
            return "🌍 지정학"
        if any(k in t for k in ["금리", "rate", "fed", "fomc", "한은", "기준금리", "통화정책", "정책"]):
            return "🏛️ 정책·금리"
        if any(k in t for k in ["유가", "oil", "환율", "달러", "원달러", "금", "gold", "원자재", "commodity", "opec"]):
            return "🛢️ 원자재·환율"
        if any(k in t for k in ["gdp", "cpi", "인플레", "경기", "고용", "실업", "수출", "경제", "recession", "inflation"]):
            return "📊 거시경제"
        return "💼 산업·기업"

    # 카테고리별 그룹핑
    categories = {"📊 거시경제": [], "🏛️ 정책·금리": [], "💼 산업·기업": [], "🛢️ 원자재·환율": [], "🌍 지정학": []}
    for item in fl:
        cat = _categorize(item)
        categories[cat].append(item)

    CAT_COLORS = {
        "📊 거시경제": "#1E293B",
        "🏛️ 정책·금리": "#1E1B2E",
        "💼 산업·기업": "#1B2E1E",
        "🛢️ 원자재·환율": "#2E2A1B",
        "🌍 지정학": "#2E1B1B",
    }

    def _render_news_card(item):
        sc = item.get("impact_score", 0)
        url = item.get("url", "")
        pub = item.get("published_time", "")
        act = item.get("action_suggestion", "")
        act_p = f'<span class="p p-a">{act}</span>' if act and act != "관망" else ""
        link = f'<a href="{url}" target="_blank">원문↗</a>' if url and url.startswith("http") else ""
        pub_date = str(pub)[:16].replace("T", " ") if pub else ""
        stale = is_stale(pub, 24)
        time_cls = "t-old" if stale else "t-new"
        time_badge = f'<span class="{time_cls}">{pub_date}</span>' if pub_date else ""

        return f'''<div class="nc">
            <div class="nc-t"><span class="p p-s">{sc}</span> {item["title"][:68]} {act_p}</div>
            <div class="nc-m">{item.get("source","")} {time_badge} {link}</div>
        </div>'''

    for cat_name, cat_items in categories.items():
        if not cat_items:
            continue

        bg = CAT_COLORS.get(cat_name, "#1A1D24")
        count = len(cat_items)

        # 카테고리 헤더
        st.markdown(
            f'<div style="background:{bg};padding:10px 16px;border-radius:10px;margin:16px 0 8px;">'
            f'<span style="font-size:14px;font-weight:700;color:#E5E7EB;">{cat_name}</span>'
            f'<span style="font-size:11px;color:#7D8590;margin-left:8px;">{count}건</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 상위 3건 표시
        for item in cat_items[:3]:
            st.markdown(_render_news_card(item), unsafe_allow_html=True)

        # 3건 초과 시 펼치기
        if count > 3:
            with st.expander(f"{cat_name} 전체 보기 (+{count - 3}건)", expanded=False):
                for item in cat_items[3:]:
                    st.markdown(_render_news_card(item), unsafe_allow_html=True)

    if not fl:
        st.info("뉴스 없음")

# ── STOCKS ──
with t2:
    ss = {}
    for n in news:
        raw = n.get("stock_impacts", "[]")
        try: imps = json.loads(raw) if isinstance(raw, str) else raw
        except: continue
        for si in imps:
            nm = si.get("stock", "")
            if not nm: continue
            if nm not in ss: ss[nm] = {"b": 0, "r": 0, "c": 0}
            w = si.get("intensity", 0.5) * n.get("impact_score", 5) / 10
            if si.get("direction") == "BULL": ss[nm]["b"] += w
            else: ss[nm]["r"] += w
            ss[nm]["c"] += 1

    if ss:
        for nm, s in sorted(ss.items(), key=lambda x: abs(x[1]["b"] - x[1]["r"]), reverse=True):
            net = round(s["b"] - s["r"], 2)
            lbl = "매수" if net >= 1.5 else "축소" if net <= -1.5 else "관망"
            lc = "#16A34A" if net > 0 else "#DC2626"
            bw = min(100, abs(net) * 12)
            pc = "p-a"

            st.markdown(f'''
            <div class="sc">
                <div><span class="sc-n">{nm}</span> <span class="p {pc}" style="margin-left:8px;">{lbl}</span></div>
                <div class="sc-bar"><div class="sc-fill" style="background:{lc};width:{bw}%;"></div></div>
                <div style="text-align:right;min-width:80px;">
                    <span style="color:#16A34A;font-size:12px;font-weight:600;">+{s["b"]:.1f}</span>
                    <span style="color:#DC2626;font-size:12px;font-weight:600;margin-left:6px;">-{s["r"]:.1f}</span>
                </div>
            </div>''', unsafe_allow_html=True)

# ── INDICATORS ──
with t3:
    if inds:
        for i in inds:
            c = i.get("change_pct", 0) or 0
            lv = i.get("threshold_level", "정상")
            ac = " alert-row" if lv in ("위험", "극단", "경고") else ""
            dc = "#16A34A" if c > 0 else "#DC2626" if c < 0 else "#B0B8C1"

            st.markdown(f'''
            <div class="ir{ac}">
                <span class="ir-n">{i["name"]}</span>
                <span class="ir-v">{i["current_value"]}</span>
                <span style="color:{dc};font-size:14px;font-weight:700;min-width:65px;text-align:right;">{c:+.1f}%</span>
            </div>''', unsafe_allow_html=True)

        st.markdown('<div class="gap"></div>', unsafe_allow_html=True)
        sel = st.selectbox("추이", [i["ticker"] for i in inds], format_func=lambda t: next((i["name"] for i in inds if i["ticker"] == t), t))
        hist = get_indicator_history(sel, 7)
        if hist:
            df = pd.DataFrame(hist)
            fig = px.line(df, x="recorded_at", y="current_value")
            fig.update_traces(line_color="#58A6FF", line_width=2.5)
            fig.update_layout(height=200, margin=dict(l=0,r=0,t=8,b=0), xaxis=dict(showgrid=False,title=""), yaxis=dict(showgrid=True,gridcolor="#21262D",title=""), plot_bgcolor="#0D1117", paper_bgcolor="#0D1117", font_color="#8B949E")
            st.plotly_chart(fig, use_container_width=True)

# ── GEOPOLITICS ──
with t4:
    gn = [n for n in news if n.get("geo_level")]
    if gn:
        rg = {}
        for n in gn:
            r = n.get("geo_region", "기타")
            if r not in rg: rg[r] = {"l": 0, "n": []}
            rg[r]["l"] = max(rg[r]["l"], n.get("geo_level", 0))
            rg[r]["n"].append(n)

        ln = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}

        for region, d in sorted(rg.items(), key=lambda x: x[1]["l"], reverse=True):
            lv = d["l"]
            gc = "g4" if lv >= 4 else "g3" if lv >= 3 else ""
            cl = "#DC2626" if lv >= 4 else "#D97706" if lv >= 3 else "#4E5968"
            nh = ""
            for n in sorted(d["n"], key=lambda x: x.get("impact_score", 0), reverse=True)[:3]:
                u = n.get("url", "")
                lk = f' <a href="{u}" target="_blank">원문↗</a>' if u and u.startswith("http") else ""
                nh += f'<div>[{n.get("impact_score",0)}] {n["title"][:55]}{lk}</div>'

            st.markdown(f'''
            <div class="gc {gc}">
                <div class="gc-t" style="color:{cl};">L{lv} {region} <span style="font-weight:400;font-size:12px;color:#8B95A1;">— {ln.get(lv,"")} · {len(d["n"])}건</span></div>
                <div class="gc-s">{nh}</div>
            </div>''', unsafe_allow_html=True)

# ── HISTORY ──
with t5:
    hd = st.selectbox("기간", [7, 14, 30], format_func=lambda d: f"최근 {d}일")
    ch = get_connection()
    hn = [dict(r) for r in ch.execute(f"SELECT * FROM news_items WHERE collected_time >= datetime('now','-{hd} days','localtime') ORDER BY collected_time DESC").fetchall()]
    ch.close()

    if hn:
        kc = Counter()
        for n in hn:
            raw = n.get("matched_keywords", "[]")
            try: kws = json.loads(raw) if isinstance(raw, str) else raw
            except: kws = []
            kc.update(kws)

        if kc:
            kdf = pd.DataFrame(kc.most_common(10), columns=["키워드", "빈도"])
            fig = px.bar(kdf, x="키워드", y="빈도")
            fig.update_traces(marker_color="#58A6FF")
            fig.update_layout(height=200, margin=dict(l=0,r=0,t=8,b=0), xaxis=dict(title=""), yaxis=dict(title="",gridcolor="#21262D"), plot_bgcolor="#0D1117", paper_bgcolor="#0D1117", font_color="#8B949E")
            st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            csv = pd.DataFrame(hn).to_csv(index=False).encode("utf-8-sig")
            st.download_button("CSV 다운로드", csv, f"nias_{hd}d.csv")
        with c2:
            st.metric("수집 뉴스", len(hn))

# ── FOOTER ──
st.markdown('<div style="height:60px"></div>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;font-size:10px;color:#30363D;">NIAS v2.0 · 투자 판단의 최종 책임은 사용자에게 있습니다</p>', unsafe_allow_html=True)
