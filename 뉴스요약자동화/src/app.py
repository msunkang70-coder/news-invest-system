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
html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; background: #0D1117 !important; color: #E6EDF3; }
h1,h2,h3 { font-family: 'Inter', sans-serif !important; color: #E6EDF3 !important; }
.block-container { padding: 2rem 2.5rem 3rem; max-width: 1060px; background: #0D1117 !important; }
[data-testid="stAppViewContainer"] { background: #0D1117 !important; }
[data-testid="stHeader"] { background: #0D1117 !important; }

/* ── verdict ── */
.vd { padding: 16px 22px; border-radius: 16px; font-size: 15px; font-weight: 600; margin-bottom: 28px; }
.vd-g { background: #0D2818; color: #4ADE80; }
.vd-r { background: #2D0F0F; color: #FCA5A5; }
.vd-y { background: #2D2006; color: #FCD34D; }

/* ── hero kpi ── */
.hero {
    background: #161B22; border-radius: 20px; padding: 36px 40px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    margin-bottom: 18px;
    transition: all 0.25s ease;
}
.hero:hover { box-shadow: 0 12px 48px rgba(0,0,0,0.5); transform: translateY(-2px); }
.hero-label { font-size: 13px; color: #8B949E; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 8px; }
.hero-val { font-size: 48px; font-weight: 800; color: #FFFFFF; letter-spacing: -1.5px; line-height: 1; }
.hero-delta { font-size: 18px; font-weight: 700; margin-top: 10px; }

/* ── secondary kpi grid ── */
.kgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(125px, 1fr)); gap: 14px; margin-bottom: 28px; }
.kcard {
    background: #161B22; border-radius: 16px; padding: 20px 18px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    transition: all 0.25s ease;
}
.kcard:hover { box-shadow: 0 8px 32px rgba(0,0,0,0.45); transform: translateY(-3px); }
.kl { font-size: 10.5px; color: #8B949E; font-weight: 600; letter-spacing: 0.4px; margin-bottom: 8px; }
.kv { font-size: 22px; font-weight: 800; color: #E6EDF3; letter-spacing: -0.4px; }
.kd { font-size: 12px; font-weight: 600; margin-top: 6px; }

/* ── news hero ── */
.nf {
    background: #161B22; border-radius: 20px; padding: 30px 32px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    margin-bottom: 14px;
    transition: all 0.25s ease;
}
.nf:hover { box-shadow: 0 12px 48px rgba(0,0,0,0.5); transform: translateY(-2px); }
.nf-title { font-size: 18px; font-weight: 700; color: #E6EDF3; line-height: 1.5; margin-bottom: 12px; }
.nf-sig { font-size: 14px; color: #8B949E; line-height: 1.6; margin-bottom: 12px; }
.nf-meta { font-size: 12px; color: #484F58; }
.nf-meta a { color: #58A6FF; text-decoration: none; font-weight: 500; }
.nf-meta a:hover { color: #79C0FF; }

/* ── news regular ── */
.nr {
    background: #161B22; border-radius: 14px; padding: 18px 22px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    margin-bottom: 10px; transition: all 0.25s ease;
}
.nr:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.4); transform: translateY(-2px); }
.nr-t { font-size: 14px; font-weight: 600; color: #E6EDF3; line-height: 1.5; margin-bottom: 6px; }
.nr-m { font-size: 11.5px; color: #484F58; }
.nr-m a { color: #58A6FF; text-decoration: none; font-weight: 500; }
.nr-m a:hover { color: #79C0FF; }

/* ── pill ── */
.p { display: inline-block; padding: 3px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; margin-right: 6px; }
.p-s { background: #21262D; color: #8B949E; }
.p-a { background: #0D2240; color: #58A6FF; }

/* ── stock ── */
.sc {
    background: #161B22; border-radius: 16px; padding: 20px 22px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 10px; transition: all 0.25s ease;
}
.sc:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.4); transform: translateY(-2px); }
.sc-n { font-weight: 700; font-size: 15px; color: #E6EDF3; }
.sc-bar { height: 6px; border-radius: 3px; background: #21262D; flex: 1; margin: 0 18px; }
.sc-fill { height: 6px; border-radius: 3px; }

/* ── indicator ── */
.ir {
    background: #161B22; border-radius: 16px; padding: 18px 22px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 10px; transition: all 0.25s ease;
}
.ir:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.4); transform: translateY(-2px); }
.ir.alert-row { box-shadow: 0 2px 10px rgba(220,38,38,0.2); }
.ir-n { font-size: 13px; color: #8B949E; font-weight: 500; }
.ir-v { font-size: 22px; font-weight: 800; color: #E6EDF3; letter-spacing: -0.4px; }

/* ── geo ── */
.gc {
    background: #161B22; border-radius: 16px; padding: 22px 26px; border-left: 4px solid #30363D;
    box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    margin-bottom: 12px; transition: all 0.25s ease;
}
.gc:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.4); transform: translateY(-2px); }
.gc.g4 { border-left-color: #F87171; }
.gc.g3 { border-left-color: #FBBF24; }
.gc-t { font-weight: 700; font-size: 15px; color: #E6EDF3; }
.gc-s { font-size: 13px; color: #8B949E; margin-top: 8px; line-height: 1.8; }
.gc-s a { color: #58A6FF; text-decoration: none; font-weight: 500; }
.gc-s a:hover { color: #79C0FF; }

/* ── util ── */
.cap { font-size: 12px; color: #484F58; font-weight: 500; margin-bottom: 24px; }
.stale { opacity: 0.25; }
.old { opacity: 0.45; }
.gap { height: 28px; }

/* ── streamlit overrides (dark) ── */
.stDeployButton, #MainMenu, footer { display: none !important; visibility: hidden !important; }
.stTabs [data-baseweb="tab-list"] { background: transparent !important; }
.stTabs [data-baseweb="tab"] { font-size: 14px; font-weight: 600; color: #484F58; }
.stTabs [aria-selected="true"] { color: #E6EDF3 !important; }
div[data-testid="stExpander"] { border: none !important; background: transparent !important; }
[data-testid="stMetricValue"] { color: #E6EDF3 !important; }
[data-testid="stMetricLabel"] { color: #8B949E !important; }
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
st.markdown('<p style="font-size:11px;color:#B0B8C1;margin:0 0 4px;">NIAS v2.0</p>', unsafe_allow_html=True)

vc = "vd-y" if gc >= 3 and is_bull else "vd-g" if is_bull else "vd-r"
vt = ("강세 우위 · 추세 매수 유효" + (" · 지정학 리스크 병존" if gc >= 3 else "")) if is_bull else ("약세 흐름 · 신규 매수 보류" + (" · 지정학 확대" if gc >= 3 else ""))
st.markdown(f'<div class="vd {vc}">{"📈" if is_bull else "📉"} {vt}</div>', unsafe_allow_html=True)

# ── KPI Grid (모든 지표 동일 크기) ──
if inds:
    h = '<div class="kgrid">'
    for i in inds[:8]:
        c = i.get("change_pct", 0) or 0
        lv = i.get("threshold_level", "정상")
        dc = "#3FB950" if c > 0.01 else "#F85149" if c < -0.01 else "#484F58"
        ds = "+" if c > 0 else ""
        alert = lv in ("위험", "극단", "경고")
        # 위험 지표만 약간 다른 배경
        bg = "#1C1210" if alert else "#161B22"
        h += f'<div class="kcard" style="background:{bg};"><div class="kl">{i["name"]}</div><div class="kv">{i["current_value"]}</div><div class="kd" style="color:{dc};">{ds}{c:.1f}%</div></div>'
    h += '</div>'
    st.markdown(h, unsafe_allow_html=True)

st.markdown(f'<div class="cap">BULL {bull} · BEAR {bear} · 뉴스 {stats["news"]} · {datetime.now().strftime("%H:%M")}</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════
t1, t2, t3, t4, t5 = st.tabs(["뉴스", "종목", "지표", "지정학", "히스토리"])

# ── NEWS ──
with t1:
    c1, c2 = st.columns([1, 1])
    with c1: ms = st.slider("최소 점수", 1.0, 10.0, 5.0, 0.5, key="ms")
    with c2: df = st.selectbox("방향", ["전체", "BULL", "BEAR"], key="df")

    fl = [n for n in news if n.get("impact_score", 0) >= ms]
    if df != "전체": fl = [n for n in fl if n.get("direction") == df]

    # Hero news (top 1)
    if fl:
        top = fl[0]
        sc = top.get("impact_score", 0)
        sig = top.get("investment_signal", "")
        act = top.get("action_suggestion", "")
        url = top.get("url", "")
        age = relative_time(top.get("published_time", ""))
        act_p = f'<span class="p p-a">{act}</span>' if act and act != "관망" else ""
        link = f'<a href="{url}" target="_blank">원문 보기 →</a>' if url and url.startswith("http") else ""
        sig_html = f'<div class="nf-sig">{sig}</div>' if sig and "키워드 감지" not in sig else ""

        st.markdown(f'''
        <div class="nf">
            <div class="nf-title"><span class="p p-s">{sc}</span> {top["title"][:75]} {act_p}</div>
            {sig_html}
            <div class="nf-meta">{top.get("source","")} · {age} {link}</div>
        </div>''', unsafe_allow_html=True)

    # Rest
    for item in fl[1:20]:
        sc = item.get("impact_score", 0)
        d = item.get("direction", "")
        url = item.get("url", "")
        age = relative_time(item.get("published_time", ""))
        fade = "stale" if is_stale(item.get("published_time"), 48) else "old" if is_stale(item.get("published_time"), 24) else ""
        act = item.get("action_suggestion", "")
        act_p = f'<span class="p p-a">{act}</span>' if act and act != "관망" else ""
        link = f'<a href="{url}" target="_blank">원문↗</a>' if url and url.startswith("http") else ""

        st.markdown(f'''
        <div class="nr {fade}">
            <div class="nr-t"><span class="p p-s">{sc}</span> {item["title"][:70]} {act_p}</div>
            <div class="nr-m">{item.get("source","")} · {age} {link}</div>
        </div>''', unsafe_allow_html=True)

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
