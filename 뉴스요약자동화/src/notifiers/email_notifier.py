"""Gmail 이메일 알림 발송기 — NIAS v2.0

방법 1 (권장): Gmail API (OAuth2)
방법 2 (대안): SMTP + 앱 비밀번호
"""
from __future__ import annotations

import base64
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

import config as cfg

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # 라벨 추가 (INBOX 배치용)
]


class GmailNotifier:
    """Gmail API 기반 이메일 알림 (재시도 + fallback + 연속 실패 감지)"""

    MAX_RETRIES = 3
    CONSECUTIVE_FAIL_THRESHOLD = 3

    def __init__(self, credentials_path: str = None):
        self.credentials_path = credentials_path or str(cfg.SRC_DIR / "credentials.json")
        self.token_path = str(cfg.DATA_DIR / "gmail_token.json")
        self.service = None
        self._consecutive_failures = 0
        self._total_sent = 0
        self._total_failed = 0

    def authenticate(self) -> bool:
        """OAuth2 인증 (최초 1회 브라우저 인증 필요)"""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None

            if os.path.exists(self.token_path):
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_path):
                        logger.error(f"credentials.json 없음: {self.credentials_path}")
                        return False
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                with open(self.token_path, "w") as f:
                    f.write(creds.to_json())

            self.service = build("gmail", "v1", credentials=creds)
            logger.info("[이메일] Gmail API 인증 성공")
            return True

        except Exception as e:
            logger.error(f"[이메일] Gmail API 인증 실패: {e}")
            return False

    def send(self, to: str, subject: str, html_body: str) -> Optional[str]:
        """HTML 이메일 전송 (최대 3회 재시도 + SMTP fallback)"""
        import time as _time

        if not self.service:
            if not self.authenticate():
                return self._send_smtp_fallback(to, subject, html_body)

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                from email.header import Header

                message = MIMEMultipart("alternative")
                message["to"] = to
                message["subject"] = Header(subject, "utf-8")
                message.attach(MIMEText(html_body, "html", "utf-8"))

                raw = base64.urlsafe_b64encode(
                    message.as_string().encode("utf-8")
                ).decode("ascii")

                sent = self.service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()

                msg_id = sent.get("id", "unknown")

                # 자기 자신에게 보낸 메일을 받은편지함에도 표시
                try:
                    self.service.users().messages().modify(
                        userId="me", id=msg_id,
                        body={"addLabelIds": ["INBOX", "UNREAD"]}
                    ).execute()
                except Exception:
                    pass

                self._consecutive_failures = 0
                self._total_sent += 1
                logger.info(f"[이메일] 발송 성공: {subject[:40]}... (ID: {msg_id})")
                return msg_id

            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    wait = 2 ** attempt  # 2s, 4s
                    logger.warning(
                        f"[이메일] 발송 실패 (시도 {attempt}/{self.MAX_RETRIES}), "
                        f"{wait}초 후 재시도: {e}"
                    )
                    _time.sleep(wait)
                else:
                    logger.error(
                        f"[이메일] Gmail API {self.MAX_RETRIES}회 실패 → SMTP fallback: {e}"
                    )

        # Gmail API 최종 실패 → SMTP fallback
        self._consecutive_failures += 1
        self._total_failed += 1

        if self._consecutive_failures >= self.CONSECUTIVE_FAIL_THRESHOLD:
            logger.critical(
                f"[이메일] 연속 {self._consecutive_failures}회 실패! "
                f"Gmail API 상태 점검 필요 (토큰 만료 또는 API 장애)"
            )

        return self._send_smtp_fallback(to, subject, html_body)

    def _send_smtp_fallback(self, to: str, subject: str, html_body: str) -> Optional[str]:
        """SMTP fallback (Gmail API 실패 시)"""
        logger.info("[이메일] SMTP fallback 시도...")
        try:
            import smtplib

            gmail_user = os.environ.get("GMAIL_USER", "")
            gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")

            if not gmail_user or not gmail_pass:
                logger.warning(
                    "[이메일] SMTP 인증정보 없음 (GMAIL_USER, GMAIL_APP_PASSWORD) — "
                    "발송 불가. .env에 설정하거나 Gmail 앱 비밀번호를 생성하세요."
                )
                self._total_failed += 1
                return None

            from email.header import Header

            msg = MIMEMultipart("alternative")
            msg["From"] = gmail_user
            msg["To"] = to
            msg["Subject"] = Header(subject, "utf-8")
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_user, gmail_pass)
                server.send_message(msg)

            self._consecutive_failures = 0
            self._total_sent += 1
            logger.info(f"[이메일] SMTP 발송 성공: {subject[:40]}...")
            return "smtp_sent"

        except Exception as e:
            self._total_failed += 1
            logger.error(f"[이메일] SMTP fallback 실패: {e}")
            return None

    @property
    def stats(self) -> dict:
        """발송 통계"""
        total = self._total_sent + self._total_failed
        success_rate = (self._total_sent / total * 100) if total > 0 else 0
        return {
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "consecutive_failures": self._consecutive_failures,
            "success_rate": f"{success_rate:.1f}%",
        }


def _clean_html(text: str) -> str:
    """HTML 태그 및 엔티티 제거"""
    import re
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&\w+;', ' ', text)
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _format_time(dt) -> str:
    """발행 시간을 한국어 포맷으로"""
    if not dt:
        return "시간 미상"
    if isinstance(dt, str):
        try:
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt[:16] if len(str(dt)) > 16 else str(dt)
    try:
        return dt.strftime("%Y년 %m월 %d일 %H:%M")
    except Exception:
        return str(dt)[:16]


def _get_keywords_str(item) -> str:
    """매칭 키워드를 표시용 문자열로"""
    import json
    kws = getattr(item, "matched_keywords", [])
    if isinstance(kws, str):
        try:
            kws = json.loads(kws)
        except Exception:
            kws = []
    return ", ".join(kws[:5]) if kws else ""


def _get_stocks_str(item) -> str:
    """태깅 종목을 표시용 문자열로"""
    import json
    stocks = getattr(item, "tagged_stocks", [])
    if isinstance(stocks, str):
        try:
            stocks = json.loads(stocks)
        except Exception:
            stocks = []
    return ", ".join(stocks[:5]) if stocks else ""


def build_urgent_email(item) -> tuple[str, str]:
    """긴급 속보 이메일 HTML 생성 (풍부한 정보 + 출처 + 시간)"""
    from datetime import datetime

    direction = getattr(item, "direction", None)
    d_emoji = "📈 강세" if direction and direction.value == "BULL" else "📉 약세" if direction and direction.value == "BEAR" else "⚪ 미판정"
    score = getattr(item, "impact_score", 0)
    title = _clean_html(getattr(item, "title", ""))
    snippet = _clean_html(getattr(item, "snippet", ""))[:300]
    source = getattr(item, "source", "미상")
    source_type = getattr(item, "source_type", "RSS")
    url = getattr(item, "url", "")
    pub_time = _format_time(getattr(item, "published_time", None))
    keywords = _get_keywords_str(item)
    stocks = _get_stocks_str(item)
    signal = getattr(item, "investment_signal", "")
    action = getattr(item, "action_suggestion", "")
    risk = getattr(item, "risk_factor", "")
    chain = getattr(item, "impact_chain", "")
    geo_level = getattr(item, "geo_level", None)
    geo_region = getattr(item, "geo_region", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M KST")

    # 지정학 섹션
    geo_html = ""
    if geo_level:
        level_names = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}
        level_colors = {1: "#22c55e", 2: "#eab308", 3: "#f97316", 4: "#ef4444", 5: "#991b1b"}
        geo_html = f"""
        <tr style="background:#fff3cd;">
          <td style="padding:10px; font-weight:bold;">🌍 지정학</td>
          <td style="padding:10px; color:{level_colors.get(geo_level, '#666')}; font-weight:bold;">
            Level {geo_level} — {level_names.get(geo_level, '?')} ({geo_region})
          </td>
        </tr>"""

    # 제목: 이모지 + 제목 + 한줄 행동
    action_hint = action if action and action != "관망" else signal[:25] if signal else ""
    subject = f"🚨 [{score}점] {title[:45]}" + (f" | {action_hint}" if action_hint else "")

    # preheader: Gmail 미리보기
    preheader_text = signal[:60] if signal and signal != "분석 대기" else snippet[:60] if snippet else title[:60]
    preheader = f'<span style="display:none!important;opacity:0;color:transparent;height:0;width:0;max-height:0;max-width:0;overflow:hidden;">{preheader_text}</span>'

    html = f"""
    {preheader}
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', Arial, sans-serif; max-width: 620px; margin: 0 auto; background: #fff;">
      <div style="background: #dc3545; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0; font-size:20px;">🚨 긴급 속보</h2>
        <p style="margin:6px 0 0; opacity:0.9; font-size:13px;">{now} | 영향도 {score}/10 | {source}</p>
      </div>

      <div style="padding: 20px; border: 1px solid #ddd; border-top: none;">
        <h3 style="margin:0 0 12px; font-size:18px; line-height:1.4;">{title}</h3>

        <table style="width:100%; border-collapse:collapse; margin:12px 0; font-size:14px;">
          <tr style="background:#f8f9fa;">
            <td style="padding:10px; font-weight:bold; width:100px;">📰 출처</td>
            <td style="padding:10px;">{source} ({source_type})</td>
          </tr>
          <tr>
            <td style="padding:10px; font-weight:bold;">🕐 발행 시각</td>
            <td style="padding:10px;">{pub_time}</td>
          </tr>
          <tr style="background:#f8f9fa;">
            <td style="padding:10px; font-weight:bold;">📊 방향성</td>
            <td style="padding:10px; font-weight:bold;">{d_emoji} (확신도: {getattr(item, 'confidence', 0):.0%})</td>
          </tr>
          {geo_html}
          {'<tr><td style="padding:10px; font-weight:bold;">🏷️ 관련 종목</td><td style="padding:10px;">' + stocks + '</td></tr>' if stocks else ''}
          {'<tr style="background:#f8f9fa;"><td style="padding:10px; font-weight:bold;">🔑 키워드</td><td style="padding:10px;">' + keywords + '</td></tr>' if keywords else ''}
        </table>

        {'<div style="background:#f0f4ff; padding:14px; border-radius:6px; margin:12px 0;"><strong>📰 본문 요약:</strong><br>' + snippet + '</div>' if snippet else ''}

        <div style="background:#e8f5e9; padding:14px; border-radius:6px; margin:12px 0;">
          <p style="margin:0 0 8px;"><strong>📌 투자 시그널:</strong> {signal or '분석 대기'}</p>
          <p style="margin:0 0 8px;"><strong>💡 행동 제안:</strong> {action or '관망'}</p>
          <p style="margin:0;"><strong>⚠️ 리스크:</strong> {risk or '추가 정보 확인 필요'}</p>
        </div>

        {f'<div style="background:#fff3cd; padding:14px; border-radius:6px; margin:12px 0;"><strong>🔗 영향 체인:</strong> {chain}</div>' if chain else ''}

        {'<a href="' + url + '" style="display:inline-block; background:#dc3545; color:white; padding:12px 24px; border-radius:6px; text-decoration:none; font-weight:bold; margin:12px 0;">📄 원본 기사 보기</a>' if url and url.startswith('http') else ''}

        <hr style="margin:20px 0; border:none; border-top:1px solid #eee;">
        <p style="color: #999; font-size: 11px; line-height:1.6;">
          ⚠️ 본 알림은 NIAS v2.0에 의해 자동 생성된 참고 정보입니다.<br>
          투자 판단의 최종 책임은 사용자에게 있으며, 반드시 원문을 확인하시기 바랍니다.
        </p>
      </div>
    </div>
    """
    return subject, html


def _build_indicator_assessment(indicator) -> str:
    """지표 종류별 정량 평가 + 시나리오 + 행동 제안 HTML 생성 (템플릿 전용)"""
    ticker = indicator.ticker
    val = indicator.current_value
    chg = indicator.change_pct

    if ticker == "^VIX":
        if val >= 30:
            risk_grade = "상위 5% 수준 (패닉 구간, 평균 5-10 거래일 체류)"
            s1 = f"▸ VIX 35 이상 → 추가 급락 가능, 헷지 비용 급등"
            s2 = f"▸ VIX 25 하회 → 1-2주 내 안정 복귀 (과거 70% 확률)"
            s3 = f"▸ VIX 40 돌파 → 시스템 리스크, 현금 비중 극대화"
            short_action = "위험자산 비중 20-30% 즉시 축소. 추격 매도 금지"
            mid_action = "VIX 25 하회 확인 전까지 신규 매수 보류"
        elif val >= 25:
            risk_grade = "상위 20% 수준 (경계 구간, 평균 3-7 거래일)"
            s1 = f"▸ VIX 30 돌파 → 공포 구간 전환, 매도 압력 가속"
            s2 = f"▸ VIX 20 하회 → 이벤트 소화 후 안정 (1-2주)"
            s3 = f"▸ VIX 25 유지 → 횡보, 방향 탐색 구간"
            short_action = "신규 매수 보류. 기존 포지션 스톱로스 점검"
            mid_action = "VIX 20 하회 확인 후 정상 매매 재개"
        else:
            risk_grade = "정상 범위 (안정 구간)"
            s1 = f"▸ VIX 20 이상 → 단기 불안 징후, 관찰 필요"
            s2 = f"▸ VIX 15 이하 → 과도한 안심, 변동성 매도 전략 유효"
            s3 = f"▸ 돌발 이벤트 시 25+ 급등 가능 — 헷지 준비"
            short_action = "정상 매매 가능. 변동성 매도 전략 유효"
            mid_action = "추세 추종 전략 유지"

    elif ticker in ("KRW/USD",):
        if val >= 1450:
            risk_grade = "상위 10% 수준 (당국 개입 경계, 외국인 유출 가속)"
            s1 = f"▸ 1,500원 돌파 → 심리적 저항 붕괴, 추가 약세"
            s2 = f"▸ 1,400원 하회 → 중동 리스크 완화 시 2-4주 내 복귀"
            s3 = f"▸ 1,450원 유지 → 수출주 환차익 지속, 내수주 부담"
            short_action = "수출주(삼성전자, 현대차) 보유 유지. 내수주 신규 매수 보류"
            mid_action = "1,400원 하회 확인 시 내수주/여행주 비중 확대"
        elif val >= 1400:
            risk_grade = "상위 25% 수준 (경계 구간)"
            s1 = f"▸ 1,450원 돌파 → 외국인 순매도 가속, 코스피 하방 압력"
            s2 = f"▸ 1,350원 하회 → 안정 구간 복귀"
            s3 = f"▸ 1,400원대 횡보 → 수출주 유리, 외국인 수급 부담"
            short_action = "외국인 순매도 종목 매수 보류. 수출주 비중 확대"
            mid_action = "환율 1,380원 하회 확인 후 내수주 재진입"
        else:
            risk_grade = "정상 범위"
            s1 = f"▸ 1,400원 돌파 → 경계 구간 진입, 수출주 부각"
            s2 = f"▸ 1,300원 하회 → 원화 강세, 내수주 유리"
            s3 = f"▸ 현 수준 유지 → 환율 중립, 종목 선별 장세"
            short_action = "정상 매매 가능"
            mid_action = "현 전략 유지"

    elif ticker in ("CL=F", "BZ=F"):
        abs_chg = abs(chg)
        if abs_chg >= 8:
            risk_grade = f"상위 3% 수준 (일변동 {abs_chg:.1f}%, OPEC/지정학 이벤트급)"
            s1 = f"▸ ${val+5:.0f} 돌파 → {'인플레 재점화, 금리 인상 기대 강화' if chg > 0 else '산유국 감산 대응, 반등 가능'}"
            s2 = f"▸ ${val-10:.0f} 복귀 → 이벤트 소화 후 되돌림 (3-5일)"
            s3 = f"▸ $120+ → 경기침체 우려 본격화" if chg > 0 else f"▸ $80 이하 → 에너지주 구조적 하락"
            short_action = f"{'에너지 ETF 단기 매수 가능. 추격 매수 금지' if chg > 0 else '항공/해운주 반등 매수 검토. 에너지주 매수 보류'}"
            mid_action = f"{'유가 $100 이상 유지 시 인플레 자산 비중 축소' if chg > 0 else '유가 $85 안정 확인 후 에너지주 분할 매수'}"
        elif abs_chg >= 5:
            risk_grade = f"상위 15% 수준 (일변동 {abs_chg:.1f}%, 주의 구간)"
            s1 = f"▸ ${val+5:.0f} 이상 → {'상승 모멘텀 지속' if chg > 0 else '추가 하락 모멘텀'}"
            s2 = f"▸ ${val-5:.0f} 이하 → 평균 회귀 (1주 이내)"
            s3 = f"▸ OPEC 회의/재고 데이터에 민감 — 이벤트 전 관망"
            short_action = f"에너지 관련 종목 단기 대응. 추격 {'매수' if chg > 0 else '매도'} 금지"
            mid_action = "유가 방향 확인 후 포지션 조정"
        else:
            risk_grade = "정상 범위"
            s1 = f"▸ ${val+10:.0f} 돌파 → 인플레 우려 부각"
            s2 = f"▸ ${val-10:.0f} 하회 → 에너지주 하방 압력"
            s3 = f"▸ 현 수준 유지 → 에너지 섹터 중립"
            short_action = "현 전략 유지"
            mid_action = "현 전략 유지"

    elif ticker == "^TNX":
        if val >= 5.0:
            risk_grade = "상위 1% 수준 (2007년 이후 최고, 밸류에이션 압박)"
            s1 = f"▸ {val+0.3:.1f}% 돌파 → 성장주 추가 하락, 부동산 직격"
            s2 = f"▸ 4.5% 하회 → Fed 개입 기대, 1-2개월 내 안정"
            s3 = f"▸ 5.5%+ 장기 체류 → 재정적자 우려, 구조적 고금리"
            short_action = "성장주/기술주 비중 즉시 축소. 단기채/현금 확대"
            mid_action = "4.5% 하회 확인 시 장기채 매수 기회 탐색"
        else:
            risk_grade = f"상위 30% 수준 (금리 변동 구간)"
            s1 = f"▸ {val+0.2:.1f}% 이상 → 성장주 밸류에이션 하방 압력"
            s2 = f"▸ {val-0.3:.1f}% 이하 → 금리 안정, 성장주 반등"
            s3 = f"▸ CPI/고용 발표일 전후 변동성 확대 예상"
            short_action = "금리 민감 섹터(부동산, 유틸리티) 매수 보류"
            mid_action = "듀레이션 중립 유지. Fed 발언 모니터링"

    else:
        risk_grade = f"{indicator.name} 변동 관찰 필요"
        s1 = f"▸ {indicator.name} {'상승' if chg > 0 else '하락'} 추세 확인 필요"
        s2 = f"▸ 추세 지속 여부 1-2일 관찰"
        s3 = f"▸ 관련 이벤트 발생 시 변동 확대 가능"
        short_action = "관련 섹터 모니터링. 신규 진입 보류"
        mid_action = "추세 확인 후 판단"

    return f"""
        <div style="border:1px solid #e2e8f0; border-radius:8px; margin:16px 0; overflow:hidden;">
          <div style="background:#f1f5f9; padding:12px 14px; font-weight:bold; font-size:14px; border-bottom:1px solid #e2e8f0;">
            📋 정량 평가
          </div>
          <div style="padding:14px; font-size:13px;">
            <span style="color:#334155; font-weight:bold;">위험도:</span> {risk_grade}
          </div>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:8px; margin:16px 0; overflow:hidden;">
          <div style="background:#f1f5f9; padding:12px 14px; font-weight:bold; font-size:14px; border-bottom:1px solid #e2e8f0;">
            🔮 시나리오
          </div>
          <div style="padding:14px; font-size:13px; line-height:1.8;">
            {s1}<br>{s2}<br>{s3}
          </div>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:8px; margin:16px 0; overflow:hidden;">
          <div style="background:#f1f5f9; padding:12px 14px; font-weight:bold; font-size:14px; border-bottom:1px solid #e2e8f0;">
            💡 행동 제안
          </div>
          <div style="padding:14px; font-size:13px;">
            <div style="margin-bottom:8px;">
              <span style="background:#dbeafe; padding:2px 8px; border-radius:3px; font-weight:bold; font-size:12px;">단기</span>
              &nbsp;{short_action}
            </div>
            <div>
              <span style="background:#ede9fe; padding:2px 8px; border-radius:3px; font-weight:bold; font-size:12px;">중기</span>
              &nbsp;{mid_action}
            </div>
          </div>
        </div>"""


def _indicator_oneliner(indicator) -> str:
    """제목/프리뷰용 한줄 해석 (subject | 뒤, preheader)"""
    ticker = indicator.ticker
    val = indicator.current_value
    chg = indicator.change_pct

    if ticker == "^VIX":
        if val >= 30: return "변동성 패닉 구간. 방어 우선, 매수 보류"
        if val >= 25: return "변동성 확대. 추격매수보다 방어 우선"
        return "변동성 안정. 정상 매매 가능"
    elif ticker == "KRW/USD":
        if val >= 1450: return f"1450 상회 지속. 수출주 유리, 지수는 부담"
        if val >= 1400: return "경계 구간. 외국인 수급 부담 지속"
        return "안정 구간. 환율 중립"
    elif ticker in ("CL=F", "BZ=F"):
        if abs(chg) >= 5:
            return f"유가 {'급등' if chg > 0 else '급락'}으로 {'인플레 재자극 우려' if chg > 0 else '에너지주 하방 압력'}"
        return "유가 안정. 에너지 섹터 중립"
    elif ticker == "^TNX":
        if val >= 5.0: return "10년물 5%+. 성장주 밸류에이션 압박 심화"
        return f"금리 {val:.1f}%. Fed 방향 주시"
    elif ticker == "^GSPC":
        if abs(chg) >= 2: return f"S&P500 {'급등' if chg > 0 else '급락'}. 변동성 확대 구간"
        return "S&P500 정상 범위"
    else:
        return f"{indicator.name} {chg:+.1f}% 변동. 모니터링 필요"


def build_indicator_email(indicator) -> tuple[str, str]:
    """시장지표 알림 이메일 HTML (풍부한 정보 + 시간)"""
    from datetime import datetime

    level_emoji = indicator.level_emoji
    level_name = indicator.threshold_level.value
    now = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    ts = _format_time(getattr(indicator, "timestamp", None))

    assessment_html = _build_indicator_assessment(indicator)
    oneliner = _indicator_oneliner(indicator)

    # 제목: [이모지][지표명] 현재값 (변동률) | 한줄 의미
    level_str = indicator.threshold_level.value
    subj_emoji = {"위험": "🔴", "극단": "🔴", "경고": "🟠", "주의": "🟠"}.get(level_str, "🟢")
    subject = f"{subj_emoji} {indicator.name} {indicator.current_value} ({indicator.change_pct:+.1f}%) | {oneliner}"

    # 프리뷰 (Gmail 받은편지함 미리보기)
    preheader = f'<span style="display:none!important;opacity:0;color:transparent;height:0;width:0;max-height:0;max-width:0;overflow:hidden;">{oneliner}</span>'

    html = f"""
    {preheader}
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', Arial, sans-serif; max-width: 620px; margin: 0 auto;">
      <div style="background: #fd7e14; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0; font-size:20px;">{level_emoji} {indicator.name}</h2>
        <p style="margin:6px 0 0; opacity:0.9; font-size:13px;">{now}</p>
      </div>
      <div style="padding: 20px; border: 1px solid #ddd; border-top: none;">
        <table style="width:100%; border-collapse:collapse; font-size:14px;">
          <tr style="background:#f8f9fa;">
            <td style="padding:10px; font-weight:bold;">📊 지표</td>
            <td style="padding:10px; font-size:16px; font-weight:bold;">{indicator.name}</td>
          </tr>
          <tr>
            <td style="padding:10px; font-weight:bold;">💰 현재값</td>
            <td style="padding:10px; font-size:18px; font-weight:bold;">{indicator.current_value} <span style="color:{'#22c55e' if indicator.change_pct > 0 else '#ef4444'};">({indicator.change_pct:+.1f}%)</span></td>
          </tr>
          <tr style="background:#f8f9fa;">
            <td style="padding:10px; font-weight:bold;">📈 전일 종가</td>
            <td style="padding:10px;">{indicator.previous_close}</td>
          </tr>
          <tr>
            <td style="padding:10px; font-weight:bold;">🚦 상태</td>
            <td style="padding:10px; font-weight:bold;">{level_emoji} {level_name}</td>
          </tr>
          <tr style="background:#f8f9fa;">
            <td style="padding:10px; font-weight:bold;">🕐 기준 시각</td>
            <td style="padding:10px;">{ts}</td>
          </tr>
        </table>

        <div style="background:#fff3cd; padding:14px; border-radius:6px; margin:16px 0;">
          <strong>⚠️ 임계값 돌파:</strong>
          <ul style="margin:8px 0 0; padding-left:20px;">
            {''.join(f'<li style="margin:4px 0;">{b}</li>' for b in indicator.threshold_breached)}
          </ul>
        </div>

        {f'<div style="background:#e8f5e9; padding:14px; border-radius:6px; margin:12px 0;"><strong>📌 시장 영향:</strong> {indicator.market_implication}</div>' if indicator.market_implication else ''}

        {assessment_html}

        <hr style="margin:20px 0; border:none; border-top:1px solid #eee;">
        <p style="color: #999; font-size: 11px;">
          ⚠️ 본 알림은 NIAS v2.0에 의해 자동 생성된 참고 정보입니다.<br>
          투자 판단의 최종 책임은 사용자에게 있습니다.
        </p>
      </div>
    </div>
    """
    return subject, html


def build_daily_report_email(verdict, top_items, indicators=None, geo_summary=None) -> tuple[str, str]:
    """일�� 리포트 이메일 HTML 생성"""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    direction = getattr(verdict, 'overall_direction', None)
    direction_emoji = "📈" if direction and direction.value == "BULL" else "📉"
    confidence = getattr(verdict, 'overall_confidence', 0.5)
    mood = getattr(verdict, 'market_mood', '분석 중')
    total_bull = getattr(verdict, 'total_bull', 0)
    total_bear = getattr(verdict, 'total_bear', 0)

    # TOP 5 뉴스
    top_news_html = ""
    for item in top_items[:5]:
        d_emoji = "📈" if getattr(item, 'direction', None) and item.direction.value == "BULL" else "����"
        score = getattr(item, 'impact_score', 0)
        top_news_html += f"""
        <tr>
          <td style="padding:8px; text-align:center; font-weight:bold;">{score}</td>
          <td style="padding:8px;">{d_emoji} {item.title[:60]}</td>
          <td style="padding:8px;">{getattr(item, 'action_suggestion', '-')}</td>
        </tr>"""

    # 시장지표
    indicator_html = ""
    if indicators:
        for ind in indicators[:6]:
            indicator_html += f"""
            <tr>
              <td style="padding:6px;">{ind.name}</td>
              <td style="padding:6px; text-align:right;">{ind.current_value}</td>
              <td style="padding:6px; text-align:right;">{ind.change_pct:+.1f}%</td>
              <td style="padding:6px; text-align:center;">{ind.level_emoji}</td>
            </tr>"""

    # 지정학
    geo_html = ""
    if geo_summary:
        level_bar = {1: "■□□□□", 2: "■■□□□", 3: "■■■□□", 4: "■■■■□", 5: "■■■■■"}
        for region, level in geo_summary.items():
            color = {1: "#22c55e", 2: "#eab308", 3: "#f97316", 4: "#ef4444", 5: "#991b1b"}.get(level, "#666")
            geo_html += f'<span style="color:{color}; margin-right:12px;">{level_bar.get(level, "?")} L{level} {region}</span> '

    # 종목 시그널
    stock_html = ""
    stock_signals = getattr(verdict, 'stock_signals', {})
    for name, ss in sorted(stock_signals.items(), key=lambda x: abs(x[1].net_score), reverse=True)[:5]:
        net = ss.net_score
        bar_pct = min(100, abs(net) * 15)
        color = "#22c55e" if net > 0 else "#ef4444"
        stock_html += f"""
        <tr>
          <td style="padding:6px;">{name}</td>
          <td style="padding:6px;"><div style="background:{color}; width:{bar_pct}%; height:14px; border-radius:4px; display:inline-block;"></div></td>
          <td style="padding:6px; text-align:right;">{net:+.1f}</td>
          <td style="padding:6px;">{ss.action}</td>
        </tr>"""

    subject = f"📊 [NIAS] {datetime.now().strftime('%Y-%m-%d')} 투자 리포트"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto;">
      <div style="background: #1e40af; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0;">📊 NIAS 일일 투자 리포트</h2>
        <p style="margin:4px 0 0; opacity:0.85;">{today}</p>
      </div>
      <div style="padding: 20px; border: 1px solid #ddd; border-top: none;">
        <div style="background:#f0f4ff; padding:16px; border-radius:8px; margin-bottom:16px;">
          <h3 style="margin:0 0 8px;">{direction_emoji} 시장 종합: {direction.value if direction else 'N/A'} (확신도 {confidence:.0%})</h3>
          <p style="margin:0;">BULL {total_bull}건 vs BEAR {total_bear}건 | {mood}</p>
        </div>
        {'<h3>📊 시장지표 현황</h3><table style="width:100%%; border-collapse:collapse; font-size:14px;"><tr style="background:#f8f9fa;"><th style="padding:6px; text-align:left;">지표</th><th style="padding:6px; text-align:right;">현재값</th><th style="padding:6px; text-align:right;">변동률</th><th style="padding:6px;">상태</th></tr>' + indicator_html + '</table>' if indicator_html else ''}
        {'<h3>🌍 지정학 리스크</h3><p>' + geo_html + '</p>' if geo_html else ''}
        <h3>🏆 TOP 5 뉴스</h3>
        <table style="width:100%%; border-collapse:collapse; font-size:14px;">
          <tr style="background:#f8f9fa;"><th style="padding:8px; width:50px;">점수</th><th style="padding:8px; text-align:left;">뉴스</th><th style="padding:8px; width:80px;">행동</th></tr>
          {top_news_html}
        </table>
        {'<h3>📈 종목 시그널</h3><table style="width:100%%; border-collapse:collapse; font-size:14px;"><tr style="background:#f8f9fa;"><th style="padding:6px;">종목</th><th style="padding:6px;">시그널</th><th style="padding:6px;">점수</th><th style="padding:6px;">행동</th></tr>' + stock_html + '</table>' if stock_html else ''}
        <hr style="margin:20px 0;">
        <p style="color: #666; font-size: 12px;">⚠️ 본 리포트는 자동 생성된 참고 정보입니다. 투자 판단의 최종 책임은 사용자에게 있습니다.<br>NIAS v2.0</p>
      </div>
    </div>
    """
    return subject, html


def build_geopolitical_email(item, assessment=None) -> tuple[str, str]:
    """지정학 알림 이메일 HTML 생성"""
    level = getattr(item, 'geo_level', 0) or 0
    region = getattr(item, 'geo_region', '미확인')
    conflict_type = getattr(item, 'geo_conflict_type', '미분류')
    impact_chain = getattr(item, 'impact_chain', '')
    score = getattr(item, 'impact_score', 0)

    level_colors = {1: "#22c55e", 2: "#eab308", 3: "#f97316", 4: "#ef4444", 5: "#991b1b"}
    level_names = {1: "긴장", 2: "긴장 고조", 3: "무력 시위", 4: "무력 충돌", 5: "전면 위기"}
    level_bar = {1: "■□□□□", 2: "■■□□□", 3: "■■■□□", 4: "■■■■□", 5: "■■■■■"}
    bg_color = level_colors.get(level, "#666")

    channels_html = ""
    if assessment and hasattr(assessment, 'market_channels'):
        for ch in assessment.market_channels:
            channels_html += f"<li>{ch}</li>"

    subject = f"���� [지정학 L{level}] {region} {conflict_type} - {item.title[:40]}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: {bg_color}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0;">🌍 NIAS 지정학 알림</h2>
        <p style="margin:4px 0 0;">{level_bar.get(level, '?')} Level {level} — {level_names.get(level, '미확인')}</p>
      </div>
      <div style="padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px;">
        <h3>{item.title}</h3>
        <table style="width:100%%; border-collapse:collapse; margin:12px 0;">
          <tr><td style="padding:8px; font-weight:bold; width:100px;">지역</td><td style="padding:8px;">{region}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:8px; font-weight:bold;">분쟁 유형</td><td style="padding:8px;">{conflict_type}</td></tr>
          <tr><td style="padding:8px; font-weight:bold;">에스컬레이션</td><td style="padding:8px; color:{bg_color}; font-weight:bold;">Level {level} — {level_names.get(level, '')}</td></tr>
          <tr style="background:#f8f9fa;"><td style="padding:8px; font-weight:bold;">영향도</td><td style="padding:8px;">{score}/10</td></tr>
        </table>
        {'<h4>📊 시장 영향 채널</h4><ul>' + channels_html + '</ul>' if channels_html else ''}
        {f'<h4>🔗 영향 체��</h4><p style="background:#fff3cd; padding:12px; border-radius:6px;">{impact_chain}</p>' if impact_chain else ''}
        <p><strong>소스:</strong> {item.source}</p>
        <hr>
        <p style="color: #666; font-size: 12px;">⚠️ 본 알림은 자동 생성된 참고 정보입니다. 투자 판단의 최종 책임은 사용자에게 있습니다.<br>NIAS v2.0</p>
      </div>
    </div>
    """
    return subject, html
