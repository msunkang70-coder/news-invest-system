# NIAS v2.0 — News-Invest Alert System

실시간 뉴스 요약 및 투자 알람 자동화 시스템.
42개 소스에서 뉴스·시장지표·지정학 이벤트를 수집하고, 13종 알림 룰로 이메일/Telegram 자동 발송.

## 에이전트 팀 (6명)

| 에이전트 | 역할 | 핵심 도구 |
|---------|------|----------|
| news-collector | 뉴스 수집 전문가 | RSS, DART, FRED, SNS 수집기 |
| market-analyzer | 시장 분석가 | yfinance, FDR, 임계값 엔진 |
| text-intelligence | 텍스트/감성 분석가 | 키워드 필터, 스코어링, LLM 요약 |
| geopolitical-analyst | 지정학 전문가 | 에스컬레이션 L1-L5, 영향 체인 |
| alert-dispatcher | 알림 관리자 | Alert Engine 13룰, Gmail API |
| report-generator | 리포트 작성자 | 일일 리포트, 익일 전망 |

## 실행 방법

```bash
# 단일 실행
python src/main.py

# 스케줄러 모드
python src/main.py --schedule

# 대시보드
streamlit run src/app.py
```

## 워크플로우

```
Phase 1: 수집 (news-collector + market-analyzer)
    ↓
Phase 2: 분석 (text-intelligence + geopolitical-analyst)
    ↓
Phase 3: 알림 (alert-dispatcher)
    ↓
Phase 4: 리포트 (report-generator)
```
