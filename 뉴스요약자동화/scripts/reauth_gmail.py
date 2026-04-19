"""Gmail OAuth 재인증 일회성 스크립트

사용: python scripts/reauth_gmail.py
효과: gmail_token.json이 없거나 만료된 경우 브라우저를 띄워 OAuth 재인증.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from notifiers.email_notifier import GmailNotifier  # noqa: E402


def main() -> int:
    print("=== Gmail OAuth 재인증 ===")
    notifier = GmailNotifier()
    print(f"token 경로: {notifier.token_path}")
    print(f"credentials: {notifier.credentials_path}")
    print()
    print("브라우저가 열리지 않으면 콘솔에 URL이 출력됩니다.")
    print("그 URL을 직접 브라우저에 복사해 로그인하세요.")
    print()

    ok = notifier.authenticate()
    if ok:
        print("\n[성공] Gmail 인증 완료 — gmail_token.json 갱신됨")
        return 0
    print("\n[실패] 인증 불가 — 오류 메시지를 확인하세요")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
