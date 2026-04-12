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

    subject = f"🚨 [{score}점] {title[:55]}"
    html = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', Arial, sans-serif; max-width: 620px; margin: 0 auto; background: #fff;">
      <div style="background: #dc3545; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0; font-size:20px;">🚨 NIAS 긴급 속보 알림</h2>
        <p style="margin:6px 0 0; opacity:0.9; font-size:13px;">알림 시각: {now} | 영향도: {'★' * int(score/2)}{'☆' * (5-int(score/2))} ({score}/10)</p>
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


def build_indicator_email(indicator) -> tuple[str, str]:
    """시장지표 알림 이메일 HTML (풍부한 정보 + 시간)"""
    from datetime import datetime

    level_emoji = indicator.level_emoji
    level_name = indicator.threshold_level.value
    now = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    ts = _format_time(getattr(indicator, "timestamp", None))

    subject = f"{level_emoji} [{indicator.name}] {indicator.current_value} ({indicator.change_pct:+.1f}%)"
    html = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', Arial, sans-serif; max-width: 620px; margin: 0 auto;">
      <div style="background: #fd7e14; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0; font-size:20px;">{level_emoji} NIAS 시장지표 알림</h2>
        <p style="margin:6px 0 0; opacity:0.9; font-size:13px;">알림 시각: {now}</p>
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
