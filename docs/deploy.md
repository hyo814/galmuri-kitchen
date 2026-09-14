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
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | 선택(운영에서 사진을 쓰려면 필수) | 장보기 메모 사진. 네 값이 모두 있으면 R2(비공개 버킷, 토큰은 해당 버킷만 "개체 읽기 및 쓰기")에 올리고, 보기는 `/api/photos/<key>`가 소유자 확인 뒤 R2에서 받아 앱 주소로 흘려보낸다(버킷 공개·CORS 필요 없음). 하나라도 비면 운영에서는 사진 올리기·보기 503(`DEV_MODE`가 아니면 로컬 디스크에 두지 않는다 — Render 디스크는 배포 때 지워진다). 로컬 개발은 값 없이 `backend/uploads/`(gitignore). 발급 순서는 `backend/.env.example` | Cloudflare 대시보드 R2 |
| `DEMO_LOGIN` | 선택 | `1`이면 로그인 화면에 `로그인 없이 체험하기`(심사·둘러보기용). 누를 때마다 예시 재고가 든 새 계정을 만들고 24시간 뒤 지운다. 설정은 아래 5-3 | 직접 설정 |
| `DEMO_IP_HOURLY_LIMIT` | 선택 | 같은 IP(IPv6는 /64)에서 1시간에 만들 수 있는 체험 계정 수(기본 30). 한 사무실 주소 뒤 여러 심사위원을 생각한 값 | 직접 설정 |
| `DEMO_IP_DAILY_LIMIT` | 선택 | 같은 IP에서 24시간에 만들 수 있는 체험 계정 수(기본 100) | 직접 설정 |
| `DEMO_AI_GLOBAL_DAILY` | 선택 | 체험 계정 전체의 사진 인식·AI 레시피 호출 24시간 예산(기본 300). 넘으면 체험 계정은 예시 결과로 동작 | 직접 설정 |
| `TRUSTED_PROXY_HOPS` | 선택 | `X-Forwarded-For`를 붙이는 앞단 프록시 수(기본 1, Render). 체험 계정 IP 한도가 이 값으로 접속 주소를 고른다. 확인은 아래 5-3 | 직접 설정 |
| `COUPANG_PARTNERS_ID` | 선택 | 쿠팡 제휴 ID(`/api/me`의 `shop_affiliates`). 없으면 일반 검색 링크. 제휴 링크 형식을 아직 채우지 않아 지금은 넣어도 링크가 바뀌지 않는다 | 쿠팡 파트너스 |
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

## 5-3. 체험하기 계정 (`DEMO_LOGIN=1`)
1. Render 웹 서비스 환경변수에 `DEMO_LOGIN` = `1`을 넣고 다시 배포한다. `DEV_MODE`와 상관없이 운영에서 켤 수 있다. 끄려면 변수를 지운다.
2. 체험 계정은 `provider=demo`, 닉네임 `체험 사용자`로 만들어지고 예시 재고 10개(두부 D-1·대파 D-2 포함)·필수품 3개·레시피 2개·양념 비율 1개가 들어 있다.
3. 막는 장치(`backend/app/demo.py`):
   - 같은 IP(IPv6는 /64 대역)에서 1시간에 `DEMO_IP_HOURLY_LIMIT`(기본 30)개, 24시간에 `DEMO_IP_DAILY_LIMIT`(기본 100)개. 공유 사무실 네트워크처럼 여럿이 주소 하나를 쓰면 한도를 함께 나눠 쓰니 필요하면 늘린다. IP는 저장하지 않고 `SECRET_KEY`에서 뽑은 키로 서명한 해시 앞 16자만 계정 식별값에 붙인다.
   - 체험 계정 전체 5,000개. 가득 차면 거절하지 않고 가장 오래된 체험 계정부터 지우고 새로 만든다(한 번에 50개까지, 그래도 차 있으면 거절).
   - 체험 계정의 메모 사진은 계정당 20MB까지(일반 사용자 200MB).
   - 체험 계정의 사진 인식·AI 레시피(링크 가져오기 포함) 하루 한도는 각각 3번. 체험 계정 전체가 24시간에 `DEMO_AI_GLOBAL_DAILY`(기본 300)번을 쓰면 AI를 부르지 않고 예시 결과를 보여 준다.
   - 영상 칸은 유튜브 할당량을 쓰지 않게 체험 계정에는 늘 예시 목록이다(채널 추가·새로 받기 없음).
4. **지우기 Cron Job:** New → **Cron Job** → 같은 GitHub 저장소, Language **Docker**, Region Singapore
   - Schedule: `0 * * * *` (한 시간마다)
   - Command: `flask --app app purge-demo-users`
   - Environment Variables: 웹 서비스와 같은 `SECRET_KEY`·`DATABASE_URL`·`R2_ACCOUNT_ID`·`R2_ACCESS_KEY_ID`·`R2_SECRET_ACCESS_KEY`·`R2_BUCKET`(Environment Group으로 묶으면 편하다). R2 값이 없으면 체험 계정의 메모 사진 파일이 R2에 남는다(행만 지워짐)
   - 24시간 지난 체험 계정과 그 데이터(재고·레시피 등, `ON DELETE CASCADE`)와 메모 사진 파일(커밋 뒤 R2에서)을 지운다. AI 호출 기록(`ai_calls`)은 원가·체험 예산 계산을 위해 사용자 칸만 비우고 남는다(`SET NULL`). Cron Job이 없어도 체험하기를 누를 때마다 만료 계정을 50개씩 함께 지운다.
5. **IP 한도 확인(배포 후 한 번):** IP 한도는 `X-Forwarded-For`의 뒤에서 `TRUSTED_PROXY_HOPS`(기본 1)번째 값을 접속 주소로 본다.
   - **꾸민 헤더가 통하지 않는지:** 같은 컴퓨터에서 앞쪽 값만 바꿔 `DEMO_IP_HOURLY_LIMIT`+1번(기본 31번) 보낸다. 마지막이 `429`면 정상이다(꾸민 값이 무시되고 같은 주소로 셈). 모두 `200`이면 앞쪽 값을 믿고 있는 것이니 `TRUSTED_PROXY_HOPS`를 줄인다. 확인 뒤 만든 체험 계정은 24시간 뒤 지워진다.
     ```
     for i in $(seq 1 31); do curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<도메인>/api/demo-login \
       -H 'X-Requested-With: fetch' -H "X-Forwarded-For: 9.9.9.$i"; done
     ```
   - **다른 사람이 막히지 않는지:** 위 확인 직후(한 시간 안) 다른 네트워크의 기기(와이파이를 끈 폰 LTE 등)에서 `로그인 없이 체험하기`를 누른다. 들어가지면 정상이다. `체험하기를 너무 많이 눌렀어요`가 나오면 모든 사람이 프록시 주소 하나로 묶인 것이니 `TRUSTED_PROXY_HOPS`를 늘려 다시 배포하고 두 확인을 반복한다.

## 6. 폰에 앱처럼 설치 (갤럭시)
1. Chrome에서 `https://<도메인>` 열기
2. 메뉴(⋮) → **홈 화면에 추가** → 설치
3. 홈 화면 아이콘으로 열면 주소창 없이 앱처럼 실행

### 폰에서 오프라인 확인
서비스 워커는 HTTPS 또는 `localhost`에서만 등록된다(LAN IP로는 안 됨).
1. 로컬: 폰 USB 디버깅 → `adb reverse tcp:5180 tcp:5180` → 폰 크롬 `http://localhost:5180`. 개발 서버는 화면 파일을 미리 받지 않으니, 오프라인 화면까지 보려면 `npm run build` 뒤 Flask가 `dist`를 주는 주소로 연다. 또는 Render 배포 뒤 `https://<도메인>`.
2. 온라인으로 한 번 열어 로그인하고 장보기 목록을 받는다(글꼴도 이때 기기에 보관된다 — 첫 방문 다음 열기부터).
3. 비행기 모드 → 앱을 완전히 닫았다가 다시 연다 → 마지막 사용자로 열리고 목록이 보여야 한다.
4. 체크·추가 후 비행기 모드를 끄면 알아서 저장된다.

## 참고
- Render 무료 웹 서비스는 15분 동안 요청이 없으면 잠들어 첫 접속이 30초가량 느리다.
- Render 무료 PostgreSQL은 생성 30일 후 만료된다. 실제로 쓸 때는 유료 플랜으로 전환한다.
