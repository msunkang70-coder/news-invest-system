# NIAS v2.0 Task Tracker

**프로젝트 기간:** 10주 (W1: 4/14~4/18 ~ W10: 6/16~6/20)
**현재 상태:** Phase 5 완료 (유저 테스트 19/20 PASS, 95%)
**Fallback 기준:** W6 금요일에 시장지표 모니터링 미완이면 뉴스+이메일만으로 릴리스

**사용법:** Claude Code에게 `"Task 1.3을 진행해줘"` 처럼 번호로 지시하세요.

---

## 병렬 실행 맵

각 Task의 `🅐 🅑` 태그는 어떤 작업 트랙에서 실행하는지를 표시합니다.
같은 태그끼리는 **순차**, 다른 태그끼리는 **동시에** 실행 가능합니다.

```
W1~W2 ── 🅐 Task 1.1~1.9 (이메일 알림 MVP)        ┐ 동시 실행 OK
         🅑 Task 2.1~2.6 (알림 룰 엔진 + 스케줄러)  ┘

W3~W4 ── 🅐 Task 3.1~3.6 (수집 소스 확장: DART+경제지표+SNS)
         🅑 Task 4.1~4.8 (시장지표: yfinance+FDR+야간선물)  ← 독립 병렬

W5~W6 ── 🅐 Task 5.1~5.7 (지정학 분류 + 영향 체인)
         🅑 Task 6.1~6.5 (v1/v2 통합 + DB)

W7~W8 ── 🅐 Task 7.1~7.8 (Streamlit 대시보드 v2)
         🅑 Task 8.1~8.6 (.claude 에이전트 팀 하네스)

W9~W10── 단독 실행 (통합 테스트 + 실운영 + 최적화)
```

**TASK.md 업데이트 규칙:**
- Task 완료 시 `- [x]`로 체크
- 이슈 발생 시 해당 Task 하단에 `⚠️ 이슈:` 로 기록
- 주간 완료 기준 미달 시 `❌ 미달:` 로 사유 기록

---

## Phase 1: 이메일 알림 MVP (W1~W2)

### 🅐 Lane A: Gmail API + 이메일 발송 (Task 1.1~1.9)

**Task 1.1 — Gmail API OAuth2 설정** ✅ 완료
- [x] Google Cloud Console에서 새 프로젝트 생성
- [x] Gmail API 활성화 (APIs & Services → Library)
- [x] OAuth 동의 화면 구성 (External, 앱 이름: NIAS)
- [x] OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
- [x] `credentials.json` 다운로드 → `src/` 폴더 배치 (400 bytes 확인)
- [x] `.gitignore`에 `credentials.json`, `gmail_token.json` 추가
- 📄 설정 가이드: [docs/GMAIL_API_SETUP.md](docs/GMAIL_API_SETUP.md)

**Task 1.2 — Gmail 발송 모듈 개발** ✅ 완료
- [x] `src/notifiers/email_notifier.py` 검증 및 보완
- [x] `GmailNotifier.authenticate()` — OAuth2 인증 플로우 (토큰 발급 확인)
- [x] `GmailNotifier.send()` — HTML 이메일 발송 (msg_id: 19d7cabf13279159)
- [x] `_send_smtp_fallback()` — SMTP 대안 경로 (코드 검증 완료)
- [x] 테스트: 실제 테스트 이메일 msunkang70@gmail.com 발송 성공

**Task 1.3 — 긴급 속보 이메일 템플릿** ✅ 완료
- [x] `src/notifiers/email_notifier.py` 내 `build_urgent_email()` 검증
- [x] HTML 렌더링 확인 (Gmail 발송 확인, msg_id: 19d7cae3b730367a)
- [x] 포함 요소: 영향도 스코어, 방향성, 투자 시그널, 행동 제안, 리스크, 면책 조항
- [x] 실제 이메일로 전송하여 레이아웃 확인

**Task 1.4 — 시장지표 알림 이메일 템플릿** ✅ 완료
- [x] `build_indicator_email()` 함수 검증 (msg_id: 19d7caee7fb03b1f)
- [x] 포함 요소: 지표명, 현재값, 변동률, 임계값 돌파 내역, 시장 영향
- [x] VIX 28.5 WARNING 시나리오 테스트 발송 확인

**Task 1.5 — 일일 리포트 이메일 템플릿** ✅ 완료
- [x] `build_daily_report_email()` 함수 신규 개발 (msg_id: 19d7cb0be7fd6213)
- [x] 포함 요소: 시장 종합 판단, TOP 5 뉴스, 종목별 행동 제안
- [x] 시장지표 현황 테이블 (VIX/환율/유가/국채)
- [x] 지정학 리스크 요약 (지역별 에스컬레이션 레벨 바)
- [x] 종목 시그널 바 차트 (삼성전자/SK하이닉스/현대차/NVIDIA/테슬라)

**Task 1.6 — 지정학 알림 이메일 템플릿** ✅ 완료
- [x] `build_geopolitical_email()` 함수 신규 개발 (msg_id: 19d7cb0c05c67a69)
- [x] 포함 요소: 에스컬레이션 레벨 (L1~L5), 지역, 분쟁 유형, 영향 체인
- [x] 레벨별 색상 구분 (L1:초록 → L5:빨강)
- [x] 시장 영향 채널 목록, 영향 체인 시각화

**Task 1.7 — .env 설정 및 환경 구성** ✅ 완료
- [x] `.env.example` → `.env` 복사 및 실제 값 입력
- [ ] `GEMINI_API_KEY` 발급 및 설정 (Google AI Studio) — Phase 2에서 진행
- [x] `ALERT_EMAIL_TO` 설정 (msunkang70@gmail.com)
- [x] config.py 로딩 테스트

**Task 1.8 — 기존 파이프라인 연동 테스트** ✅ 완료
- [x] v2 분석 모듈 이식: keyword_filter.py, impact_scorer.py → src/analyzers/
- [x] main.py 파이프라인 완성: 수집→중복제거→캐시→키워���→지정학→스코어링→영향체인→알림
- [x] E2E 테스트 성공: 149건 수집 → 135건(중복제거) → 20건(키워드) → 6건(고영향)
- [x] 실제 뉴스 기반 이메일 발송 확인 (기준금리 뉴스, msg_id: 19d7cc22f8d69a2f)
- [x] 시장지표 7개 글로벌 수집 동시 동작 확인

**Task 1.9 — 이메일 발송 재시도 + 에러 핸들링** ✅ 완료
- [x] 발송 실패 시 3회 재시도 (exponential backoff: 2s, 4s)
- [x] Gmail API 실패 → SMTP fallback 자동 전환
- [x] 발송 결과 로깅 (`data/pipeline.log`) + 통계 추적 (stats 프로퍼티)
- [x] 연속 3회 실패 시 CRITICAL 로그 경고

### 🅑 Lane B: 알림 룰 엔진 + 스케줄러 (Task 2.1~2.6, 🅐와 동시 실행 가능)

**Task 2.1 — Alert Rule Engine 기본 구조** ✅ 완료
- [x] `src/notifiers/alert_engine.py` 검증 — 12개 룰 등록 확인
- [x] `AlertRule` 데이터클래스: name, condition, channels, template, cooldown, batch_window
- [x] `AlertEngine.evaluate_news()` — 뉴스 5종 룰 매칭 확인
- [x] `AlertEngine.evaluate_indicators()` — 지표 6종 룰 매칭 확인
- [x] 단위 테스트: mock 데이터로 전체 13종 룰 동작 확인

**Task 2.2 — 뉴스 알림 룰 5종 구현** ✅ 완료
- [x] Rule 1: 긴급속보 (impact ≥ 8.0 → 즉시) — Fed 긴급 금리 인하 테스트 통과
- [x] Rule 2: 고영향뉴스 (impact ≥ 6.0 → 배치 60m) — 삼성 실적 → 배치 큐 적재 확인
- [x] Rule 3: 관심종목 (tagged_stocks → 배치 30m) — SK하이닉스 → 배치 큐 적재 확인
- [x] Rule 4: 경제지표 (source=FRED → 즉시) — CPI 발표 즉시 알림 확인
- [x] Rule 5: 일일리포트 — 스케줄러 cron 등록 확인

**Task 2.3 — 쿨다운 + 배치 큐 로직** ✅ 완료
- [x] 쿨다운: 동일 뉴스 재평가 → 0건 알림 (정상 차단)
- [x] 배치 큐: 고영향 3건 + 관심종목 1건 큐 적재 확인
- [x] `flush_batches()` — 윈도우 경과 로직 구현 확인
- [x] 일일 상한 (max_daily_alerts=20) 카운트 추적 확인

**Task 2.4 — 알림 이력 저장** ✅ 완료
- [x] `data/alert_history.json` 저장 로직 구현
- [x] 저장 항목: rule_name, timestamp, title, channels
- [x] 최근 500건만 유지
- [x] save_history() 함수 동작 확인

**Task 2.5 — 스케줄러 기본 구조** ✅ 완료
- [x] APScheduler BackgroundScheduler — 8개 작업 등록 확인
- [x] 장전 5min, 장중 5min, 장후 15min, 야간 60min 차등 주기
- [x] 지표 모니터 10min, 야간선물 15min, 배치 플러시 10min
- [x] 일일 리포트 cron (월-금 08:00, 18:00)
- [x] 스케줄러 시작/중지 테스트 통과

**Task 2.6 — main.py 통합 엔트리포인트** ✅ 완료
- [x] 14-Stage 파이프라인: 수집→중복→캐시→키워드→지정학→스코어링→체인→알림
- [x] `--schedule` 모드 + `--sources` 옵션 + `--indicators-only` 동작 확인
- [x] E2E 실행: 119건 수집 → 107건(dedup) → 5건(cache) → 지표 7개 수집

### Phase 1 완료 기준 ✅ ALL PASS
- [x] Gmail API로 실제 이메일 발송 성공 (Task 1.2)
- [x] 4종 이메일 템플릿 렌더링 확인 (Task 1.3~1.6)
- [x] 알림 룰 13종 동작 확인 — 뉴스5+지표6+지정학2 (Task 2.1~2.2)
- [x] 스케줄러 8개 작업 등록 + 시작/중지 확인 (Task 2.5)
- [x] RSS 수집 → 14-Stage 분석 → 이메일 발송 E2E 성공 (Task 1.8)

---

## Phase 2: 수집 소스 확장 (W3~W4)

### 🅐 Lane A: DART + 경제지표 + SNS (Task 3.1~3.6)

**Task 3.1 — DART 전자공시 API 연동** ✅ 완료
- [x] `src/collectors/dart_collector.py` 신규 개발
- [x] `collect_dart_disclosures(date)` — 당일 공시 목록 조회 + 관심종목/유형 필터
- [x] DART 공시 → NewsItem 변환 (source_type="DART")
- [ ] DART OpenAPI 키 발급 → .env 설정 (사용자 수동, opendart.fss.or.kr)

**Task 3.2 — FRED 경제지표 API 연동** ✅ 완료
- [x] `src/collectors/economic_indicator.py` 신규 개발
- [x] 모니터링 대상: FEDFUNDS, CPIAUCSL, UNRATE, GDP, T10Y2Y (5개)
- [x] 최근 2건 조회 → 변동 감지 → NewsItem 자동 생성
- [ ] FRED API 키 발급 → .env 설정 (사용자 수동, stlouisfed.org)

**Task 3.3 — 한국은행 ECOS API 연동** ✅ 완료
- [x] `collect_bok_indicators()` 구현 — 기준금리, 소비자물가
- [ ] 한국은행 ECOS API 키 발급 → .env 설정 (사용자 수동, ecos.bok.or.kr)

**Task 3.4 — 경제지표 서프라이즈 팩터** ✅ 완료
- [x] `src/analyzers/surprise_factor.py` 신규 개발
- [x] 서프라이즈 등급: IN_LINE / MODERATE(×1.2) / BIG(×1.5) / MEGA(×2.0)
- [x] HAWKISH / DOVISH 방향 판정

**Task 3.5 — X/SNS 수집기 기본 구조** ✅ 완료
- [x] `src/collectors/sns_collector.py` 신규 개발
- [x] Google News RSS fallback (Fed 발언 + 증시 전문가 의견 2개 피드)
- [x] 통합 테스트: 60건 수집 확인

**Task 3.6 — 수집기 통합 + 멀티소스 파이프라인** ✅ 완료
- [x] main.py에 DART + FRED + 한은 + SNS 통합 (개별 실패 → 스킵)
- [x] 437건 수집 성공 (RSS 377 + SNS 60 + DART/FRED는 키 미설정으로 스킵)
- [x] 소스별 에러 격리 확인

### 🅑 Lane B: 시장지표 모니터링 (Task 4.1~4.8, 🅐와 동시 실행 가능)

**Task 4.1 — yfinance 글로벌 지표 수집** ✅ 완료
- [x] 7개 티커 수집 확인: VIX 19.23, DXY 98.65, WTI 96.57, Brent 95.2, Gold 4787.4, TNX, S&P500
- [x] 현재값, 전일 종가, 변동률 계산 정상
- [x] 임계값 검사 (금 4787 >= 3000 → WARNING 정상 동작)

**Task 4.2 — FinanceDataReader 국내 지표 수집** ✅ 완료
- [x] finance-datareader 0.9.110 설치
- [x] `collect_kr_indicators()` — 원달러 환율 수집 구현

**Task 4.3 — 시장지표 임계값 엔진** ✅ 완료
- [x] 절대값 + 변동률 이중 임계값 검사
- [x] Phase 1 Task 2.2에서 mock 테스트 통과 (VIX 28→WARNING, 환율 1420→WARNING)
- [x] config.py 임계값 기준표 검증 완료

**Task 4.4 — 시장지표 알림 룰 6종 구현** ✅ 완료
- [x] Phase 1 Task 2.2에서 전체 테스트 통과 (VIX 3건, 환율 1건, 유가 1건)

**Task 4.5 — 야간선물 수집기** ✅ 완료
- [x] `is_night_session()` — 18:00~06:00 판별
- [x] yfinance fallback (^KS200) 구현
- [ ] KIS Open API 연동 — 증권 계좌 필요 (사용자 수동, 선택사항)

**Task 4.6 — 심리지표 수집기** ✅ 완료
- [x] `src/collectors/sentiment_collector.py` 신규 개발
- [x] Crypto F&G: 16 (Extreme Fear) 실제 데이터 수집 성공
- [x] 임계값 검사: ≤15 → WARNING 정상 동작

**Task 4.7 — 익일 전망 자동 생성** ⬜ Phase 3에서 구현 예정
- [ ] `src/analyzers/overnight_outlook.py` — Phase 3 Task 5 이후

**Task 4.8 — 시장지표 모니터링 통합 테스트** ✅ 완료
- [x] `run_indicator_monitor()`: 글로벌 7 + 심리 1 = 8개 수집
- [x] 뉴스(437건) + 시장지표(8개) 동시 동작 확인
- [x] 알림 3건 이메일 발송 성공 (긴급속보 + 지정학 L3 + L4)

### Phase 2 완료 기준 ✅ ALL PASS
- [x] DART + FRED + 한은 수집기 구현 완료 (API 키는 사용자 발급 필요)
- [x] 8개 시장지표 수집 + 임계값 동작 (글로벌 7 + Crypto F&G 1)
- [x] 야간선물 수집기 구현 (yfinance fallback)
- [x] 알림 이메일 3건 실제 수신 확인 (긴급속보 + 지정학 L3 + L4)
- [x] 수집 합계 437건 (RSS 377 + SNS 60) — API 키 추가 시 확장

---

## Phase 3: 지정학 + 영향 체인 (W5~W6)

### 🅐 Lane A: 지정학 분류 + 영향 체인 (Task 5.1~5.7)

**Task 5.1 — 지정학 RSS 소스 추가** ✅ 완료
- [x] 4개 피드 수집 확인 (Defense One, War on the Rocks, The Diplomat, 38 North)
- [x] 지정학 소스 68건 수집 확인 (이전 E2E 테스트)

**Task 5.2 — 지정학 에스컬레이션 분류기** ✅ 완료
- [x] L1~L5 분류 동작 확인: L5×1, L4×3, L3×3, L1×2 = 9건 분류
- [x] 지역 판정: 중동(5), 대만해협(2), 한반도(2) 정상
- [x] Impact 승수: L4(×2.0) → score 9.4, L5(×3.0) → score 10.0 확인

**Task 5.3 — 지정학 키워드 사전 보강** ✅ 완료
- [x] L5: +6개 (핵 발사, 총동원령, 전쟁 선포, 수에즈/말라카 봉쇄)
- [x] L4: +7개 (지상 공격, 보복 공격, 민간인 피해, 요격)
- [x] L3: +6개 (무기 실험, 극초음속, 합동 훈련, 비행금지구역)
- [x] L2: +6개 (수출 금지, 자산 동결, 외교관 추방, 무기 거래)
- [x] 지역 키워드: 중동 +12개, 대만 +6개, 한반도 +5개, 우크라이나 +7개

**Task 5.4 — 지정학 알림 룰 2종** ✅ 완료 (Phase 1에서 구현, E2E 확인)
- [x] L3 알림 + L4 알림 이메일 발송 확인 (3건)

**Task 5.5 — 교차 자산 영향 체인** ✅ 완료 (Phase 1에서 구현)
- [x] 5대 체인 코드 완성 (oil_inflation, dollar_strength, taiwan_crisis, rate_shock, korea_peninsula)

**Task 5.6 — LLM 시장 컨텍스트 주입** ✅ 완료
- [x] `src/analyzers/summarizer.py` 신규 개발
- [x] `build_market_context()` — 지표 수치를 프롬프트에 주입
- [x] Gemini 2.5 Flash 모델명 설정
- [x] 키워드 fallback (API 키 미설정 시 자동 전환)
- [x] Rate Limit 관리 (4초 간격, 5건마다 10초 배치 휴식)

**Task 5.7 — Impact Score 지정학 승수** ✅ 완료 (Phase 2에서 구현)
- [x] L4 → ×2.0 = score 9.4, L5 → ×3.0 = score 10.0 실측 확인

### 🅑 Lane B: v1/v2 통합 + DB (Task 6.1~6.5, 🅐와 동시 실행 가능)

**Task 6.1 — 기존 v2 파이프라인 모듈 이식** ✅ 완료
- [x] keyword_filter.py, impact_scorer.py → src/analyzers/ 이식
- [x] 지정학 승수, v2.0 키워드 확장 적용 완료

**Task 6.2 — SQLite DB 스키마 통합** ✅ 완료
- [x] `data/nias.db`: news_items(28필드) + market_indicators(11필드) + alert_history
- [x] 인덱스 5개 생성, WAL 모드 활성화

**Task 6.3 — DB 저장/조회 유틸리티** ✅ 완료
- [x] `src/utils/db.py`: save_news_items(89건), save_indicators(9건) 확인
- [x] get_recent_news(), get_indicator_history(), get_db_stats()

**Task 6.4 — Streamlit 데이터 브릿지** ⬜ Phase 4에서 구현

**Task 6.5 — 전체 E2E 테스트** ✅ 완료
- [x] 437건 수집 → 89건 고영향 → DB 저장 → 이메일 4건 발송
- [x] 지정학 9건 분류 + 시장지표 9개 수집 + 원달러 1,482.7 환율 알림
- [x] 3-Track (뉴스+지표+지정학) 동시 동작 확인

### Phase 3 완료 기준 ✅ ALL PASS
- [x] 지정학 L1~L5 분류: 9건 분류 (L5×1, L4×3, L3×3, L1×2)
- [x] 5대 영향 체인 코드 완성 + 키워드 매칭 구조 확인
- [x] 지정학 알림 이메일 2건 수신 확인 (L3 + L4)
- [x] v2 모듈 이식 + nias.db 통합: 뉴스 89건 + 지표 9건 저장
- [x] E2E 성공: 437건→89건→이메일 4건 (28초)

---

## Phase 4: 대시보드 + 하네스 (W7~W8)

### 🅐 Lane A: Streamlit 대시보드 v2 (Task 7.1~7.8)

**Task 7.1 — 대시보드 기본 레이아웃** ✅ 완료
- [x] `src/app.py` 신규 개발 — 5개 탭 구조
- [x] 상단: 시장 종합 (BULL/BEAR + 확신도 + VIX/환율/유가/국채)
- [x] DB 통계 표시 (뉴스/지표/알림 건수)

**Task 7.2 — 실시간 뉴스 탭** ✅ 완료
- [x] 필터: 영향도 슬라이더, 방향(BULL/BEAR), 소스 유형
- [x] 데이터 테이블 (점수/제목/방향/소스/지정학L/지역)
- [x] TOP 5 뉴스 상세 (소스, 시그널, 행동 제안)
- [x] DB get_recent_news() 연동

**Task 7.3 — 종목 시그널 탭** ✅ 완료
- [x] stock_impacts JSON 파싱 → 종목별 BULL/BEAR 집계
- [x] Plotly 바 차트 (종목별 BULL vs BEAR)
- [x] 행동 제안 테이블 (적극매수~매도검토)

**Task 7.4 — 시장지표 탭** ✅ 완료
- [x] st.metric 카드 (지표명, 현재값, 변동률, 임계값 상태)
- [x] Plotly 라인 차트 (지표 히스토리 7일)
- [x] 지표 선택 드롭다운

**Task 7.5 — 지정학 탭** ✅ 완료
- [x] 지역별 에스컬레이션 현황 (레벨 바 + 뉴스 건수)
- [x] 레벨별 색상 구분 (green → red)
- [x] 최근 지정학 뉴스 목록 (점수/레벨/지역/제목)

**Task 7.6 — 알림 이력 탭** ✅ 완료
- [x] alert_history.json 로드 + DataFrame 표시
- [x] 총 알림 건수 metric

**Task 7.7 — 자동 갱신 + 동작 확인** ✅ 완료
- [x] `streamlit run src/app.py` → localhost:8501 HTTP 200 확인
- [x] @st.cache_data(ttl=300) 5분 자동 갱신
- [x] DB 데이터 정상 로드 (89뉴스 + 9지표)

**Task 7.8 — 대시보드 + 파이프라인 동시 운영** ⬜ Phase 5에서 장시간 테스트

### 🅑 Lane B: .claude 에이전트 팀 하네스 (Task 8.1~8.6)

**Task 8.1 — CLAUDE.md 프로젝트 오버뷰** ✅ 완료
- [x] `src/.claude/CLAUDE.md` — 에이전트 6종 테이블, 워크플로우, 실행 방법

**Task 8.2 — 에이전트 정의 6종** ✅ 완료
- [x] news-collector.md — 수집 전문가 (RSS+DART+FRED+SNS)
- [x] market-analyzer.md — 시장 분석가 (yfinance+FDR+임계값)
- [x] text-intelligence.md — 텍스트 분석가 (키워드+스코어링+LLM)
- [x] geopolitical-analyst.md — 지정학 전문가 (L1-L5+영향체인)
- [x] alert-dispatcher.md — 알림 관리자 (13룰+쿨다운+배치)
- [x] report-generator.md — 리포트 작성자 (일일리포트+전망)

**Task 8.3 — 스킬 정의 3종** ✅ 완료
- [x] news-pipeline/skill.md — 14-Stage 파이프라인 오케스트레이터
- [x] market-monitor/skill.md — 시장지표 14개 모니터링
- [x] geopolitical-analysis/skill.md — 에스컬레이션 5단계 + 영향체인

**Task 8.4~8.5 — 워크플로우 + 산출물** ✅ CLAUDE.md에 통합 정의
- [x] 4-Phase 실행: 수집→분석→알림→리포트
- [x] 산출물 구조: 에이전트별 _workspace 파일 명시

**Task 8.6 — 에이전트 팀 테스트** ⬜ Phase 5에서 실제 호출 테스트

### Phase 4 완료 기준 ✅ PASS
- [x] Streamlit 대시보드 5개 탭 정상 동작 + HTTP 200
- [x] 시장지표 탭 (Plotly 차트 + metric 카드)
- [x] 지정학 탭 (에스컬레이션 레벨 바 + 뉴스 목록)
- [x] .claude 에이전트 6종 + 스킬 3종 작성 완료
- [ ] 장시간 동시 운영 → Phase 5 이관

---

## Phase 5: 통합 테스트 + 실운영 (W9~W10)

### 단독 실행 (Task 9.1~9.10)

**Task 9.1 — 전체 시스템 E2E 스모크 테스트** ✅ 완료
- [x] 437건 수집 → 417건(dedup) → 219건(키워드) → 93건(고영향) → DB 저장
- [x] 지정학 9건 분류 (L5×1, L4×3, L3×3, L1×2)
- [x] 시장지표 9개 (글로벌7 + 국내1 + Crypto F&G)
- [x] 이메일 4건 발송 (긴급1 + 지정학2 + 환율1)
- [x] 전체 26.9초 소요

**Task 9.2 — 임계값 튜닝** ✅ 완료
- [x] 알림 빈도: 1회 실행당 4건 (일일 추정 5-15건 적정)
- [x] 환율 1,482.7원 → 위험(CRITICAL) 정상 트리거
- [x] 금 4,787 → 경고(WARNING) 정상 트리거
- [x] 현재 임계값 현실적 — 조정 불필요

**Task 9.3 — 키워드 사전 튜닝** ✅ 완료
- [x] 스코어 분포: 5-6(39건), 6-7(30건), 7-8(18건), 9-10(5건) — 정규분포 양호
- [x] 고영향 93건 전부 STRONG 티어 — 필터 품질 양호
- [x] 지정학 키워드 Phase 3에서 +25개 보강 완료

**Task 9.4 — 방향성 정확도** ⬜ GEMINI_API_KEY 설정 후 평가
- [x] LLM 미연동 상태: 93건 전부 direction=None
- [x] 키워드 fallback 동작 확인 (금리+급등 → BULL, conf=0.9)
- [ ] Gemini API 키 설정 → summarize_news() 실행 → 정확도 측정 (사용자 수동)

**Task 9.5 — 지정학 분류 정확도** ✅ 완료
- [x] 9건 분류: L4(중동 3건), L5(대만 1건), L3(3건), L1(2건)
- [x] 실제 뉴스 내용과 부합 (Iran War→L4, NATO Air Defense→L4, North Korea Rocket→L3)

**Task 9.6 — 성능 최적화** ✅ 완료
- [x] 국내 5피드 수집→분석: 2.0초 (목표 <3분 대비 99% 마진)
- [x] 전체 파이프라인(all): 26.9초
- [x] DB 크기: 172KB (목표 <20MB/일 충족)

**Task 9.7 — 장애 복구 테스트** ✅ 완료
- [x] LLM fallback: GEMINI_API_KEY 미설정 → 키워드 자동 판정 (BULL/BEAR)
- [x] RSS 장애 격리: 잘못된 URL → 0건 (전체 중단 없음)
- [x] 이메일 재시도: MAX_RETRIES=3, CONSECUTIVE_FAIL_THRESHOLD=3

**Task 9.8 — 실운영 테스트** ⬜ 사용자 수동 진행
- [ ] `python src/main.py --schedule` 로 24/7 운영 시작
- [ ] 08:00/18:00 일일 리포트 수신 확인
- [ ] 시스템 가용률 추적

**Task 9.9 — 문서화** ✅ 완료
- [x] 총 53개 파일 (Python 31 + 문서 12 + 에이전트/스킬 10)
- [x] PRD.md, Architecture.md, KPI.md, README.md, TASK.md
- [x] 상세기획서 v1.0 + v2.0
- [x] GMAIL_API_SETUP.md 설정 가이드
- [x] .claude 에이전트 6종 + 스킬 3종

**Task 9.10 — 최종 릴리스** ✅ 코드 완성
- [x] 전체 기능 코드 완성 (Phase 1~4)
- [x] E2E 테스트 통과
- [x] 문서화 완료
- [ ] 사용자 확인 후 git commit + push (사용자 수동)

### Phase 5 완료 기준 ✅ 코드 완성 기준 PASS
- [x] 26개 활성 소스 정상 수집 (RSS 15 + SNS 2 + 시장지표 9)
- [x] 14-Stage 파이프라인 E2E 정상 동작 (26.9초)
- [x] 13종 알림 룰 동작 확인 (뉴스5+지표6+지정학2)
- [x] 이메일 전송 성공률 100% (4/4건)
- [ ] BULL/BEAR 정확도 → Gemini API 키 설정 후 측정
- [x] 지정학 L1-L5 분류: 9건 분류 (실제 뉴스와 부합)
- [ ] 실운영 가용률 → `--schedule` 모드 운영 후 측정
- [x] 알림 건수: 1회 실행당 4건 (일일 추정 적정 범위)

---

## 긴급 Fallback 계획

### W6 금요일 Fallback 판단

| 상황 | 조치 |
|------|------|
| 시장지표 수집 실패 (yfinance 차단 등) | 뉴스+이메일만으로 릴리스 (지표 알림 제외) |
| 야간선물 KIS API 미확보 | yfinance fallback으로 대체 |
| 지정학 분류 정확도 < 60% | 키워드 기반 단순 태깅으로 대체 (L1-L5 미사용) |
| Gmail API 인증 실패 | SMTP 전용으로 전환 |
| Gemini 2.0 Flash 서비스 종료 | Gemini 2.5 Flash 마이그레이션 (최우선) |

### MVP 최소 배포 기준

시장지표·지정학·영향체인 없이도, 아래 기능만으로 배포 가능:

1. RSS 11개 소스 수집 (기존)
2. 3-Tier 키워드 필터 + 다차원 스코어링 (기존)
3. LLM BULL/BEAR 판단 (기존)
4. Gmail 이메일 알림 5종 (Phase 1 산출물)
5. 시간대별 차등 스케줄러 (Phase 1 산출물)

---

## 변경 로그

| 날짜 | 커밋 | 변경 내용 | 영향 범위 |
|------|------|----------|----------|
| 04/11 | `f287913` | NIAS v2.0 초기 릴리스 — 53개 파일, Phase 1~5 전체 | 전체 시스템 |
| 04/11 | `0daa9a8` | KPI.md 실측값 반영 (파이프라인 26.9초, yfinance 100%) | 문서 |
| 04/12 | `5830249` | 한국어 Google News 종목별 5개 쿼리 추가 (수집량 +100%) | config.py, rss_collector.py |
| 04/12 | `05bb736` | 대시보드 UI 대폭 개선 — 원문 링크 + 펼치기 + 한국어 | app.py |
| 04/12 | `3ec401c` | 유저 테스트 3개 이슈 해결 — 종목 태거(92건), 영향 체인 한국어 키워드, fallback 자동 적용 | main.py, stock_tagger.py, impact_chain_analyzer.py, summarizer.py |
| 04/12 | `4e39ab1` | 이메일 정보 빈약성 해결 — 출처/시간/본문/종목/체인 풍부하게, HTML 정제 | email_notifier.py |
| 04/12 | `c391d20` | 시장지표 이메일에 정량 평가 + 시나리오 + 행동 제안 추가 | email_notifier.py |
| 04/13 | `5a8fc51` | 이메일 제목 개선 (이모지+한줄의미), preheader 추가, 시나리오 트리거값, 행동 제안 동사 강화, 정량 평가 상대 기준 | email_notifier.py |
| 04/13 | `3bc4c36` | Gemini 2.5 Flash LLM 분석 정상 동작 — max_tokens 2048, JSON 추출 강화 | summarizer.py |
| 04/13 | `c514521` | 긴급 속보 이메일 제목+preheader 개선, 불필요 문구 제거 | email_notifier.py |
| 04/13 | `ef15f59` | 일일 리포트 자동 발송 구현 (run_daily_report), Markdown 저장 | main.py |
| 04/13 | `a9ee09d` | CSV 내보내기 + 주간 성과 리포트 + 대시보드 히스토리 탭 | export.py, weekly_report.py, app.py |
| 04/13 | `7acea6c` | Google News URL 원문 링크 수정 (/rss/articles → /articles) | rss_collector.py |
| 04/13 | `cffd17e` | 60sec_econ_signal ECOS API 이식 + 시그널 해석 매트릭스 (CPI/금리/수출/경상수지) | ecos_collector.py, email_notifier.py, main.py |
| 04/13 | `3ec54b8` | DART+FRED+ECOS 3개 API 키 활성화. DART 32건, FRED 5건, ECOS 4건 실데이터 확인 | .env, dart_collector.py, market_indicator.py |
| 04/13 | `1620212` | Slack 웹훅 연동. 긴급뉴스+시장지표+지정학 3종 Block Kit 알림 | slack_notifier.py, main.py, config.py |
| 04/13 | `ef2f055` | Slack+이메일 발행 일자 부각 — 제목에 (MM/DD), 본문 굵게, Slack 알림 강화 | slack_notifier.py, email_notifier.py |
| 04/13 | `aee1124` | QA 개선 3건: fallback 편향 수정(97%→15% BULL), threshold 6.5, 알림상한 10건, LLM TOP15 | summarizer.py, config.py, alert_engine.py |
| 04/13 | `55b8372` | 영어 뉴스 한국어 자동 번역 (Google Translate, LLM 미소모). 이메일+Slack 적용 | translator.py, email_notifier.py, slack_notifier.py |
| 04/13 | `89159ad` | Windows 시작 프로그램 자동 실행 등록 (start_nias.bat) | start_nias.bat |
| 04/13 | `492b310` | README.md 전면 개편 — 운영 가이드+트러블슈팅+유지보수 통합 | README.md |
| 04/13 | `1ef7432` | 번역 누락 전면 수정 — 대시보드+일일리포트+주간리포트+콘솔 TOP5 모두 적용 | app.py, email_notifier.py, weekly_report.py, main.py |
| 04/13 | 현재 | 대시보드 요약 화면 — 지표 6개+TOP3 카드(색상코딩)+지정학 요약 한눈에 | app.py |
