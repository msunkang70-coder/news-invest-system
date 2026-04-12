---
name: news-pipeline
description: 뉴스 파이프라인 오케스트레이터 — 수집부터 알림까지 전체 워크플로우 조율
---

# 뉴스 파이프라인 오케스트레이터

전체 14-Stage 파이프라인을 조율합니다.

## 실행 방법

```bash
# 전체 파이프라인 1회 실행
python src/main.py

# 국내 소스만
python src/main.py --sources kr

# 스케줄러 모드 (24/7)
python src/main.py --schedule
```

## 파이프라인 단계

1. **수집** — RSS 15피드 + DART + FRED + 한은 + SNS
2. **중복 제거** — URL 해시 + 제목 유사도(≥0.7)
3. **캐시 필터** — 24시간 TTL URL 캐시
4. **키워드 필터** — STRONG/MEDIUM/WEAK 3-Tier
5. **지정학 분류** — L1~L5 에스컬레이션
6. **영향도 스코어링** — urgency × scope × certainty × geo_mult
7. **영향 체인** — 5대 교차 자산 체인 매칭
8. **DB 저장** — nias.db
9. **알림 평가** — 13종 룰 매칭 + 이메일 발송

## 에이전트 호출 순서

```
news-collector → text-intelligence + geopolitical-analyst (병렬)
    → alert-dispatcher → report-generator
market-analyzer (독립 병렬)
```
