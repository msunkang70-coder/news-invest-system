"""LLM 기반 뉴스 요약 + 방향성 판단 — NIAS v2.0

Gemini 2.5 Flash API를 사용하여 뉴스를 분석.
시장 컨텍스트(VIX, 환율, 유가 등)를 프롬프트에 주입하여 판단 정확도 향상.
API 장애 시 키워드 기반 fallback으로 자동 전환.
"""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

import config as cfg
from models.news_item import NewsItem, Direction
from models.market_indicator import MarketIndicator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 금융 뉴스 분석 전문가입니다. 주어진 뉴스와 현재 시장 상황을 종합하여 투자 판단을 내려야 합니다.

## 현재 시장 컨텍스트
{market_context}

## 규칙
1. direction은 반드시 "BULL" 또는 "BEAR" 중 하나. "NEUTRAL"은 절대 불가.
2. 시장 컨텍스트(VIX, 환율, 유가 등)를 반드시 참고하여 판단.
3. 지정학 뉴스의 경우 영향 받는 지역, 섹터, 종목을 구체적으로 명시.
4. risk_factor에 반대 시나리오의 핵심 리스크를 반드시 포함.

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{{
  "summary_1line": "한 줄 요약 (50자 이내)",
  "direction": "BULL 또는 BEAR",
  "confidence": 0.5~1.0,
  "investment_signal": "구체적 투자 시그널",
  "action_suggestion": "적극매수/분할매수/관망/비중축소/매도검토 중 하나",
  "risk_factor": "핵심 리스크 1문장"
}}"""

# 키워드 기반 fallback
BULL_KEYWORDS = [
    "호실적", "급등", "surge", "beat", "upgrade", "bullish",
    "흑자", "수혜", "호재", "사상최고", "사상최대",
    "outperform", "rally", "breakthrough", "record",
    "수주", "수출 호조", "공급 계약", "점유율 확대",
    "상승", "growth", "성장", "매수", "반등", "회복",
    "호황", "역대", "최대", "최고", "수출 증가", "투자 확대",
    "실적 개선", "이익 증가", "매출 증가", "흑자 전환",
    "강세", "강화", "확대", "개선", "rise", "gain", "soar",
    "optimism", "positive", "boost", "expand",
]
BEAR_KEYWORDS = [
    "적자", "하락", "급락", "폭락", "plunge", "downgrade", "bearish",
    "decline", "loss", "감소", "악재", "하향",
    "매도", "underperform", "crash",
    "부진", "둔화", "감산", "철수", "중단",
    "경기침체", "recession",
    "slump", "selloff", "tumble",
    "파업", "리콜", "소송",
]


def build_market_context(indicators: List[MarketIndicator] = None) -> str:
    """현재 시장지표를 프롬프트에 주입할 컨텍스트 문자열 생성"""
    if not indicators:
        return "시장지표 데이터 없음"

    lines = []
    for ind in indicators:
        alert = " ⚠️" if ind.is_alert_worthy else ""
        lines.append(
            f"- {ind.name}: {ind.current_value} ({ind.change_pct:+.1f}%){alert}"
        )
    return "\n".join(lines)


def summarize_with_llm(
    item: NewsItem,
    market_context: str = "시장지표 데이터 없음",
) -> bool:
    """LLM으로 뉴스 분석 (Gemini 2.5 Flash)

    Returns:
        True if LLM 분석 성공, False if fallback 사용
    """
    if not cfg.GEMINI_API_KEY or cfg.GEMINI_API_KEY.startswith("your_"):
        return _fallback_analyze(item)

    try:
        import google.generativeai as genai

        genai.configure(api_key=cfg.GEMINI_API_KEY)
        model = genai.GenerativeModel(cfg.GEMINI_MODEL)

        system = SYSTEM_PROMPT.format(market_context=market_context)
        user_msg = f"다음 뉴스를 분석해주세요:\n\n제목: {item.title}\n소스: {item.source}\n내용: {item.text_for_analysis[:500]}"
        full_prompt = f"{system}\n\n---\n\n{user_msg}"

        response = model.generate_content(
            full_prompt,
            generation_config={
                "max_output_tokens": 2048,
                "temperature": 0.1,
            },
        )

        text = response.text.strip()
        # JSON 파싱 (markdown 코드블록 제거)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # { } 범위 추출 (코드블록 없이 JSON만 온 경우)
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        result = json.loads(text)

        item.summary_1line = result.get("summary_1line", "")
        item.direction = Direction(result.get("direction", "BULL"))
        item.confidence = float(result.get("confidence", 0.6))
        item.investment_signal = result.get("investment_signal", "")
        item.action_suggestion = result.get("action_suggestion", "관망")
        item.risk_factor = result.get("risk_factor", "")

        return True

    except Exception as e:
        logger.warning(f"[LLM] 분석 실패 → fallback: {e}")
        return _fallback_analyze(item)


# 제목 기반 명시적 방향 규칙 (키워드 카운트보다 우선)
_TITLE_RULES_BULL = [
    ("호실적", 0.8), ("역대 최대", 0.8), ("역대급", 0.8), ("사상 최고", 0.8),
    ("흑자 전환", 0.8), ("수출 호조", 0.75), ("수주", 0.7),
    ("실적 개선", 0.75), ("매출 증가", 0.75), ("이익 증가", 0.75),
    ("record profit", 0.8), ("beat expectations", 0.8), ("earnings surprise", 0.8),
]
_TITLE_RULES_BEAR = [
    ("급락", 0.8), ("폭락", 0.85), ("crash", 0.85), ("plunge", 0.85),
    ("제재", 0.7), ("sanctions", 0.7),
    ("금리 인상", 0.7), ("rate hike", 0.7), ("inflation", 0.65),
    ("경기침체", 0.8), ("recession", 0.8), ("적자", 0.75),
    ("slump", 0.75), ("tumble", 0.75), ("selloff", 0.8),
    ("하락", 0.65), ("decline", 0.6), ("lower", 0.55),
]


def _fallback_analyze(item: NewsItem) -> bool:
    """규칙 기반 fallback 분석 (제목 규칙 → 키워드 카운트 → 보수적 판단)"""
    text = item.text_for_analysis.lower()
    title = item.title.lower()

    # 1단계: 제목 명시적 규칙 (가장 신뢰도 높음)
    for kw, conf in _TITLE_RULES_BULL:
        if kw.lower() in title:
            item.direction = Direction.BULL
            item.confidence = conf
            item.summary_1line = item.title[:50]
            item.investment_signal = f"강세 신호: 제목에 '{kw}' 감지"
            item.action_suggestion = "분할매수" if conf >= 0.75 else "관망"
            item.risk_factor = "제목 기반 판정. 본문 확인 권장"
            return False

    for kw, conf in _TITLE_RULES_BEAR:
        if kw.lower() in title:
            item.direction = Direction.BEAR
            item.confidence = conf
            item.summary_1line = item.title[:50]
            item.investment_signal = f"약세 신호: 제목에 '{kw}' 감지"
            item.action_suggestion = "비중축소" if conf >= 0.75 else "관망"
            item.risk_factor = "하방 리스크 주의. 본문 확인 권장"
            return False

    # 2단계: 키워드 카운트 (제목 규칙 미매칭 시)
    bull_count = sum(1 for kw in BULL_KEYWORDS if kw.lower() in text)
    bear_count = sum(1 for kw in BEAR_KEYWORDS if kw.lower() in text)

    # 지정학 뉴스(L3+)는 BEAR 가산
    if getattr(item, "geo_level", None) and item.geo_level >= 3:
        bear_count += 1

    # 동점이면 BEAR (보수적)
    if bull_count > bear_count:
        item.direction = Direction.BULL
    else:
        item.direction = Direction.BEAR

    total = bull_count + bear_count
    item.confidence = min(0.95, 0.5 + abs(bull_count - bear_count) / max(total, 1) * 0.4)
    item.summary_1line = item.title[:50]

    if item.direction == Direction.BULL:
        item.investment_signal = "강세 시그널 감지 — 관련 섹터 매수 기회 탐색"
        if item.confidence >= 0.7:
            item.action_suggestion = "분할매수"
        else:
            item.action_suggestion = "관망"
        item.risk_factor = "키워드 기반 판정. 반대 방향 전환 가능성 점검 필요"
    else:
        item.investment_signal = "약세 시그널 감지 — 리스크 관리 필요"
        if item.confidence >= 0.7:
            item.action_suggestion = "비중축소"
        else:
            item.action_suggestion = "관망"
        item.risk_factor = "하방 리스크 주의. 추격 매도 금지, 저점 확인 후 대응"

    return False


def summarize_news(
    items: List[NewsItem],
    indicators: List[MarketIndicator] = None,
    llm_limit: int = 15,
) -> List[NewsItem]:
    """뉴스 목록 분석: TOP N건은 LLM, 나머지는 fallback

    QA 개선: Free tier 일 20건 → TOP 15건만 LLM 호출.
    impact_score 내림차순으로 정렬하여 고영향 뉴스 우선 분석.
    """
    market_ctx = build_market_context(indicators)
    llm_count = 0
    fallback_count = 0

    # impact_score 높은 순으로 정렬 (LLM 우선 대상)
    sorted_items = sorted(items, key=lambda x: x.impact_score, reverse=True)

    for i, item in enumerate(sorted_items):
        if item.direction is not None:
            continue  # 이미 분석된 항목 스킵

        # TOP llm_limit건만 LLM 시도, 나머지는 바로 fallback
        if llm_count >= llm_limit:
            _fallback_analyze(item)
            fallback_count += 1
            continue

        success = summarize_with_llm(item, market_ctx)
        if success:
            llm_count += 1
        else:
            fallback_count += 1

        # Rate Limit: 건 사이 대기
        if cfg.GEMINI_API_KEY and not cfg.GEMINI_API_KEY.startswith("your_"):
            time.sleep(cfg.LLM_DELAY_BETWEEN_CALLS)
            if (i + 1) % 5 == 0:
                time.sleep(cfg.LLM_BATCH_PAUSE)

    logger.info(
        f"[LLM] {len(items)}건 분석 완료 (LLM: {llm_count}, fallback: {fallback_count})"
    )
    return items
