# NIAS (News-Invest Alert System) v2.0

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | NIAS — 실시간 뉴스 요약 및 투자 알람 자동화 시스템 |
| 현재 상태 | **운영 중** (Phase 5 완료, 유저 테스트 95%) |
| 담당 | MS |

## 한 줄 설명

PC를 켜면 자동으로 금융 뉴스 + 시장지표를 수집·분석하여, 중요한 투자 정보를 **이메일 + Slack**으로 알려주는 시스템.

---

## 빠른 시작 (처음 설정)

### 1단계: 의존성 설치

```bash
cd 뉴스요약자동화
pip install -r requirements.txt
```

### 2단계: API 키 설정

`.env.example`을 `.env`로 복사하고 실제 키를 입력:

```bash
cp .env.example .env
```

| API | 발급처 | 용도 |
|-----|--------|------|
| GEMINI_API_KEY | [Google AI Studio](https://aistudio.google.com/apikey) | 뉴스 BULL/BEAR 분석 |
| ALERT_EMAIL_TO | 본인 Gmail | 알림 수신 이메일 |
| SLACK_WEBHOOK_URL | [Slack API](https://api.slack.com/apps) | Slack 알림 |
| DART_API_KEY | [DART](https://opendart.fss.or.kr) | 전자공시 |
| FRED_API_KEY | [FRED](https://fred.stlouisfed.org) | 미국 경제지표 |
| BOK_API_KEY | [한국은행 ECOS](https://ecos.bok.or.kr) | 한국 경제지표 |

### 3단계: Gmail OAuth 인증 (최초 1회)

1. [Google Cloud Console](https://console.cloud.google.com)에서 Gmail API 활성화
2. OAuth 2.0 클라이언트 생성 → `credentials.json` 다운로드
3. `src/` 폴더에 배치
4. 아래 명령 실행 → 브라우저에서 인증:

```bash
python src/main.py
```

상세 가이드: [docs/GMAIL_API_SETUP.md](docs/GMAIL_API_SETUP.md)

### 4단계: 테스트 실행

```bash
python src/main.py --sources kr
```

성공하면 이메일+Slack으로 알림이 옵니다.

---

## 일상 운영 가이드

### PC 켤 때 자동 시작 (설정 완료됨)

```
PC 로그온 → Task Scheduler "NIAS_Scheduler" → start_nias.bat → 스케줄러 + 대시보드
```

Windows **작업 스케줄러**에 등록되어 있어, PC를 켜고 로그인만 하면 자동 동작합니다.
(2026-04-18 이전의 Startup 폴더 방식은 Windows Update 강제 재부팅 후 복구 실패 이슈로 폐기됨)

- 트리거: 로그온 시 + 5분마다 keep-alive 점검
- 실패 시 1분 후 3회 재시도
- 배터리·전원 상태 무관, 절전 복귀 시 지나간 트리거 자동 실행
- 상태 확인: `taskschd.msc` → `NIAS_Scheduler` 또는 `Get-ScheduledTaskInfo -TaskName NIAS_Scheduler`

### 자동 실행 스케줄

| 시간대 | 작업 | 주기 |
|--------|------|------|
| 06:00~09:00 (장전) | 뉴스 수집 (all) | 5분 |
| 09:00~15:30 (장중) | 뉴스 수집 (all) | 5분 |
| 15:30~23:00 (장후) | 뉴스 수집 (all) | 15분 |
| 23:00~06:00 (야간) | 글로벌 뉴스만 | 60분 |
| **24/7** | **지정학 전용 fast (호르무즈·해상봉쇄·이란·대만·북한 핫스팟 포함)** | **5분** |
| **항상** | 시장지표 모니터링 (VIX, 환율, 유가 등 13개) | 10분 |
| 월~금 08:00, 18:00 | 일일 투자 리포트 이메일 | 자동 |

### PC가 꺼져 있을 때

- 야간(23:00~06:00) 글로벌 뉴스 수집이 중단됩니다
- **다음 날 08:00 일일 리포트가 야간 누락분을 보완합니다**
- 장중(09:00~15:30)에 PC가 켜져있으면 투자 판단에 필요한 알림은 전부 받습니다

### 알림 채널

| 채널 | 언제 | 내용 |
|------|------|------|
| **이메일** | 긴급 뉴스, 지표 급변, 일일 리포트 | 상세 분석 (시나리오, 행동 제안, 원문 링크) |
| **Slack** | 동일 | 즉시 인지용 간결 알림 (팝업) |
| **대시보드** | 항상 | http://localhost:8501 (6탭: 뉴스/종목/지표/지정학/알림/히스토리) |

### 알림 기준

| 알림 유형 | 조건 | 발송 |
|-----------|------|------|
| 긴급 속보 | 영향도 8점 이상 | 즉시 (이메일+Slack) |
| 고영향 뉴스 | 영향도 6.5점 이상 | 1시간 배치 |
| VIX 경고 | VIX 25 이상 | 즉시 |
| VIX 패닉 | VIX 30 이상 | 즉시 (전 채널) |
| 환율 급변 | 원달러 1,400원+ 또는 일변동 1.5%+ | 즉시 |
| 유가 급변 | WTI 일변동 5%+ | 즉시 |
| 지정학 L3+ | 무력 시위 이상 | 즉시 (전 채널) |
| 일일 리포트 | 월~금 08:00, 18:00 | 자동 |

일일 알림 상한: **10건** (과다 알림 방지)

---

## 모니터링 명령어

```bash
# 스케줄러 동작 확인
ps aux | grep "main.py"

# 실시간 로그 보기
tail -f 뉴스요약자동화/data/scheduler.log

# 최근 알림 확인
tail -20 data/scheduler.log | grep "알림"

# DB 현황 확인
cd 뉴스요약자동화
python -c "import sys; sys.path.insert(0,'src'); from utils.db import get_db_stats; print(get_db_stats())"

# CSV 내보내기 (Excel 분석용)
python -c "import sys; sys.path.insert(0,'src'); from utils.export import export_all; export_all()"

# 주간 리포트 수동 발송
python -c "import sys; sys.path.insert(0,'src'); from reports.weekly_report import send_weekly_report; send_weekly_report()"

# 대시보드 수동 시작
streamlit run src/app.py
```

---

## 트러블슈팅

### 스케줄러가 안 돌아요

```bash
# 1. 프로세스 확인
ps aux | grep "main.py"

# 2. 없으면 수동 시작
cd 뉴스요약자동화
nohup python -X utf8 src/main.py --schedule > data/scheduler.log 2>&1 &

# 또는 bat 파일 더블클릭
start_nias.bat
```

### 이메일이 안 와요

```bash
# Gmail 토큰 확인
ls data/gmail_token.json

# 토큰 만료 시 재인증
rm data/gmail_token.json
python src/main.py
# → 브라우저에서 Google 인증
```

### Slack 알림이 안 와요

```bash
# 웹훅 URL 확인
grep SLACK .env

# 테스트 발송
python -c "
import sys; sys.path.insert(0,'src')
from notifiers.slack_notifier import send_slack
send_slack('NIAS 테스트 메시지')
"
```

### 알림이 너무 많아요

`.env`가 아닌 `src/config.py`에서 조정:

```python
IMPACT_THRESHOLD = 6.5    # 높이면 알림 줄어듦 (7.0 권장)
```

`src/notifiers/alert_engine.py`:

```python
max_daily_alerts = 10     # 줄이면 일일 상한 감소
```

수정 후 **스케줄러 재시작 필수:**

```bash
pkill -f "main.py"
nohup python -X utf8 src/main.py --schedule > data/scheduler.log 2>&1 &
```

### 코드 수정 후 반영이 안 돼요

Python은 실행 시점의 코드를 메모리에 로드합니다. **코드 수정 후 반드시 재시작:**

```bash
pkill -f "main.py"
start_nias.bat
```

---

## 정기 유지보수

| 주기 | 작업 | 명령 |
|------|------|------|
| **자동** | 뉴스 수집 + 분석 + 알림 | 없음 (스케줄러) |
| **월 1회** | 로그 정리 | `> data/scheduler.log` |
| **90일** | Gmail 재인증 | `rm data/gmail_token.json` → `python src/main.py` |
| **필요 시** | DB 백업 | `cp data/nias.db data/nias_backup.db` |

---

## 수집 소스 현황 (all 모드 기준 48개 피드 + 외부 API)

| 카테고리 | 소스 | 수량 |
|---------|------|------|
| 국내 뉴스 RSS | 연합뉴스, 한경, 매경, 조선, SBS | 5 |
| 글로벌 뉴스 RSS | Reuters, CNBC, Bloomberg, WSJ, FT, Investing (2026-04-18: `breaking/world` 카테고리 포함하도록 쿼리 완화) | 6 |
| 지정학 RSS | Defense One, War on the Rocks, The Diplomat, 38 North | 4 |
| 한국어 Google News | 삼성전자, SK하이닉스, 코스피, 금리환율, 유가에너지 | 5 |
| 영어 Google News (섹터) | 반도체, AI, 금리, 유가, 한국경제, 관세 | 6 |
| 영어 Google News (지정학) | 전쟁/분쟁, 제재, 대만/중국 | 3 |
| **지정학 핫스팟 (2026-04-18 신규)** | 호르무즈, 해상봉쇄, 수에즈, 이란 긴장, 대만해협, 북한 도발, 우크라이나, 홍해/바벨만데브 | **8** |
| SNS | Fed 발언, 증시 전문가 | 2 |
| 전자공시 | DART | 1 |
| 경제지표 | FRED(미국 5개) + 한은(2개) + ECOS(4개) | 3 API |
| 시장지표 | yfinance(7) + FDR(1) + Crypto F&G(1) | 9 ticker |
| 야간선물 | KIS Open API (fallback: yfinance) | 1 |

### 해외 직접 RSS (2026-04-19 **활성화**, `ENABLE_EXTENDED_GLOBAL=True`)
Google News 간접 수집의 카테고리 필터 한계를 보완하기 위해 아래 9개 피드 활성화 — 전체 피드 **46개**:
- **AP (Google News 경유, `site:apnews.com`)** — 공식 RSS 폐쇄로 GN 필터로 대체
- BBC World / BBC Business (직접)
- Al Jazeera (직접)
- Guardian World / Guardian Business (직접)
- Reuters Top News / Reuters World Direct (직접, 간헐적)
- NYT World (직접)

### 수집 정책 (2026-04-18 보정)
- `MAX_ARTICLES_PER_FEED`: 30 → **100** (RSS 밀림·3일 공백 복원력 강화)
- 지정학 전용 `geopolitical_fast` 잡: 24/7 5분 간격 (main 잡과 2분 오프셋)

## 핵심 기능

| 기능 | 설명 |
|------|------|
| 3-Tier 키워드 필터 | STRONG(80+) / MEDIUM(30+) / WEAK(8+) 키워드 자동 분류 |
| 다차원 영향도 | urgency × scope × certainty × tier → 1~10점 |
| LLM BULL/BEAR 판단 | Gemini 2.5 Flash (TOP 15건) + 키워드 fallback |
| 지정학 에스컬레이션 | L1(긴장) ~ L5(전면위기) 5단계 분류 |
| 교차 자산 영향 체인 | 5대 체인 (중동→유가, 달러→원화, 대만→반도체, 금리→성장주, 북한→코스피) |
| 영어 뉴스 자동 번역 | Google Translate (LLM 미소모) |
| 시장지표 임계값 알림 | VIX, 환율, 유가, 국채, 야간선물 + Level×Direction×Change 복합 판단 / 상태 변화형 / 접근·돌파·유지 구분 / 현재 근접 시나리오 마커 / 행동 조건 1줄 / 지표별 시장 영향 |
| **이벤트 Fallback (2026-04-18)** | 키워드 사전 miss 시 (엔티티 클래스 × 액션 카테고리) 매트릭스로 L1~L3 승격. shipping_lane+blockade 등 치명 조합은 impact +2.5 부스트. `이벤트후보` 알림 룰이 긴급속보 아래 우선순위로 발송 |
| **누락 이벤트 로거** | impact≥5.0인데 모든 룰 탈락한 뉴스는 `data/missed_events.json`에 롤링 저장. 대시보드 `🔔 놓친 이벤트` 탭에서 확인 가능 |
| **중복 알림 제거** | 한 뉴스가 여러 룰에 매칭되어도 최상위 1개만 발송 (NEWS_RULE_PRIORITY) |

---

## 관련 문서

| 문서 | 내용 |
|------|------|
| [PRD.md](./PRD.md) | 제품 요구사항 (15개 기능, P0/P1/P2) |
| [Architecture.md](./Architecture.md) | 시스템 아키텍처 (6-Layer) |
| [KPI.md](./KPI.md) | KPI 추적 + 주간 로그 |
| [TASK.md](./TASK.md) | 65개 Task + 변경 로그 |
| [docs/QA_REPORT.md](./docs/QA_REPORT.md) | QA 품질 개선 리포트 (5 페르소나) |
| [docs/GMAIL_API_SETUP.md](./docs/GMAIL_API_SETUP.md) | Gmail OAuth 설정 가이드 |
| [상세기획서 v2.0](./뉴스요약자동화_상세기획서_v2.0.md) | 16챕터 상세 기획 |
