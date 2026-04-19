# 아키텍처: NIAS (News-Invest Alert System) v2.0

> AI_Playbook/06_Projects/Project_Template/Architecture.md 기반 작성

---

## 1. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    Presentation Layer                            │
│         Streamlit 1.40+ │ Jinja2 (이메일 템플릿)                │
├──────────────────────────────��──────────────────────────────────┤
│                    Delivery Layer                                │
│      Gmail API │ Telegram Bot │ Markdown Report                 │
├───────────────────────────────���─────────────────────────────────┤
│                    Alert Engine                                  │
│   13 Rules (뉴스 5 + 지표 6 + 지정학 2)                         │
│   쿨다운 │ 배치 큐 │ 템플릿 선택 │ 이력 저장                    │
├──────────┬──────────┬──────────┬────────────��───────────────────┤
│ Analysis │ Geo      │ Market   │ Impact Chain                   │
│ Pipeline │ Classif. │ Indicator│ Analyzer                       │
│ (14-Stage)│ (L1-L5) │ Threshold│ (5 chains)                    │
├──────────┴──────────┴──────────┴──────��─────────────────────────┤
│                    Preprocessing Layer                           │
│    URL Dedup │ Title Dedup │ Cache │ Keyword Filter              │
├──────────┬──────────┬──────────┬──────────┬──��──────────────────┤
│ News     │ Market   │ Geo      │ Economic │ Social              │
│ Collect  │ Data     │ Sources  │ Indicator│ Monitor             │
│ RSS+GN   │ yfinance │ RSS+GPR  │ FRED+BOK │ X/SNS              │
│ +DART    │ FDR+KIS  │          │          │                     │
├��─────────┴──────────┴─��────────┴──────────┴─────────────────────┤
│                    Data Layer                                    │
│    SQLite 3    │    JSON Cache    │    File Storage              │
└──────���────────────────────────���───────────────────────────────���─┘
```

---

## 2. 설계 원칙

| 원칙 | 적용 방법 |
|------|-----------|
| 모듈 독립성 | NewsItem 데이터 모델 통해서만 통신. 수집기 추가/제거가 분석 레이어에 영향 없음 |
| 점진적 확장 | 기존 v2 파이프라인 유지 + 새 모듈을 플러그인 방식으로 추가 |
| 장애 격리 | 단일 수집기 장애 → 전체 중단 없음. LLM 장애 → 키워드 fallback |
| 뉴스-지표 이원화 | 텍스트(뉴스)와 수치(지표) 경로 분리, Alert Engine에서 합류 |
| 임계값 외부화 | 모든 임계값 config.py에서 중앙 관리, 코드 수정 없이 조정 |

---

## 3. 컴포넌트 상세

### 3.1 수집 레이어 (Collectors)

| 항목 | 내용 |
|------|------|
| 역할 | 42개 소스에서 뉴스/지표/공시/SNS 데이터 수집 |
| 기술 | feedparser, yfinance, FinanceDataReader, requests, snscrape |
| 입력 | RSS URL, API 엔드포인트, 티커 심볼 |
| 출력 | NewsItem[], MarketIndicator[], SentimentIndicator[] |
| 의존성 | config.py (소스 목록, API 키) |

### 3.2 전처리 레이어 (Preprocessing)

| 항목 | 내용 |
|------|------|
| 역할 | 중복 제거, 캐시 필터, 키워드 분류, 텍스트 정제 |
| 기술 | difflib, hashlib, trafilatura, BeautifulSoup4 |
| 입력 | Raw NewsItem[] |
| 출력 | Filtered & Tagged NewsItem[] |
| 의존성 | utils/dedup_v2.py, utils/cache.py |

### 3.3 분석 레이어 (Analyzers)

| 항목 | 내�� |
|------|------|
| 역할 | 14-Stage 분석: 스코어링, 시간/시장/지정학 분류, 종목 매핑, LLM 요약, 시그널 집계 |
| 기술 | Gemini 2.5 Flash API, 키워드 매칭, 수학적 스코어링 |
| 입력 | Filtered NewsItem[] + MarketIndicator[] |
| 출력 | MarketVerdict + Analyzed NewsItem[] + GeopoliticalAssessment[] |
| 의존성 | Gemini API (외부), config.py (키워드/임계값) |

### 3.4 알림 엔진 (Alert Engine)

| 항목 | 내용 |
|------|------|
| 역할 | 13종 룰 기반 조건 매칭 → 채널별 알림 디스패치 |
| 기술 | 룰 엔진 (조건 함수 + 쿨다운 + 배치 큐) |
| 입력 | Analyzed NewsItem[] + MarketIndicator[] + GeopoliticalAssessment[] |
| 출력 | Alert dispatch (이메일/텔레그램) + alert_history 기록 |
| 의존성 | notifiers/email_notifier.py, notifiers/telegram_notifier.py |

### 3.5 배달 레이어 (Delivery)

| 항목 | 내용 |
|------|------|
| 역할 | 이메일 발송, 텔레그램 전송, 대시보드 표시, 리포트 생성 |
| 기술 | Gmail API (OAuth2), Telegram Bot API, Streamlit, Jinja2 |
| 입력 | Alert 객체 + HTML 템플릿 |
| 출력 | 이메일/텔레그램 메시지, 대시보드 페이지, MD 리포트 |
| 의존성 | Gmail credentials, Telegram token |

---

## 4. 데이터 흐름

```
[42개 소스]
    │
    ▼
[수집 레이어] → NewsItem[] + MarketIndicator[]
    │
    ▼
[전처리] → Dedup → Cache → Keyword Tag
    │                              │
    │        ┌─────────────────────┤
    ▼        ▼                     ▼
[분석 14-Stage]              [지표 임계값 검사]
    │  스코어링                    │
    │  시간/시장 분류              │ 돌파 시 → IndicatorNewsItem
    │  지정학 L1-L5               │
    │  종목 매핑                   │
    │  LLM 요약                    │
    │  영향 체인                   │
    │  시그널 집계                 │
    ▼                              ▼
[알림 엔진 (13 Rules)] ←──── 합류
    │
    ├── 즉시 발송 (URGENT/VIX_PANIC/GEO_L4+)
    ├── 배치 발송 (HIGH/WATCHLIST → 30-60분 집계)
    └── 정기 발송 (DAILY → 08:00/18:00)
    │
    ▼
[배달] → 이메일 / 텔레그램 / 대시보드 / MD 리포트
```

---

## 5. 인프라 구성

| 환경 | 구성 | 용도 |
|------|------|------|
| 로컬 | Windows 11 + Python 3.12 + APScheduler | 개발 & 운영 (단일 사용자) |
| 데이터 | SQLite 3 + JSON 캐시 | 뉴스 이력 + URL 캐시 + 지표 히스토리 |
| 스케줄링 | APScheduler BackgroundScheduler | 시간대별 차등 주기 |

---

## 6. 보안 아키텍처

| 레이어 | 보안 조치 |
|--------|-----------|
| API 키 | .env 파일 로컬 저장 + .gitignore 등록 |
| Gmail 인증 | OAuth 2.0 (credentials.json + token.json) |
| 데이터 | 공개 데이터만 수집 (개인정보 없음) |
| 네트워크 | HTTPS (API 통신), Rate Limiting (API 호출 제한) |
| 파일 | credentials/token 파일 .gitignore 필수 |

---

## 7. 모니터링

| 대상 | 방법 | 알림 조건 |
|------|------|-----------|
| 파이프라인 실행 | Python logging → pipeline.log | ERROR 레벨 발생 시 |
| 수집 성공률 | 수집기별 성공/실패 카운트 | 성공률 < 80% |
| LLM API | 연속 실패 카운트 | 3회 연속 실패 → fallback 전환 |
| 이메일 발송 | 발송/실패 로그 | 실패 3회 연속 → 관리자 알림 |
| 디스크 | data/ 폴더 사이즈 | > 5GB → 오래된 캐시 정리 |
| 스케줄러 | APScheduler job 상태 | 미스된 job 감지 |

---

## 8. 이벤트 Fallback 레이어 (2026-04-18 Phase 6)

키워드 사전 의존도를 낮추기 위한 2단 구조. 기존 `geopolitical_classifier` 내부에 삽입.

```
[수집] → [keyword_filter] → [geopolitical_classifier]
                                 │
                                 ├── 에스컬레이션 키워드 hit → L1~L5 확정
                                 │
                                 └── miss (기존엔 여기서 탈락)
                                     ▼
                                 [event_actions.py fallback]
                                 엔티티 클래스 × 액션 카테고리 매트릭스
                                 - shipping_lane × blockade → L3 + impact +2.5
                                 - strategic_geography × attack → L3
                                 - commodity × supply_disruption → L3
                                 - institution × policy_shock → L3
                                 - … 기타 조합 → L1~L2
                                     ▼
                             item.event_fallback=True
                             item.event_category / event_entity_class 기록
                                     ▼
                             [impact_scorer] geo_mult × + event_boost +
                                     ▼
                             [alert_engine] NEWS_RULE_PRIORITY:
                             지정학_L4 > L3 > 긴급속보 > 이벤트후보 > 관심종목 > 경제지표 > 고영향뉴스
                                     ▼
                             매칭 無 + impact≥5.0 → data/missed_events.json 롤링 기록
```

### 엔티티 클래스 (5종, 민감도 순)
`shipping_lane` → `strategic_geography` → `commodity` → `institution` → `major_corporate`

### 액션 카테고리 (7종)
`blockade` · `supply_disruption` · `attack` · `sanction` · `official_warning` · `policy_shock` · `major_incident`

### 데이터 모델 / 영속화
- `models/news_item.py`: `event_fallback`, `event_category`, `event_entity_class` 필드 추가
- `utils/db.py`: `news_items` 테이블에 동일 3개 컬럼 ALTER 자동 마이그레이션 (기동 시)
- `data/missed_events.json`: 누락 이벤트 롤링(상한 2000건) — 중기안(event_type_classifier) 학습 입력

### 수집 소스 아키텍처 업데이트
- `GOOGLE_NEWS_QUERIES` + `GOOGLE_NEWS_QUERIES_GEOPOLITICAL` dead code 활성화 (rss_collector 연결)
- `GOOGLE_NEWS_QUERIES_HOTSPOT` 8종 신규 — 호르무즈·해상봉쇄·수에즈·이란·대만·북한·우크라이나·홍해
- `geopolitical_fast` 잡 — 24/7 5분 간격 (main 잡과 2분 오프셋, ID `geopolitical_fast`)
- `MAX_ARTICLES_PER_FEED` 30 → 100
- `RSS_SOURCES_GLOBAL_DIRECT` 11개 준비 (AP/BBC/AJ/Guardian/Reuters/NYT) — `ENABLE_EXTENDED_GLOBAL` 플래그 OFF 상태

### 대시보드 추가
- `🔔 놓친 이벤트` 탭 — `missed_events.json` 읽어 metrics 3종(누락 수·fallback 매칭·평균 impact) + 테이블
- 환율 중복(FDR 실시간 vs ECOS 공시)은 UI에서 `KRW/USD_ECOS` 숨김 처리 (`_UI_HIDDEN_TICKERS`)
- KPI 상단 슬롯 8 → 12개로 확대

### 자동 시작 (Task Scheduler 이관)
- `NIAS_Scheduler` 작업 — 로그온 트리거 + 5분 keep-alive + 실패 시 1분 후 3회 재시도
- 기존 Windows Startup 폴더 방식(`NIAS_AutoStart.lnk`)은 Update 강제 재부팅 후 복구 실패로 2026-04-18 폐기
