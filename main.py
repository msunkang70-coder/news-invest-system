"""시장 영향 뉴스 투자 의사결정 시스템 v2

파이프라인:
  수집 → 중복제거 → 키워드필터 → 다차원스코어링 →
  시간대분류 → 시장영역분류 → 종목영향매핑 → LLM방향판정 →
  시그널집계 → 투자리포트 생성

사용법:
    python main.py                    # 전체 실행
    python main.py --no-body          # 빠른 실행
    python main.py --sources kr       # 국내만
    python main.py --date 20260409    # 날짜 지정
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config as cfg
from collectors.rss_collector import collect_rss
from collectors.html_collector import collect_html_fallback
from collectors.google_news import collect_google_news
from filters.keyword_filter import filter_by_keywords
from filters.impact_scorer import score_impact
from analyzers.time_classifier import classify_timeslots
from analyzers.market_classifier import classify_markets
from analyzers.stock_impact_mapper import map_stock_impacts
from analyzers.summarizer import summarize_news
from analyzers.signal_aggregator import aggregate_signals
from utils.dedup_v2 import deduplicate
from utils.cache import URLCache
from reports.daily_report import generate_report
from models.news_item import Direction

KST = timezone(timedelta(hours=9))


def setup_logging():
    log_dir = cfg.DATA_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)

    fh = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)

    logging.basicConfig(level=logging.DEBUG, handlers=[console, fh])
    logging.getLogger("trafilatura").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)


def collect_news(sources: str = "all", fetch_body: bool = True) -> list:
    logger = logging.getLogger(__name__)
    all_items = []

    if sources in ("all", "kr"):
        logger.info("=" * 60)
        logger.info("📰 국내 RSS 수집")
        all_items.extend(collect_rss(cfg.RSS_SOURCES_KR, fetch_body=fetch_body))

    if sources in ("all", "global"):
        logger.info("=" * 60)
        logger.info("🌍 해외 RSS 수집")
        all_items.extend(collect_rss(cfg.RSS_SOURCES_GLOBAL, fetch_body=fetch_body))
        logger.info("🔍 Google News 보조")
        all_items.extend(collect_google_news())

    if sources in ("all", "kr"):
        logger.info("🏛️ 정부기관 HTML")
        all_items.extend(collect_html_fallback())

    logger.info(f"📊 총 수집: {len(all_items)}건")
    return all_items


def print_console_summary(items: list, verdict):
    """콘솔에 투자 판단 요약 출력"""
    logger = logging.getLogger(__name__)

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"📊 [투자 판단] {verdict.market_mood}")
    logger.info("=" * 60)
    logger.info(f"🟢 BULL: {verdict.total_bull}건 / 🔴 BEAR: {verdict.total_bear}건")
    logger.info("-" * 60)

    # 종목별 시그널
    if verdict.stock_signals:
        logger.info("📋 종목 신호:")
        for ss in sorted(verdict.stock_signals.values(), key=lambda x: abs(x.net_score), reverse=True)[:8]:
            logger.info(
                f"  {ss.direction.emoji} {ss.stock_name:12s} "
                f"순점수:{ss.net_score:+.1f} | {ss.strength} | → {ss.action}"
            )

    logger.info("-" * 60)

    # TOP 5 뉴스
    logger.info("🔥 TOP 5:")
    top5 = sorted(items, key=lambda x: x.impact_score, reverse=True)[:5]
    for rank, item in enumerate(top5, 1):
        d = item.direction
        de = d.emoji if d else "?"
        dv = d.value if d else "?"
        act = f" → {item.action_suggestion}" if item.action_suggestion else ""
        logger.info(
            f"  {rank}. {de}[{dv}] (영향도:{item.impact_score}) "
            f"{item.summary_1line or item.title[:50]}{act}"
        )

    logger.info("=" * 60)


def run_pipeline(
    sources: str = "all",
    fetch_body: bool = True,
    date_str: str | None = None,
):
    """전체 파이프라인 실행"""
    logger = logging.getLogger(__name__)
    start = time.time()

    logger.info("🚀 투자 의사결정 시스템 v2 시작")
    logger.info(f"   소스: {sources} | 본문추출: {fetch_body}")
    logger.info(f"   Gemini API: {'✅' if cfg.GEMINI_API_KEY else '❌ fallback'}")

    cache = URLCache()
    cache.cleanup()

    # ① 수집
    raw = collect_news(sources=sources, fetch_body=fetch_body)

    # ② 중복 제거
    unique = deduplicate(raw)

    # ③ 캐시 필터
    new_items = cache.filter_new(unique)
    if not new_items:
        logger.warning("⚠️ 신규 뉴스 없음")
        return

    # ④ 키워드 필터
    filtered = filter_by_keywords(new_items)
    if not filtered:
        logger.warning("⚠️ 매칭 뉴스 없음")
        cache.add_many(new_items)
        return

    # ⑤ 다차원 영향도 스코어링
    high_impact = score_impact(filtered)
    if not high_impact:
        logger.warning(f"⚠️ 영향도 {cfg.IMPACT_THRESHOLD}+ 없음")
        cache.add_many(new_items)
        return

    # ⑥ 시간대 분류
    high_impact = classify_timeslots(high_impact)

    # ⑦ 시장 영역 분류
    high_impact = classify_markets(high_impact)

    # ⑧ 종목 영향 매핑 (방향+강도)
    high_impact = map_stock_impacts(high_impact)

    # ⑨ LLM 방향 강제 판정 + 투자 시그널
    high_impact = summarize_news(high_impact)

    # ⑩ 시그널 집계 (종목/섹터/시장)
    verdict = aggregate_signals(high_impact)

    # ⑪ 투자 리포트 생성
    report_path = generate_report(high_impact, verdict, date_str=date_str)

    # ⑫ 콘솔 요약
    print_console_summary(high_impact, verdict)

    # ⑬ 캐시 업데이트
    cache.add_many(new_items)

    elapsed = time.time() - start
    logger.info(f"\n✅ 완료 ({elapsed:.1f}초)")
    logger.info(
        f"   수집:{len(raw)} → 중복제거:{len(unique)} → "
        f"필터:{len(filtered)} → 고영향:{len(high_impact)}"
    )
    logger.info(f"   리포트: {report_path}")

    return report_path


def main():
    parser = argparse.ArgumentParser(description="투자 의사결정 시스템 v2")
    parser.add_argument("--sources", choices=["all", "kr", "global"], default="all")
    parser.add_argument("--no-body", action="store_true", help="본문 추출 스킵")
    parser.add_argument("--date", type=str, default=None, help="YYYYMMDD")
    args = parser.parse_args()

    setup_logging()
    run_pipeline(
        sources=args.sources,
        fetch_body=not args.no_body,
        date_str=args.date,
    )


if __name__ == "__main__":
    main()
