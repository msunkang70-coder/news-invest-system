"""NIAS v2.0 — 5 페르소나 유저 테스트"""
import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))

from utils.db import get_recent_news, get_db_stats, get_connection

news = get_recent_news(48, 200)
conn = get_connection()
indicators = [dict(r) for r in conn.execute("SELECT * FROM market_indicators ORDER BY recorded_at DESC").fetchall()]
conn.close()
alerts_path = os.path.join("data", "alert_history.json")
alerts = json.load(open(alerts_path, encoding="utf-8")) if os.path.exists(alerts_path) else []

latest = {}
for ind in indicators:
    if ind["ticker"] not in latest:
        latest[ind["ticker"]] = ind

results_all = {}

def log(msg):
    print(msg)

# ═══════════════════════════════════════════
log("=" * 80)
log("NIAS v2.0 유저 테스트 — 5 페르소나 x 21 테스트 케이스")
log("=" * 80)

# ── 페르소나 1: 김투자 (직장인 개인 투자자) ──
log("\n" + "━" * 80)
log("페르소나 1: 김투자 (직장인 개인 투자자, 포트폴리오 5,000만원)")
log("시나리오: 출근 전 08:00, 오늘 핵심 뉴스를 5분 안에 파악하고 싶다")
log("━" * 80)

p1 = []

# T1-1: 삼성전자 뉴스
samsung = [n for n in news if "삼성" in n.get("title", "")]
log(f"[T1-1] 삼성전자 관련 뉴스: {len(samsung)}건")
for s in samsung[:3]:
    log(f"  [{s['impact_score']}] {s['title'][:60]}")
r = "PASS" if len(samsung) >= 2 else "FAIL"
p1.append(r); log(f"  >> {r}")

# T1-2: 실적 뉴스
earnings = [n for n in news if any(kw in n.get("title","") for kw in ["실적","영업이익","매출","earnings"])]
log(f"[T1-2] 실적 관련 뉴스: {len(earnings)}건")
for e in earnings[:3]:
    log(f"  [{e['impact_score']}] {e['title'][:60]}")
r = "PASS" if earnings else "FAIL"
p1.append(r); log(f"  >> {r}")

# T1-3: 원문 URL
valid_urls = sum(1 for n in news if n.get("url","").startswith("http"))
pct = valid_urls / len(news) * 100 if news else 0
r = f"PASS ({pct:.0f}% 유효)" if pct >= 80 else f"FAIL ({pct:.0f}%)"
p1.append(r); log(f"[T1-3] 원본 기사 URL: {valid_urls}/{len(news)}건 >> {r}")

# T1-4: 이메일 알림
r = f"PASS ({len(alerts)}건)" if alerts else "FAIL"
p1.append(r); log(f"[T1-4] 이메일 알림 수신: >> {r}")

results_all["김투자(직장인)"] = p1

# ── 페르소나 2: 박분석 (증권사 리서치 분석가) ──
log("\n" + "━" * 80)
log("페르소나 2: 박분석 (증권사 리서치 센터, 매크로/섹터 분석 10년)")
log("시나리오: 지정학 이벤트의 구조화된 시장 영향도 분석이 필요")
log("━" * 80)

p2 = []

geo = [n for n in news if n.get("geo_level")]
regions = {}
for n in geo:
    rg = n.get("geo_region", "기타")
    regions[rg] = max(regions.get(rg, 0), n.get("geo_level", 0))

log(f"[T2-1] 지정학 뉴스: {len(geo)}건, 지역: {len(regions)}개")
for rg, lv in sorted(regions.items(), key=lambda x: x[1], reverse=True):
    cnt = sum(1 for n in geo if n.get("geo_region") == rg)
    log(f"  L{lv} {rg}: {cnt}건")
r = "PASS" if len(geo) >= 3 and len(regions) >= 2 else "PARTIAL"
p2.append(r); log(f"  >> {r}")

levels = set(n.get("geo_level") for n in geo if n.get("geo_level"))
r = f"PASS (L{min(levels)}~L{max(levels)})" if len(levels) >= 3 else f"PARTIAL ({len(levels)}개)"
p2.append(r); log(f"[T2-2] 레벨 다양성: {levels} >> {r}")

chains = [n for n in news if n.get("impact_chain")]
r = f"PASS ({len(chains)}건)" if chains else "FAIL"
p2.append(r); log(f"[T2-3] 영향 체인: {len(chains)}건 >> {r}")

ctypes = set(n.get("geo_conflict_type") for n in geo if n.get("geo_conflict_type"))
r = f"PASS {ctypes}" if ctypes else "FAIL"
p2.append(r); log(f"[T2-4] 분쟁 유형: {ctypes} >> {r}")

results_all["박분석(분석가)"] = p2

# ── 페르소나 3: 이글로벌 (해외주식 투자자) ──
log("\n" + "━" * 80)
log("페르소나 3: 이글로벌 (미국+유럽 주식, NVIDIA/Tesla 보유)")
log("시나리오: 미국 시장 동향 + 환율 + 빅테크 종목 모니터링")
log("━" * 80)

p3 = []

us_news = [n for n in news if any(kw in n.get("title","").lower() for kw in ["fed","fomc","us ","s&p","nasdaq","wall street","trump","tariff"])]
log(f"[T3-1] 미국 관련 뉴스: {len(us_news)}건")
for u in us_news[:3]:
    log(f"  [{u['impact_score']}] {u['title'][:60]}")
r = "PASS" if len(us_news) >= 3 else "PARTIAL"
p3.append(r); log(f"  >> {r}")

must_have = ["^VIX", "CL=F", "DX-Y.NYB", "^TNX", "^GSPC"]
missing = [t for t in must_have if t not in latest]
log(f"[T3-2] 핵심 시장지표: {len(latest)}개, 누락: {missing}")
for t in must_have:
    if t in latest:
        i = latest[t]
        log(f"  {i['name']}: {i['current_value']} ({i['change_pct']:+.1f}%)")
r = "PASS" if not missing else f"FAIL 누락:{missing}"
p3.append(r); log(f"  >> {r}")

krw = latest.get("KRW/USD", {})
krw_val = krw.get("current_value", 0)
fx_alert = any(a.get("rule") == "환율_급변" for a in alerts)
r = f"PASS (원달러 {krw_val}, 알림:{fx_alert})" if krw_val else "FAIL"
p3.append(r); log(f"[T3-3] 환율 모니터링: >> {r}")

bigtech = set()
for n in news:
    raw = n.get("tagged_stocks", "[]")
    try: stocks = json.loads(raw) if isinstance(raw, str) else raw
    except: stocks = []
    for s in stocks:
        if s in ["NVIDIA","TSMC","애플","마이크로소프트","구글","아마존","메타","테슬라"]:
            bigtech.add(s)
r = f"PASS {bigtech}" if bigtech else "FAIL"
p3.append(r); log(f"[T3-4] 빅테크 종목 태깅: {bigtech} >> {r}")

results_all["이글로벌(해외투자)"] = p3

# ── 페르소나 4: 최신입 (투자 초보자) ──
log("\n" + "━" * 80)
log("페르소나 4: 최신입 (투자 6개월, 주식 용어에 익숙하지 않음)")
log("시나리오: 복잡한 분석 없이 '사야 하나 말아야 하나'를 알고 싶다")
log("━" * 80)

p4 = []

scores = [n.get("impact_score", 0) for n in news]
avg = sum(scores) / len(scores) if scores else 0
log(f"[T4-1] 영향도 점수: 평균 {avg:.1f}, 범위 {min(scores):.1f}~{max(scores):.1f}")
r = "PASS" if avg > 0 else "FAIL"
p4.append(r); log(f"  >> {r} — 1-10 점수로 직관적 이해 가능")

kr_news = [n for n in news if any(ord(c) >= 0xAC00 for c in n.get("title","")[:5])]
ratio = len(kr_news) / len(news) * 100 if news else 0
r = f"PASS ({ratio:.0f}%)" if ratio >= 30 else f"ISSUE ({ratio:.0f}% — 한국어 뉴스 부족)"
p4.append(r); log(f"[T4-2] 한국어 뉴스 비중: {len(kr_news)}/{len(news)}건 >> {r}")

has_dir = sum(1 for n in news if n.get("direction"))
r = f"PASS ({has_dir}건)" if has_dir > 0 else "PENDING — Gemini API 할당량 리셋 후 BULL/BEAR 판정 가능"
p4.append(r); log(f"[T4-3] BULL/BEAR 방향 표시: {has_dir}/{len(news)}건 >> {r}")

has_action = sum(1 for n in news if n.get("action_suggestion"))
r = f"PASS ({has_action}건)" if has_action > 0 else "PENDING — LLM 연동 시 행동 제안 생성"
p4.append(r); log(f"[T4-4] 행동 제안 (매수/매도/관망): {has_action}건 >> {r}")

results_all["최신입(초보자)"] = p4

# ── 페르소나 5: 정위기 (리스크 관리 트레이더) ──
log("\n" + "━" * 80)
log("페르소나 5: 정위기 (리스크 관리 트레이더, 변동성 전략)")
log("시나리오: VIX 급등, 환율 급변, 지정학 위기 시 1분 내 알림 필요")
log("━" * 80)

p5 = []

vix = latest.get("^VIX", {})
vix_val = vix.get("current_value", 0)
r = f"PASS (VIX {vix_val})" if vix_val else "FAIL"
p5.append(r); log(f"[T5-1] VIX 모니터링: {vix_val} >> {r}")

urgent = [a for a in alerts if a.get("rule") in ("긴급속보","지정학_L3","지정학_L4","VIX_패닉","환율_급변")]
r = f"PASS ({len(urgent)}건)" if urgent else "PARTIAL"
p5.append(r); log(f"[T5-2] 긴급 알림: {len(urgent)}건 >> {r}")
for a in urgent:
    log(f"  [{a.get('rule')}] {a.get('title','')[:50]}")

geo_l4 = [n for n in news if (n.get("geo_level") or 0) >= 4]
geo_alerts = [a for a in alerts if "지정학" in a.get("rule","")]
r = f"PASS (L4+ {len(geo_l4)}건, 알림 {len(geo_alerts)}건)" if geo_alerts else "PARTIAL"
p5.append(r); log(f"[T5-3] 지정학 L4+ 대응: {len(geo_l4)}건 감지, {len(geo_alerts)}건 알림 >> {r}")

rule_counts = {}
for a in alerts:
    rule_counts[a.get("rule","?")] = rule_counts.get(a.get("rule","?"), 0) + 1
mx = max(rule_counts.values()) if rule_counts else 0
r = f"PASS (룰당 최대 {mx}건)" if mx <= 3 else f"WARNING ({mx}건)"
p5.append(r); log(f"[T5-4] 쿨다운 정상: {rule_counts} >> {r}")

results_all["정위기(트레이더)"] = p5

# ═══════════════════════════════════════════
log("\n" + "=" * 80)
log("종합 결과")
log("=" * 80)

total_pass = 0
total_tests = 0
issues = []

for persona, results in results_all.items():
    passes = sum(1 for r in results if r.startswith("PASS"))
    total = len(results)
    total_pass += passes
    total_tests += total
    pct = passes / total * 100
    icon = "✅" if passes == total else "🟡" if pct >= 50 else "❌"
    log(f"  {icon} {persona}: {passes}/{total} ({pct:.0f}%)")
    for r in results:
        if not r.startswith("PASS"):
            issues.append(f"  {persona}: {r}")

log(f"\n전체: {total_pass}/{total_tests} PASS ({total_pass/total_tests*100:.0f}%)")

if issues:
    log(f"\n미해결 이슈 ({len(issues)}건):")
    for iss in issues:
        log(f"  ⚠️ {iss}")
