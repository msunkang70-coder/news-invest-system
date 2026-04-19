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
[Cause / Driver Analyzer] — 원인 가설 생성 (확정값 아님, hypothesis로 취급)  ← 신규
  ├─ 구조적 요인 가설(structural) / 단기 트리거 가설(trigger)
  ├─ 대체 가설(alternative) 2~3개 + 각 확률
  ├─ 유력 가설(leading hypothesis) 선정
  ├─ hypothesis_confidence: 가설의 상대적 확신도 (참고 지표)
  └─ information_completeness: 의사결정에 필요한 정보의 충분성 (주 기준) ⭐
  ↓
[Impact Analyzer] — 가설별 분기 영향
  ↓
Signal — **information_completeness 기반**으로 행동 결정
  ├─ 정보 충분(≥0.7): 유력 가설 기반 포지션
  ├─ 정보 중간(0.4~0.7): 양측 헷지 / 축소
  └─ 정보 부족(<0.4): 포지션 유보
```

**설계 원칙:**
- 원인은 언제나 **가설(hypothesis)** 이며, 확정값으로 쓰지 않는다.
- Signal 판단은 **가설이 맞을 확률(confidence)이 아니라 "이 판단을 내릴 정보가 충분한가(information_completeness)"**를 기준으로 한다.
- 높은 confidence라도 정보 불완전 상태에서는 보수적으로 대응한다 (불완전 정보 + 확신 = 오판의 전형적 패턴).

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
이벤트 분류(=무엇) 직후 **원인 가설 생성(=왜일 가능성)**을 수행하여:
1. 구조적 요인 가설과 단기 트리거 가설을 구분 (**가설이지 결론이 아님**)
2. 대체 가설을 나열 (단일 해석 오류 방지)
3. 가설별 영향 분기를 다음 단계(Impact Analyzer)에 전달
4. 두 종류 불확실성을 분리 표기:
   - **hypothesis_confidence**: 유력 가설이 맞을 상대적 확률 (참고 지표)
   - **information_completeness**: 의사결정에 필요한 정보 충분성 ⭐ **Signal 판단의 주 기준**

**설계 철학:** 원인은 알 수 없다. 알 수 있는 것은 "얼마나 아는가"뿐이다.
따라서 hypothesis_confidence가 높아도 information_completeness가 낮으면 행동 보류한다.

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

**출력:** (모든 원인은 hypothesis — 확정값 아님)
```python
{
    "structural_hypotheses": [             # 장기·구조 요인 가설 (0~N개)
        {
            "label": "OPEC+ 감산 기조 장기화",
            "hypothesis_type": "structural",
            "evidence": ["2025-Q4 감산 연장", "사우디 재정 균형 유가 $85"],
            "direction_bias": "bullish_oil",
            "probability": 0.7,            # 이 가설이 맞을 상대적 확률
            "hypothesis_confidence": 0.7   # 가설 자체에 대한 확신도
        }
    ],
    "short_term_trigger_hypotheses": [     # 단기 트리거 가설 (0~N개)
        {
            "label": "Iran-Israel 긴장 고조",
            "hypothesis_type": "trigger",
            "evidence": ["04/18 Hormuz 봉쇄 통보"],
            "direction_bias": "bullish_oil",
            "probability": 0.8,
            "hypothesis_confidence": 0.85
        }
    ],
    "alternative_hypotheses": [            # 대체 가설
        {
            "label": "수요 붕괴형 하락 (경기침체)",
            "hypothesis_type": "alternative",
            "probability": 0.15,
            "direction_bias": "bearish_risk_assets",
            "disqualifying_evidence": ["VIX 정상 범위", "PMI 견조"]
        },
        {
            "label": "공급 증가형 하락 (OPEC 결렬)",
            "hypothesis_type": "alternative",
            "probability": 0.05,
            "direction_bias": "neutral_oil_bullish_consumer",
            "disqualifying_evidence": ["감산 기조 유지 중"]
        }
    ],
    "leading_hypothesis": {                # 유력 가설 (확정 아님, 가장 가능성 높은 것)
        "label": "지정학 긴장 고조",
        "hypothesis_type": "trigger",
        "probability": 0.8,
        "hypothesis_confidence": 0.75
    },
    "hypothesis_confidence": 0.75,         # 유력 가설의 상대적 확신도 (참고 지표)
    "information_completeness": 0.6,       # ⭐ Signal 판단의 주 기준
    "completeness_breakdown": {            # information_completeness 산출 근거
        "source_diversity": 0.5,           # 서로 다른 출처 수 (1차 발행처·해설·시장 반응)
        "market_context_coverage": 0.7,    # 관련 시장지표 최신성 (VIX, 유가, 환율 등)
        "corroborating_signals": 0.6,      # 교차 확증 시그널 (다른 뉴스·지표 일치)
        "time_since_event_hours": 4,       # 발생 후 경과시간 (짧을수록 정보 불충분)
        "contradicting_signals": 0.2       # 가설과 상충하는 시그널 (높을수록 정보 혼란)
    }
}
```

**핵심 변경점:**
- `dominant_cause` → `leading_hypothesis` (확정적 함의 제거)
- `cause_candidates` → `cause_hypotheses` (모든 원인은 가설)
- `cause_confidence` → `hypothesis_confidence` (참고 지표로 강등)
- **`information_completeness` + `completeness_breakdown` 신규** (Signal 주 기준)

### 3-3. 작동 흐름

```
[Event Type Classifier 결과 수신]
     ↓
[Tier 1: Cause Hypothesis Engine (규칙)]
 ├─ YAML 기반 원인 가설 사전 로딩
 │    category별 structural_hypotheses 템플릿
 │    category별 trigger_hypotheses 템플릿
 │    category별 alternative_hypotheses 템플릿
 ├─ 본문·시장 context 대조해 가설별 evidence 수집
 └─ 가설별 probability 초안 부여 (템플릿 기본값)
     ↓
[Tier 2: Cause Hypothesis LLM (선택적)]
 ├─ Tier 1 결과 + NewsItem + market context를 prompt에 주입
 ├─ LLM 지시:
 │   1) 구조·트리거·대체 가설 나열 (확정 X, 가설 O)
 │   2) 가설별 probability 정제
 │   3) information_completeness 산출 (5개 서브 지표로 분해)
 ├─ 응답 JSON 파싱 → output schema에 맞춤
 └─ cause_cache.db 영속화
     ↓
[information_completeness 계산]
 completeness_breakdown 5개 지표를 가중 평균
 - source_diversity (0.25)
 - market_context_coverage (0.20)
 - corroborating_signals (0.20)
 - time_freshness_factor (0.15)
 - low_contradiction_factor (0.20)  ← contradicting_signals의 역수
     ↓
[CauseAnalysis 결과를 NewsItem에 첨부]
 item.cause_analysis = CauseAnalysis(
     ...,
     leading_hypothesis=...,
     information_completeness=...  # Signal 판단의 주 기준
 )
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
너는 시장 뉴스의 원인을 "가설"로 제시하는 분석가다.
원인은 절대 확정하지 말고, 항상 여러 가설의 집합으로 출력하라.

주어진 이벤트에 대해 다음을 JSON으로 응답:

1. structural_hypotheses: 장기·제도적 배경 가설. 현재 이벤트가 없었어도 존재할 요인.
2. short_term_trigger_hypotheses: 이번 이벤트를 직접 촉발했을 가능성 있는 단일 사건.
3. alternative_hypotheses: 같은 이벤트를 다르게 해석할 수 있는 가설 2~3개.
4. leading_hypothesis: 가장 가능성 높은 가설 하나 (확정이 아닌 "가장 유력").

각 가설에는 probability(상대 확률)와 hypothesis_confidence(가설 자체의 확신도)를 부여.

★ 중요 — information_completeness 별도 산출:
  "이 판단을 내리기에 정보가 충분한가"를 0.0~1.0으로 평가.
  다음 5개 서브 지표로 분해하여 completeness_breakdown에 담는다:
  - source_diversity: 서로 다른 출처 수 (1차·해설·시장 반응 독립적 확인)
  - market_context_coverage: 관련 시장지표 최신성
  - corroborating_signals: 가설을 뒷받침하는 교차 확증 시그널
  - time_since_event_hours: 발생 후 경과시간 (짧을수록 정보 불충분)
  - contradicting_signals: 가설과 상충하는 시그널 (높을수록 정보 혼란)

주의:
- 정보 부족(속보 직후, 출처 1개, 시장 미반응)이면 information_completeness를 0.4 이하로.
- hypothesis_confidence가 높더라도 information_completeness가 낮을 수 있다 (별개 지표).
- 근거 없는 가설은 hypothesis_confidence < 0.4로 표기.

category별 후보 가설 사전:
{cause_taxonomy YAML 삽입}

[사용자 — 매번 갱신]
event_category: energy_supply
event_subtype: production_halt
event_severity: 3
news_title: ...
news_snippet: ...
publish_time: 2026-04-19T12:30:00  # time_since_event_hours 계산용
sources_seen_so_far: ["Reuters", "연합뉴스"]  # source_diversity 계산용
market_context:
  VIX: 22.5
  KRW_USD: 1480
  CL_F: 92.0
  (기타 지표)
```

### 3-6. Impact Analyzer 단계에서의 활용

Cause Analyzer 결과가 주어지면 Impact Analyzer는 **가설별 영향을 분기**하되, 절대 하나로 환원하지 않는다:

```python
def analyze_impact(item: NewsItem) -> ImpactAssessment:
    cause = item.cause_analysis
    leading = cause.leading_hypothesis  # "가장 유력"이지 "확정" 아님

    if leading.hypothesis_type == "trigger":
        # 단기 트리거 가설 → 단기 변동성↑, 되돌림 가능성 고려
        leading_impact = _trigger_impact_template(leading, item)
    elif leading.hypothesis_type == "structural":
        # 구조적 요인 가설 → 지속성↑, 방향 고정
        leading_impact = _structural_impact_template(leading, item)
    else:
        leading_impact = _alternative_impact_template(leading, item)

    # 대체 가설도 같이 계산 (확률 가중 시나리오)
    alternative_impacts = [
        _impact_from_hypothesis(alt, item)
        for alt in cause.alternative_hypotheses
    ]

    return ImpactAssessment(
        leading_scenario=leading_impact,       # 유력 가설 기반 (확정 아님)
        alternative_scenarios=alternative_impacts,
        hypothesis_confidence=cause.hypothesis_confidence,  # 참고용
        information_completeness=cause.information_completeness,  # ⭐ Signal 주 기준
        completeness_breakdown=cause.completeness_breakdown,
    )
```

**주의:** `leading_scenario`는 `primary`라는 이름 대신 `leading`으로 표기해 확정 아님을 명시.

### 3-7. Signal Layer — **information_completeness 기반 행동 결정** ⭐

**설계 전환:** 이전 안은 `hypothesis_confidence`로 분기했으나, 확신은 높지만 정보가 불충분한 상태가 가장 위험한 오판 유형임을 반영해 **information_completeness를 주 기준으로 전환**.

```python
def decide_signal(item: NewsItem) -> Signal:
    cause = item.cause_analysis
    impact = item.impact_assessment
    completeness = cause.information_completeness   # ⭐ 주 기준
    conf = cause.hypothesis_confidence              # 참고 지표

    if completeness >= 0.7:
        # 정보 충분 → 유력 가설 기반 포지션 가능
        # (단, conf가 낮으면 규모 축소)
        action = _leading_action(impact.leading_scenario)
        position_size = 1.0 if conf >= 0.7 else 0.5
        note = "정보 충분 + 유력 가설 기반"

    elif completeness >= 0.4:
        # 정보 중간 → 양측 헷지 / 축소 포지션
        action = "양측 시나리오 헷지 + 포지션 축소(50%)"
        position_size = 0.5
        note = "정보 중간 — 단일 가설에 베팅 금지"

    else:
        # 정보 부족 → 신규 포지션 유보
        # confidence가 높더라도 무조건 보류
        action = "신규 포지션 보류 — 추가 정보 확인 후 재평가"
        position_size = 0.0
        note = f"정보 부족 (completeness={completeness:.2f}). " \
               f"가설 확신도({conf:.2f})와 무관하게 보류"

    return Signal(
        action=action,
        position_size=position_size,
        note=note,
        # 참고 정보로 두 지표 모두 기록
        information_completeness=completeness,
        hypothesis_confidence=conf,
        leading_hypothesis_label=cause.leading_hypothesis.label,
    )
```

**왜 confidence가 아니라 completeness인가:**

| 상황 | hypothesis_confidence | information_completeness | 적절한 행동 |
|------|----------------------|--------------------------|------------|
| 속보 직후, 출처 1개, 매우 그럴듯한 가설 | **0.85 (높음)** | 0.3 (낮음) | 🚫 **보류** (과거 보이스피싱 헤드라인에 시장이 오판한 유형) |
| 반복 확인된 사건, 가설 애매 | 0.5 (중간) | 0.8 (높음) | ⚖️ 양측 헷지 |
| 출처 다양 + 시장 반응 일치 + 가설 명확 | 0.8 | 0.85 | ✅ 유력 가설 기반 포지션 |
| 이견 많고 출처 적음 | 0.4 | 0.3 | 🚫 보류 |

**이메일/Slack 템플릿 표기 (확정 문구 제거):**
```
📌 유력 가설 (확정 아님): 지정학 긴장 고조 (단기 트리거 가설, 확률 80%)
⚠️ 대체 가설: 수요 붕괴 (15%) · 공급 증가 (5%)
📊 정보 충분성: 60% (출처 2개 · 시장 반응 일부 확인 · 발생 4시간 경과)
   ├ source_diversity: 0.5
   ├ market_context_coverage: 0.7
   ├ corroborating_signals: 0.6
   ├ freshness: 0.55
   └ low_contradiction: 0.6

💡 행동 (정보 충분성 기반):
   정보 중간 구간 → 양측 헷지 + 포지션 50% 축소
   (가설 확신도 75%와 무관하게 정보 충분성이 기준)
```

### 3-8. 데이터 모델 확장

`models/news_item.py`에 추가 (모든 필드가 "가설" 표기 일관):
```python
@dataclass
class CauseHypothesis:
    label: str
    hypothesis_type: str                  # "structural" | "trigger" | "alternative"
    evidence: list[str] = field(default_factory=list)
    direction_bias: str = ""
    probability: float = 0.0              # 가설의 상대적 확률
    hypothesis_confidence: float = 0.0    # 가설 자체 확신도 (참고)
    disqualifying_evidence: list[str] = field(default_factory=list)

@dataclass
class CompletenessBreakdown:
    source_diversity: float = 0.0          # 출처 다양성
    market_context_coverage: float = 0.0   # 시장지표 커버리지
    corroborating_signals: float = 0.0     # 교차 확증 시그널
    time_since_event_hours: float = 0.0    # 발생 후 경과시간
    contradicting_signals: float = 0.0     # 상충 시그널

@dataclass
class CauseAnalysis:
    structural_hypotheses: list[CauseHypothesis] = field(default_factory=list)
    short_term_trigger_hypotheses: list[CauseHypothesis] = field(default_factory=list)
    alternative_hypotheses: list[CauseHypothesis] = field(default_factory=list)
    leading_hypothesis: Optional[CauseHypothesis] = None   # 유력 가설 (확정 X)
    hypothesis_confidence: float = 0.0                     # 참고 지표
    information_completeness: float = 0.0                  # ⭐ Signal 주 기준
    completeness_breakdown: Optional[CompletenessBreakdown] = None

# NewsItem에 필드 추가
cause_analysis: Optional[CauseAnalysis] = None
```

`utils/db.py` news_items 테이블 ALTER (용어·의미 일치):
- `leading_hypothesis_label TEXT`          # 유력 가설 라벨 (확정 아님)
- `leading_hypothesis_type TEXT`           # structural / trigger / alternative
- `hypothesis_confidence REAL`             # 참고 지표
- `information_completeness REAL`          # ⭐ Signal 판단 기준
- `completeness_breakdown_json TEXT`       # 5개 서브 지표 원본
- `alternative_hypotheses_json TEXT`       # 대체 가설 목록 + 확률
- `structural_hypotheses_json TEXT`        # 구조 가설 목록

**이유:** 컬럼명에서 `dominant_cause`·`cause_confidence`를 배제해, DB 쿼리 작성 시에도 "확정 아닌 가설"·"information completeness가 주 기준"이 자연히 전달되도록 한다.

### 3-9. 비용 및 리스크 관리

| 항목 | 값 / 대응 |
|------|----------|
| Tier 2 추가 토큰 (분류 대비 ~2~3배) | 월 +$1~2 예상 (Gemini Flash 기준) |
| 정보 불완전 시 오판 위험 | **Signal Layer가 `information_completeness < 0.4`일 때 포지션 자동 보류**. 알림은 "가설·정보 부족" 라벨로 발송 |
| "확신은 높은데 정보 부족" 역설 | completeness를 주 기준으로 둔 이유. 이 케이스에서 Signal 보류 처리가 자동으로 됨 |
| UX 피로 (양측 시나리오 표시) | Leading hypothesis만 기본 노출, 대체 가설 및 completeness_breakdown은 접힘 |
| 원인 오인 방지 | "추정 원인" 대신 "유력 가설(leading hypothesis)"로 UI 표기. 확정 함의 주는 단어 전면 배제 |
| Cache 무효화 | Cause 판정은 새 맥락(market_context) 변화 + 새 출처 유입 시 재계산. 기본 24h TTL |

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
- **Cause 결과 포함**: Leading Hypothesis + 대체 가설 + **information_completeness 섹션 별도**
- 확정 어휘 배제 ("추정 원인" → "유력 가설", "dominant" 단어 불사용)
- Signal 섹션은 information_completeness 구간별로 행동 자동 라벨링

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
| **information_completeness 평균** (주요 기준) | N/A | ≥0.55 |
| **completeness<0.4 시 Signal 보류율** | N/A | 100% (자동 보류, 예외 없음) |
| hypothesis_confidence 평균 (참고 지표) | N/A | ≥0.5 |
| 동일 이벤트 대체 가설 노출률 | 0% | ≥60% (completeness<0.7일 때 필수 표시) |
| "확신 높은데 정보 부족" 케이스 오판 방지율 | 측정 불가 | ≥90% (completeness 기반 보류로 자동 해결) |
| missed_events 주간 건수 | 측정 개시 | 단기안 대비 -50% |
| 사후 가설 적중률 (주간 리뷰) | 측정 불가 | ≥60% (leading hypothesis가 실제 주요 요인과 일치) |
| 이메일 1건당 토큰 비용 | ~500 | ~1400 (Cause + completeness_breakdown 포함) |

---

## 10. 공개 질문 (구현 전 결정 필요)

**✅ 전부 결정 완료 (2026-04-19) — 이 섹션은 구현 스펙으로 확정.**

1. ~~Cause Analyzer Tier 2 호출 범위~~ → **(b) `event_severity >= 3`만 LLM 호출**. 비용 최소화. 나머지는 Tier 1 규칙만 적용.
2. ~~대체 가설 노출 방식~~ → **(b) 접힘 상태 기본**. 이메일·대시보드에 `<details>` 형태. 사용자가 클릭하면 펼침.
3. ~~Cause 적중률 회고 주기~~ → **(a) 주간 자동**. 매주 일요일 야간 cron으로 `missed_events.json` + `cause_cache.db` 재분석. 피드백 루프 단축.
4. ~~Cause Taxonomy 편집 방식~~ → **(a) YAML 직접 편집**. `config/cause_taxonomy.yaml` · `config/event_taxonomy.yaml`. 대시보드 UI는 구현 안 함.
5. ~~원인 확신도 낮을 때 기본 행동~~ → **결정됨**: information_completeness를 주 기준으로 전환. completeness<0.4면 hypothesis_confidence 무관 100% Signal 보류. 알림은 "가설·정보 부족" 라벨.
6. ~~completeness 5지표 가중치~~ → **기본값 유지** (source_diversity 0.25 / market_context_coverage 0.20 / corroborating_signals 0.20 / freshness 0.15 / low_contradiction 0.20). 2주 운영 후 튜닝 여부 재평가.
7. ~~completeness 구간 경계 0.7/0.4~~ → **초기값 유지 + 2주 후 재조정**. Phase 7 데이터 축적 기간과 맞물려 재검토.

### 10-1. 확정 사항 요약 (구현 반영 시 체크리스트)
- [x] Tier 2 호출 조건: `if event_severity >= 3 and classifier_confidence < threshold: call_llm()`
- [x] 이메일 템플릿: Dominant 가설 기본 노출 + `<details><summary>대체 가설 보기</summary>...</details>`
- [x] 주간 회고 cron: `scheduler/pipeline_scheduler.py`에 `CronTrigger(day_of_week="sun", hour=23)` 추가
- [x] Taxonomy 편집: YAML 직접. 스키마 검증용 Pydantic 모델만 제공 (UI 미구현)
- [x] completeness 가중치 상수: `src/analyzers/cause_analyzer.py` 모듈 상단 `_DEFAULT_WEIGHTS` 딕셔너리
- [x] completeness 구간: `_THRESHOLD_HIGH = 0.7`, `_THRESHOLD_LOW = 0.4` 상수. 2주 후 운영 데이터로 재평가

---

## 11. 참조

- Phase 6 단기안 구현: `src/analyzers/event_actions.py`, `src/utils/missed_events.py`
- LLM 연동 기준: `src/analyzers/summarizer.py` (Gemini 2.5 Flash, 시장 context 주입)
- 영향 체인 기존 사전: `src/analyzers/impact_chain_analyzer.py` (5대 체인)
- 이메일 템플릿: `src/notifiers/email_notifier.py`
- 대시보드: `src/app.py`
