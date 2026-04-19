"""일회성 누락 복기 백필 스크립트 (단기안 적용 후 과거 누락 건 복구)

동작:
  1. DB에서 최근 N일 뉴스 중 geo_level IS NULL OR < 3 AND impact_score >= 5.0 조회
  2. 분류기(fallback 포함) + impact_scorer 재실행
  3. event_fallback=True OR 재산정 impact_score >= 7.0인 건만 선별
  4. alert_history.json 에 이미 기록된 제목 제외
  5. 상위 --limit 건만 남김
  6. 기본 dry-run (목록만 출력). --send 로 실제 발송

사용:
  python scripts/backfill_missed.py                 # 미리보기
  python scripts/backfill_missed.py --send          # 실제 발송
  python scripts/backfill_missed.py --days 7 --limit 5

이메일 표식:
  - 제목 앞에 [사후 알림] 프리픽스 추가
  - 본문 최상단에 "누락 복기" 배너 삽입
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# src/ 를 import 경로에 추가
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

import config as cfg  # noqa: E402
from models.news_item import NewsItem  # noqa: E402
from analyzers.geopolitical_classifier import classify_geopolitical  # noqa: E402
from analyzers.impact_scorer import score_impact  # noqa: E402
from notifiers.email_notifier import GmailNotifier, build_urgent_email  # noqa: E402


SUBJECT_PREFIX = "[사후 알림] "
BODY_BANNER_HTML = (
    '<div style="background:#6366f1; color:white; padding:10px 14px; '
    'text-align:center; font-size:13px; font-weight:bold; border-radius:8px 8px 0 0; '
    'max-width:620px; margin:0 auto;">'
    '🔔 누락 복기 — 단기안 Fallback 적용 후 재검토된 뉴스입니다'
    '</div>'
)


def load_sent_titles() -> set[str]:
    """alert_history.json 의 제목 집합 (이미 발송된 것 제외용)"""
    history_path = cfg.DATA_DIR / "alert_history.json"
    titles: set[str] = set()
    if history_path.exists():
        try:
            with open(history_path, encoding="utf-8") as f:
                hist = json.load(f)
            for h in hist:
                t = (h.get("title") or "").strip()
                if t:
                    titles.add(t)
        except Exception:
            pass
    return titles


def fetch_candidates(days: int):
    """DB 후보 조회: geo_level 낮거나 None & impact>=5.0 & 최근 N일"""
    db_path = cfg.DATA_DIR / "nias.db"
    if not db_path.exists():
        print(f"[오류] DB 없음: {db_path}")
        return []

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, source, source_type, url, snippet,
               published_time, impact_score, geo_level, geo_region,
               keyword_tier, tagged_stocks
        FROM news_items
        WHERE published_time >= ?
          AND (geo_level IS NULL OR geo_level < 3)
          AND impact_score >= 5.0
        ORDER BY impact_score DESC
        LIMIT 200
        """,
        (cutoff,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def row_to_newsitem(row) -> NewsItem:
    """DB row → NewsItem 복원 (분류기/스코어러 재실행용)"""
    (id_, title, source, source_type, url, snippet,
     published_time, impact_score, geo_level, geo_region,
     keyword_tier, tagged_stocks_raw) = row

    pt = None
    if published_time:
        try:
            pt = datetime.fromisoformat(str(published_time).replace("Z", ""))
        except Exception:
            pt = None

    stocks: list[str] = []
    if tagged_stocks_raw:
        try:
            s = json.loads(tagged_stocks_raw) if isinstance(tagged_stocks_raw, str) else tagged_stocks_raw
            if isinstance(s, list):
                stocks = [str(x) for x in s]
        except Exception:
            pass

    item = NewsItem(
        title=title or "",
        source=source or "",
        url=url or "",
        source_type=source_type or "RSS",
        published_time=pt,
        snippet=snippet or "",
        keyword_tier=keyword_tier,
        tagged_stocks=stocks,
    )
    # 기존 점수는 참고용 (재계산 전)
    item.impact_score = float(impact_score or 0.0)
    return item


def reevaluate(items: list[NewsItem]) -> list[NewsItem]:
    """분류기 + 스코어러 재실행 (in-place 수정)"""
    for it in items:
        # 기존 지정학 판정 초기화하고 fallback 포함해 재분류
        it.geo_level = None
        it.geo_region = ""
        it.geo_conflict_type = ""
        it.event_fallback = False
        it.event_category = None
        it.event_entity_class = None
        classify_geopolitical(it)
    # in-place로 impact_score 재산정 (반환값은 필터된 것이라 무시)
    score_impact(items)
    return items


def filter_promoted(items: list[NewsItem]) -> list[NewsItem]:
    """발송 자격: event_fallback=True OR 재산정 impact_score >= 7.0"""
    return [
        it for it in items
        if getattr(it, "event_fallback", False) or (it.impact_score or 0.0) >= 7.0
    ]


def print_preview(items: list[NewsItem]) -> None:
    print("\n=== 발송 예정 목록 ===")
    for i, it in enumerate(items, 1):
        pt = it.published_time.strftime("%m/%d %H:%M") if it.published_time else "-"
        fb_mark = f"fallback({it.event_entity_class}+{it.event_category})" if it.event_fallback else "no-fallback"
        print(f"\n{i}. [{it.impact_score:.1f}] L{it.geo_level or '-'} | {fb_mark}")
        print(f"   제목: {it.title[:90]}")
        print(f"   출처: {it.source} | 발행: {pt}")
        print(f"   URL : {(it.url or '')[:110]}")


def send_backfill(items: list[NewsItem]) -> int:
    """이메일 실발송 — 제목/본문에 사후 알림 표식 추가"""
    to = cfg.ALERT_EMAIL_TO
    if not to:
        print("[오류] ALERT_EMAIL_TO 미설정. 발송 불가.")
        return 0

    notifier = GmailNotifier()
    if not notifier.authenticate():
        print("[오류] Gmail 인증 실패")
        return 0

    sent = 0
    for it in items:
        try:
            subject, html = build_urgent_email(it)
            subject = f"{SUBJECT_PREFIX}{subject}"
            html = BODY_BANNER_HTML + html
            result = notifier.send(to, subject, html)
            if result:
                sent += 1
                print(f"  ✓ 발송: [{it.impact_score:.1f}] {it.title[:60]} (ID: {result})")
            else:
                print(f"  ✗ 실패: {it.title[:60]}")
        except Exception as e:
            print(f"  ✗ 예외: {it.title[:60]} — {e}")
    return sent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="과거 며칠 범위 (기본 7)")
    parser.add_argument("--limit", type=int, default=5, help="최대 발송 건수 (기본 5)")
    parser.add_argument("--send", action="store_true", help="실제 발송 (기본 dry-run)")
    args = parser.parse_args()

    mode = "SEND" if args.send else "DRY-RUN"
    print(f"=== 누락 복기 백필 [{mode}] ===")
    print(f"기간: 최근 {args.days}일 / 상한: {args.limit}건")

    rows = fetch_candidates(args.days)
    print(f"\n[1/5] DB 후보 조회: {len(rows)}건 (geo_level None|<3 & impact≥5.0)")
    if not rows:
        print("후보 없음. 종료.")
        return

    items = [row_to_newsitem(r) for r in rows]
    items = reevaluate(items)
    print(f"[2/5] 재평가 완료: {len(items)}건 재분류·재스코어링")

    promoted = filter_promoted(items)
    print(f"[3/5] 승격 필터링: {len(promoted)}건 (event_fallback=True OR impact≥7.0)")

    sent_titles = load_sent_titles()
    filtered = [it for it in promoted if (it.title or "").strip() not in sent_titles]
    print(f"[4/5] 발송이력 제외 후: {len(filtered)}건 (이력 {len(sent_titles)}건과 대조)")

    filtered.sort(key=lambda x: x.impact_score, reverse=True)
    final = filtered[: args.limit]
    print(f"[5/5] 상한 {args.limit}건 → 최종 발송 대상: {len(final)}건")

    if not final:
        print("\n발송 대상 없음. 종료.")
        return

    print_preview(final)

    if not args.send:
        print("\n--- DRY-RUN 완료. 실제 발송하려면 --send 옵션으로 재실행 ---")
        return

    print("\n=== 실제 발송 시작 ===")
    sent = send_backfill(final)
    print(f"\n총 {sent}/{len(final)}건 발송 완료.")


if __name__ == "__main__":
    main()
