# NIAS 중기안 설계 — Event Taxonomy + Event Type Classifier + **Cause Analyzer**

**문서 상태:** 설계안 (구현 미착수)
**작성일:** 2026-04-19
**전제:** Phase 6 단기안(이벤트 Fallback 레이어) 가동 중. 본 문서는 그 위에 얹는 중기 구조.

---

## 0. 설계 동기 (Why this doc exists)

### 0-1. 단기안의 한계
Phase 6 단기안은 "키워드 사전이 있어야만 잡는 구조"에서 "엔티티×액션 매트릭스로 의미적 감지"로 1차 탈피했음. 그러나:
- 여전히 **분류 중심** (어떤 카테고리인가?) — 의미 해석은 LLM summarizer에 위임
- 동일 이벤트를 다양한 관점에서 해석하는 구조 없음
- 단일 시나리오로 환원된 이후 가중치·확률 관리 불가

### 0-2. 핵심 공백 — "Event → Impact" 사이 **Why** 부재
> 문제는 이벤트 해석이 틀린 것이 아니라, 해석 이전에 필요한 "원인 분석" 단계가 없는 구조이다.

현 시스템:
```
Event → (Classifier) → Impact → Signal
```
Classifier가 "무엇"을 알려주지만, "왜 그렇게 되었는가"를 분해하는 단계 없음 → 동일 이벤트의 상반된 시나리오 모두 놓침.

예: "유가 -8%" 한 줄 이벤트에 대해
- (A) 수요 붕괴형 하락 → 경기침체 신호, 위험자산 ↓
- (B) 공급 증가형 하락 → 소비 여력 ↑, 위험자산 ↑
- (C) 지정학 완화형 하락 → 안도 랠리

현재는 A 하나만 해석.

### 0-3. 목표 구조
```
Event
  ↓
[Event Type Classifier] — 무엇이 일어났는가
  ↓
[Cause / Driver Analyzer] — 왜 일어났는가 (구조적 vs 트리거, 대체 원인 시나리오)  ← 신규
  ↓
[Impact Analyzer] — 원인별 분기 영향
  ↓
Signal (확률 가중 or 보수적 최대 손실 기반)
```

---

## 1. Event Taxonomy (이벤트 분류 체계) — YAML 외부화

**파일:** `config/event_taxonomy.yaml` (신규)

```yaml
version: 1
categories:
  - id: geopolitical
    label: 지정학
    severity_range: [1, 5]
    subtypes:
      - id: blockade
        actions_ref: [blockade, supply_disruption]
        entities_ref: [shipping_lane, strategic_geography]
        default_severity: 4
        market_template: naval_blockade
      - id: strike
        actions_ref: [attack]
        entities_ref: [strategic_geography]
        default_severity: 4
      - id: sanction
        actions_ref: [sanction]
        entities_ref: [strategic_geography, major_corporate]
        default_severity: 2
    market_impact_vector: {oil: "+", defense: "+", airline: "-", emerging_markets: "-"}

  - id: energy_supply
    label: 에너지 공급
    subtypes:
      - id: production_halt
        actions_ref: [supply_disruption]
        entities_ref: [commodity]
        default_severity: 3
      - id: opec_decision
        triggers: ["OPEC+ cut", "OPEC+ increase"]
    market_impact_vector: {oil: "+", energy_stocks: "+", consumer_discretionary: "-"}

  - id: supply_chain
    label: 공급망
    subtypes: [chip_shortage, port_closure, export_ban, fab_incident]

  - id: monetary_policy
    label: 통화정책
    subtypes: [rate_shock, intervention, qe_change, forward_guidance_shift]

  - id: fiscal_policy
    label: 재정/무역정책
    subtypes: [tariff, subsidy, default_risk, budget_crisis]

  - id: earnings_shock
    label: 실적 쇼크
    subtypes: [guidance_cut, guidance_raise, miss, beat, restatement]

  - id: liquidity_event
    label: 유동성 이벤트
    subtypes: [bank_run, margin_call, credit_crunch, spread_blowout]
```

### 1-1. 설계 원칙
- 신규 키워드는 **카테고리 트리에만 연결** (하드코딩 제거)
- `actions_ref` / `entities_ref`는 Phase 6 `event_actions.py` 사전을 그대로 참조 (이중 유지 금지)
- `market_impact_vector`는 이메일 템플릿 선택 + 향후 포트폴리오 연동의 기반

---

## 2. Event Type Classifier — 2-Tier

**파일 배치:**
```
src/analyzers/
├── event_actions.py              (단기안, 재사용)
├── event_type_classifier.py      (신규 — 중기안 진입점)
└── event_classifiers/
    ├── tier1_rule_based.py        (매트릭스 확장판)
    ├── tier2_llm.py               (Gemini Flash 분류)
    └── taxonomy_loader.py         (YAML 파싱)
```

### 2-1. Tier 1 (규칙 기반, 빠름·무료)
- Phase 6 event_actions 매트릭스 확장
- Taxonomy 서브타입 매핑 테이블
- 응답: `{category, subtype, severity, confidence}`
- 처리 시간: ~1ms, 비용: 0

### 2-2. Tier 2 (LLM, 느림·유료)
- Tier 1 미매칭 + `impact_score ≥ 5.0`인 뉴스만 대상 (비용 절감)
- Gemini 2.5 Flash (이미 연동됨)에 분류 태스크 추가
- **프롬프트 캐싱**: 카테고리 정의·예시는 캐시 (~80% 토큰 절감)
- 배치 처리 (5~10건씩 묶어서)
- 결과는 `data/event_cache.db` 영속화 (재분류 방지)

### 2-3. Tier 2 프롬프트 구조
```
[시스템 - 캐시됨]
다음 taxonomy에서 이 뉴스의 이벤트 카테고리/서브타입/심각도(1~5)를
JSON으로 답하라. 매칭 불가면 category="none".
{taxonomy 전체 YAML 삽입}

[사용자 - 매번 갱신]
뉴스 제목: ...
요약: ...
```

---

## 3. **⭐ Cause / Driver Analyzer — 신규 서브스펙**

### 3-1. 목적
이벤트 분류(=무엇) 직후 **원인 분해(=왜)**를 수행하여:
1. 구조적 요인과 단기 트리거를 구분
2. 대체 원인 시나리오를 나열 (단일 해석 오류 방지)
3. 원인별 영향 분기를 다음 단계(Impact Analyzer)에 전달
4. 불확실성을 명시적으로 표기 (confidence)

### 3-2. 입출력 명세

**입력:**
```python
{
    "news_item": NewsItem,
    "event_category": "energy_supply",    # Event Type Classifier 결과
    "event_subtype": "production_halt",
    "event_severity": 3,
    "market_context": {                   # Task 5.6에서 이미 수집 중인 것 재사용
        "VIX": 22.5,
        "KRW_USD": 1480,
        "CL_F": 92.0,
        "TNX": 4.5
    }
}
```

**출력:**
```python
{
    "structural_drivers": [               # 장기·구조 요인 (0~N개)
        {
            "label": "OPEC+ 감산 기조 장기화",
            "evidence": ["2025-Q4 감산 연장", "사우디 재정 균형 유가 $85"],
            "direction_bias": "bullish_oil",
            "confidence": 0.7
        }
    ],
    "short_term_triggers": [              # 단기 트리거 (0~N개)
        {
            "label": "Iran-Israel 긴장 고조",
            "evidence": ["04/18 Hormuz 봉쇄 통보"],
            "direction_bias": "bullish_oil",
            "confidence": 0.85
        }
    ],
    "alternative_causes": [               # 대체 원인 시나리오
        {
            "label": "수요 붕괴형 하락 (경기침체)",
            "probability": 0.15,
            "direction_bias": "bearish_risk_assets",
            "disqualifying_evidence": ["VIX 정상 범위", "PMI 견조"]
        },
        {
            "label": "공급 증가형 하락 (OPEC 결렬)",
            "probability": 0.05,
            "direction_bias": "neutral_oil_bullish_consumer",
            "disqualifying_evidence": ["감산 기조 유지 중"]
        }
    ],
    "dominant_cause": {                   # 가장 가능성 높은 원인
        "label": "지정학 긴장 고조",
        "cause_type": "short_term_trigger",
        "probability": 0.8,
        "confidence": 0.75
    },
    "cause_confidence": 0.75,             # 전체 원인 분석 확신도
    "information_completeness": 0.6       # 정보 충분성 (불완전=낮음)
}
```

### 3-3. 작동 흐름

```
[Event Type Classifier 결과 수신]
     ↓
[Tier 1: Cause Rule Engine]
 ├─ YAML 기반 원인 후보 사전 로딩
 │    category별 structural_drivers 템플릿
 │    category별 short_term_triggers 템플릿
 ├─ 본문·시장 context 대조
 └─ 매칭된 원인 후보 + evidence 수집
     ↓
[Tier 2: Cause LLM (선택적)]
 ├─ Tier 1 결과 + NewsItem + market context를 prompt에 주입
 ├─ LLM에게 "구조 vs 트리거 분해, 대체 시나리오 나열, 확률 부여" 지시
 ├─ 응답 JSON 파싱 → output schema에 맞춤
 └─ cause_cache.db 에 영속화
     ↓
[Cause 결과를 NewsItem에 첨부]
 item.cause_analysis = CauseAnalysis(...)
     ↓
[다음 단계 Impact Analyzer로 전달]
```

### 3-4. Cause Taxonomy (원인 사전) — YAML 외부화

**파일:** `config/cause_taxonomy.yaml` (신규)

```yaml
version: 1
categories:
  energy_supply:
    structural:
      - id: opec_supply_policy
        keywords: [OPEC+, production cut, sustained output, 감산 기조]
        indicators_check:
          - {field: CL_F, condition: "> 85", weight: 0.3}
        typical_direction: bullish_oil
      - id: strategic_inventory
        keywords: [SPR, 전략비축유, 방출]
        typical_direction: bearish_oil_short
      - id: transition_energy_structure
        keywords: [재생에너지, 탈탄소, 전환기 수요]
        typical_direction: mixed

    trigger:
      - id: geopolitical_flareup
        keywords: [strike, Iran, blockade, sabotage, Hormuz, Houthi]
        indicators_check:
          - {field: VIX, condition: "> 22", weight: 0.3}
        typical_direction: bullish_oil
      - id: natural_disaster
        keywords: [hurricane, earthquake, refinery fire]
        typical_direction: bullish_oil_short
      - id: policy_announcement
        keywords: [tariff, sanction, ban exports, emergency release]
        typical_direction: depends_on_direction

    alternative_causes:
      - id: demand_collapse
        keywords: [recession, PMI drop, consumer weakness]
        typical_direction: bearish_oil_and_equities
        probability_default: 0.15
      - id: supply_surge
        keywords: [OPEC+ break, output increase, Russia barrel]
        typical_direction: bearish_oil_bullish_consumer
        probability_default: 0.1

  geopolitical:
    structural:
      - id: hegemonic_rivalry
        keywords: [US-China, strategic competition, multipolar]
      - id: regional_proxy_conflict
        keywords: [proxy, Yemen, Hezbollah, IRGC]
    trigger:
      - id: overt_military_action
        keywords: [strike, missile attack, invasion]
      - id: diplomatic_breakdown
        keywords: [expulsion, embassy closed, ultimatum]

  monetary_policy:
    structural:
      - id: inflation_regime
        keywords: [persistent inflation, sticky CPI, wage growth]
      - id: debt_sustainability
        keywords: [fiscal deficit, debt-to-GDP, long-end yields]
    trigger:
      - id: surprise_data_print
        keywords: [CPI surprise, nonfarm, hot inflation]
      - id: fed_speak_shift
        keywords: [Powell, dovish, hawkish, pivot]

  # ... (기타 카테고리는 구현 시 확장)
```

### 3-5. Cause Analyzer Tier 2 LLM 프롬프트 설계

```
[시스템 — 캐시됨]
너는 시장 뉴스의 원인을 분해하는 분석가다.
주어진 이벤트에 대해:
1. 구조적 요인(structural driver): 장기·제도적 배경. 현재 이벤트가 없었어도 존재할 요인.
2. 단기 트리거(trigger): 이번 이벤트를 직접 촉발한 단일·특수 사건.
3. 대체 원인(alternative causes): 같은 이벤트를 다르게 해석할 시나리오 2~3개. 각 확률 부여.
4. 지배적 원인(dominant cause): 가장 가능성 높은 원인 하나.

반드시 JSON으로만 응답. 근거 없는 원인은 confidence < 0.4로 표기.
정보 부족하면 "information_completeness"를 0.5 이하로.

category별 후보 원인 사전:
{cause_taxonomy YAML 삽입}

[사용자 — 매번 갱신]
event_category: energy_supply
event_subtype: production_halt
event_severity: 3
news_title: ...
news_snippet: ...
market_context:
  VIX: 22.5
  KRW_USD: 1480
  CL_F: 92.0
  (기타 지표)
```

### 3-6. Impact Analyzer 단계에서의 활용

Cause Analyzer 결과가 주어지면 Impact Analyzer는 **원인별 영향을 분기**:

```python
def analyze_impact(item: NewsItem) -> ImpactAssessment:
    cause = item.cause_analysis

    if cause.dominant_cause.cause_type == "short_term_trigger":
        # 단기 트리거 → 단기 변동성↑, 되돌림 가능성 고려
        primary_impact = _trigger_impact_template(cause.dominant_cause, item)
    else:
        # 구조적 요인 → 지속성↑, 방향 고정
        primary_impact = _structural_impact_template(cause.dominant_cause, item)

    # 대체 시나리오도 같이 계산 (확률 가중)
    alternative_impacts = [
        _impact_from_cause(alt, item) for alt in cause.alternative_causes
    ]

    return ImpactAssessment(
        primary=primary_impact,
        alternatives=alternative_impacts,
        confidence=cause.cause_confidence,
        information_completeness=cause.information_completeness,
    )
```

### 3-7. Signal Layer 연동 — 확률 가중 행동 제안

```
if cause.confidence >= 0.7:
    # 확신 있음 → 지배 시나리오 기반 행동 제안
    action = primary_impact.action
elif cause.confidence >= 0.4:
    # 중간 확신 → 보수적 액션 (양측 리스크 고려)
    action = "관망 + 양측 헷지"
else:
    # 낮은 확신 (정보 불충분)
    action = "신규 포지션 보류 — 원인 확정 전까지"
```

이메일·Slack 템플릿에는 **Dominant Cause + 대체 시나리오 확률**을 명시:
```
📌 추정 원인: 지정학 긴장 고조 (단기 트리거, 확률 80%, 확신 75%)
⚠️ 대체 시나리오: 수요 붕괴 (15%) · 공급 증가 (5%)
💡 행동: 확률 가중 BULL 포지션, 단 VIX 재급등 시 축소
```

### 3-8. 데이터 모델 확장

`models/news_item.py`에 추가:
```python
@dataclass
class CauseCandidate:
    label: str
    cause_type: str          # "structural" | "trigger" | "alternative"
    evidence: list[str]
    direction_bias: str
    probability: float = 0.0
    confidence: float = 0.0

@dataclass
class CauseAnalysis:
    structural_drivers: list[CauseCandidate]
    short_term_triggers: list[CauseCandidate]
    alternative_causes: list[CauseCandidate]
    dominant_cause: Optional[CauseCandidate]
    cause_confidence: float
    information_completeness: float

# NewsItem에 필드 추가
cause_analysis: Optional[CauseAnalysis] = None
```

`utils/db.py` news_items 테이블 ALTER:
- `cause_dominant TEXT`
- `cause_type TEXT`            # structural / trigger
- `cause_confidence REAL`
- `cause_alternatives_json TEXT`
- `information_completeness REAL`

### 3-9. 비용 및 리스크 관리

| 항목 | 값 / 대응 |
|------|----------|
| Tier 2 추가 토큰 (분류 대비 ~2~3배) | 월 +$1~2 예상 (Gemini Flash 기준) |
| 정보 불완전 시 오판 위험 | `information_completeness < 0.5`면 알림 보류 또는 "원인 미확정" 라벨 |
| UX 피로 (양측 시나리오 표시) | Dominant만 기본 노출, 대체는 접혀 있음 |
| Cache 무효화 | Cause 판정은 새 맥락(market_context) 변화 시 재계산. 기본 24h TTL |

### 3-10. 구현 단계 (Cause Analyzer 내부)

| Phase | 내용 | 소요 | 비용 |
|-------|------|------|------|
| C-1 | `cause_taxonomy.yaml` 스키마 정의 + 3개 카테고리(energy_supply / geopolitical / monetary_policy) 샘플 | 1일 | 0 |
| C-2 | Tier 1 Cause Rule Engine (키워드 매칭 + market_context 조건 검사) | 2일 | 0 |
| C-3 | `CauseAnalysis` dataclass + DB 스키마 마이그레이션 | 0.5일 | 0 |
| C-4 | Tier 2 Cause LLM 프롬프트 + 배치 호출 + 캐시 | 2일 | $1~2/월 |
| C-5 | Impact Analyzer에서 Cause 결과 분기 사용 | 1일 | 0 |
| C-6 | 이메일·Slack 템플릿에 Dominant + 대체 시나리오 노출 | 1일 | 0 |
| C-7 | 대시보드 "원인 분석" 탭 추가 (Cause 품질 모니터링) | 1일 | 0 |
| C-8 | 회귀 테스트: 과거 오판 사례 10건 재분석해 Cause 다양성 검증 | 1일 | 0 |

**총 8~10 작업일**, LLM 운영비 월 $1~2 증가.

---

## 4. 누락 복기 루프 (Missed-Event Reviewer)

### 4-1. 흐름
```
[매일 23:00 cron]
  ↓
missed_events.json 로드 (최근 24시간)
  ↓
Tier 2 LLM 재분류 (+Cause Analyzer 적용)
  ↓
  ├─ 분류 결과 L3+ → "알림_사후_발송" 룰로 지연 전송
  ├─ 분류 결과 L2~ → 누락 로그에 suggestion 추가
  └─ 수집된 엔티티/액션 → 후보 사전(entity_candidates.json) 기록
  ↓
[매주 일요일]
주간 리포트: "이번 주 놓쳤어야 했던 TOP 10 + 추가 권장 키워드"
  → 사용자가 승인하면 event_taxonomy/cause_taxonomy에 반영
```

### 4-2. 추가 가치
- Cause Analyzer로 재분석 시 **"그때 원인을 오판했는지"**도 기록
- 원인 오판 사례를 누적하면 Cause Taxonomy 튜닝 근거 확보

---

## 5. 엔티티 자동 확장 (NER)

- spaCy 한·영 NER 모델로 기사에서 고유명사 추출
- 기존 사전에 없는 `ORG`/`GPE` 엔티티 → `data/entity_candidates.json`
- 주간 빈도 TOP N을 `ENTITY_CLASSES`에 승격 후보로 제시
- Cause Taxonomy에도 동일 방식 적용 (새 원인 패턴 탐지)

---

## 6. 알림·대시보드 확장

### 6-1. 알림 템플릿 동적 선택
- `event_type`에 따라 이메일 템플릿 자동 선택:
  - `blockade` → 해상로 봉쇄 템플릿 (유가·물류·항공 영향)
  - `rate_shock` → 금리 쇼크 템플릿 (성장주·리츠·채권)
  - `earnings_shock` → 실적 쇼크 템플릿 (개별 종목 + 섹터 파급)
- **Cause 결과 포함**: Dominant Cause + 대체 시나리오 명시

### 6-2. 신규 이메일 템플릿 (카테고리별)
```
event_geopolitical_blockade.html
event_energy_supply.html
event_monetary_shock.html
event_supply_chain.html
event_earnings_shock.html
```

### 6-3. 대시보드 "원인 분석" 탭 신설
- 최근 이벤트별 Dominant Cause 분포
- Cause confidence vs 시장 움직임 실측 비교 (사후 검증)
- "원인 오판 상위" 리스트 (alerting 대상)

---

## 7. 비용·리스크·롤백

| 항목 | 추정값 |
|------|--------|
| Tier 2 LLM 호출 (Classifier + Cause) | 일 30~50건 |
| 월 LLM 비용 | $2~4 (Gemini Flash + 캐싱) |
| 전체 구현 기간 | 4~6주 (1인) |
| 롤백 안전성 | Tier 2 끄면 Tier 1으로 축소 운영 가능 |
| 단기안과의 공존 | Phase 6 event_actions·missed_events 그대로 유지 |
| 실패 시 fallback | Cause 분석 실패 → 기존 summarizer 단일 해석으로 회귀 |

---

## 8. 이관 경로 (Phase 7~10)

```
Phase 6 (완료, 2026-04-18~19):
  단기안 — event_actions + event_fallback + 핫스팟 쿼리 + 대시보드 QA

Phase 7 (+1~2주):
  missed_events 데이터 축적 → 단기안 튜닝
  Event Taxonomy YAML 정의 (카테고리 7종 + 서브타입)

Phase 8 (+2~3주):
  Event Type Classifier Tier 1 (규칙) 구현
  Tier 2 LLM 연동 (분류만)

Phase 9 (+3~4주):
  ★ Cause Analyzer Tier 1 + Tier 2 구현 (C-1~C-8)
  Impact Analyzer의 원인별 분기 적용
  이메일 템플릿에 Dominant + 대체 시나리오 노출

Phase 10 (+5~6주):
  동적 템플릿 (카테고리별)
  Missed-Event 야간 LLM 재분류 cron
  대시보드 "원인 분석" 탭

Phase 11 (+6~7주):
  엔티티 자동 확장 (NER)
  Cause Taxonomy 자동 튜닝 루프
  주간 "원인 오판 리포트" 생성
```

---

## 9. 성공 지표 (KPI)

| 지표 | 단기안(현재) | 중기안 목표 |
|------|------|------|
| 이벤트 분류율 (geo_level 설정된 비율) | ~30% | ≥70% |
| Cause confidence 평균 | N/A | ≥0.6 |
| 동일 이벤트 대체 시나리오 노출률 | 0% | ≥40% (confidence<0.7일 때) |
| missed_events 주간 건수 | 측정 개시 | 단기안 대비 -50% |
| 사후 원인 오판 비율 (주간 리뷰) | 측정 불가 | ≤15% |
| 이메일 1건당 토큰 비용 | ~500 | ~1200 (Cause 포함) |

---

## 10. 공개 질문 (구현 전 결정 필요)

1. **Cause Analyzer Tier 2를 어디까지 돌릴지** — 모든 고영향 뉴스 vs event_severity≥3만 vs Classifier 결과 confidence<0.7인 경우만
2. **대체 시나리오 노출 방식** — 이메일 본문에 펼쳐서 / 접힌 상태로 / 별도 탭만
3. **Cause 오판 회고 주기** — 주간 자동 vs 월간 수동 리뷰
4. **Cause Taxonomy 편집 권한** — 직접 YAML 편집 vs 대시보드 UI
5. **원인 확신도 낮을 때 기본 행동** — 알림 발송 보류 vs "원인 불확정" 라벨로 발송

---

## 11. 참조

- Phase 6 단기안 구현: `src/analyzers/event_actions.py`, `src/utils/missed_events.py`
- LLM 연동 기준: `src/analyzers/summarizer.py` (Gemini 2.5 Flash, 시장 context 주입)
- 영향 체인 기존 사전: `src/analyzers/impact_chain_analyzer.py` (5대 체인)
- 이메일 템플릿: `src/notifiers/email_notifier.py`
- 대시보드: `src/app.py`
