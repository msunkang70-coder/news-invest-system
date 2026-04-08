"""파이프라인 v2 검증 — 모의 데이터"""
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config as cfg
from models.news_item import NewsItem, TimeSlot, Direction, MarketDomain
from filters.keyword_filter import filter_by_keywords
from filters.impact_scorer import score_impact
from analyzers.time_classifier import classify_timeslots
from analyzers.market_classifier import classify_markets
from analyzers.stock_impact_mapper import map_stock_impacts
from analyzers.summarizer import summarize_news
from analyzers.signal_aggregator import aggregate_signals
from utils.dedup_v2 import deduplicate
from reports.daily_report import generate_report

KST = timezone(timedelta(hours=9))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_mock_news() -> list[NewsItem]:
    now_kst = datetime.now(KST)
    return [
        NewsItem(
            title="FOMC 금리 동결 결정, 인플레이션 우려에 추가 인상 가능성 시사",
            source="Reuters", url="https://reuters.com/fomc-2026",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=7, minute=30),
            snippet="미 연준이 기준금리를 동결했으나 CPI 상승세가 지속되며 향후 금리인상 가능성을 열어두었다. 파월 의장은 인플레이션과의 전쟁이 끝나지 않았다고 경고.",
            region="GLOBAL",
        ),
        NewsItem(
            title="삼성전자 HBM4 양산 가속, NVIDIA 공급계약 확대 수주",
            source="한국경제", url="https://hankyung.com/samsung-hbm4",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=9, minute=15),
            snippet="삼성전자가 HBM4 양산 시기를 앞당기며 NVIDIA와의 공급 계약을 확대했다. 반도체 수출 호조에 기여 전망.",
            region="KR",
        ),
        NewsItem(
            title="유가 급등 WTI 95달러 돌파, 중동 전쟁 격화로 OPEC 감산 연장",
            source="CNBC", url="https://cnbc.com/oil-95",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=2, minute=0),
            snippet="중동 지정학 리스크와 OPEC 감산 연장으로 WTI 원유가 95달러를 돌파. 글로벌 인플레이션 우려 재점화.",
            region="GLOBAL",
        ),
        NewsItem(
            title="테슬라 1분기 실적 부진, 매출 10% 감소에 가이던스 하향",
            source="Bloomberg", url="https://bloomberg.com/tesla-miss",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=6, minute=30),
            snippet="테슬라 1분기 매출이 전년비 10% 감소하며 시장 기대를 하회. 가이던스도 하향 조정되며 주가 급락.",
            region="GLOBAL",
        ),
        NewsItem(
            title="한국 반도체 수출 3개월 연속 증가, AI칩 수요 견인",
            source="연합뉴스", url="https://yna.co.kr/export-semi",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=10, minute=0),
            snippet="산업부에 따르면 반도체 수출이 전년비 25% 증가. AI칩과 HBM 수요가 성장을 주도했다.",
            region="KR",
        ),
        NewsItem(
            title="미중 관세전쟁 재점화, 중국산 제품 추가 관세 25% 부과",
            source="WSJ", url="https://wsj.com/tariff-war",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=3, minute=0),
            snippet="미국이 중국산 제품에 25% 추가 관세를 부과. 글로벌 공급망 불안과 무역전쟁 격화 우려 확산.",
            region="GLOBAL",
        ),
        NewsItem(
            title="현대차 차세대 전기차 공개, 유럽 수출 확대 전략",
            source="매일경제", url="https://mk.co.kr/hyundai-ev",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=14, minute=30),
            snippet="현대자동차가 차세대 EV 모델을 유럽에서 공개. 수출 확대와 투자 확대 계획도 발표.",
            region="KR",
        ),
        NewsItem(
            title="NVIDIA AI칩 매출 사상 최대, 데이터센터 수요 폭증",
            source="Reuters", url="https://reuters.com/nvidia-record",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=22, minute=0),
            snippet="NVIDIA 데이터센터 매출 사상 최대 기록. AI칩 수요 급증과 HBM 확대가 핵심 성장 동력.",
            region="GLOBAL",
        ),
        NewsItem(
            title="원달러 환율 1,400원 돌파, 강달러에 원화 급락",
            source="한국경제", url="https://hankyung.com/usdkrw-1400",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=11, minute=0),
            snippet="원달러 환율이 1,400원을 돌파하며 원화가 급락. 강달러 기조와 무역적자 우려가 원인.",
            region="KR",
        ),
        NewsItem(
            title="연예인 A씨 새 드라마 출연 확정",
            source="스포츠조선", url="https://sports.chosun.com/ent",
            published_time=datetime.now(timezone.utc),
            published_time_kst=now_kst.replace(hour=11, minute=0),
            snippet="인기 배우 A씨가 새 드라마에 출연한다.",
            region="KR",
        ),
    ]


def test():
    logger.info("=" * 60)
    logger.info("🧪 투자 의사결정 시스템 v2 테스트")
    logger.info("=" * 60)

    items = create_mock_news()
    logger.info(f"📰 모의 뉴스: {len(items)}건")

    # 중복 제거
    items = deduplicate(items)

    # 키워드 필터
    items = filter_by_keywords(items)
    assert not any("드라마" in i.title for i in items), "연예 뉴스 미제거"
    logger.info(f"✅ 키워드 필터 통과: {len(items)}건")

    # 영향도 스코어링 (v2 다차원)
    items = score_impact(items)
    for i in items:
        assert i.urgency >= 0, "urgency 누락"
        assert i.scope >= 0, "scope 누락"
        assert i.certainty >= 0, "certainty 누락"
    logger.info(f"✅ 다차원 스코어링: {len(items)}건 (score≥{cfg.IMPACT_THRESHOLD})")

    # 시간대 분류
    items = classify_timeslots(items)

    # 시장 영역 분류
    items = classify_markets(items)
    assert all(len(i.market_domains) > 0 for i in items), "시장 영역 누락"
    logger.info(f"✅ 시장 영역 분류 완료")

    # 종목 영향 매핑
    items = map_stock_impacts(items)
    mapped = sum(1 for i in items if i.stock_impacts)
    logger.info(f"✅ 종목 매핑: {mapped}/{len(items)}건")
    for i in items:
        for si in i.stock_impacts:
            assert si.direction in (Direction.BULL, Direction.BEAR)
            assert 0 <= si.intensity <= 1

    # LLM 요약 (fallback)
    items = summarize_news(items)
    for i in items:
        assert i.direction in (Direction.BULL, Direction.BEAR), f"NEUTRAL 발견: {i.title}"
        assert i.confidence >= 0.5
    logger.info(f"✅ 방향 강제 판정 완료 — NEUTRAL 0건")

    # 시그널 집계
    verdict = aggregate_signals(items)
    logger.info(f"✅ 시그널 집계: 종목 {len(verdict.stock_signals)}개, 섹터 {len(verdict.sector_signals)}개")
    logger.info(f"   시장 판결: {verdict.market_mood}")

    # 리포트 생성
    report_path = generate_report(items, verdict, date_str="20260409")
    assert Path(report_path).exists()

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "투자 의사결정" in content
    assert "종목별 투자 신호" in content
    assert "섹터별 시그널" in content
    assert "리스크 / 기회" in content

    logger.info(f"\n📄 리포트: {report_path} ({len(content)} bytes)")
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ 모든 테스트 통과!")
    logger.info("=" * 60)

    # 미리보기
    logger.info("\n📋 리포트 미리보기 (40줄):")
    for line in content.split("\n")[:40]:
        logger.info(f"  {line}")


if __name__ == "__main__":
    test()
