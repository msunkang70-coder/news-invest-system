"""종목-기사 연관성 분석 + 영향도 점수화"""

import logging

from core.models import get_conn, get_stocks, insert_analysis
from utils.keyword_match import match_keywords

logger = logging.getLogger(__name__)

# 영향 분류
IMPACT_DIRECT = "직접"    # 종목명 직접 언급
IMPACT_INDIRECT = "간접"  # 섹터/경쟁사/공급망 키워드
IMPACT_MACRO = "시장"     # 거시경제/시장 전반

MACRO_KEYWORDS = [
    "금리", "기준금리", "연준", "fed", "fomc", "인플레이션", "inflation",
    "환율", "달러", "원달러", "유가", "gdp", "고용", "실업률",
    "관세", "tariff", "무역전쟁", "trade war", "경기침체", "recession",
    "반도체 시장", "chip market", "ai market", "tech sector",
]


def classify_impact_type(title: str, body: str, stock_name: str,
                         keywords: list[str]) -> str:
    """영향 유형 분류: 직접/간접/시장"""
    text_lower = f"{title} {body}".lower()

    # 종목명이 직접 언급되면 직접 영향
    if stock_name.lower() in text_lower:
        return IMPACT_DIRECT

    # 종목 고유 키워드(첫 번째 제외, 종목명 자체가 아닌 것)가 매칭되면 직접
    specific_kw = [k for k in keywords if k.lower() != stock_name.lower()]
    for kw in specific_kw:
        if kw.lower() in title.lower():
            return IMPACT_DIRECT

    # 거시경제 키워드가 있으면 시장 영향
    for mk in MACRO_KEYWORDS:
        if mk.lower() in text_lower:
            return IMPACT_MACRO

    return IMPACT_INDIRECT


def calc_relevance(title: str, body: str, keywords: list[str],
                   config: dict) -> tuple[float, list[str]]:
    """위치 기반 가중치를 적용한 관련도 계산"""
    analyzer_cfg = config.get("analyzer", {})
    w_title = analyzer_cfg.get("weight_title", 0.5)
    w_body_early = analyzer_cfg.get("weight_body_early", 0.3)
    w_body_late = analyzer_cfg.get("weight_body_late", 0.1)
    early_chars = analyzer_cfg.get("early_body_chars", 500)

    title_matches = match_keywords(title, keywords)
    body_early = body[:early_chars] if body else ""
    body_late = body[early_chars:] if body and len(body) > early_chars else ""

    early_matches = match_keywords(body_early, keywords)
    late_matches = match_keywords(body_late, keywords)

    all_matches = list(set(title_matches + early_matches + late_matches))
    if not all_matches:
        return 0.0, []

    # 위치별 가중 점수
    score = 0.0
    score += len(set(title_matches)) * w_title
    # 본문 초반에만 있고 제목에 없는 키워드
    early_only = set(early_matches) - set(title_matches)
    score += len(early_only) * w_body_early
    # 본문 후반에만 있는 키워드
    late_only = set(late_matches) - set(title_matches) - set(early_matches)
    score += len(late_only) * w_body_late

    score = min(1.0, max(0.1, score))
    return score, all_matches


def calc_impact(title: str, body: str, matches: list[str],
                impact_type: str,
                positive_signals: list[str],
                negative_signals: list[str]) -> tuple[str, float, str]:
    """영향 방향 + 강도 + reasoning 반환"""
    text = f"{title} {body}"
    text_lower = text.lower()

    # 제목에서 감성 신호 찾기 (가중 2배)
    title_lower = title.lower()
    pos_in_title = [s for s in positive_signals if s.lower() in title_lower]
    neg_in_title = [s for s in negative_signals if s.lower() in title_lower]
    pos_in_body = [s for s in positive_signals if s.lower() in text_lower and s not in pos_in_title]
    neg_in_body = [s for s in negative_signals if s.lower() in text_lower and s not in neg_in_title]

    # 가중 합산: 제목 신호 x2
    pos_score = len(pos_in_title) * 2 + len(pos_in_body)
    neg_score = len(neg_in_title) * 2 + len(neg_in_body)
    total = pos_score + neg_score

    all_pos = pos_in_title + pos_in_body
    all_neg = neg_in_title + neg_in_body

    if total == 0:
        direction = "neutral"
        impact = 0.2
        reasoning_detail = "방향성 신호 없음"
    else:
        if pos_score > 0 and neg_score > 0:
            direction = "mixed"
        elif pos_score > neg_score:
            direction = "positive"
        else:
            direction = "negative"

        # 영향 강도: 기본 0.3 + 신호 수 반영 + 제목 신호 보너스
        impact = min(1.0, 0.3 + total * 0.08)
        # 제목에 신호가 있으면 추가 보너스
        if pos_in_title or neg_in_title:
            impact = min(1.0, impact + 0.1)

        parts = []
        if all_pos:
            parts.append(f"긍정({', '.join(all_pos[:4])})")
        if all_neg:
            parts.append(f"부정({', '.join(all_neg[:4])})")
        reasoning_detail = "; ".join(parts)

    # 영향 유형에 따른 보정
    type_label = f"[{impact_type}]"
    if impact_type == IMPACT_MACRO:
        impact = impact * 0.8  # 시장 전반 뉴스는 개별 종목 영향 낮춤

    reasoning = (
        f"{type_label} 매칭: {', '.join(matches[:5])}. {reasoning_detail}."
    )

    return direction, round(impact, 3), reasoning


def analyze_articles(config: dict, article_ids: list[int] | None = None):
    """기사 목록에 대해 종목별 분석 수행"""
    analyzer_cfg = config.get("analyzer", {})
    min_relevance = analyzer_cfg.get("min_relevance", 0.3)
    pos_signals = analyzer_cfg.get("positive_signals", [])
    neg_signals = analyzer_cfg.get("negative_signals", [])

    stocks = get_stocks(config)
    if not stocks:
        logger.warning("[분석] 등록된 종목 없음")
        return

    conn = get_conn(config)
    if article_ids:
        placeholders = ",".join("?" * len(article_ids))
        rows = conn.execute(
            f"SELECT * FROM articles WHERE id IN ({placeholders})", article_ids
        ).fetchall()
    else:
        rows = conn.execute("""
            SELECT ar.* FROM articles ar
            WHERE NOT EXISTS (SELECT 1 FROM analysis a WHERE a.article_id = ar.id)
        """).fetchall()
    conn.close()

    articles = [dict(r) for r in rows]
    logger.info(f"[분석] 대상 기사 {len(articles)}건, 종목 {len(stocks)}개")

    analysis_count = 0
    skip_low_relevance = 0

    for article in articles:
        title = article["title"] or ""
        body = article["body"] or ""

        for stock in stocks:
            kw_str = stock["keywords"] or stock["name"]
            kw_list = [k.strip() for k in kw_str.split(",") if k.strip()]

            relevance, matches = calc_relevance(title, body, kw_list, config)
            if relevance < min_relevance:
                if relevance > 0:
                    skip_low_relevance += 1
                continue

            impact_type = classify_impact_type(title, body, stock["name"], kw_list)

            direction, impact, reasoning = calc_impact(
                title, body, matches, impact_type, pos_signals, neg_signals
            )

            result = insert_analysis(
                config,
                article_id=article["id"],
                stock_id=stock["id"],
                relevance=round(relevance, 3),
                direction=direction,
                impact=impact,
                reasoning=reasoning,
            )
            if result:
                analysis_count += 1
                logger.info(
                    f"  [{stock['name']}] {direction}({impact:.2f}) - {title[:50]}"
                )

    logger.info(
        f"[분석 완료] 매칭 {analysis_count}건 저장 | 저관련도 스킵 {skip_low_relevance}건"
    )
