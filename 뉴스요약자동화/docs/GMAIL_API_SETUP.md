# Gmail API OAuth2 설정 가이드

> Task 1.1 작업 가이드. 아래 6단계를 순서대로 진행하세요.

---

## Step 1: Google Cloud Console 프로젝트 생성

1. https://console.cloud.google.com/ 접속
2. 상단 프로젝트 선택 드롭다운 → **"새 프로젝트"** 클릭
3. 프로젝트 이름: `NIAS` (또는 원하는 이름)
4. **"만들기"** 클릭
5. 생성된 프로젝트가 선택되었는지 확인 (상단 드롭다운)

---

## Step 2: Gmail API 활성화

1. 좌측 메뉴 → **APIs & Services** → **Library**
2. 검색창에 `Gmail API` 입력
3. **Gmail API** 클릭 → **"사용"(Enable)** 버튼 클릭
4. "API가 사용 설정됨" 메시지 확인

---

## Step 3: OAuth 동의 화면 구성

1. 좌측 메뉴 → **APIs & Services** → **OAuth consent screen**
2. User Type: **External** 선택 → **"만들기"**
3. 앱 정보 입력:
   - 앱 이름: `NIAS`
   - 사용자 지원 이메일: 본인 이메일
   - 개발자 연락처 이메일: 본인 이메일
4. **"저장 후 계속"** 클릭
5. 범위(Scopes) 페이지 → **"저장 후 계속"** (기본값 유지)
6. 테스트 사용자 페이지 → **"+ ADD USERS"** → 본인 Gmail 주소 추가 → **"저장 후 계속"**
7. 요약 페이지 → **"대시보드로 돌아가기"**

> **중요:** "게시 상태"가 **"테스트 중"**으로 표시되어야 합니다.
> 테스트 모드에서는 "테스트 사용자"로 등록된 계정만 OAuth 인증이 가능합니다.

---

## Step 4: OAuth 2.0 클라이언트 ID 생성

1. 좌측 메뉴 → **APIs & Services** → **Credentials**
2. 상단 **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. 애플리케이션 유형: **데스크톱 앱 (Desktop app)**
4. 이름: `NIAS Desktop Client`
5. **"만들기"** 클릭
6. 팝업에서 **"JSON 다운로드"** 클릭
7. 다운로드된 파일명을 **`credentials.json`** 으로 변경

---

## Step 5: credentials.json 배치

다운로드한 `credentials.json` 파일을 프로젝트의 `src/` 폴더에 복사:

```
뉴스요약자동화/
└── src/
    └── credentials.json    ← 여기에 배치
```

> **보안 경고:** credentials.json은 절대 git에 커밋하지 마세요.
> `.gitignore`에 이미 등록되어 있습니다.

---

## Step 6: 최초 인증 테스트

아래 명령을 실행하면 브라우저가 열리면서 Google 로그인을 요청합니다:

```bash
cd 뉴스요약자동화
python -c "
import sys; sys.path.insert(0, 'src')
from notifiers.email_notifier import GmailNotifier
notifier = GmailNotifier()
result = notifier.authenticate()
print('인증 성공!' if result else '인증 실패')
"
```

1. 브라우저에서 Google 계정 로그인
2. "이 앱은 Google에서 확인하지 않았습니다" → **"계속"** 클릭
3. Gmail 전송 권한 허용 → **"계속"**
4. 인증 성공 시 `data/gmail_token.json`이 자동 생성됨
5. 이후 실행부터는 브라우저 인증 없이 자동으로 토큰 갱신

---

## 인증 후 테스트 이메일 발송

```bash
cd 뉴스요약자동화
python -c "
import sys; sys.path.insert(0, 'src')
from notifiers.email_notifier import GmailNotifier
notifier = GmailNotifier()
result = notifier.send(
    to='본인이메일@gmail.com',
    subject='[NIAS] Gmail API 테스트',
    html_body='<h2>NIAS v2.0</h2><p>Gmail API 연동 테스트 성공!</p>'
)
print(f'발송 결과: {result}')
"
```

---

## 트러블슈팅

| 문제 | 해결 |
|------|------|
| "Access blocked: This app's request is invalid" | OAuth 동의 화면에서 테스트 사용자로 본인 이메일 추가 |
| "credentials.json not found" | Step 5에서 파일을 src/ 폴더에 복사했는지 확인 |
| "Token has been expired or revoked" | data/gmail_token.json 삭제 후 재인증 |
| "Insufficient Permission" | Gmail API가 활성화되었는지 확인 (Step 2) |
| SMTP fallback 사용 시 | Gmail 설정 → 보안 → 앱 비밀번호 생성 → .env에 GMAIL_APP_PASSWORD 설정 |
