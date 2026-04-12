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
    "호실적", "상승", "급등", "surge", "beat", "upgrade", "bullish",
    "growth", "성장", "흑자", "수혜", "호재", "사상최고", "상향",
    "매수", "outperform", "rally", "breakthrough", "사상최대",
]
BEAR_KEYWORDS = [
    "적자", "하락", "급락", "plunge", "downgrade", "bearish",
    "decline", "loss", "감소", "악재", "리스크", "하향", "위기",
    "매도", "underperform", "crash", "제재", "불확실",
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

        gen_config = {
            "max_output_tokens": 1024,
            "temperature": 0.2,
            "response_mime_type": "application/json",
        }
        # Gemini 2.5 모델의 thinking 비활성화 (JSON 잘림 방지)
        if "2.5" in cfg.GEMINI_MODEL:
            gen_config["thinking_config"] = {"thinking_budget": 0}

        response = model.generate_content(
            full_prompt,
            generation_config=gen_config,
        )

        text = response.text.strip()
        # JSON 파싱 (markdown 코드블록 제거)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

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


def _fallback_analyze(item: NewsItem) -> bool:
    """키워드 기반 fallback 분석"""
    text = item.text_for_analysis.lower()

    bull_count = sum(1 for kw in BULL_KEYWORDS if kw.lower() in text)
    bear_count = sum(1 for kw in BEAR_KEYWORDS if kw.lower() in text)

    if bull_count >= bear_count:
        item.direction = Direction.BULL
    else:
        item.direction = Direction.BEAR

    total = bull_count + bear_count
    item.confidence = min(0.95, 0.5 + abs(bull_count - bear_count) / max(total, 1) * 0.4)
    item.summary_1line = item.title[:50]
    item.investment_signal = f"{'강세' if item.direction == Direction.BULL else '약세'} 키워드 감지"
    item.action_suggestion = "관망"
    item.risk_factor = "키워드 기반 분석 — LLM 분석 불가 상태"

    return False


def summarize_news(
    items: List[NewsItem],
    indicators: List[MarketIndicator] = None,
) -> List[NewsItem]:
    """뉴스 목록 일괄 LLM 분석 (Rate Limit 관리)"""
    market_ctx = build_market_context(indicators)
    llm_count = 0
    fallback_count = 0

    for i, item in enumerate(items):
        if item.direction is not None:
            continue  # 이미 분석된 항목 스킵

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
