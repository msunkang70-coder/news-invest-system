"""NIAS v2.0 — 메인 엔트리포인트

실시간 뉴스 요약 및 투자 알람 자동화 시스템
Usage:
    python main.py              # 단일 실행
    python main.py --schedule   # 스케줄러 모드 (24/7)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# src 디렉토리를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as cfg
from models.news_item import NewsItem
from models.market_indicator import MarketIndicator
from collectors.rss_collector import collect_rss_feeds
from collectors.market_data_collector import collect_global_indicators, collect_kr_indicators
from collectors.night_futures_collector import collect_night_futures
from collectors.dart_collector import collect_dart_disclosures
from collectors.economic_indicator import collect_fred_indicators, collect_bok_indicators
from collectors.sns_collector import collect_sns_posts
from collectors.sentiment_collector import collect_sentiment_indicators
from collectors.ecos_collector import collect_ecos_indicators, collect_ecos_news
from analyzers.keyword_filter import filter_by_keywords
from analyzers.impact_scorer import score_impact
from analyzers.geopolitical_classifier import classify_geopolitical
from analyzers.impact_chain_analyzer import analyze_impact_chains
from analyzers.summarizer import summarize_news, build_market_context
from utils.dedup import deduplicate
from utils.cache import UrlCache
from utils.db import save_news_items, save_indicators, get_db_stats
from notifiers.alert_engine import AlertEngine
from notifiers.email_notifier import GmailNotifier, build_urgent_email, build_indicator_email

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(cfg.DATA_DIR / "pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("NIAS")

# 글로벌 인스턴스
alert_engine = AlertEngine()
email_notifier = GmailNotifier()
url_cache = UrlCache()


def run_news_pipeline(sources: str = "all"):
    """뉴스 수집 → 전처리 → 분석 → 알림 파이프라인 (14-Stage)"""
    logger.info(f"{'='*60}")
    logger.info(f"[파이프라인] 뉴스 사이클 시작 (sources={sources})")
    start = time.time()

    # Stage 1: 수집 (멀티소스)
    items = collect_rss_feeds(sources)

    # 추가 소스 수집 (개별 실패해도 전체 중단 없음)
    for collector_name, collector_fn in [
        ("DART", collect_dart_disclosures),
        ("FRED", collect_fred_indicators),
        ("한은", collect_bok_indicators),
        ("ECOS뉴스", collect_ecos_news),
        ("SNS", collect_sns_posts),
    ]:
        try:
            extra = collector_fn()
            if extra:
                items.extend(extra)
                logger.info(f"[S1 수집] +{collector_name}: {len(extra)}건")
        except Exception as e:
            logger.warning(f"[S1 수집] {collector_name} 실패 (스킵): {e}")

    logger.info(f"[S1 수집] 합계 {len(items)}건")
    if not items:
        logger.info("[파이프라인] 수집 결과 없음 — 종료")
        return []

    # Stage 2: 중복 제거
    items = deduplicate(items)

    # Stage 3: 캐시 필터 (이전에 처리한 URL 제외)
    items = url_cache.filter_new(items)
    if not items:
        logger.info("[파이프라인] 신규 뉴스 없음 — 종료")
        return []

    # Stage 4: 키워드 필터 (STRONG/MEDIUM/WEAK 분류)
    items = filter_by_keywords(items)
    if not items:
        logger.info("[파이프라인] 키워드 매칭 없음 — 종료")
        return []

    # Stage 5: 지정학 분류 (v2.0)
    geo_count = 0
    for item in items:
        assessment = classify_geopolitical(item)
        if assessment:
            geo_count += 1
    if geo_count:
        logger.info(f"[S5 지정학] {geo_count}건 분류")

    # Stage 6: 영향도 스코어링 (+ 지정학 승수 적용)
    items = score_impact(items)
    if not items:
        logger.info("[파이프라인] 고영향 뉴스 없음 (threshold 미달) — 종료")
        return []

    # Stage 7: 종목 영향 매핑 (직접 + 섹터 간접)
    from analyzers.stock_tagger import tag_stocks
    tag_stocks(items)
    tagged_count = sum(1 for i in items if i.tagged_stocks)
    if tagged_count:
        logger.info(f"[S7 종목매핑] {tagged_count}건 종목 태깅")

    # Stage 8: 영향 체인 분석 (v2.0)
    chain_count = 0
    for item in items:
        chains = analyze_impact_chains(item)
        if chains:
            chain_count += 1
    if chain_count:
        logger.info(f"[S8 영향체인] {chain_count}건 매칭")

    # Stage 9: LLM 요약 + BULL/BEAR 판단 (fallback: 키워드 기반)
    try:
        # 시장 컨텍스트 가져오기 (최근 지표)
        from utils.db import get_connection as _get_conn
        _conn = _get_conn()
        _ind_rows = _conn.execute(
            "SELECT * FROM market_indicators ORDER BY recorded_at DESC LIMIT 10"
        ).fetchall()
        _conn.close()
        from models.market_indicator import MarketIndicator, IndicatorCategory
        _indicators_for_ctx = []
        for r in _ind_rows:
            _indicators_for_ctx.append(MarketIndicator(
                ticker=r["ticker"], name=r["name"],
                category=IndicatorCategory(r["category"]) if r["category"] else IndicatorCategory.VOLATILITY,
                current_value=r["current_value"] or 0,
                previous_close=r["previous_close"] or 0,
                change_pct=r["change_pct"] or 0,
            ))
        summarize_news(items, _indicators_for_ctx)
    except Exception as e:
        logger.warning(f"[S9 LLM] 요약 실패 → fallback 적용: {e}")
        # LLM 전체 실패 시 키워드 fallback 일괄 적용
        from analyzers.summarizer import _fallback_analyze
        for item in items:
            if not item.direction:
                _fallback_analyze(item)

    analyzed_count = sum(1 for i in items if i.direction)
    logger.info(f"[S9 요약] {analyzed_count}/{len(items)}건 방향성 판정")

    # Stage 10: DB 저장
    save_news_items(items)

    # Stage 11: 알림 평가 + 디스패치
    alerts = alert_engine.evaluate_news(items)
    if alerts:
        _dispatch_alerts(alerts)

    elapsed = time.time() - start
    logger.info(
        f"[파이프라인] 뉴스 사이클 완료 ({elapsed:.1f}초) — "
        f"고영향 {len(items)}건, 알림 {len(alerts)}건"
    )

    # 콘솔 TOP 5 요약
    for i, item in enumerate(items[:5], 1):
        d = "BULL" if item.direction and item.direction.value == "BULL" else "BEAR" if item.direction else "?"
        geo = f" L{item.geo_level}" if item.geo_level else ""
        logger.info(
            f"  TOP{i}: [{item.impact_score}]{geo} {item.title[:50]} "
            f"({item.source}, {item.keyword_tier})"
        )

    return items


def run_indicator_monitor():
    """시장지표 수집 → 임계값 검사 → 알림"""
    logger.info("[지표] 시장지표 모니터링 사이클")

    indicators = []
    indicators.extend(collect_global_indicators())
    indicators.extend(collect_kr_indicators())

    # 야간선물 (거래시간일 때만)
    night = collect_night_futures()
    if night:
        indicators.append(night)

    # 심리지표 (Crypto F&G 등)
    try:
        sentiments = collect_sentiment_indicators()
        indicators.extend(sentiments)
    except Exception as e:
        logger.warning(f"[지표] 심리지표 수집 실패: {e}")

    # 한국은행 ECOS 거시지표
    try:
        ecos = collect_ecos_indicators()
        indicators.extend(ecos)
    except Exception as e:
        logger.warning(f"[지표] ECOS 수집 실패: {e}")

    # 임계값 돌파 지표 로깅
    alert_worthy = [i for i in indicators if i.is_alert_worthy]
    if alert_worthy:
        for ind in alert_worthy:
            logger.warning(
                f"[지표 알림] {ind.level_emoji} {ind.name}: {ind.current_value} "
                f"({ind.change_pct:+.1f}%) — {ind.threshold_level.value}"
            )

    # 알림 평가
    alerts = alert_engine.evaluate_indicators(indicators)
    if alerts:
        _dispatch_alerts(alerts)

    # DB 저장
    save_indicators(indicators)

    # 지표 현황 요약
    summary = " | ".join(
        f"{i.name}: {i.current_value}({i.change_pct:+.1f}%){i.direction_emoji}"
        for i in indicators[:5]
    )
    logger.info(f"[지표] {len(indicators)}개 수집 | {summary}")

    return indicators


def run_daily_report():
    """일일 리포트 생성 및 발송 (08:00/18:00 cron)"""
    from datetime import datetime
    from dataclasses import dataclass, field
    from notifiers.email_notifier import build_daily_report_email

    logger.info("[리포트] 일일 리포트 생성 시작")

    try:
        # 1) 최근 뉴스 로드
        from utils.db import get_recent_news, get_connection
        news = get_recent_news(hours=12, limit=100)

        if not news:
            logger.info("[리포트] 뉴스 없음 — 리포트 스킵")
            return

        # 2) MarketVerdict 구성
        import json

        @dataclass
        class _StockSignal:
            stock_name: str = ""
            net_score: float = 0.0
            action: str = "관망"

        @dataclass
        class _Verdict:
            overall_direction: object = None
            overall_confidence: float = 0.5
            market_mood: str = ""
            total_bull: int = 0
            total_bear: int = 0
            stock_signals: dict = field(default_factory=dict)

        from models.news_item import Direction

        bull = sum(1 for n in news if n.get("direction") == "BULL")
        bear = sum(1 for n in news if n.get("direction") == "BEAR")
        total = bull + bear
        ratio = bull / total if total > 0 else 0.5

        verdict = _Verdict()
        verdict.overall_direction = Direction.BULL if ratio > 0.5 else Direction.BEAR
        verdict.overall_confidence = abs(ratio - 0.5) * 2
        verdict.total_bull = bull
        verdict.total_bear = bear
        if ratio > 0.65:
            verdict.market_mood = "강세장"
        elif ratio < 0.35:
            verdict.market_mood = "약세장"
        else:
            verdict.market_mood = "혼조세"

        # 종목 시그널 집계
        stock_scores = {}
        for n in news:
            raw = n.get("stock_impacts", "[]")
            try:
                impacts = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                continue
            for si in impacts:
                name = si.get("stock", "")
                if not name:
                    continue
                if name not in stock_scores:
                    stock_scores[name] = {"bull": 0, "bear": 0}
                w = si.get("intensity", 0.5) * n.get("impact_score", 5) / 10
                if si.get("direction") == "BULL":
                    stock_scores[name]["bull"] += w
                else:
                    stock_scores[name]["bear"] += w

        for name, s in stock_scores.items():
            net = round(s["bull"] - s["bear"], 2)
            if net >= 3.0:
                act = "적극매수"
            elif net >= 1.5:
                act = "분할매수"
            elif net >= -0.5:
                act = "관망"
            elif net >= -3.0:
                act = "비중축소"
            else:
                act = "매도검토"
            verdict.stock_signals[name] = _StockSignal(name, net, act)

        # 3) TOP 뉴스 → NewsItem-like 객체
        @dataclass
        class _NewsLike:
            title: str = ""
            impact_score: float = 0
            direction: object = None
            action_suggestion: str = ""

        top_items = []
        for n in sorted(news, key=lambda x: x.get("impact_score", 0), reverse=True)[:5]:
            item = _NewsLike(
                title=n.get("title", ""),
                impact_score=n.get("impact_score", 0),
                direction=Direction(n["direction"]) if n.get("direction") in ("BULL", "BEAR") else None,
                action_suggestion=n.get("action_suggestion", ""),
            )
            top_items.append(item)

        # 4) 시장지표 로드
        conn = get_connection()
        ind_rows = conn.execute(
            "SELECT * FROM market_indicators ORDER BY recorded_at DESC LIMIT 10"
        ).fetchall()
        conn.close()

        from models.market_indicator import MarketIndicator as MI, IndicatorCategory as IC
        indicators = []
        seen = set()
        for r in ind_rows:
            if r["ticker"] in seen:
                continue
            seen.add(r["ticker"])
            indicators.append(MI(
                ticker=r["ticker"], name=r["name"],
                category=IC(r["category"]) if r["category"] else IC.VOLATILITY,
                current_value=r["current_value"] or 0,
                previous_close=r["previous_close"] or 0,
                change_pct=r["change_pct"] or 0,
            ))

        # 5) 지정학 요약
        geo_summary = {}
        for n in news:
            gl = n.get("geo_level")
            gr = n.get("geo_region")
            if gl and gr:
                geo_summary[gr] = max(geo_summary.get(gr, 0), gl)

        # 6) 이메일 빌드 + 발송
        subject, html = build_daily_report_email(verdict, top_items, indicators, geo_summary or None)

        if cfg.ALERT_EMAIL_TO:
            result = email_notifier.send(cfg.ALERT_EMAIL_TO, subject, html)
            if result:
                logger.info(f"[리포트] 일일 리포트 발송 완료: {subject[:40]}")
            else:
                logger.error("[리포트] 일일 리포트 발송 실패")

        # 7) Markdown 파일 저장
        md_path = cfg.OUTPUT_DIR / f"daily_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# NIAS 일일 투자 리포트\n")
            f.write(f"**{datetime.now().strftime('%Y-%m-%d %H:%M')}**\n\n")
            f.write(f"## 시장 종합: {verdict.overall_direction.value} ({verdict.overall_confidence:.0%})\n")
            f.write(f"BULL {bull}건 vs BEAR {bear}건 | {verdict.market_mood}\n\n")
            f.write(f"## TOP 5 뉴스\n")
            for i, t in enumerate(top_items, 1):
                d = t.direction.value if t.direction else "?"
                f.write(f"{i}. [{t.impact_score}] {d} {t.title[:60]}\n")
            f.write(f"\n## 종목 시그널\n")
            for name, ss in sorted(verdict.stock_signals.items(), key=lambda x: abs(x[1].net_score), reverse=True)[:10]:
                f.write(f"- {name}: {ss.net_score:+.1f} → {ss.action}\n")

        logger.info(f"[리포트] Markdown 저장: {md_path.name}")

    except Exception as e:
        logger.error(f"[리포트] 일일 리포트 생성 실패: {e}")


def flush_alert_batches():
    """배치 알림 큐 플러시"""
    batched = alert_engine.flush_batches()
    if batched:
        logger.info(f"[알림] 배치 큐 플러시: {len(batched)}건")
        _dispatch_alerts(batched)


def _dispatch_alerts(alerts: list[dict]):
    """알림 디스패치 (이메일 + Slack)"""
    from notifiers.slack_notifier import (
        notify_urgent_news, notify_indicator_alert, notify_geopolitical
    )

    for alert in alerts:
        item = alert["item"]
        channels = alert["channels"]

        # 이메일
        if "email" in channels and cfg.ALERT_EMAIL_TO:
            if isinstance(item, NewsItem):
                subject, html = build_urgent_email(item)
            elif isinstance(item, MarketIndicator):
                subject, html = build_indicator_email(item)
            else:
                continue

            result = email_notifier.send(cfg.ALERT_EMAIL_TO, subject, html)
            if result:
                logger.info(f"[알림] 이메일 발송: {alert['rule']}")

        # Slack (이메일+텔레그램 채널이면 Slack도 발송)
        if cfg.SLACK_WEBHOOK_URL:
            try:
                if isinstance(item, NewsItem) and (item.geo_level or 0) >= 3:
                    notify_geopolitical(item)
                elif isinstance(item, NewsItem):
                    notify_urgent_news(item)
                elif isinstance(item, MarketIndicator):
                    notify_indicator_alert(item)
            except Exception as e:
                logger.warning(f"[Slack] 발송 실패: {e}")

    alert_engine.save_history(alerts)


def main():
    parser = argparse.ArgumentParser(description="NIAS v2.0 — 실시간 뉴스 투자 알람 시스템")
    parser.add_argument("--schedule", action="store_true", help="스케줄러 모드 (24/7 운영)")
    parser.add_argument("--sources", default="all", choices=["all", "kr", "global", "geopolitical"])
    parser.add_argument("--indicators-only", action="store_true", help="시장지표만 수집")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("NIAS v2.0 — News-Invest Alert System")
    logger.info("=" * 60)

    if args.schedule:
        from scheduler.pipeline_scheduler import PipelineScheduler

        scheduler = PipelineScheduler(
            run_news_pipeline=run_news_pipeline,
            run_indicator_monitor=run_indicator_monitor,
            run_night_futures=lambda: collect_night_futures(),
            run_daily_report=run_daily_report,
            flush_alerts=flush_alert_batches,
        )
        scheduler.start()

        logger.info("[메인] 스케줄러 모드 — Ctrl+C로 종료")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.stop()
            logger.info("[메인] 종료")

    elif args.indicators_only:
        run_indicator_monitor()

    else:
        # 단일 실행
        run_news_pipeline(args.sources)
        run_indicator_monitor()


if __name__ == "__main__":
    main()
