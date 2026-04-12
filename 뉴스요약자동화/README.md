# NIAS (News-Invest Alert System) v2.0

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | NIAS — 실시간 뉴스 요약 및 투자 알람 자동화 시스템 |
| 시작일 | 2026-04-11 |
| 목표 완료일 | 2026-06-20 (10주) |
| 현재 상태 | 기획 완료 / 개발 준비 |
| 담당 | MS |

## 핵심 문제

개인 투자자가 하루 수백 건의 금융 뉴스, 시장지표 변동, 지정학 이벤트 속에서 투자에 실제 영향을 주는 핵심 정보를 놓치거나, 감지가 30분~1시간 지연되어 적시 대응이 불가능한 문제.

## 핵심 솔루션

42개 소스에서 뉴스·시장지표·지정학 이벤트를 5~10분 주기로 자동 수집하고, LLM 기반 BULL/BEAR 방향성 판단 + 지정학 에스컬레이션 5단계 분류 + 교차 자산 영향 체인 분석을 수행하여, 13종 알림 룰에 따라 이메일/Telegram으로 자동 알림한다.

## 성공 기준

| KPI | 현재값 | 목표값 | 측정 방법 |
|-----|--------|--------|-----------|
| 투자 의사결정 시간 | 90분/일 | 10분/일 | 사용자 기록 |
| BULL/BEAR 정확도 | - | 75% | 200건 라벨링 |
| 알림 지연시간 | - | < 2분 | 로그 분석 |
| 시장지표 모니터링 | 0개 | 14개 | 수집 로그 |
| 지정학 분류 정확도 | 0% | 80% | 50건 검증 |

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Frontend | Streamlit 1.40+ |
| Backend | Python 3.12+ / APScheduler 3.11+ |
| AI/ML | Gemini 2.5 Flash API |
| Market Data | yfinance / FinanceDataReader / KIS Open API |
| Database | SQLite 3 + JSON Cache |
| Notification | Gmail API (OAuth2) + Telegram Bot |
| Template | Jinja2 (HTML 이메일 템플릿) |

## 프로젝트 구조

```
뉴스요약자동화/
├── PRD.md                    # 제품 요구사항 문서
├── Architecture.md           # 시스템 아키텍처
├── KPI.md                    # KPI 추적
├── README.md                 # 본 문서
│
├── src/
│   ├── main.py               # 통합 엔트리포인트
│   ├── config.py             # 중앙 설정 (소스, 키워드, 임계값)
│   │
│   ├── collectors/           # 수집 레이어
│   │   ├── rss_collector.py
│   │   ├── market_data_collector.py
│   │   ├── night_futures_collector.py
│   │   ├── dart_collector.py
│   │   ├── economic_indicator.py
│   │   └── sentiment_collector.py
│   │
���   ├── analyzers/            # 분석 레이어
│   │   ├── impact_scorer.py
│   │   ├── geopolitical_classifier.py
│   │   ├── impact_chain_analyzer.py
│   │   ├── market_classifier.py
│   │   ├── summarizer.py
│   │   └── signal_aggregator.py
│   │
│   ├── models/               # 데이터 모델
│   │   ���── news_item.py
│   │   └── market_indicator.py
│   │
│   ├── notifiers/            # 알림 레이어
│   │   ├── alert_engine.py
│   │   ├── email_notifier.py
│   │   └── templates/
│   │       ├── urgent.html
│   │       ├── daily_report.html
│   │       └── market_alert.html
│   │
│   ├── scheduler/            # 스케줄러
│   │   └── pipeline_scheduler.py
│   │
│   └── utils/                # 유틸리티
│       ├── cache.py
│       └── dedup.py
│
├── data/                     # 데이터 (gitignore)
├── output/                   # 리포트 출력
├── requirements.txt
└── .env.example              # 환경변수 템플릿
```

## 실행 방법

### 환경 설정

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 설정

# 3. Gmail OAuth 설정 (최초 1회)
# Google Cloud Console → Gmail API 활성화 → OAuth 2.0 클라이언트 생성
# credentials.json 다운로드 → src/ 폴더에 배치
```

### 실행

```bash
# 단일 실행
python src/main.py

# 스케줄러 모드 (24/7 운영)
python src/main.py --schedule

# 대시보드
streamlit run src/app.py
```

## 관련 문서

| 문서 | 경로 |
|------|------|
| PRD | [./PRD.md](./PRD.md) |
| 아키텍처 | [./Architecture.md](./Architecture.md) |
| KPI | [./KPI.md](./KPI.md) |
| 상세기획서 v2.0 | [./뉴스요���자동화_상세기획서_v2.0.md](./뉴스요약자동화_상세기획서_v2.0.md) |
