"""파이프라인 스케줄러 — NIAS v2.0

시간대별 차등 스케줄링 + 시장지표 고정 10분 + 야간선물 15분
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class PipelineScheduler:
    def __init__(self, run_news_pipeline, run_indicator_monitor,
                 run_night_futures, run_daily_report, flush_alerts):
        self.scheduler = BackgroundScheduler()
        self._run_news = run_news_pipeline
        self._run_indicators = run_indicator_monitor
        self._run_night = run_night_futures
        self._run_report = run_daily_report
        self._flush = flush_alerts

    def setup(self):
        """모든 스케줄 작업 등록"""
        # 장전 (06:00-09:00): 5분 간격
        self.scheduler.add_job(
            self._run_news, CronTrigger(hour="6-8", minute="*/5"),
            kwargs={"sources": "all"}, id="pre_market", replace_existing=True,
        )

        # 장중 (09:00-15:30): 5분 간격
        self.scheduler.add_job(
            self._run_news, CronTrigger(hour="9-15", minute="*/5"),
            kwargs={"sources": "all"}, id="market_hours", replace_existing=True,
        )

        # 장후 (15:30-23:00): 15분 간격
        self.scheduler.add_job(
            self._run_news, CronTrigger(hour="15-22", minute="*/15"),
            kwargs={"sources": "all"}, id="after_market", replace_existing=True,
        )

        # 야간 (23:00-06:00): 60분 간격, 글로벌만
        self.scheduler.add_job(
            self._run_news, CronTrigger(hour="23,0-5", minute="0"),
            kwargs={"sources": "global"}, id="overnight", replace_existing=True,
        )

        # 단기안: 지정학 전용 fast 수집 — 24/7 5분 간격 (main 잡과 2분 오프셋으로 경합 완화)
        # - 핫스팟 쿼리(호르무즈·해상봉쇄·이란·대만·북한 등) 포함
        # - main 잡이 이미 돌고 있어도 dedup/cache가 중복 처리 차단
        self.scheduler.add_job(
            self._run_news, CronTrigger(minute="2-59/5"),
            kwargs={"sources": "geopolitical"}, id="geopolitical_fast", replace_existing=True,
        )

        # 시장지표 모니터링: 항상 10분 간격
        self.scheduler.add_job(
            self._run_indicators, CronTrigger(minute="*/10"),
            id="indicator_monitor", replace_existing=True,
        )

        # 야간선물: 18:00-06:00 15분 간격
        self.scheduler.add_job(
            self._run_night, CronTrigger(hour="18-23,0-5", minute="*/15"),
            id="night_futures", replace_existing=True,
        )

        # 일일 리포트: 월-금 08:00, 18:00
        self.scheduler.add_job(
            self._run_report, CronTrigger(day_of_week="mon-fri", hour="8,18", minute="0"),
            id="daily_report", replace_existing=True,
        )

        # 배치 알림 큐 플러시: 10분 간격
        self.scheduler.add_job(
            self._flush, CronTrigger(minute="*/10"),
            id="batch_flush", replace_existing=True,
        )

        logger.info("[스케줄러] 9개 작업 등록 완료")

    def start(self):
        """스케줄러 시작"""
        self.setup()
        self.scheduler.start()
        logger.info("[스케줄러] 시작")

    def stop(self):
        """스케줄러 중지"""
        self.scheduler.shutdown()
        logger.info("[스케줄러] 중지")
