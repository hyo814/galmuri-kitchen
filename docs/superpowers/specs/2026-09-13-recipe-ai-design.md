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
| 1. 기반 | 카카오/구글 로그인, 냉장고 재료 수기 CRUD(구입일 필수), 임박 표시, Render 배포 |
| 2. 스캔 | 냉장고 사진·영수증 → Claude 비전 → 확인 화면 → 일괄 등록, AI 일일 한도 |
| 3. 레시피 | 내 레시피 CRUD, 식약처 공공 DB 동기화·매칭, AI 레시피 생성, 추천 화면 |
| 4. 조리 기록 | 사용 재료 차감, 날짜·별점·메모·완성 사진, 기록 목록 |

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
- AI: Anthropic API, 모델은 `CLAUDE_MODEL` 환경변수(기본 `claude-sonnet-5`).

## 4. 데이터 모델

모든 사용자 소유 테이블은 `user_id` FK를 갖고, 모든 조회는 현재 사용자로 한정한다.

- `users`: id, provider(`kakao`|`google`), provider_id, nickname, created_at. UNIQUE(provider, provider_id)
- `ingredients`: id, user_id, name, quantity(float, 기본 1), unit(str, 기본 `개`), purchased_on(date, 필수), expires_on(date, 선택), created_at
- `recipes`: id, user_id, title, ingredients(JSON `[{name, amount}]`), steps(JSON `[str]`), source(`mine`|`public`|`ai`), image_url(선택), created_at
- `public_recipes`: id, rcp_seq(UNIQUE), title, ingredients_text(원문), ingredient_names(JSON, 파싱된 이름 목록), steps(JSON), image_url. 사용자 소유 아님.
- `cook_logs`: id, user_id, recipe_id(선택, SET NULL), title, cooked_on(date), rating(1~5, 선택), memo(선택), photo_key(선택), created_at
- `ai_calls`: id, user_id, kind(`fridge`|`receipt`|`recipe`), created_at

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
| GET | `/api/me` | 현재 사용자 (비로그인 401) |
| GET/POST | `/api/ingredients` | 목록(임박 순, status 포함) / 생성 |
| POST | `/api/ingredients/bulk` | 스캔 확인 후 일괄 생성 |
| PATCH/DELETE | `/api/ingredients/<id>` | 수정 / 삭제 |
| POST | `/api/scan?kind=fridge\|receipt` | multipart 이미지 → `{items:[{name, quantity, unit}], purchased_on?}` |
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

하단 탭: 냉장고 · 추천 · 레시피 · 기록. 비로그인 시 로그인 화면.

1. **로그인**: 카카오/구글 버튼.
2. **냉장고**: 임박 순 목록 + 배지. `+ 직접 추가`(이름, 수량, 단위, 구입일[기본 오늘], 유통기한). 항목 탭 → 수정/삭제.
   `📷 냉장고 사진` / `🧾 영수증` → 브라우저에서 긴 변 1568px JPEG로 축소 → `/api/scan` → 확인 화면(체크, 이름·수량·단위 수정, 구입일 일괄 입력; 영수증은 인식된 날짜로 프리필) → `/api/ingredients/bulk`.
3. **추천**: 내 레시피 / 공공 DB 섹션(일치율 순, 부족 재료 표시). `AI에게 물어보기` 버튼 → AI 제안 3개. 카드 → 상세.
4. **레시피 상세**(공통): 재료(보유 여부 표시), 단계. `내 레시피로 저장`(public/ai일 때), `요리했어요`.
5. **레시피 탭**: 내 레시피 목록, 등록/수정/삭제 폼(재료 행 추가, 단계 행 추가).
6. **요리했어요 폼**: 냉장고와 매칭된 재료 목록 + 사용량(기본 전량), 날짜(기본 오늘), 별점, 메모, 사진 → 저장.
7. **기록 탭**: 날짜 역순, 썸네일·제목·별점·메모.

## 7. 핵심 동작

- **스캔**: Claude Messages API에 이미지(base64) + 종류별 프롬프트, 구조화 출력(JSON 스키마)으로
  `{items:[{name, quantity, unit}], purchased_on: "YYYY-MM-DD"|null}`. 영수증에서 식재료가 아닌 항목(봉투, 세제 등)은 제외하도록 지시.
- **AI 레시피**: 보유 재료 목록(임박 표시 포함)을 전달, 구조화 출력으로 `[{title, ingredients:[{name, amount}], steps:[str]}]` 3개. 임박 재료 우선 사용 지시.
- **조리 기록 저장**: 한 트랜잭션에서 `usages=[{ingredient_id, amount}]` 각각 소유 확인 → quantity 차감 → 0 이하면 삭제 → cook_log 생성. 사진 업로드 실패 시 전체 롤백.
- **AI 일일 한도**: 요청 전 오늘(서버 기준 Asia/Seoul) 해당 사용자의 `ai_calls` 수를 kind 그룹(scan: fridge+receipt / recipe)별로 센다.
  한도 `AI_DAILY_SCAN_LIMIT`(기본 10), `AI_DAILY_RECIPE_LIMIT`(기본 10) 초과 시 429. 호출 성공 시에만 기록.

## 8. 에러 처리

- AI 실패/타임아웃/스키마 불일치 → 502 `{"error": "인식에 실패했어요. 직접 입력해 주세요."}`, 프론트는 수기 입력 폼으로 이동.
- 업로드: `MAX_CONTENT_LENGTH` 10MB(413), `image/*` 외 415.
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
- 시작 명령: `flask db upgrade && gunicorn -w 2 -b 0.0.0.0:$PORT "app:create_app()"`.
- 단계 1 완료 시 `docs/deploy.md`: OAuth 앱 등록(카카오 개발자, Google Cloud), 식약처 API 키, R2 버킷, Render 환경변수 설정 절차.

## 12. 범위 밖 (필요해질 때 추가)

- 푸시 알림(임박은 화면 표시만), 가족 공유 냉장고, 이메일/비밀번호 가입, 네이티브 앱, 영양 정보, 장보기 목록.
