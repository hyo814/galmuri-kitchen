# 배포 가이드 (Render + 카카오/구글 로그인)

## 1. GitHub에 올리기
1. GitHub에서 **비공개** 저장소 생성
2. `git remote add origin <주소> && git push -u origin main`

## 2. Render 데이터베이스
1. https://dashboard.render.com → New → **PostgreSQL**
2. Region: **Singapore**(한국과 가장 가까움)
3. 생성 후 **Internal Database URL** 복사

## 3. Render 웹 서비스
1. New → **Web Service** → GitHub 저장소 선택
2. Language: **Docker**, Region: DB와 같은 Singapore
3. Environment Variables:
   | 키 | 값 |
   |---|---|
   | `SECRET_KEY` | Generate 버튼으로 생성 |
   | `DATABASE_URL` | 2번에서 복사한 Internal Database URL |
   | `KAKAO_CLIENT_ID` / `KAKAO_CLIENT_SECRET` | 4번에서 발급 |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | 5번에서 발급 |
   `DEV_MODE`는 **절대 넣지 않는다**(넣으면 앱이 시작을 거부함).
4. 배포가 끝나면 주소 확인: `https://<서비스명>.onrender.com` (아래에서 `<도메인>`)

## 4. 카카오 로그인
1. https://developers.kakao.com → 내 애플리케이션 → 애플리케이션 추가
2. 앱 키의 **REST API 키** → `KAKAO_CLIENT_ID`
3. 플랫폼 → Web → 사이트 도메인에 `https://<도메인>` 등록
4. 카카오 로그인 → 활성화 ON → Redirect URI에 `https://<도메인>/auth/callback/kakao` 등록
5. 동의항목 → **닉네임** 설정
6. 보안 → Client Secret 코드 생성, 활성화 → `KAKAO_CLIENT_SECRET`

## 5. 구글 로그인
1. https://console.cloud.google.com → 프로젝트 생성
2. OAuth 동의 화면(외부) 구성
3. 사용자 인증 정보 → OAuth 클라이언트 ID → 웹 애플리케이션
4. 승인된 리디렉션 URI: `https://<도메인>/auth/callback/google`
5. 클라이언트 ID/보안 비밀 → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
6. 동의 화면을 "프로덕션 게시"하기 전까지는 테스트 사용자로 등록한 계정만 로그인 가능

환경변수를 바꾼 뒤에는 Render에서 Manual Deploy → Deploy latest commit.

## 6. 폰에 앱처럼 설치 (갤럭시)
1. Chrome에서 `https://<도메인>` 열기
2. 메뉴(⋮) → **홈 화면에 추가** → 설치
3. 홈 화면 아이콘으로 열면 주소창 없이 앱처럼 실행

## 참고
- Render 무료 웹 서비스는 15분 동안 요청이 없으면 잠들어 첫 접속이 30초가량 느리다.
- Render 무료 PostgreSQL은 생성 30일 후 만료된다. 실제로 쓸 때는 유료 플랜으로 전환한다.
