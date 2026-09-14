# 배포 가이드 (Render + 카카오/네이버/구글 로그인)

## 0. 로컬 개발

- `./dev.sh` 실행: Flask는 `127.0.0.1:5181`, Vite는 `0.0.0.0:5180`(폰은 같은 와이파이에서 `http://<맥 IP>:5180`).
- 백엔드 의존성: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
  (테스트 없이 앱만 돌릴 때는 `requirements.txt`만 설치해도 된다).

## 배포 전 로컬 검증

배포하기 전에 아래를 순서대로 실행해 문제를 미리 잡는다. Postgres는
`brew install postgresql@17`, 컨테이너 실행은 `brew install colima docker`로 준비한다.

1. **SQLite 테스트 스위트**
   ```
   backend/.venv/bin/pytest -q -W error::DeprecationWarning
   ```
2. **Postgres 테스트 스위트** (실제 배포 DB와 같은 엔진으로 재검증)
   ```
   brew services start postgresql@17
   createdb recipe_ai_test
   createdb recipe_ai_migrate
   TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test \
   TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate \
   backend/.venv/bin/pytest -q -W error::DeprecationWarning
   ```
3. **마이그레이션 점검**
   ```
   DATABASE_URL=postgresql://localhost/recipe_ai_migrate DEV_MODE=1 SECRET_KEY=x \
   backend/.venv/bin/flask --app app db upgrade
   DATABASE_URL=postgresql://localhost/recipe_ai_migrate DEV_MODE=1 SECRET_KEY=x \
   backend/.venv/bin/flask --app app db check
   ```
4. **Docker 이미지 빌드 + 스모크 테스트** (Render가 쓰는 것과 같은 이미지)
   ```
   colima start
   docker build -t recipe-ai:local .
   createdb recipe_ai_docker
   docker run -d --name recipe-ai-smoke -p 18000:8000 \
     --add-host=host.docker.internal:host-gateway \
     -e DATABASE_URL=postgresql://$(whoami)@host.docker.internal:5432/recipe_ai_docker \
     -e SECRET_KEY=local-docker-check -e PORT=8000 \
     recipe-ai:local
   curl -s http://localhost:18000/                     # <title>갈무리부엌</title> 포함
   curl -s -o /dev/null -w '%{http_code}\n' http://localhost:18000/api/me            # 401
   curl -s -o /dev/null -w '%{http_code}\n' http://localhost:18000/manifest.webmanifest  # 200
   docker logs recipe-ai-smoke   # 마이그레이션 로그 + gunicorn access log 확인
   docker stop recipe-ai-smoke && docker rm recipe-ai-smoke
   ```
   colima의 Lima VM은 `host.docker.internal`을 macOS 호스트로 자동 연결해 주므로,
   이 로컬 검증에는 `pg_hba.conf`/`listen_addresses` 변경이 필요 없었다(맥 로컬
   Postgres에 이미 있는 `127.0.0.1` trust 규칙으로 충분). 만약 환경에 따라 컨테이너가
   호스트 Postgres에 연결하지 못하면 `postgresql.conf`의 `listen_addresses`를 `*`로,
   `pg_hba.conf`에 컨테이너 네트워크 대역(`host` 레코드)을 로컬 전용으로 추가한다.

## 환경 변수

| 변수 | 필수/선택 | 사용 단계 | 발급처 |
|---|---|---|---|
| `SECRET_KEY` | 필수 | 항상(세션 서명) | 직접 생성(긴 랜덤 문자열) |
| `DATABASE_URL` | 필수(운영) | 항상 | Render PostgreSQL Internal Database URL |
| `KAKAO_CLIENT_ID` / `KAKAO_CLIENT_SECRET` | 선택 | 로그인 | 카카오 개발자 콘솔 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 선택 | 로그인 | 네이버 개발자센터 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | 선택 | 로그인 | Google Cloud Console |
| `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` | 선택 | 2단계 사진으로 추가, 3단계 AI 레시피(없으면 개발 모드는 예시 결과, 운영은 버튼 숨김) | console.anthropic.com |
| `AI_DAILY_SCAN_LIMIT` / `AI_DAILY_RECIPE_LIMIT` | 선택 | 사진 인식 / AI 레시피 하루 한도(기본 10, 서울 날짜) | 직접 설정 |
| `AI_SCAN_BURST_LIMIT` | 선택 | 사진 인식·AI 레시피 짧은 연속 호출 한도(기본 3, 60초) | 직접 설정 |
| `FOODSAFETY_API_KEY` | 선택 | 3단계 레시피 추천. 배포 후 한 번 `flask sync-public-recipes`(없으면 `flask seed-sample-recipes` 예시 레시피) | 식약처 공공데이터포털(COOKRCP01) |
| `FOOD_NUTRITION_API_KEY` | 선택 | 영양 계산기 구현 후 | 식약처 공공데이터포털(식품영양성분 DB) |
| `YOUTUBE_API_KEY` | 선택 | 3단계 요리 채널 영상·유튜브 링크 가져오기(없으면 개발 모드는 예시 영상, 운영은 영상 칸 숨김). 설정은 아래 5-2 | Google Cloud Console(YouTube Data API v3) |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | 선택 | 사진 업로드 구현 후 | Cloudflare 대시보드 R2 |
| `DEV_MODE` | 로컬 전용 | 로컬 개발 | 운영(Render)에는 **넣지 않는다** |

키가 비어 있으면 개발 모드에서는 샘플 데이터로 동작(각 기능 구현 시 적용), 운영에서는 해당 기능을 숨긴다.

## 배포 전 체크리스트

- [ ] `DEV_MODE` 환경변수가 없다 (있으면 Render에서 시작 거부). 이 거부 장치는 `RENDER` 환경변수를 기준으로 동작하므로, Render가 아닌 다른 호스팅에 올릴 때는 `DEV_MODE`를 직접 비워 둬야 한다.
- [ ] `SECRET_KEY`를 새로 생성해 넣었다(로컬 값 재사용 금지).
- [ ] 카카오/네이버/구글 OAuth 리다이렉트 URI가 실제 배포 도메인으로 등록돼 있다.
- [ ] `flask db upgrade` 후 `flask db check`가 깨끗하다(Postgres 대상).

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
   | `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 5-1번에서 발급 |
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

## 5-1. 네이버 로그인
1. https://developers.naver.com → Application → 애플리케이션 등록
2. 사용 API: **네이버 로그인**, 제공 정보: **별명** 선택
3. 로그인 오픈 API 서비스 환경 → PC 웹 → 서비스 URL `https://<도메인>`, Callback URL `https://<도메인>/auth/callback/naver`
4. Client ID / Client Secret → `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`
5. 등록 직후는 "개발 중" 상태라 멤버관리에 넣은 테스트 계정만 로그인 가능. 누구나 쓰게 하려면 **검수 요청** 후 승인받기
6. 한 번 발급한 네이버 앱(Client ID)은 바꾸지 않는다. 네이버 사용자 id는 앱마다 달라서, 바꾸면 기존 회원이 새 계정으로 생긴다.

환경변수를 바꾼 뒤에는 Render에서 Manual Deploy → Deploy latest commit.

## 5-2. 유튜브 영상 (요리 채널)
1. https://console.cloud.google.com → 프로젝트 선택 → API 및 서비스 → 라이브러리 → **YouTube Data API v3** 사용 설정
2. 사용자 인증 정보 → 사용자 인증 정보 만들기 → **API 키**
3. 키 수정 → API 제한사항 → **키 제한 → YouTube Data API v3만** 선택(다른 API에 쓰이지 않게)
4. Render 환경변수 `YOUTUBE_API_KEY`에 넣고 다시 배포
5. 기본 채널이 확정되면 `backend/app/data/default_channels.json`에 `[{"channel_id": "UC…", "name": "메모용 이름"}]` 모양으로 적고 배포한 뒤 Render Shell에서 `flask seed-default-channels`(목록에서 뺀 채널은 기본 채널에서 꺼진다). **지금 파일은 사용자 확정 전이라 빈 목록(`[]`)이다.**
6. 사용량: 무료 한도 하루 10,000 units. 채널 하나 새로 받기 3 units(channels·playlistItems·videos 각 1), 채널당 6시간마다·요청당 3채널까지, 채널 추가 3 units, 유튜브 링크 가져오기 1 unit. 앱이 사용자별 하루 새로 받기 20번·채널 추가 30번, 전체 24시간 추정 8,000 units로 막는다(`backend/app/videos.py`의 `DAILY_UNIT_BUDGET`). 전체 검색(search.list, 100 units)은 쓰지 않는다.

## 6. 폰에 앱처럼 설치 (갤럭시)
1. Chrome에서 `https://<도메인>` 열기
2. 메뉴(⋮) → **홈 화면에 추가** → 설치
3. 홈 화면 아이콘으로 열면 주소창 없이 앱처럼 실행

## 참고
- Render 무료 웹 서비스는 15분 동안 요청이 없으면 잠들어 첫 접속이 30초가량 느리다.
- Render 무료 PostgreSQL은 생성 30일 후 만료된다. 실제로 쓸 때는 유료 플랜으로 전환한다.
