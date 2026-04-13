"""LLM 요약 v2 — 방향 강제(NEUTRAL 없음) + 투자 시그널 추출

핵심 변경:
- NEUTRAL 제거: 반드시 BULL 또는 BEAR 판정
- investment_signal: "반도체 섹터 매수 신호" 형태
- action_suggestion: "관망" / "분할매수" / "비중축소" 등
- risk_factor: 리스크 요인 명시
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import requests

import config as cfg
from models.news_item import NewsItem, Direction

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """너는 주식 시장 전문 투자 분석가다.
주어진 뉴스를 분석하여 아래 JSON 형식으로만 응답하라.

{
  "summary_1line": "핵심 이벤트 1줄 요약 (30자 이내)",
  "summary_3line": "1. 원인\\n2. 시장 영향\\n3. 투자 시사점",
  "direction": "BULL 또는 BEAR",
  "confidence": 0.5~1.0 사이 소수,
  "investment_signal": "구체적 투자 시그널 1문장",
  "risk_factor": "핵심 리스크 요인 1문장",
  "action_suggestion": "관망/분할매수/적극매수/비중축소/매도 중 택1"
}

핵심 규칙:
- direction은 반드시 BULL 또는 BEAR만 가능. NEUTRAL 절대 금지.
- 애매하더라도 약간이라도 기울어진 방향으로 판정하라.
- confidence는 확신도. 0.5=반반이지만 한쪽, 1.0=확실
- investment_signal은 구체적으로: "반도체 섹터 단기 매수 신호" 식으로
- action_suggestion은 투자자 행동 제안
- 반드시 유효한 JSON만 출력 (다른 텍스트 없이)"""


def _call_gemini(text: str) -> Optional[dict]:
    """Gemini API 호출"""
    if not cfg.GEMINI_API_KEY:
        return None

    url = GEMINI_URL.format(model=cfg.GEMINI_MODEL)
    payload = {
        "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n---\n뉴스:\n{text[:2000]}"}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600},
    }

    for attempt in range(cfg.LLM_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, params={"key": cfg.GEMINI_API_KEY},
                json=payload, timeout=cfg.LLM_TIMEOUT,
            )
            if resp.status_code == 429:
                wait = min(30, 5 * (2 ** attempt))
                logger.warning(f"[Gemini] Rate limit, {wait}초 대기 ({attempt+1}/{cfg.LLM_MAX_RETRIES+1})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                return None

            raw = candidates[0]["content"]["parts"][0]["text"]
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            return json.loads(raw.strip())

        except requests.exceptions.HTTPError as e:
            logger.warning(f"[Gemini] HTTP {resp.status_code}: {e}")
            if attempt < cfg.LLM_MAX_RETRIES:
                time.sleep(3)
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"[Gemini] 파싱 실패: {e}")
            return None
        except Exception as e:
            logger.warning(f"[Gemini] 호출 실패: {e}")
            return None

    return None


def _fallback_direction(item: NewsItem) -> tuple[Direction, float]:
    """키워드 기반 방향 강제 판정"""
    text = f"{item.title} {item.snippet or ''}".lower()

    bull_kw = [
        "호실적", "상승", "급등", "호재", "성장", "수출증가", "매수",
        "surge", "beat", "upgrade", "bullish", "growth", "rally",
        "반등", "신고가", "상향", "흑자", "호조", "개선", "확대", "증가",
        "수요", "양산", "수주", "돌파", "최대",
    ]
    bear_kw = [
        "적자", "하락", "급락", "악재", "위기", "손실", "매도",
        "plunge", "downgrade", "bearish", "decline", "crash",
        "부진", "둔화", "제재", "폭락", "감소", "축소",
        "우려", "리스크", "불안", "충격", "전쟁", "관세",
        "적자전환", "하향", "감산", "철수",
    ]

    bull = sum(1 for kw in bull_kw if kw in text)
    bear = sum(1 for kw in bear_kw if kw in text)

    if bull > bear:
        conf = 0.5 + min(0.4, (bull - bear) * 0.08)
        return Direction.BULL, round(conf, 2)
    elif bear > bull:
        conf = 0.5 + min(0.4, (bear - bull) * 0.08)
        return Direction.BEAR, round(conf, 2)

    # 동점 → 제목 첫 단어 기반
    title_lower = item.title.lower()
    for kw in bear_kw[:10]:
        if kw in title_lower:
            return Direction.BEAR, 0.52
    return Direction.BULL, 0.51


def _fallback_summary(item: NewsItem) -> dict:
    """LLM 없을 때 키워드 기반 분석"""
    direction, confidence = _fallback_direction(item)
    keywords_str = ', '.join(item.matched_keywords[:5]) if item.matched_keywords else "N/A"

    action = "관망"
    if confidence >= 0.7:
        action = "분할매수" if direction == Direction.BULL else "비중축소"
    elif confidence >= 0.6:
        action = "관심종목 등록" if direction == Direction.BULL else "리스크 모니터링"

    return {
        "summary_1line": item.title[:50],
        "summary_3line": (
            f"1. {item.title[:60]}\n"
            f"2. 관련: {keywords_str}\n"
            f"3. 영향도 {item.impact_score}/10 | {direction.label_kr} 신호"
        ),
        "direction": direction.value,
        "confidence": confidence,
        "investment_signal": f"{'상승' if direction == Direction.BULL else '하락'} 신호 (영향도 {item.impact_score})",
        "risk_factor": "키워드 기반 분석 — LLM 검증 필요",
        "action_suggestion": action,
    }


def summarize_news(items: list[NewsItem]) -> list[NewsItem]:
    """뉴스에 방향 강제 판정 + 투자 시그널 태깅"""
    use_llm = bool(cfg.GEMINI_API_KEY)
    if not use_llm:
        logger.warning("[요약] GEMINI_API_KEY 미설정 → fallback")

    delay = getattr(cfg, 'LLM_DELAY_BETWEEN_CALLS', 4)
    batch_pause = getattr(cfg, 'LLM_BATCH_PAUSE', 10)
    success = 0
    fallback_count = 0
    consecutive_fails = 0

    for i, item in enumerate(items):
        if consecutive_fails >= 3:
            if consecutive_fails == 3:
                logger.warning("[요약] 연속 3회 실패 → 나머지 fallback")
            use_llm = False

        text = f"제목: {item.title}\n출처: {item.source}\n본문: {item.text_for_analysis[:1500]}"

        result = None
        if use_llm:
            if i > 0:
                time.sleep(delay)
            if i > 0 and i % 5 == 0:
                logger.info(f"[요약] {i}/{len(items)}건... {batch_pause}초 대기")
                time.sleep(batch_pause)
            result = _call_gemini(text)

        if result:
            item.summary_1line = result.get("summary_1line", item.title[:50])
            item.summary_3line = result.get("summary_3line", "")
            item.investment_signal = result.get("investment_signal", "")
            item.risk_factor = result.get("risk_factor", "")
            item.action_suggestion = result.get("action_suggestion", "관망")

            dir_str = result.get("direction", "BULL").upper()
            if dir_str not in ("BULL", "BEAR"):
                dir_str = _fallback_direction(item)[0].value
            item.direction = Direction(dir_str)
            item.confidence = max(0.5, min(1.0, float(result.get("confidence", 0.6))))
            success += 1
            consecutive_fails = 0
        else:
            fb = _fallback_summary(item)
            item.summary_1line = fb["summary_1line"]
            item.summary_3line = fb["summary_3line"]
            item.investment_signal = fb["investment_signal"]
            item.risk_factor = fb["risk_factor"]
            item.action_suggestion = fb["action_suggestion"]
            item.direction = Direction(fb["direction"])
            item.confidence = fb["confidence"]
            fallback_count += 1
            if use_llm:
                consecutive_fails += 1

    # 방향 통계
    bulls = sum(1 for i in items if i.direction == Direction.BULL)
    bears = len(items) - bulls
    logger.info(f"[요약] {len(items)}건: LLM {success} / Fallback {fallback_count} | 🟢BULL:{bulls} 🔴BEAR:{bears}")

    return items
