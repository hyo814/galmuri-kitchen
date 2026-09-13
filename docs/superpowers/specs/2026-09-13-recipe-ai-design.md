# Recipe AI — 설계 문서

작성일: 2026-09-13
상태: 승인됨 (브레인스토밍 3개 섹션 승인)

## 1. 목표

누구나 가입해 쓰는 모바일 우선 웹 서비스.
냉장고 사진/영수증 사진(또는 수기)으로 재료를 등록하고, 구입일은 사용자가 직접 입력한다.
보유 재료로 만들 수 있는 요리를 추천받고(내 레시피 · 공공 DB · AI), 요리하면 재고 차감과 함께 기록을 남긴다.

네이티브 앱은 만들지 않는다. 모바일 브라우저 + `<input type="file" accept="image/*" capture>`로
안드로이드/iOS 카메라를 모두 사용한다.

## 2. 단계 (순서대로 전부 구현, 단계마다 배포 가능한 상태)

| 단계 | 범위 |
|---|---|
| 1. 기반 | 카카오/구글 로그인, 냉장고 재료 수기 CRUD(구입일 필수), 임박 표시 |
| 1b. 보관 위치·필수품·품목별 경고 | 사용자 정의 보관 위치(종류별 오래됨 기준), 필수품 목록과 떨어진 필수품 표시, 품목별 경고 규칙(식약처 참고값 기본 제공), 새 디자인 적용 → 이후 Render 배포 |
| 1c. 주방 도구 | 조리도구·조리기구 목록, 코팅 프라이팬 등 주기 점검 알림 (18절) |
| 2. 스캔 | 냉장고 사진·영수증·온라인 주문완료 캡처 → Claude 비전 → 확인 화면(보관 위치 추정 포함) → 일괄 등록, AI 일일 한도 |
| 3. 레시피 | 내 레시피 CRUD, 식약처 공공 DB 동기화·매칭, AI 레시피 생성, 유튜브·인스타그램 링크 가져오기, 추천 화면, 양념 비율 계산기 (22절) |
| 4. 장보기 | 장보기 목록(살 날짜·쇼핑몰), 부족 재료·떨어진 필수품·임박 재료 담기, 7개 쇼핑몰 검색·정렬(낮은 가격순 등) 링크, 구매 완료 → 냉장고, 오프라인 장보기(메모·사진·AI 목록 변환·인터넷 없이 보기/체크) |
| 4b. 식단·영양 | 1주·1달 식단 달력(셀프 배치·복사/반복), 다이어트 AI 초안, 유튜브 인기 레시피, 식단 → 장보기 자동 생성 (20절), 칼로리·당류 계산기·기초대사량·먹은 것 기록 (21절) |
| 5. 조리 기록 | 사용 재료 차감, 날짜·별점·메모·완성 사진, 기록 목록 |

단계별 상세는 14~23절(2026-09-13 추가 요구사항)이 4~7절보다 우선한다.

## 3. 구조

접근법 A: Flask 단일 앱. Flask가 `/api/*`와 React 빌드 결과(정적 파일)를 같은 오리진에서 서빙한다. CORS 없음.

```
recipe-ai/
  backend/    Flask 3, Flask-SQLAlchemy, Flask-Migrate, Authlib, anthropic, boto3, gunicorn
  frontend/   Vite + React + TypeScript + React Router, 순수 CSS(모바일 우선)
  Dockerfile  멀티스테이지: node로 frontend 빌드 → python 이미지에 복사
  docs/
```

- DB: 로컬/테스트 SQLite, 운영 Render PostgreSQL (SQLAlchemy로 동일 코드)
- 사진: Cloudflare R2(S3 호환, 비공개 버킷, presigned URL). R2 환경변수가 없으면 로컬 `uploads/` 폴더.
- 인증: 소셜 로그인만(카카오, 구글). 비밀번호를 저장하지 않는다.
- AI: Anthropic API, 모델은 `CLAUDE_MODEL` 환경변수(기본 `claude-sonnet-5`). `ANTHROPIC_API_KEY`가 없으면 개발 모드(`DEV_MODE=1`)의 스캔은 종류별 예시 결과(`sample: true`, 한도·기록 없음)를 돌려주고, 운영에서는 503이며 화면에서 `사진으로 추가`를 숨긴다(`/api/me`의 `scan`).

## 4. 데이터 모델

모든 사용자 소유 테이블은 `user_id` FK를 갖고, 모든 조회는 현재 사용자로 한정한다.

- `users`: id, provider(`kakao`|`google`), provider_id, nickname, created_at. UNIQUE(provider, provider_id)
- `ingredients`: id, user_id, name, quantity(float, 기본 1), unit(str, 기본 `개`), purchased_on(date, 필수), expires_on(date, 선택), created_at
- `recipes`: id, user_id, title, ingredients(JSON `[{name, amount}]`), steps(JSON `[str]`), source(`mine`|`public`|`ai`), image_url(선택), created_at
- `public_recipes`: id, rcp_seq(UNIQUE), title, ingredients_text(원문), ingredient_names(JSON, 파싱된 이름 목록), steps(JSON), image_url. 사용자 소유 아님.
- `cook_logs`: id, user_id, recipe_id(선택, SET NULL), title, cooked_on(date), rating(1~5, 선택), memo(선택), photo_key(선택), created_at
- `ai_calls`: id, user_id, kind(`fridge`|`receipt`|`order`|`memo`|`recipe`|`link`), created_at(인덱스)
- `storage_locations`, `staples`, `item_rules`(14절), `shopping_items`(16절), `kitchen_tools`(18절)

### 규칙

- **임박:** `expires_on`이 오늘부터 3일 이내(지난 것 포함)면 `urgent`(빨강).
  `expires_on`이 없고 `purchased_on`이 7일 이상 지났으면 `old`(노랑). 그 외 `ok`.
- **재료 이름 매칭:** 정규화(공백 제거, 소문자, 괄호 내용 제거) 후 한쪽이 다른 쪽을 포함하면 일치.
  `ponytail:` 부분 문자열 매칭 — "파"가 "파프리카"에 매칭되는 오류 가능. 문제되면 동의어 사전 또는 AI 매칭으로 교체.
- **일치율:** (보유한 레시피 재료 수 / 레시피 재료 수). 임박 재료를 쓰면 정렬 가산점(+0.1/개).

## 5. API

모든 응답은 JSON. 오류는 `{"error": "메시지"}` + 적절한 상태 코드.
상태 변경 요청(POST/PUT/PATCH/DELETE)은 `X-Requested-With: fetch` 헤더가 없으면 400(CSRF 방어, SameSite=Lax 쿠키와 함께).

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/auth/login/<provider>` | OAuth 시작 |
| GET | `/auth/callback/<provider>` | OAuth 콜백 → 세션 발급 → `/`로 리다이렉트 |
| POST | `/api/logout` | 세션 삭제 |
| GET | `/api/me` | 현재 사용자 `{id, nickname, scan: "on"\|"sample"\|"off", scan_limit}` (비로그인 401). 개발용 로그인 응답도 같은 모양 |
| GET/POST | `/api/ingredients` | 목록(임박 순, status 포함) / 생성 |
| POST | `/api/ingredients/bulk` | 스캔 확인 후 일괄 생성 `{items:[{name, quantity, unit, purchased_on, expires_on?, location_id?}]}` 1~50개. 하나라도 틀리면 아무것도 만들지 않고 400 `{error: "N번째 재료: …", errors:[{index, error}]}` |
| PATCH/DELETE | `/api/ingredients/<id>` | 수정 / 삭제 |
| POST | `/api/scan?kind=fridge\|receipt\|order` | multipart `image` → `{items:[{name, quantity, unit, location_kind}], purchased_on, sample}` |
| GET/POST | `/api/recipes` | 내 레시피 목록 / 생성 |
| GET/PUT/DELETE | `/api/recipes/<id>` | 상세 / 수정 / 삭제 |
| GET | `/api/public-recipes/<id>` | 공공 레시피 상세 |
| GET | `/api/recommendations` | `{mine:[...], public:[...]}` 일치율 순, 각 항목에 missing 재료 |
| POST | `/api/recommendations/ai` | AI 레시피 3개 생성(저장 안 함) |
| GET/POST | `/api/cook-logs` | 기록 목록 / 생성(multipart: 필드 + 사진 + `usages` JSON) |
| DELETE | `/api/cook-logs/<id>` | 기록 삭제(재고 복원 안 함) |
| GET | `/api/photos/<key>` | 소유자 확인 후 presigned URL로 302(로컬은 파일 전송) |

CLI: `flask sync-public-recipes` — 식약처 COOKRCP01 전체(약 1,100건)를 1,000건 단위로 받아 upsert.

## 6. 화면 흐름

하단 탭(사용자 결정 2026-09-13): **재고 · 레시피 · 장보기 · 식단 · 더보기**. 다섯 탭을 모두 노출하고, 아직 기능이 없는 탭은 앞으로 들어올 기능을 안내하는 `준비 중` 화면을 보여 준다(사용자 결정 2026-09-13). 각 단계에서 진짜 화면으로 교체한다. 첫 탭 제목은 `내 재고`.
더보기: 조리 기록, 주방 도구, 설정(보관 위치·필수품·품목별 경고·내 몸 정보·로그아웃). 레시피 탭에 추천(보유 재료)·내 레시피·링크 가져오기.
화면 전환은 해시 경로(`#/`, `#/more`, `#/tools` …)로 하여 폰 뒤로가기가 동작한다. 비로그인 시 로그인 화면.

1. **로그인**: 카카오/구글 버튼.
2. **냉장고**: 임박 순 목록 + 배지. `+ 직접 추가`(이름, 수량, 단위, 구입일[기본 오늘], 유통기한). 항목 탭 → 수정/삭제.
   `사진으로 추가`(냉장고 사진 · 영수증 · 온라인 주문 캡처, 카메라·갤러리는 폰이 고르게 함) → 브라우저에서 긴 변 1568px JPEG로 축소 → `/api/scan` → 확인 화면(체크, 행을 펼쳐 이름·수량·단위·보관 위치 수정, 구입일 일괄 입력; 영수증·주문은 인식된 날짜로 프리필) → `/api/ingredients/bulk`. 시안 `docs/design/scan-2/`.
3. **추천**: 내 레시피 / 공공 DB 섹션(일치율 순, 부족 재료 표시). `AI에게 물어보기` 버튼 → AI 제안 3개. 카드 → 상세.
4. **레시피 상세**(공통): 재료(보유 여부 표시), 단계. `내 레시피로 저장`(public/ai일 때), `요리했어요`.
5. **레시피 탭**: 내 레시피 목록, 등록/수정/삭제 폼(재료 행 추가, 단계 행 추가).
6. **요리했어요 폼**: 냉장고와 매칭된 재료 목록 + 사용량(기본 전량), 날짜(기본 오늘), 별점, 메모, 사진 → 저장.
7. **기록 탭**: 날짜 역순, 썸네일·제목·별점·메모.

## 7. 핵심 동작

- **스캔**: Claude Messages API에 이미지(base64) + 종류별 프롬프트, 구조화 출력(JSON 스키마)으로
  `{items:[{name, quantity, unit, location_kind}], purchased_on: "YYYY-MM-DD"|null}`. 영수증·주문에서 식재료가 아닌 항목(봉투, 세제 등)은 제외하도록 지시. 서버가 결과를 정리한다(최대 50개, 이름 50자·단위 10자, 수량이 0 이하·숫자 아님 → 1, 미래 구입일·냉장고 사진의 구입일 → null).
- **AI 레시피**: 보유 재료 목록(임박 표시 포함)을 전달, 구조화 출력으로 `[{title, ingredients:[{name, amount}], steps:[str]}]` 3개. 임박 재료 우선 사용 지시.
- **조리 기록 저장**: 한 트랜잭션에서 `usages=[{ingredient_id, amount}]` 각각 소유 확인 → quantity 차감 → 0 이하면 삭제 → cook_log 생성. 사진 업로드 실패 시 전체 롤백.
- **AI 일일 한도**: 요청 전 오늘(서버 기준 Asia/Seoul) 해당 사용자의 `ai_calls` 수를 kind 그룹(scan: fridge+receipt+order+memo / recipe)별로 센다. 서울 하루를 UTC 구간으로 바꿔 created_at으로 센다.
  한도 `AI_DAILY_SCAN_LIMIT`(기본 10), `AI_DAILY_RECIPE_LIMIT`(기본 10) 초과 시 429. AI로 보낸 호출은 성공·실패와 관계없이 센다(실패도 비용이 들어 남용을 막기 위해). 업로드 검증에서 걸린 요청은 세지 않는다. 짧은 연속 호출은 `AI_SCAN_BURST_LIMIT`(기본 3, 60초)로 별도 429.

## 8. 에러 처리

- AI 실패/타임아웃/스키마 불일치 → 502 `{"error": "인식에 실패했어요. 직접 입력해 주세요."}`, 프론트는 수기 입력 폼으로 이동.
- 업로드: `MAX_CONTENT_LENGTH` 10MB(413), 파일 시그니처로 판별해 JPEG·PNG·WEBP 외 415(선언된 Content-Type은 신뢰하지 않는다). 스캔 한도 초과 429, 키 없는 운영 503.
- 남의 리소스 id → 404.
- 입력 검증: name 1~50자, quantity > 0, rating 1~5, 날짜 ISO 형식. 위반 시 400.
- 프론트: fetch 래퍼 하나에서 401 → 로그인 화면, 그 외 오류 → 토스트.

## 9. 보안

- 세션 쿠키: HttpOnly, Secure(운영), SameSite=Lax. `SECRET_KEY` 환경변수 필수.
- OAuth state 검증(Authlib).
- CSRF: 상태 변경 요청에 커스텀 헤더 요구.
- 사진: 비공개 버킷, 소유자 확인 후 만료 5분 presigned URL.
- 비밀값(ANTHROPIC_API_KEY, FOODSAFETY_API_KEY, KAKAO_CLIENT_ID/SECRET, GOOGLE_CLIENT_ID/SECRET, R2_*, DATABASE_URL, SECRET_KEY)은 환경변수. `.env`는 gitignore.

## 10. 테스트

- 백엔드: pytest, SQLite 메모리 DB, 테스트 전용 로그인 헬퍼(세션에 user_id 주입).
  Claude 클라이언트·식약처 HTTP·스토리지는 가짜 객체로 대체.
- 필수 테스트: 임박 판정, 이름 매칭/일치율, 조리 기록 재고 차감(+롤백), AI 일일 한도, 타 사용자 리소스 404, CSRF 헤더 요구, 공공 레시피 파싱.
- 프론트: `tsc --noEmit` + `vite build` 통과. 단계 종료 시 브라우저로 주요 흐름 수동 확인.

## 11. 배포

- Render Web Service(Docker) + Render PostgreSQL + Cloudflare R2.
- 시작 명령: `flask db upgrade && gunicorn -w 2 --threads 4 -k gthread --timeout 120 -b 0.0.0.0:$PORT "app:create_app()"` (gthread 워커는 요청 처리 중에도 계속 heartbeat를 보내므로 gunicorn --timeout이 긴 AI 호출을 끊지 않는다. Claude 호출 타임아웃 45초 × 최대 2회 시도 사이에 SDK가 retry-after(최대 60초)를 기다릴 수 있어 최악의 경우 약 150초까지 걸릴 수 있고, 사용자는 화면에서 취소할 수 있다. 스레드 워커로 동시 요청 처리).
- 단계 1 완료 시 `docs/deploy.md`: OAuth 앱 등록(카카오 개발자, Google Cloud), 식약처 API 키, R2 버킷, Render 환경변수 설정 절차.

## 12. 로컬 개발 & 폰 확인 (추가: 2026-09-13)

- 사용자 기기: 갤럭시 S22 Ultra(Chrome/삼성 인터넷, 뷰포트 약 384px).
- `./dev.sh`: Flask(127.0.0.1:5181) + Vite(0.0.0.0:5180, strictPort, `/api`·`/auth` 프록시) 실행, 폰은 같은 와이파이에서 `http://<맥 IP>:5180`. (2026-09-13 변경: 5173·5000은 다른 프로젝트·AirPlay와 충돌)
- OAuth 리다이렉트 URI에 사설 IP를 등록할 수 없으므로 `DEV_MODE=1`일 때만 `POST /api/dev-login`(개발용 로그인) 활성화.
  `DEV_MODE=1`이면 세션 쿠키 Secure 해제. `RENDER` 환경변수가 있으면 DEV_MODE 켜진 채 시작 거부.
- `GET /api/auth-options` → `{providers: [설정된 provider], dev_login: bool}` (로그인 화면 버튼 표시용).
- PWA manifest + 아이콘 포함. HTTP(LAN)에서는 "홈 화면에 추가"가 바로가기로만 동작하고, 앱 모드(standalone)는 HTTPS 배포 후 동작.

## 13. 범위 밖 (필요해질 때 추가)

- 푸시 알림(임박·떨어진 필수품은 화면 표시만), 가족 공유 냉장고, 이메일/비밀번호 가입, 네이티브 앱, 영양 정보,
  쇼핑몰 주문내역 자동 연동·장바구니 담기(6개 쇼핑몰 모두 공개 API 없음).

## 14. 1b단계: 보관 위치 · 필수품 (추가: 2026-09-13)

### 보관 위치
- `storage_locations`: id, user_id, name(1~20자), kind(`fridge`|`freezer`|`room`), sort_order(int), created_at. UNIQUE(user_id, name).
- 사용자 생성 시(및 기존 사용자 마이그레이션 시) 기본 3개: `냉장실`(fridge), `냉동실`(freezer), `실온`(room).
- `ingredients.location_id`: FK NOT NULL. 기존 재료는 마이그레이션에서 해당 사용자의 `냉장실`로 채운다.
- 사용자는 위치를 추가·이름 변경·삭제(예: 김치냉장고=fridge, 냉장고 문칸=fridge, 찬장=room, 베란다=room).
  재료가 들어 있는 위치 삭제는 400 `{"error": "이 위치에 있는 재료를 먼저 옮겨 주세요."}`. 마지막 1개는 삭제 불가.
- **오래됨 기준(유통기한 없을 때):** fridge 7일, freezer 60일, room 표시 안 함. 유통기한이 있으면 종류와 무관하게 D-3부터 urgent.
- 재료 JSON에 `location_id`, `location_name`, `location_kind` 추가.

### 필수품
- `staples`: id, user_id, name(1~50자), category(최대 10자, 기본 `기타`; 추천값 `조미료`·`야채`·`기타`), created_at. UNIQUE(user_id, name).
- `in_stock`: 사용자의 재료 중 이름 매칭(4절 규칙)되는 것이 하나라도 있으면 true.
- 필수품은 재료를 삭제해도 남는다(떨어짐으로 표시).

### 품목별 경고 규칙
- `item_rules`: id, user_id, keyword(1~20자, 재료 이름 매칭 4절 규칙), warn_days(int ≥1), danger_days(int > warn_days), source(`mfds`|`user`), created_at. UNIQUE(user_id, keyword).
- 기준일은 **구입일**. `today - purchased_on >= warn_days` → `old`(노랑), `>= danger_days` → `danger`(빨강, 문구 `섭취 주의`).
- 기본 규칙(사용자 생성 시 시드, 모두 수정·삭제 가능):
  - 달걀·계란: warn 25 / danger 30 (사용자 결정 2026-09-13; 식약처 권장 산란일 기준 45일·가정 3~5주 권장을 구입일 기준으로 보수화).
  - 식약처 「식품유형별 소비기한 설정 보고서」 참고값(확인됨: 두부 23일, 발효유 32일, 과채주스 35일, 빵류 31일, 어묵 42일, 소시지 56일, 햄 57일):
    키워드 두부 / 요거트·요구르트 / 주스 / 빵 / 어묵 / 소시지 / 햄.
  - 우유: 참고값 없음(우유류 소비기한 표시제는 2031년 적용). 규칙을 두지 않고, 재료 입력 시 이름이 우유면 `포장에 적힌 소비기한을 입력하면 가장 정확해요` 안내.
    참고값은 **제조일 기준**이므로 구입일 기준 danger_days = 참고값의 80%(내림), warn_days = danger_days − 3. **구현 시 공식 문서에서 품목·값을 확인하고 출처를 코드 주석에 남긴다.**
- 판정 우선순위 (사용자 결정 2026-09-13):
  1. 유통기한(expires_on)을 입력했으면 그것만 본다: D-3 이내면 `urgent`, 아니면 `ok`. 품목 규칙은 쓰지 않는다.
  2. 냉동(freezer) 위치면 품목 규칙을 쓰지 않고 60일 기준.
  3. 그 외 매칭되는 품목 규칙이 있으면 규칙(노랑 `old` / 빨강 `danger`).
  4. 없으면 위치 종류 기준(fridge 7일 / room 없음).
- 여러 키워드가 매칭되면 danger_days가 가장 짧은 규칙.
- 화면: 설정 시트의 `품목별 경고` 목록(키워드, 노랑/빨강 일수, 식약처 참고값 표시), 추가·수정·삭제. 빨강 배지 `섭취 주의`, 재료 줄에 `구입 31일째` 보조 문구.

### API
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST | `/api/item-rules` | 목록 / 생성 |
| PATCH/DELETE | `/api/item-rules/<id>` | 수정 / 삭제 |
| GET/POST | `/api/locations` | 목록(sort_order 순, 각 위치 재료 수 포함) / 생성 |
| PATCH/DELETE | `/api/locations/<id>` | 이름·종류 변경 / 삭제(규칙 위) |
| GET/POST | `/api/staples` | 목록(`in_stock` 포함, 떨어진 것 먼저) / 생성 |
| DELETE | `/api/staples/<id>` | 삭제 |

### 화면
- 냉장고 화면 상단: 떨어진 필수품이 있으면 배너 `필수품 N개가 떨어졌어요: 대파, 참기름` → 탭하면 필수품 시트.
- 위치 탭(가로 스크롤 칩): `전체 · 냉장실 · 냉동실 · 실온 · …` + 끝에 `위치 관리`. 전체 탭도 임박 순 정렬.
- 재료 입력 시트에 `보관 위치` 선택(기본: 현재 선택된 탭, 전체 탭이면 첫 fridge 위치).
- 필수품 시트: 분류별 목록(있음/떨어짐 표시), 추가(이름 + 분류), 삭제.
- 위치 관리 시트: 목록, 추가(이름 + 종류), 이름·종류 변경, 삭제.

## 15. 2단계 추가: 온라인 주문 캡처 · 위치 추정
- `/api/scan?kind=fridge|receipt|order`. `order`는 쿠팡·네이버스토어·컬리·이마트·홈플러스·롯데마트·G마켓 주문완료/주문상세 화면 캡처.
- 인식 결과 항목에 `location_kind`(fridge|freezer|room) 추정 포함 → 확인 화면에서 해당 종류의 첫 위치로 프리필, 변경 가능.

## 16. 4단계: 장보기
- `shopping_items`: id, user_id, name, quantity, unit, planned_on(date, 선택), store(`coupang`|`naver`|`kurly`|`emart`|`homeplus`|`lottemart`|`gmarket`|null),
  location_id(선택, 구매 후 넣을 위치), source(`manual`|`recipe`|`staple`|`urgent`|`meal_plan`), done_at(선택), created_at.
- 담기 경로: 직접 추가, 레시피 상세의 부족 재료, 떨어진 필수품 배너, 임박/소진 재료.
- 목록: 살 날짜별 그룹(오늘·이번 주·날짜 미정), 완료 항목은 아래로.
- 쇼핑몰 검색 링크: 항목마다 7개 쇼핑몰(쿠팡·네이버스토어·컬리·이마트·홈플러스·롯데마트·G마켓) 검색 결과로 이동(URL 형식은 구현 시 실제 동작 검증).
- 정렬 링크(추가 2026-09-13): 쇼핑몰마다 `낮은 가격순`·`판매량(많이 산)순`·`신상품순`으로 연 검색 결과 링크. 쇼핑몰별 정렬 URL 파라미터는 구현 시 실제 동작을 검증하고, 지원하지 않는 정렬은 버튼을 숨긴다.
- 구매·결제는 앱에서 하지 않는다(공개 주문 API 없음). 링크로 쇼핑몰 앱/웹의 검색·상품 화면까지 연결하는 것이 범위.
- ~~네이버 최저가~~ (변경 2026-09-13): 네이버 쇼핑 검색 API가 2026-07-31에 종료되고 공식 대체 API가 없어 앱 안 가격 표시는 하지 않는다. 사용자 결정으로 쇼핑몰별 `낮은 가격순` 검색 링크(위 정렬 링크)로 대체한다. 가격 스크래핑은 약관·차단 위험으로 하지 않는다.
- 구매 완료: 체크 시 재료로 등록(구입일 기본 오늘·수정 가능, 위치 선택). 주문 캡처/영수증 스캔 결과로 장보기 항목 일괄 체크.

## 17. 3단계 추가: 링크로 레시피 가져오기
- `POST /api/recipes/import` `{url}` 또는 `{text}` → Claude 구조화 출력 `{title, ingredients:[{name, amount}], steps:[str]}` → 확인 후 저장(`source`: `youtube`|`instagram`|`text`, `source_url`).
- 유튜브: 영상 설명란 + 자막(자동 자막 포함)을 가져와 정리. 데이터센터 IP 차단 등으로 실패하면 설명란만 사용하거나 텍스트 붙여넣기로 안내.
- 인스타그램: 공식적으로 타인 게시물 본문 조회 불가 → 링크 미리보기(og:description) 시도, 부족하면 캡션 붙여넣기 안내. 링크만으로 항상 성공을 약속하지 않는다.
- AI 일일 한도에 `link` 포함(recipe 그룹).

## 18. 1c단계: 주방 도구 (추가: 2026-09-13)
- `kitchen_tools`: id, user_id, name(1~30자), category(`조리도구`|`조리기구`|`칼·도마`|`기타`), bought_on(선택), check_every_months(선택, 1~60),
  last_checked_on(선택), created_at.
- 점검 기준일 = last_checked_on·bought_on 중 늦은 날짜(둘 다 없으면 created_at의 서울 날짜). 기준일 + check_every_months ≤ 오늘이면 `점검할 때가 됐어요`.
- 프리셋(추가 시 이름 매칭으로 제안, 수정 가능): `코팅 프라이팬`·`프라이팬`·`코팅 냄비` → 6개월 점검,
  안내 문구 "코팅이 30% 이상 벗겨졌다면 교체를 권장해요(식약처)". 그 외 도구는 기본 주기 없음(구매일도 선택).
  근거: 식약처는 기간이 아닌 상태 기준(코팅 30% 이상 벗겨짐) 교체 권고. 6개월 교체 근거는 확인되지 않아 '점검' 알림으로 둔다.
- 동작: `점검했어요`(last_checked_on=오늘), `교체했어요`(bought_on=오늘, last_checked_on=오늘), 수정, 삭제.
- 3단계 연결(선택): 레시피에 필요한 도구 표시와 보유 여부.
- API: `GET/POST /api/tools`, `PATCH/DELETE /api/tools/<id>`, `POST /api/tools/<id>/checked`, `POST /api/tools/<id>/replaced`.

## 19. 4단계 추가: 오프라인(매장) 장보기 (추가: 2026-09-13)
- **장보기 메모** `shopping_notes`: id, user_id, body(최대 2000자), planned_on(선택), place(선택, 최대 30자, 예: `이마트 성수점`), created_at, updated_at.
  장보기 화면 상단에 메모 카드. 목록 항목과 별개로 자유롭게 적는다(예: "세일 수요일까지").
- **사진 첨부** `shopping_note_photos`: id, note_id(CASCADE), photo_key, created_at. 메모당 최대 10장. 손메모·전단지·상품 사진.
  카메라 촬영(`<input type="file" accept="image/*" capture="environment">`) 또는 앨범 선택, 브라우저에서 긴 변 1568px로 축소 후 업로드(R2, 3절).
- **사진 → AI 목록 변환**: `/api/scan?kind=memo`(손메모·전단지) → 품목 추출 → 확인 화면 → `shopping_items` 일괄 추가. AI 일일 한도 scan 그룹.
- **인터넷 없이 보기·체크**(마트 지하 등):
  - 서비스 워커로 앱 화면(정적 파일) 캐시, 장보기 목록·메모는 마지막으로 받은 내용을 IndexedDB에 저장해 오프라인에서도 열린다.
  - 오프라인 중 체크·항목 추가·메모 수정·사진 촬영은 기기 대기열에 쌓고, 연결되면 순서대로 서버에 반영.
  - 충돌 규칙: 항목 체크는 `done_at` 타임스탬프 기준 마지막 변경 우선, 메모 본문은 `updated_at` 기준 마지막 저장 우선(덮어쓰기 전 기기 쪽 사본 보관).
  - 화면에 `오프라인 · 연결되면 저장돼요` 표시, 대기 중 건수 표시.
  - 앱 모드(PWA standalone)·서비스 워커는 HTTPS에서만 동작 → 배포 이후 동작 확인.

## 20. 4b단계: 식단 짜기 (추가: 2026-09-13)
- `meal_plans`: id, user_id, name(예: `9월 둘째 주`), start_on, days(7 또는 30 등 1~31), goal(선택: `kcal_per_day` int, `note` ≤100자), created_at.
- `meal_slots`: id, plan_id(CASCADE), date, meal(`breakfast`|`lunch`|`dinner`|`snack`), recipe_id(선택, SET NULL), title(레시피가 없을 때 자유 입력), servings(기본 1), est_kcal(선택, AI 추정).
- **셀프**: 달력(주 보기 기본, 월 보기)에서 칸을 눌러 내 레시피·저장된 링크 레시피·자유 입력으로 채움. 주 단위 복사, N주 반복.
- **다이어트 AI 초안**: 목표(하루 kcal, 단백질 위주 등 메모)와 기간 → Claude가 보유·임박 재료를 우선 써서 끼니별 레시피 초안(구조화 출력, 끼니별 추정 kcal). 확인 화면에서 칸별 수락/교체. kcal은 **AI 추정치**라고 화면에 명시.
  정확한 영양성분(식약처 식품영양성분 DB 연동)은 범위 밖, 필요해지면 추가. AI 일일 한도 recipe 그룹.
- **유튜브 인기 레시피**: YouTube Data API v3 `search.list`(q=`레시피`, regionCode=KR, order=viewCount, publishedAfter=최근 30일, type=video) 결과를 목록으로 보여주고,
  고른 영상은 17절 링크 가져오기로 레시피화해 식단 칸에 넣는다(`YOUTUBE_API_KEY`, 결과 1시간 캐시로 쿼터 절약).
  인스타그램·틱톡은 인기 목록 공개 API가 없어 링크 공유로만 추가(17절).
- **장보기 자동 생성**: 식단 기간의 레시피 재료 합산 → 냉장고 재고와 이름 매칭(4절)해 없는 것만 → `shopping_items`(source `meal_plan`, planned_on=해당 끼니 전날) 미리보기 후 추가.
- 순서: 4단계(장보기) 다음, 5단계(조리 기록) 앞.

## 21. 4b단계 추가: 영양 계산기 (추가: 2026-09-13)
### 음식·식단 영양 합산
- 데이터: 식약처 「식품영양성분 데이터베이스」 공공 API(`FOOD_NUTRITION_API_KEY`). 식품별 100g당 에너지(kcal), 탄수화물, 단백질, 지방, **당류**, 나트륨.
  자주 쓰는 식품은 로컬 테이블 `food_nutrients`(food_code UNIQUE, name, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg, source)에 캐시.
- 재료 → 식품 매칭: 이름 매칭(4절) 후보를 보여주고 사용자가 확정, 확정 결과는 사용자별로 기억(`food_matches`).
- 양 환산: g·kg·ml·L는 그대로 계산. `개·단·모·봉` 등은 식품별 기본 중량 표(구현 시 출처 확인) 또는 AI 추정 → 화면에 `추정` 표시.
- 매칭 실패 식품은 20절 AI 추정치를 쓰고 `추정` 표시.
- 합산 단위: 레시피(1인분), 끼니, 하루, 식단 기간. 표시: kcal, 탄·단·지, 당류, 나트륨.
### 하루 필요 칼로리
- 입력: 성별, 나이, 키(cm), 몸무게(kg), 활동량(거의 없음·가벼움·보통·많음·매우 많음). **식단 탭 맨 위 `내 몸 정보·목표` 카드**에서 입력·수정(설정에서도 진입), 언제든 삭제. (사용자 결정 2026-09-13)
- 기초대사량: Mifflin–St Jeor 식. 필요량 = 기초대사량 × 활동계수. 다이어트 목표 제안 = 필요량 − 500kcal(하한은 구현 시 공인 권고치 확인 후 적용).
- 키·몸무게만으로는 오차가 커서 성별·나이를 필수로 받는다.
- 당류 기준: 식약처 영양성분 표시 당류 1일 기준치와 WHO 권고(총 섭취 에너지 대비 비율) — **구현 시 공식 수치와 출처를 확인해 화면에 출처와 함께 표시**.
- `body_profiles`: user_id(UNIQUE), sex, birth_year, height_cm, weight_kg, activity, updated_at. 건강 정보이므로 본인만 조회, 계정 삭제 시 함께 삭제.
### 먹은 것 기록
- `food_logs`: id, user_id, eaten_on, meal, food_code(선택)/recipe_id(선택)/title, amount_g 또는 servings, kcal·당류 등 계산값 스냅숏, estimated(bool).
- 식품 검색(캐시 → 공공 API) 또는 내 레시피·식단 칸에서 `먹었어요`로 추가.
- 하루 화면: 목표 대비 kcal 막대, 당류·나트륨 기준 대비 표시.
- 의료 조언이 아니라 참고용이라는 문구를 계산기 화면에 표시.

## 22. 3단계 추가: 양념 비율 계산기 (추가: 2026-09-13)
- 레시피 탭 안 `양념 비율` 목록. 불고기·제육볶음·간장조림·초고추장·쌈장·갈비 양념 등 기본 양념을 제공하고 사용자가 추가·수정("내 비율").
- `seasonings`: id, user_id(NULL이면 기본 제공), name, basis(`main_weight`|`servings`|`yield`), basis_amount(예: 100), basis_unit(`g`|`인분`|`컵`|`ml`), main_ingredient(선택, 예: `돼지고기`), source(`default`|`user`), source_note(기본 비율 출처), created_at.
- `seasoning_items`: id, seasoning_id(CASCADE), name, amount(float), unit(`큰술`|`작은술`|`컵`|`ml`|`g`|`개`|`꼬집`), sort_order.
- 기준(사용자 결정, 모두 지원): 주재료 무게당(예: 고기 100g당), 인분(예: 2인분), 완성량(예: 양념장 1컵).
- 계산: 입력량 ÷ basis_amount 배율로 각 재료 양을 늘리고 줄인다.
- **숟가락 단위(사용자 강조):** 기준은 계량스푼(1큰술 15ml, 1작은술 5ml, 1컵 200ml). 결과는 실제로 뜰 수 있는 분수로 반올림해 표시(¼·⅓·½·⅔·¾, 예: `3½큰술`, `⅓작은술`), 큰술이 너무 작으면 작은술로 자동 환산(1큰술 = 3작은술).
  집에서 쓰는 **밥숟가락 환산을 함께 표시**(예: `3큰술 (밥숟가락 약 4개)`) — 밥숟가락 1개 용량 기준치는 구현 시 출처를 확인해 정한다.
- 기본 비율 수치는 레시피마다 차이가 크므로 구현 시 신뢰할 수 있는 출처 여러 곳을 비교해 정하고 `source_note`에 남긴다. "취향에 따라 조절" 안내.
- 연결: 레시피 재료로 가져오기, 없는 양념 재료는 장보기 목록에 담기(4단계).

## 23. 사용성 점검 반영 — 인분·차감·장보기 수량 (추가: 2026-09-13, 사용자 선택)
주부(4인 가족)·1인 가구 페르소나 점검(발견 D1~D5)에서 사용자가 설계 반영을 고른 항목. 이 절이 4·16·20절의 해당 내용보다 우선한다.

- **레시피 기준 인분 (D1, 3단계):** `recipes.servings`(int 1~20, 기본 2) 추가. AI 생성·링크 가져오기는 인분을 추정해 채우고 확인 화면에서 수정.
  공공 레시피는 원문 인분이 있으면 사용, 없으면 2. 식단·장보기·영양 계산은 `필요 인분 / recipes.servings` 배율로 재료 양을 늘리거나 줄인다.
  레시피 상세에 인분 −/+ 조절(화면에서만 배율 적용, 저장하지 않음).
- **식단 기본 인분 (D5, 4b단계):** `meal_plans.default_servings`(int 1~20). 식단을 만들 때 한 번 입력(기본값: 마지막으로 만든 식단의 값, 없으면 1)하고 새 칸의 `servings` 기본값으로 쓴다.
- **요리했어요 차감 기본값 (D2, 5단계):** "전량" 대신 — 레시피 재료 양을 파싱해 재고와 단위가 같으면 `레시피 양 × (요리 인분 / recipes.servings)`,
  단위가 다르거나 파싱할 수 없으면 `1`(재고 단위). 조미료 분류 필수품과 매칭되는 재료는 기본 "차감 안 함"(체크 해제 상태로 표시, 사용자가 켤 수 있음). 차감 결과가 0 이하면 삭제.
- **장보기 체크와 재고 등록 분리 (D3, 4단계):** 매장에서 항목을 체크하면 `done_at`만 기록한다(폼 없음, 오프라인 대기열 대상).
  장보기 화면 상단 `체크한 N개 재고에 넣기` 버튼 → 한 화면에서 일괄 등록: 구입일 하나(기본 오늘), 위치는 항목의 `location_id` → 같은 이름의 최근 재료 위치 → 기본 냉장 위치 순으로 프리필, 항목별 수정 가능.
  16절의 "체크 시 재료로 등록"은 이 방식으로 대체한다.
- **식단 → 장보기 수량 비교 (D4, 4b단계):** 필요량(인분 배율 적용 합계)과 재고를 이름 매칭 후 단위가 같으면 `필요 − 보유`가 0보다 클 때만 그만큼 담는다.
  단위가 다르거나 파싱 불가면 미리보기에 `있음 2개 · 필요 12개`처럼 보여 주고 사용자가 체크해 담는다. 20절의 "없는 것만"은 이 방식으로 대체한다.
- 공통 전제: 이름 매칭 오탐(짧은 이름) 수정은 지금 화면 개선(사용성 개선 단계)에서 `names_match` 한곳에 적용하므로 3·4·4b단계 매칭에도 그대로 쓰인다.
- 나머지 설계 발견(D6~D18)은 사용성 리포트 페이지에서 사용자가 체크하면 이 절에 추가한다.
