"""파이프라인 실행 진입점

사용법:
    python run_pipeline.py --once        # 1회 실행
    python run_pipeline.py --schedule    # 스케줄러로 반복 실행
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

# 프로젝트 루트를 path에 추가
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.models import init_db, sync_stocks, get_conn
from core.collector import collect_all
from core.analyzer import analyze_articles
from core.notifier import notify_all


def load_config() -> dict:
    config_path = ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging():
    import os
    os.makedirs(ROOT / "data", exist_ok=True)

    stream_handler = logging.StreamHandler(
        open(sys.stdout.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)
    )
    file_handler = logging.FileHandler(ROOT / "data" / "pipeline.log", encoding="utf-8")

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S")
    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[stream_handler, file_handler],
    )


def _db_stats(config: dict) -> dict:
    """DB 현황 조회"""
    conn = get_conn(config)
    stats = {}
    stats["articles"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    stats["analysis"] = conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
    stats["notifications"] = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE status IN ('sent','console')"
    ).fetchone()[0]
    conn.close()
    return stats


def run_once(config: dict):
    """수집 -> 분석 -> 알림 1회 실행"""
    logger = logging.getLogger(__name__)
    start = time.time()
    logger.info("=" * 55)
    logger.info("파이프라인 시작")
    logger.info("=" * 55)

    # 1. DB 초기화 + 종목 동기화
    init_db(config)
    sync_stocks(config)
    before = _db_stats(config)

    # 2. 수집
    new_ids = collect_all(config)

    # 3. 분석
    analyze_articles(config, article_ids=new_ids if new_ids else None)

    # 4. 알림
    notify_all(config)

    # 5. 결과 요약
    after = _db_stats(config)
    elapsed = time.time() - start
    logger.info("-" * 55)
    logger.info(
        f"[요약] 기사 {before['articles']}->{after['articles']}(+{after['articles']-before['articles']}) | "
        f"분석 {before['analysis']}->{after['analysis']}(+{after['analysis']-before['analysis']}) | "
        f"알림 {before['notifications']}->{after['notifications']}(+{after['notifications']-before['notifications']})"
    )
    logger.info(f"[요약] 소요시간: {elapsed:.1f}초")
    logger.info("=" * 55)


def run_schedule(config: dict):
    """APScheduler로 반복 실행"""
    from apscheduler.schedulers.blocking import BlockingScheduler

    interval = config.get("scheduler", {}).get("interval_minutes", 30)
    logger = logging.getLogger(__name__)
    logger.info(f"스케줄러 시작 - {interval}분 간격")

    run_once(config)

    scheduler = BlockingScheduler()
    scheduler.add_job(run_once, "interval", minutes=interval, args=[config])

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료")


def main():
    parser = argparse.ArgumentParser(description="주식 뉴스 파이프라인")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="1회 실행")
    group.add_argument("--schedule", action="store_true", help="스케줄러 반복 실행")
    args = parser.parse_args()

    setup_logging()
    config = load_config()

    if args.once:
        run_once(config)
    elif args.schedule:
        run_schedule(config)


if __name__ == "__main__":
    main()
