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
| 1. 기반 | 카카오/네이버/구글 로그인, 냉장고 재료 수기 CRUD(구입일 필수), 임박 표시 |
| 1b. 보관 위치·필수품·품목별 경고 | 사용자 정의 보관 위치(종류별 오래됨 기준), 필수품 목록과 떨어진 필수품 표시, 품목별 경고 규칙(식약처 참고값 기본 제공), 새 디자인 적용 → 이후 Render 배포 |
| 1c. 주방 도구 | 조리도구·조리기구 목록, 코팅 프라이팬 등 주기 점검 알림 (18절) |
| 2. 스캔 | 냉장고 사진·영수증·온라인 주문완료 캡처 → Claude 비전 → 확인 화면(보관 위치 추정 포함) → 일괄 등록, AI 일일 한도 |
| 3. 레시피 | 내 레시피 CRUD, 식약처 공공 DB 동기화·매칭, AI 레시피 생성, 유튜브·인스타그램 링크 가져오기, 추천 화면, 양념 비율 계산기 (22절) |
| 4. 장보기 | 장보기 목록(살 날짜·쇼핑몰), 부족 재료·떨어진 필수품·임박 재료 담기, 7개 쇼핑몰 검색·정렬(낮은 가격순 등) 링크, 구매 완료 → 냉장고, 오프라인 장보기(메모·사진·AI 목록 변환·인터넷 없이 보기/체크) |
| 4b. 식단·영양 | 1주·1달 식단 달력(셀프 배치·복사/반복), 다이어트 AI 초안, 유튜브 인기 레시피, 식단 → 장보기 자동 생성 (20절), 칼로리·당류 계산기·기초대사량·먹은 것 기록 (21절), 먹은 기록 달력 (24절) |
| 5. 조리 기록 | 사용 재료 차감, 날짜·별점·메모·완성 사진, 기록 목록, 먹은 기록 달력에 요리 기록 합쳐 보이기 (24절) |

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
- 사진: Cloudflare R2(S3 호환, 비공개 버킷, boto3). 보기는 서버가 R2에서 받아 흘려보낸다(2026-09-14 연결, presigned 302는 대역폭이 문제될 때). R2 환경변수가 없으면 개발(`DEV_MODE`)에서만 로컬 `uploads/` 폴더. `DEV_MODE`가 아니면(운영) R2가 없을 때 로컬에 두지 않고 사진 올리기를 503 `사진을 지금은 올릴 수 없어요.`로 막는다(Render 디스크는 배포 때 지워짐) (2026-09-14, 4단계 시안 승인). 사진이 앱 주소로 오므로 오프라인 보관에 R2 버킷 CORS는 필요 없다(19절).
- 인증: 소셜 로그인만(카카오, 네이버, 구글 — 네이버는 2026-09-13 사용자 결정으로 추가). 비밀번호를 저장하지 않는다.
- AI: Anthropic API, 모델은 `CLAUDE_MODEL` 환경변수(기본 `claude-sonnet-5`). `ANTHROPIC_API_KEY`가 없으면 개발 모드(`DEV_MODE=1`)의 스캔은 종류별 예시 결과(`sample: true`, 한도·기록 없음)를 돌려주고, 운영에서는 503이며 화면에서 `사진으로 추가`를 숨긴다(`/api/me`의 `scan`).

## 4. 데이터 모델

모든 사용자 소유 테이블은 `user_id` FK를 갖고, 모든 조회는 현재 사용자로 한정한다.

- `users`: id, provider(`kakao`|`google`), provider_id, nickname, created_at. UNIQUE(provider, provider_id)
- `ingredients`: id, user_id, name, quantity(float, 기본 1), unit(str, 기본 `개`), purchased_on(date, 필수), expires_on(date, 선택), price(원, 선택), created_at
- `recipes`: id, user_id, title(1~60자), servings(1~20, 기본 2), ingredients(JSON `[{name, amount}]` 1~50개), steps(JSON `[str]` 0~30개), source(`mine`|`public`|`ai`|`youtube`|`instagram`|`blog`|`text`|`photo`), source_url(선택), public_recipe_id(선택, SET NULL), image_url(선택, AI 레시피는 비슷한 공공 레시피 사진 17절), created_at, updated_at. UNIQUE(user_id, public_recipe_id)
- `public_recipes`: id, rcp_seq(UNIQUE), title, category(RCP_PAT2), method(RCP_WAY2), kcal(INFO_ENG), servings(원문 `N인분`, 없으면 2), ingredients_text(원문), ingredients(JSON `[{name, amount}]`, 파싱), ingredient_keys(JSON, ingredients와 같은 순서의 매칭용 이름), steps(JSON), image_url, is_sample(키 없을 때 넣는 예시 레시피), updated_at. 사용자 소유 아님.
- `cook_logs`: id, user_id, recipe_id(선택, SET NULL), title, cooked_on(date), rating(1~5, 선택), memo(선택), photo_key(선택), created_at
- `ai_calls`: id, user_id, kind(`fridge`|`receipt`|`order`|`memo`|`recipe`|`link`|`recipe_photo`|`meal`|`link_fetch`|`channel_add`|`video_refresh`|`export`), model, input_tokens, output_tokens, created_at(인덱스). 토큰은 원가 계산용(25절)이다. model은 성공하면 실제로 답한 모델, 실패하면 요청한 모델이다. AI 호출이 AiError로 끝나면(오류·타임아웃·거절·max_tokens·스키마 불일치) 토큰은 비워 둔다. 새 AI 기능도 같은 방식으로 남긴다. `link_fetch`(링크 가져오기 외부 요청)·`channel_add`(채널 추가)·`video_refresh`(영상 새로 받기)·`export`(데이터 내보내기 27절)는 AI를 부르지 않는 한도용 기록이라 model이 NULL이고 토큰이 없다(17절). **원가·사용량 집계는 model IS NOT NULL(또는 scan·recipe·link·recipe_photo·meal kind)만 센다.**
- `ingredient_removals`: id, user_id(CASCADE, 인덱스), name(지운 재료 이름 복사, ≤50자), reason(`eaten`|`discarded`), created_at. INDEX(user_id, created_at). 재료를 이유를 골라 지울 때만 남긴다(27절)
- `storage_locations`, `staples`, `item_rules`(14절), `shopping_items`(16절), `kitchen_tools`(18절)

### 규칙

- **임박:** `expires_on`이 오늘부터 3일 이내(지난 것 포함)면 `urgent`(빨강).
  `expires_on`이 없고 `purchased_on`이 7일 이상 지났으면 `old`(노랑). 그 외 `ok`.
- **재료 이름 매칭:** 정규화(공백 제거, 소문자, 괄호 내용 제거) 후 한쪽이 다른 쪽을 포함하면 일치.
  `ponytail:` 부분 문자열 매칭 — "파"가 "파프리카"에 매칭되는 오류 가능. 문제되면 동의어 사전 또는 AI 매칭으로 교체.
- **일치율:** (보유한 레시피 재료 수 / 레시피 재료 수). 임박 재료를 쓰면 정렬 가산점(+0.1/개). `물`은 늘 있는 것으로 센다. 재고와 겹치는 재료가 없는 레시피는 추천하지 않는다.

## 5. API

모든 응답은 JSON. 오류는 `{"error": "메시지"}` + 적절한 상태 코드.
상태 변경 요청(POST/PUT/PATCH/DELETE)은 `X-Requested-With: fetch` 헤더가 없으면 400(CSRF 방어, SameSite=Lax 쿠키와 함께).

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/auth/login/<provider>` | OAuth 시작 |
| GET | `/auth/callback/<provider>` | OAuth 콜백 → 세션 발급 → `/`로 리다이렉트 |
| POST | `/api/logout` | 세션 삭제 |
| GET | `/api/me` | 현재 사용자 `{id, nickname, scan: "on"\|"sample"\|"off", scan_limit, recipe_limit, videos: "on"\|"sample"\|"off"}` (비로그인 401). `scan`은 사진으로 추가·AI 레시피 입구 표시에 함께 쓴다. `videos`는 영상 칸 표시용(17절). `recipe_limit`은 호환용으로 남겨 두고, 화면의 남은 횟수는 `/api/ai-usage`를 읽는다. 개발용 로그인 응답도 같은 모양 |
| GET/POST | `/api/ingredients` | 목록(임박 순, status 포함) / 생성 |
| POST | `/api/ingredients/bulk` | 스캔 확인 후 일괄 생성 `{items:[{name, quantity, unit, purchased_on, expires_on?, price?, location_id?}]}` 1~50개. 하나라도 틀리면 아무것도 만들지 않고 400 `{error: "N번째 재료: …", errors:[{index, error}]}` |
| PATCH/DELETE | `/api/ingredients/<id>` | 수정 / 삭제. 삭제는 `?reason=eaten\|discarded`(선택)를 주면 같은 커밋에 `ingredient_removals` 행을 남긴다. 없거나 비면 기록 없이 지우고, 다른 값이면 400 `잘못된 요청이에요.`(지우지 않음) (27절) |
| POST | `/api/scan?kind=fridge\|receipt\|order\|memo` | multipart `image` → `{items:[{name, quantity, unit, location_kind, price}], purchased_on, sample}` (fridge·memo는 price·purchased_on 항상 null, memo는 장보기 메모 사진·전단지) |
| GET/POST | `/api/recipes` | 목록(생성일 아님, `updated_at`·id 내림차순 커서 페이지 25절) / 생성. 목록 `?limit=1~50(기본 30)&cursor=` → `{items:[...], next_cursor}`. 생성 body의 `source`는 `mine`(기본)·`ai`·`youtube`·`instagram`·`blog`·`text`만 받고(`public`은 저장 API로만), `image_url`은 식약처 https 사진 주소만 받는다(AI 레시피 저장용) (2026-09-14, 시안 승인) |
| GET/PUT/DELETE | `/api/recipes/<id>` | 상세 / 수정 / 삭제. 상세의 `ingredients`는 `[{name, amount, have, matched_name}]`(현재 재고 기준) |
| GET | `/api/public-recipes/<id>` | 공공 레시피 상세(같은 `ingredients` 모양) |
| POST | `/api/public-recipes/<id>/save` | 내 레시피로 복사(source `public`) 201. 이미 저장했으면 그 레시피 200 |
| GET | `/api/recommendations?section=all\|public&offset=0&limit=20` | 점수 순(25절: `section=all` 기본은 내 레시피 상위 10개 + 공공 레시피 한 페이지, `section=public`은 공공 레시피만). `{mine:[...10개], mine_total, public:[...], public_total, next_offset, sample, inventory_count}`(`section=public`이면 `mine`·`mine_total` 없음). 카드 항목: kind, id, title, image_url, servings, match_rate, have_count, total_count, missing(최대 5, 화면 표시용 이름), urgent_used, urgent_names, score(= match_rate + 0.1 × urgent_used) |
| POST | `/api/recommendations/ai` | AI 레시피 3개 생성(저장 안 함). 하루 한도는 `AI_DAILY_RECIPE_LIMIT`, 짧은 연속 호출은 사진 인식과 같은 `AI_SCAN_BURST_LIMIT`(60초)로 막는다. `{recipes:[{title, servings, minutes, ingredients:[{name, amount, have, matched_name}], steps, urgent_names, image_url}], urgent_first, sample}`. 저장은 화면이 `POST /api/recipes`(source `ai`, image_url)로 한다 (2026-09-14, 시안 승인) |
| POST | `/api/recipes/import` | 링크·글(JSON) 또는 사진 1~3장(multipart `image`) → 레시피 초안(저장 안 함, 17절). 저장은 확인 화면에서 `POST /api/recipes` |
| GET | `/api/recipes/choices?q=` | 식단 칸 채우기 시트의 `내 레시피` 목록(20절). 최근 200개 후보를 재고 일치 점수 순으로 최대 50개 `{items:[{id, title, servings, have_count, total_count, urgent_names}]}` |
| GET/POST | `/api/meal-plans` | 목록(`start_on`·id 내림차순, 50개 상한, 페이지 없음) `{items:[plan_summary…], default_servings}` / 만들기 201(20절) |
| GET/PATCH/DELETE | `/api/meal-plans/<id>` | 상세(`plan_summary` + `goal_kcal`·`goal_note`·`slots`) / 보낸 칸만 고치기(기간이 줄면 밖의 칸은 같은 커밋에서 삭제) / 삭제(칸은 CASCADE) |
| PUT | `/api/meal-plans/<id>/slots` | 칸 채우기·바꾸기(`{date, meal, recipe_id?, title?, servings?}` → 200, 없던 칸이면 만들고 있으면 덮어씀) |
| POST | `/api/meal-plans/<id>/copy-week` | 이번 주 복사(`{from_on, weeks}` → 200 `{plan: plan_json, copied, kept}`, 20절) |
| POST | `/api/meal-plans/<id>/ai-draft` | AI 식단 초안(`{start_on, days 1~7, meals, goal_kcal?, goal_note?}` → 200 `{dishes, slots:[{date, meal, options}], kept, sample}`). 칸은 저장 안 함(목표 두 칸만 저장). AI 레시피 하루 한도 공유(`ai_calls.kind = meal`, 20절) |
| POST | `/api/meal-plans/<id>/ai-draft/apply` | 초안 넣기(`{dishes 1~30, slots:[{date, meal, dish, est_kcal?}] 1~28}` → 201 `{filled, kept, created_recipes}`). 아직 빈 칸만 채우고 새 요리는 요리마다 한 번 내 레시피(source `ai`)로 저장. AI를 부르지 않음(20절) |
| PATCH/DELETE | `/api/meal-slots/<id>` | 인분 고치기(`{servings}`, `SlotDetail` −/+ 바로 저장) / 칸 비우기 |
| GET | `/api/meal-plans/<id>/shopping-preview` | 장보기 미리보기(23절 D4) `{start_on, end_on, recipe_slot_count, buy, manual, skip}`. 담기는 이 API가 하지 않는다(화면이 `POST /api/shopping/items/bulk`로) |
| GET | `/api/export/summary` | (`X-Requested-With: fetch` 필요) 내보낼 개수와 오늘(서울) 남은 횟수 `{ingredients, recipes, seasonings, shopping, memos, limit: 5, remaining}`(27절) |
| GET | `/api/export` | (`X-Requested-With: fetch` 필요) zip 내려받기(`Content-Disposition: attachment; filename="galmuri-kitchen-YYYYMMDD.zip"`, 서울 날짜). `ingredients.csv`·`recipes.csv`·`seasonings.csv`·`shopping.csv`·`shopping_memos.csv`(UTF-8 BOM, 한국어 머리글). 하루 5회(`ai_calls.kind = export`), 넘으면 429 `오늘 내보내기는 5번까지 할 수 있어요. 내일 다시 해주세요.`(27절) |
| GET | `/api/ai-usage` | 오늘(서울) `{scan:{used, limit}, recipe:{used, limit}}` — `오늘 N번 남음`·더보기 AI 사용량 |
| GET/POST | `/api/seasonings` · GET/PUT/DELETE `/api/seasonings/<id>` | 내 양념 비율 목록·추가 / 상세·수정·삭제(22절) |
| GET | `/api/shopping` | 장보기 한 번에 받기 `{items, stocked, notes, today}` — 페이지 없음(오프라인 보관, 26절 예외). 7일 지난 산 것은 이때 지운다(28절) |
| POST/PUT/DELETE | `/api/shopping/notes`, `/api/shopping/notes/<id>` | 메모 만들기(같은 `client_id`면 200) / 고치기 `{place, body, edited_at}`(서버가 더 늦게 저장됐으면 409 + 서버 메모) / 삭제(사진 파일도)(28절) |
| POST/DELETE | `/api/shopping/notes/<id>/photos`, `…/photos/<photo_id>` | 사진 올리기(multipart `image`, `client_id?`, 메모당 10장) / 삭제(28절) |
| POST | `/api/shopping/items` | 살 것 추가 201. 같은 `client_id`가 있으면 그 항목 200(28절) |
| POST | `/api/shopping/items/bulk` | 한 번에 담기 `{source, source_label?, items:[…] 1~50}` → 201 `{created, skipped}`. 목록에 있는 이름·요청 안 겹치는 이름은 건너뜀, 하나라도 틀리면 400 `{error: "N번째 재료: …", errors}`(28절) |
| PATCH/DELETE | `/api/shopping/items/<id>` | 고치기 또는 체크 `{done, changed_at}`(마지막 변경 우선) / 삭제(28절) |
| GET | `/api/shopping/stock-draft` | 재고에 넣기 초안 `{purchased_on, items:[{id, name, quantity, unit, location_id, location_reason}]}` — 체크했고 안 넣은 항목(28절) |
| POST | `/api/shopping/items/stock` | 체크한 항목 재고에 넣기 `{purchased_on, items:[{id, name, quantity, unit, location_id}] 1~300}` → 201 `{created}`(이미 넣은 요청을 다시 보내면 200 `{created: 0}`), 재료 생성과 산 것 기록은 한 트랜잭션(28절) |
| POST | `/api/shopping/items/match` | 스캔으로 넣은 이름과 맞는 목록 항목 `{names:[…] 1~50}` → `{items:[{id, name}]}`(28절) |
| POST | `/api/shopping/items/mark-stocked` | 산 것으로 옮기기(재료 안 만듦) `{ids:[…] 1~300}` → 204(28절) |
| GET | `/api/videos`, `/api/videos/<id>` | 요리 채널 영상(17절) |
| GET/POST | `/api/channels` · PATCH/DELETE `/api/channels/<id>` | 채널 목록·추가 / 기본 채널 숨기기·내 채널 빼기(17절) |
| GET/POST | `/api/cook-logs` | 기록 목록 / 생성(multipart: 필드 + 사진 + `usages` JSON) |
| DELETE | `/api/cook-logs/<id>` | 기록 삭제(재고 복원 안 함) |
| GET | `/api/photos/<key>` | 소유자 확인(내 접두사 + 사진 행) 후 로컬은 파일 전송(`private, max-age=3600`·nosniff·`Content-Security-Policy: default-src 'none'; sandbox`), R2는 같은 소유자 확인 뒤 R2에서 받아 같은 헤더로 흘려보냄(없는 객체 404, R2 오류 503 `사진을 지금은 볼 수 없어요.`)(28절). 남의 키·지운 사진 404 |

CLI: `flask sync-public-recipes` — 식약처 COOKRCP01 전체(약 1,100건)를 1,000건 단위로 받아 upsert(`FOODSAFETY_API_KEY` 필요, 받으면 예시 레시피는 지움). `flask seed-sample-recipes` — 키 없이 화면을 확인하는 직접 쓴 예시 레시피 12개(`is_sample`).

## 6. 화면 흐름

하단 탭(사용자 결정 2026-09-13): **재고 · 레시피 · 장보기 · 식단 · 더보기**. 다섯 탭을 모두 노출하고, 아직 기능이 없는 탭은 앞으로 들어올 기능을 안내하는 `준비 중` 화면을 보여 준다(사용자 결정 2026-09-13). 각 단계에서 진짜 화면으로 교체한다. 첫 탭 제목은 `내 재고`.
더보기: 27절 구성을 따른다(기록·우리 부엌·나·앱·도움말·계정). 레시피 탭은 칸 `추천 · 내 레시피 · 영상 · 양념 비율`(17·22절). 링크 가져오기는 칸이 아니라 `내 레시피`의 `레시피 추가` 시트 안에 있다(17절) (2026-09-14, 시안 승인).
화면 전환은 해시 경로(`#/`, `#/more`, `#/tools` …)로 하여 폰 뒤로가기가 동작한다. 비로그인 시 로그인 화면.

1. **로그인**: 카카오/네이버/구글 버튼.
2. **냉장고**: 임박 순 목록 + 배지. `+ 직접 추가`(이름, 수량, 단위, 구입일[기본 오늘], 유통기한). 항목 탭 → 수정/삭제.
   `사진으로 추가`(냉장고 사진 · 영수증 · 온라인 주문 캡처, 카메라·갤러리는 폰이 고르게 함) → 브라우저에서 긴 변 1568px JPEG로 축소 → `/api/scan` → 확인 화면(체크, 행을 펼쳐 이름·수량·단위·보관 위치 수정, 구입일 일괄 입력; 영수증·주문은 인식된 날짜로 프리필) → `/api/ingredients/bulk`. 시안 `docs/design/scan-2/`.
3. **추천**: 내 레시피 / 공공 DB 섹션(일치율 순, 부족 재료 표시). 카드 → 상세.
   AI 입구 (2026-09-14, 시안 승인): 추천 칸 맨 위 한 줄 카드 `내 재고로 새 레시피` · `AI가 3개 만들어줘요 · 오늘 N번 남음` · `만들기` → 별도 화면 `#/recipes/ai`. 만드는 중 화면(다람이, `빨리 먹어야 할 두부·대파를 먼저 넣어볼게요.` `10초쯤 걸려요.`) → 결과 카드 3개(사진·임박 배지·제목·`2인분 · 20분`·일치 막대, `자세히`/`저장` 버튼, 저장하면 초록 `저장했어요`), 안내 `AI가 만든 레시피예요. 간과 익힘은 맛보면서 조절해주세요.`, 아래 `다시 만들기 · 오늘 N번 남음`. 시안 `docs/design/recipes-3b3c/`.
4. **레시피 상세**(공통): 재료(보유 여부 표시), 단계. `내 레시피로 저장`(public/ai일 때), `요리했어요`.
5. **레시피 탭**: 내 레시피 목록, 등록/수정/삭제 폼(재료 행 추가, 단계 행 추가).
6. **요리했어요 폼**: 냉장고와 매칭된 재료 목록 + 사용량(기본 전량), 날짜(기본 오늘), 별점, 메모, 사진 → 저장.
7. **기록 탭**: 날짜 역순, 썸네일·제목·별점·메모.

## 7. 핵심 동작

- **스캔**: Claude Messages API에 이미지(base64) + 종류별 프롬프트, 구조화 출력(JSON 스키마)으로
  `{items:[{name, quantity, unit, location_kind, price}], purchased_on: "YYYY-MM-DD"|null}`. 영수증·주문에서 식재료가 아닌 항목(봉투, 세제 등)은 제외하도록 지시. 서버가 결과를 정리한다(최대 50개, 이름 50자·단위 10자, 수량이 0 이하·숫자 아님 → 1, 미래 구입일·냉장고 사진의 구입일 → null). price는 품목별 결제 금액(원, 할인 반영)이며 숫자가 아니거나 0보다 크고 10,000,000원 이하가 아니면 null(직접 입력은 0원도 허용), 냉장고 사진은 항상 null.
- **AI 레시피**: 보유 재료 목록(임박 표시 포함)을 전달, 구조화 출력으로 `[{title, servings, minutes, ingredients:[{name, amount}], steps:[str]}]` 3개. 임박 재료 우선 사용 지시.
  - **사진 (2026-09-14, 시안 승인)(사용자 선택 "비슷한 공공 레시피 사진 쓰기"):** 이미지를 만들지 않는다. 각 AI 레시피 이름으로 `public_recipes` 중 사진이 있는 가장 비슷한 요리를 찾아 그 `image_url`을 쓴다(정규화 이름 같음 → 한쪽이 다른 쪽 포함(짧은 쪽 3자 이상) → 토큰 겹침 Jaccard 0.5 이상). 없으면 사진 없이 반짝이 자리 표시. 화면에는 `비슷한 요리 사진`(대체 텍스트·상세 캡션)으로 밝힌다. 저장할 때 `recipes.image_url`로 남긴다. 조리 시간(minutes)은 결과 화면에만 보이고 저장하지 않는다.
- **조리 기록 저장**: 한 트랜잭션에서 `usages=[{ingredient_id, amount}]` 각각 소유 확인 → quantity 차감 → 0 이하면 삭제 → cook_log 생성. 사진 업로드 실패 시 전체 롤백.
- **AI 일일 한도**: 요청 전 오늘(서버 기준 Asia/Seoul) 해당 사용자의 `ai_calls` 수를 kind 그룹(scan: fridge+receipt+order+memo / recipe: recipe+link+recipe_photo+meal (2026-09-14, 시안 승인; meal은 20절 AI 식단 초안, recipe_photo는 17절 사진으로 가져오기))별로 센다. 서울 하루를 UTC 구간으로 바꿔 created_at으로 센다.
  한도 `AI_DAILY_SCAN_LIMIT`(기본 10), `AI_DAILY_RECIPE_LIMIT`(기본 10, AI 레시피와 링크·글·사진 가져오기, AI 식단 초안을 합산) 초과 시 429. AI로 보낸 호출은 성공·실패와 관계없이 센다(실패도 비용이 들어 남용을 막기 위해). 업로드 검증에서 걸린 요청은 세지 않는다. 짧은 연속 호출은 `AI_SCAN_BURST_LIMIT`(기본 3, 60초)로 별도 429.

## 8. 에러 처리

- AI 실패/타임아웃/스키마 불일치 → 502 `{"error": "인식에 실패했어요. 직접 입력해주세요."}`(코드·문구 규칙대로 붙여 씀 (2026-09-14, 시안 승인)), 프론트는 수기 입력 폼으로 이동.
- 업로드: `MAX_CONTENT_LENGTH` 10MB(413), 파일 시그니처로 판별해 JPEG·PNG·WEBP 외 415(선언된 Content-Type은 신뢰하지 않는다). 스캔 한도 초과 429, 키 없는 운영 503.
- 남의 리소스 id → 404.
- 입력 검증: name 1~50자, quantity > 0, rating 1~5, 날짜 ISO 형식. 위반 시 400.
- 프론트: fetch 래퍼 하나에서 401 → 로그인 화면, 그 외 오류 → 토스트.

## 9. 보안

- 세션 쿠키: HttpOnly, Secure(운영), SameSite=Lax. `SECRET_KEY` 환경변수 필수.
- OAuth state 검증(Authlib).
- CSRF: 상태 변경 요청에 커스텀 헤더 요구.
- 사진: 비공개 버킷, 소유자 확인 후 만료 5분 presigned URL.
- 체험하기 계정(추가: 2026-09-14, 사용자 결정 "체험 계정 + 카카오 로그인"): `DEMO_LOGIN=1`일 때만 `POST /api/demo-login`이 열린다. 누를 때마다 새 계정(`provider=demo`)과 예시 데이터를 만들고 24시간 뒤 `flask purge-demo-users`로 지운다. IP(IPv6는 /64)별 1시간 3개·하루 10개, 전체 5,000개(차면 오래된 체험 계정부터 재활용), IP는 `SECRET_KEY`에서 뽑은 키의 HMAC 해시만 남긴다. 체험 계정 AI 하루 한도 3번, 체험 전체 AI 24시간 예산(`DEMO_AI_GLOBAL_DAILY`)을 넘으면 예시 결과, 영상은 늘 예시 목록. 세션은 `user_id`와 `provider_id`가 함께 맞아야 한다. `ai_calls`는 사용자를 지워도 남는다(`SET NULL`, `demo` 표시).
- 비밀값(ANTHROPIC_API_KEY, FOODSAFETY_API_KEY, KAKAO_CLIENT_ID/SECRET, NAVER_CLIENT_ID/SECRET, GOOGLE_CLIENT_ID/SECRET, R2_*, DATABASE_URL, SECRET_KEY)은 환경변수. `.env`는 gitignore.

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
  쇼핑몰 주문내역 자동 연동·장바구니 담기(16절 7개 쇼핑몰 모두 공개 API 없음).

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
- `shopping_items`: id, user_id, client_id(선택, 기기에서 만든 id — 오프라인에서 다시 보내도 하나만 생김, UNIQUE(user_id, client_id)), name, quantity, unit, planned_on(date, 선택), ~~store~~, location_id(선택, 구매 후 넣을 위치, 위치를 지우면 NULL — FK ondelete SET NULL),
  source(`manual`|`recipe`|`staple`|`urgent`|`meal_plan`|`memo`), source_label(선택, 레시피 이름 등 태그용), done_at(선택), done_changed_at(선택, 체크·해제를 마지막으로 바꾼 시각 — 19절 충돌 규칙), stocked_at(선택, 재고에 넣은 시각), created_at.
  (2026-09-14, 시안 승인) `store` 칸은 두지 않는다 — 시안에 항목별 쇼핑몰이 없고 마지막으로 연 쇼핑몰은 기기에 기억한다. `memo`는 19절 메모 사진 → AI 목록이 담는 source. 해제 때는 done_at이 비어 비교할 시각이 없어 `done_changed_at`을 둔다.
- 담기 경로: 직접 추가, 레시피 상세의 부족 재료, 떨어진 필수품 배너, 임박/소진 재료, 장보기 메모 사진(19절).
- **생활용품 (2026-09-14, 사용자 결정):** 수세미·휴지·세제 같은 생활용품도 장보기 목록에 담지만 **재고(냉장고)에는 넣지 않는다.** `shopping_items.household`(bool, 기본 false). 담을 때 안 보내면 이름으로 짐작한다(`app/household.py` 낱말 목록 — 두 글자 이상은 들어 있으면, `랩`처럼 한 글자는 이름 전체가 같을 때만). 재고에 넣기 화면은 생활용품 줄을 회색 태그 `생활용품`과 함께 `재고에 넣기` 끔(산 것으로만 옮김)으로 보여주고, 줄마다 켜고 끌 수 있다(식품은 켬이 기본). 영수증·주문 스캔은 지금처럼 식품만 고른다. **후속:** 목록 화면 고치기 시트에 `생활용품` 켜기·끄기(Task 8 병합 뒤).
- 목록: 살 날짜별 그룹(오늘·이번 주·날짜 미정), ~~완료 항목은 아래로~~.
- **목록 화면 (2026-09-14, 시안 승인):** 시안 `docs/design/shopping-4/`(`ShoppingList`·`ShoppingOffline`·`ShoppingDark`·`AddSheet`·`StoreSheet`·`RecipeEntry`·`MemoPage`·`StockIn`).
  - 머리 `장보기` + `항목 추가`(+) 버튼, 요약 `살 것 N개 · 체크한 M개`, 메모 카드(19절), 묶음 `오늘`(지난 날짜 포함) · `이번 주`(오늘부터 7일) · `나중에`(그 뒤 날짜) · `날짜 미정`.
  - 행: 체크 칸 · 이름 + 수량(`두부 1모`) · 태그(`레시피 · 두부조림` / `곧 떨어져요` / `필수품`) · 오른쪽 쇼핑몰 아이콘 버튼(`{이름} 쇼핑몰에서 찾기`).
  - **체크한 항목은 제자리에서 줄을 긋고(다시 누르면 해제), 다시 열어도 아래로 내려가지 않는다.** 체크한 항목이 있을 때만 목록 위 초록 막대 `체크한 N개를 재고에 넣을까요?` + `재고에 넣기`.
  - **재고에 넣은 항목은 목록에서 빠지고 맨 아래 접힌 `산 것 N개`(최근 7일)에 남는다**(`stocked_at`, 7일 지나면 지움, `다시 담기`).
  - 살 것 추가 시트: 이름 + 수량 한 줄(수량은 `1모`·`30구`처럼 한 칸), `언제 살까요?` 칩 `오늘 · 이번 주 · 날짜 미정 · 날짜 고르기`, 버튼 `계속 추가` / `추가`.
  - 레시피 상세: 재료 목록 아래 버튼 하나 `없는 재료 N개 장보기에 담기` — 고르지 않고 한 번에 담고, 이미 목록에 있는 이름은 건너뛴다. 빼기는 장보기에서 한다.
  - 사용자당 목록 300개(산 것 제외). 목록은 오프라인 보관 때문에 페이지 없이 한 번에 받는다(26절 예외).
- 쇼핑몰 검색 링크: 항목마다 7개 쇼핑몰(쿠팡·네이버 쇼핑·컬리·이마트몰·홈플러스·롯데마트·G마켓) 검색 결과로 이동(URL 형식은 구현 시 실제 동작 검증).
- 정렬 링크(추가 2026-09-13): 쇼핑몰마다 `낮은 가격순`·`판매량(많이 산)순`·`신상품순`으로 연 검색 결과 링크. 쇼핑몰별 정렬 URL 파라미터는 구현 시 실제 동작을 검증하고, 지원하지 않는 정렬은 버튼을 숨긴다.
- **쇼핑몰에서 찾기 시트 (2026-09-14, 시안 승인):** 제목 `{이름} 찾기`, 설명 `누르면 쇼핑몰 검색 결과로 이동해요. 결제는 쇼핑몰에서 해요.` 쇼핑몰마다 이름 + 칩 `낮은 가격순 · 많이 산 순 · 새 상품순`(확인된 것만). **마지막으로 연 쇼핑몰이 맨 위(기기 localStorage), 나머지는 고정 순서** — 제휴 여부와 무관. 제휴 쇼핑몰은 이름 옆 `광고`, 시트 아래 한 줄 `‘광고’가 붙은 링크로 사면 갈무리부엌이 수수료를 받을 수 있어요. 순서와는 상관없어요.` 주소 표는 화면 모듈 `frontend/src/storeLinks.ts` 한 곳에 두고, 사용자가 폰에서 열어 확인하기 전에는 화면에 내보내지 않는다.
- 구매·결제는 앱에서 하지 않는다(공개 주문 API 없음). 링크로 쇼핑몰 앱/웹의 검색·상품 화면까지 연결하는 것이 범위.
- ~~네이버 최저가~~ (변경 2026-09-13): 네이버 쇼핑 검색 API가 2026-07-31에 종료되고 공식 대체 API가 없어 앱 안 가격 표시는 하지 않는다. 사용자 결정으로 쇼핑몰별 `낮은 가격순` 검색 링크(위 정렬 링크)로 대체한다. 가격 스크래핑은 약관·차단 위험으로 하지 않는다.
- 제휴 링크(추가 2026-09-13, 25절): 쇼핑몰 링크는 한 함수에서만 만든다. 제휴 ID는 환경변수(예: `COUPANG_PARTNERS_ID`)로 받고, 없으면 일반 검색 링크를 쓴다. 제휴 링크 옆에는 `광고` 표시를 단다(공정위 추천·보증 심사지침). 정렬·노출 순서는 수수료와 무관하게 둔다. 파트너스 가입·약관 확인은 Render 배포 후. (2026-09-14) 링크는 화면에서 만들므로 제휴 ID는 `/api/me`의 `shop_affiliates`로 넘긴다(Vite 빌드 변수는 Render 환경변수가 들어가지 않음). 쇼핑몰별 제휴 링크 형식은 가입 후 확인하고, 그 전에는 제휴 링크·`광고` 표시가 없다.
- **주소 표 (2026-09-14, 4단계 Task 5):** 쇼핑몰 × 정렬 주소 표와 링크 만드는 함수는 `frontend/src/storeLinks.ts` 한 곳(`STORES`·`storeLinks()`). 지금 표는 네트워크 없이 적은 **검증 전 후보**라 모든 쇼핑몰 `verified: null`이고, 화면은 `onlyVerified`로 걸러 사용자 폰 검증(Task 9) 전에는 보이지 않는다. 후보가 없는 정렬(컬리·홈플러스·롯데마트 전부, 네이버 쇼핑 `많이 산 순`)은 칸을 비워 칩을 숨기고, 정렬이 하나도 없으면 `검색 결과` 칩 하나. 검증용 링크 목록은 `node scripts/check-store-links.mjs --print`. 제휴 ID는 `COUPANG_PARTNERS_ID` → `/api/me`의 `shop_affiliates`(값 있는 것만, 없으면 `{}`), 링크 형식 `AFFILIATE_FORMATS`는 가입 후 채운다(지금 비어 있어 `광고` 없음).
- ~~구매 완료: 체크 시 재료로 등록(구입일 기본 오늘·수정 가능, 위치 선택). 주문 캡처/영수증 스캔 결과로 장보기 항목 일괄 체크.~~ → 23절 D3(체크는 `done_at`만, `재고에 넣기` 화면에서 일괄 등록)로 대체.
  **재고에 넣기 화면 (2026-09-14, 시안 승인 `StockIn`):** `체크한 N개를 재고로 옮겨요`, `산 날` 하나(기본 오늘), 행마다 위치(프리필 이유 `같은 이름 재료가 있던 곳` 등), 안내 `재고에 넣으면 장보기 목록에서 빠져요. 유통기한은 재고에서 고칠 수 있어요.`, `취소`/`N개 넣기`. 재료 생성과 `stocked_at` 기록은 한 트랜잭션.
  **영수증·주문 스캔 (2026-09-14):** 일괄 체크하면 23절 재고에 넣기와 겹쳐 재고에 두 번 들어가므로, 스캔으로 재고에 넣은 뒤 이름이 맞는 장보기 항목이 있으면 `장보기 목록에 있던 우유·양파도 샀나요?` → `장보기에서 빼기`(산 것으로 옮김) / `그대로 두기`를 제안한다.

## 17. 3단계 추가: 링크로 레시피 가져오기
- `POST /api/recipes/import` `{url}` 또는 `{text}` → Claude 구조화 출력 `{title, servings, ingredients:[{name, amount}], steps:[str]}` → 확인 후 저장(`source`: `youtube`|`instagram`|`blog`|`text`, `source_url`). 응답 `{title, servings, ingredients, steps, source, source_url, source_card:{title, author, thumbnail_url}|null, sample}`, 저장하지 않는다. source_card(영상 제목·채널명·썸네일)는 확인 화면 표시용이고 저장하지 않는다(25절 링크·요약만).
- **입구·흐름 (2026-09-14, 시안 승인):** `내 레시피` 칸 `레시피 추가` → 시트 `레시피 추가 / 어떻게 넣을지 골라주세요`에 `링크로 가져오기(유튜브·인스타그램·블로그 주소)` · `글 붙여넣기(메모나 게시물 설명을 복사해서)` · `직접 쓰기(재료와 만드는 법을 하나씩)`, 아래 `링크·글은 AI가 정리해요 · 오늘 N번 남음`. 링크를 못 읽으면(422 `need_text`) 같은 시트가 `글 붙여넣기`로 바뀌고 경고 상자에 이유(예: `인스타그램 링크에서는 레시피를 읽지 못했어요. 게시물 설명을 길게 눌러 복사한 뒤 아래에 붙여 넣어주세요.`)를 보여준다. 확인 화면은 기존 레시피 폼에 초안을 채운 `가져온 레시피 확인`(보조 `AI가 정리했어요. 틀린 곳을 고친 뒤 저장해주세요`, 출처 카드 `썸네일 · 제목 · 유튜브 · 채널명 · 원본`, 재료 `양은 비워도 괜찮아요`). 영상 보기의 `레시피로 가져오기`도 같은 확인 화면으로 간다.
- 유튜브: `videos.list`(1 unit)로 **영상 설명란만** 가져와 정리한다. ~~자막(자동 자막 포함)~~ — 다른 사람 영상의 자막 내려받기는 공식 API(captions.download)가 영상 주인 인증을 요구해 쓸 수 없고 비공식 추출은 약관·차단 위험이 있어 쓰지 않는다 (2026-09-14, 시안 승인). `YOUTUBE_API_KEY`가 없거나 실패하면 글 붙여넣기로 안내한다.
- 블로그 등 일반 링크 (2026-09-14, 시안 승인): https 주소만, 서버가 요청하기 전에 DNS 결과가 모두 공인 IP인지 보고 연결된 소켓의 상대 주소도 다시 확인한다(사설·루프백·링크로컬 거부), 리다이렉트는 매번 같은 검사로 최대 3번, 응답은 `text/html`·3MB(2026-09-14, 만개의레시피 페이지가 1.2MB라 1MB에서 올림)·8초 이내. 네이버 블로그는 모바일 주소로 바꿔 읽는다. 사진은 받지 않는다.
- 인스타그램: 공식적으로 타인 게시물 본문 조회 불가 → 링크 미리보기(og:description) 시도, 부족하면 캡션 붙여넣기 안내. 링크만으로 항상 성공을 약속하지 않는다.
- AI 일일 한도에 `link` 포함(recipe 그룹).
- **구현 세부 (2026-09-14, 3b 태스크 2):** 링크는 500자 이하. 유튜브(`watch?v=`·`shorts`·`live`·`embed`·`youtu.be`, ID 11자)·인스타그램(`p`·`reel`·`reels`)은 `http://`도 받지만 서버는 표준 https 주소(`source_url`)만 부르고, 그 밖의 링크는 `https://`만 받는다. 입력 오류 400(`링크나 글을 입력해주세요.` · `글은 10~10,000자로 붙여 넣어주세요.` · `링크를 다시 확인해주세요. https로 시작하는 주소를 붙여 넣어주세요.`), 키 없는 운영 503 `레시피 가져오기를 지금은 쓸 수 없어요.`, 없는 영상 404 `영상을 찾을 수 없어요. 링크를 다시 확인해주세요.`. 링크를 못 읽었거나(키 없음·요청 실패·본문 10자 미만) AI가 레시피를 못 찾으면 422 `{error, need_text: true}`(유튜브·인스타그램·그 밖의 링크·글마다 문구가 다르다). AI 호출 실패 502 `레시피를 정리하지 못했어요. 잠시 후 다시 시도해주세요.`. 한도는 외부 요청 전에 한 번, AI 호출 직전에 잠금을 잡고 다시 센다(외부 요청 실패는 세지 않고, AI를 부른 뒤 레시피가 없으면 센다). 한도 문구는 AI 레시피와 같은 묶음이라 `오늘 AI 레시피는 N번까지…`. 블로그 `source_url`은 리다이렉트를 따라간 최종 주소(500자를 넘으면 처음 주소), 출처 카드는 `{페이지 제목, 사이트 이름, null}`. 연결은 DNS 검사를 통과한 첫 IP 하나에만 하고(다시 묻지 않음), 상대 주소 확인은 TLS를 시작하기 전(소켓 연결 직후)에 한다. 8초는 리다이렉트까지 합친 전체 시간이며 감시 타이머가 소켓을 끊는다. 유튜브·인스타그램·블로그 외부 요청은 `ai_calls.kind = link_fetch`(토큰 없음)로 따로 기록해 60초 5번·하루 50번(`오늘 링크 가져오기는 50번까지…`)으로 막고, AI 레시피 한도·AI 사용량·원가에는 넣지 않는다. 링크 칸이 공백뿐이면 비어 있는 것으로 본다. 인스타그램은 og:title이 게시물 미리보기(`on Instagram` 등)일 때만 캡션을 쓴다.
- **사진으로 가져오기 (2026-09-14, 사용자 요청):** 요리책 페이지·레시피 화면 캡처·손글씨 레시피를 사진으로 가져온다. `레시피 추가` 시트의 세 번째 줄(`직접 쓰기` 앞) `사진으로 가져오기(요리책·캡처·손글씨 레시피를 찍어서)`, 아이콘 카메라. 고르면 시트가 사진 단계(`사진으로 가져오기 / 레시피 사진을 찍거나 고르면 재료와 만드는 법을 정리해줘요`)로 바뀌고 버튼 두 개: `카메라로 찍기`(주 버튼, `capture="environment"`, 1장) · `앨범에서 고르기`(보조 버튼, 여러 장, 3장까지 — 더 고르면 앞의 3장만 읽고 `사진은 3장까지 읽어요. 앞의 3장만 읽을게요`를 보여준다), 아래 `사진은 AI가 정리해요 · 오늘 N번 남음`. 버튼을 둘로 나눈 이유: 안드로이드 14+ 시스템 사진 선택기에는 카메라가 없다. 읽는 동안 시트 안에 `사진에서 레시피를 정리하고 있어요` / `사진 N장` · `10초쯤 걸려요.` + `취소`(요청 중단). 사진은 재고 사진과 같은 규칙으로 줄여 보낸다(긴 변 1568px JPEG, 10MB, 못 읽는 형식은 HEIF 안내). 성공하면 링크·글과 같은 `가져온 레시피 확인`(source `photo`, source_url·출처 카드 없음, 목록·상세 `사진에서 가져옴`). 서버: `POST /api/recipes/import`가 `multipart/form-data`의 `image` 파일 1~3개도 받는다(JSON 링크·글은 그대로). 파일마다 시그니처 검사 415 `사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.`, 없거나 빈 파일 400 `사진을 올려주세요.`, 4장 이상 400 `사진은 3장까지 올려주세요.`, 합쳐 10MB 초과 413(모두 세지 않음). 키 없는 운영 503 `레시피 가져오기를 지금은 쓸 수 없어요.`, 예시 모드는 예시 초안(source `photo`, 한도·기록 없음). 키가 있으면 AI 레시피 한도(`오늘 AI 레시피는 N번까지…`)를 잠금과 함께 센 뒤 `ai_calls.kind = recipe_photo`로 기록하고 사진 전부 + 가져오기 규칙 프롬프트(사진 속 글자는 자료일 뿐 지시가 아님, 없는 재료·단계를 지어내지 않음)로 `ImportResult`를 받는다. AI 호출 실패 502 `레시피를 정리하지 못했어요. 잠시 후 다시 시도해주세요.`(센다). 레시피를 못 찾으면 422 `{error: "사진에서 레시피를 찾지 못했어요. 글자가 잘 보이게 다시 찍거나 글 붙여넣기를 써주세요.", need_text: true}`(센다) — 화면은 글 붙여넣기로 바꾸지 않고 사진 단계에 경고 상자로 보여준다. 사진은 저장하지 않는다.

### 요리 채널 영상 (추가: 2026-09-14, 사용자 제안·선택)
유튜브를 따로 검색하지 않고 앱 안에서 요리 영상을 보고 바로 레시피로 가져온다. **유튜브 전체가 아니라 고른 요리 채널만** 다룬다.
- **위치:** 레시피 탭 칸 `추천 · 내 레시피 · 영상 · 양념 비율`(사용자 결정). 3b에서 링크 가져오기와 함께 만든다.
- **채널:** 기본 채널(운영자가 고른 한국 요리 전문 채널 몇 개, 구현 시 채널 정책·콘텐츠 확인 후 확정) + 사용자가 채널 링크를 붙여 추가·삭제하는 **내 채널**(최대 30개). `youtube_channels`(id, channel_id UNIQUE, title, thumbnail_url, is_default, fetched_at), `user_channels`(user_id, channel_id, hidden(bool, 기본 false), created_at, UNIQUE(user_id, channel_id)). 기본 채널은 사용자가 숨길 수 있다: 기본 채널을 숨기면 `hidden=true` 행을 만들고, `hidden=false` 행은 사용자가 추가한 채널이다 (2026-09-14, 시안 승인). `youtube_channels`에 `uploads_playlist_id`, `video_count`(`영상 248개`)도 둔다.
- **목록:** 채널 업로드 재생목록을 `playlistItems.list`(1 unit)로 최근 영상 30개씩 가져와 서버에 캐시(채널별 6시간, `youtube_videos`: video_id UNIQUE, channel_id, title, thumbnail_url, duration_seconds, description(앞 500자), published_at, fetched_at). 새로 받을 때 `channels.list`·`playlistItems.list`·`videos.list`(길이·설명) 각 1 unit, 요청당 오래된 채널 최대 3개. 화면은 내 채널 + 기본 채널 영상을 최신순으로 합쳐 무한 스크롤(26절). **(2026-09-14, 사용자 선택)** 채널 칩·검색 없이 보는 `전체` 목록에는 채널마다 최신 12개(`FEED_PER_CHANNEL`)까지만 섞는다 — 자주 올리는 채널이 목록을 도배하지 않게. 받아두는 건 채널당 30개 그대로라 채널 칩·제목 검색에서는 모두 보인다. **전체 검색(`search.list`, 100 units)은 쓰지 않고** 캐시된 제목 안에서만 찾는다(무료 한도 하루 10,000 units 보호). 20절 "유튜브 인기 레시피"도 이 채널 캐시를 쓰도록 바꾼다(20절 반영함).
- **영상 칸 화면 (2026-09-14, 시안 승인):** 검색 칸 `영상 제목에서 찾기`(캐시된 제목만), 채널 칩 줄(맨 앞 `채널` 설정 칩 → 요리 채널 화면, `전체`, 채널별 칩으로 거르기), 목록은 작은 썸네일 한 줄 행(128×72, 길이 배지, `채널 · 3일 전`).
- **요리 채널 화면 (2026-09-14, 시안 승인):** 시트가 아닌 별도 화면 `#/recipes/channels`(`요리 채널 / 고른 채널의 새 영상만 보여줘요`): 채널 링크 붙여넣기 + `추가`, `내 채널 N / 30`(행마다 연빨강 배경·테두리 `빼기`), `기본 채널`(행마다 숨기기 스위치 `보여줘요`/`숨겼어요`).
- **보기:** 영상을 누르면 유튜브 공식 삽입 플레이어(IFrame, `youtube-nocookie.com`)로 앱 안에서 재생한다. 영상 파일·자막은 저장하지 않는다. 화면에 YouTube 출처 표시.
- **가져오기:** 영상 보기 화면(제목·채널·설명 앞부분) 하단 주 버튼 `레시피로 가져오기` → 17절 링크 가져오기(`videos.list` 설명란, 1 unit)로 `가져온 레시피 확인` → 내 레시피 저장(source `youtube`, source_url) (2026-09-14, 시안 승인).
- **정책:** YouTube API 서비스 약관에 따라 저장한 메타데이터(제목·썸네일)는 주기적으로 새로 받고(30일 넘기지 않음), 채널이 삭제·비공개되면 목록에서 뺀다. `YOUTUBE_API_KEY`가 없으면 개발 모드에서는 예시 영상 목록(썸네일 없이 제목만), 운영에서는 영상 칸을 숨긴다.
- **구현 세부 (2026-09-14, 3b 태스크 3):** 테이블 `youtube_channels`·`user_channels`·`youtube_videos`(마이그레이션 `b2b2c2d2e2f2`). `GET /api/videos?limit=1~50(기본 30)&cursor=&q=(50자까지)&channel=` → 보이는 채널(숨기지 않은 기본 채널 ∪ 내 채널) 영상 `published_at`·id 내림차순 커서 페이지 `{items, next_cursor, sample}`, 첫 페이지(cursor 없음)에서만 먼저 30일 넘게 새로 받지 못한 영상 행을 지우고 6시간 지난(또는 받은 적 없는) 보이는 채널을 오래된 순 3개까지, 요청당 8초 안에서 새로 받는다(채널마다 `fetched_at`을 조건부로 먼저 바꿔 동시 요청이 같은 채널을 두 번 받지 않음, 실패해도 `fetched_at` 갱신). 30일 넘은 영상은 목록·보기에서도 빠진다(보기 404). **쿼터 예산:** 새로 받기는 `ai_calls.kind = video_refresh`, 채널 추가는 `channel_add`로 기록하고(토큰 없음, AI 사용량·원가에 안 셈) 사용자별 하루 새로 받기 20번, 전체 지난 24시간 추정 8,000 units(새로 받기·채널 추가 각 3) 안에서만 새로 받는다 — 넘으면 오류 없이 캐시된 영상을 보여준다. 새로 받기 = `channels.list`+`playlistItems.list`(30개, 공개 날짜 없는 비공개·삭제 영상 뺌)+`videos.list`(길이·설명 500자) 3 units, 채널이 없거나 재생목록이 없으면(404) 그 채널 영상을 지우고 썸네일·영상 수·재생목록을 비워 채널 목록에 `unavailable: true`로 보인다(요청 실패는 캐시를 그대로 둔다). 썸네일은 `i.ytimg.com`·`yt3.ggpht.com`·`yt3.googleusercontent.com`의 https 주소만 저장한다. `GET /api/videos/<id>`(보이는 채널만, + description·channel_thumbnail_url). `GET /api/channels` → 내 채널(추가한 순) 다음 기본 채널, `{items:[{id, title, thumbnail_url, video_count, is_default, hidden, unavailable}], mine_count, mine_limit: 30, sample}`. `POST /api/channels {url}` — `youtube.com/channel/UC…`(캐시에 있으면 외부 요청 없음)·`/@핸들`(한글 핸들 포함)·맨 `@핸들`·`/user/이름`(forUsername), 스킴 없이 `youtube.com/@이름`도 받는다. `/c/이름`은 공식 조회 방법이 없어 받지 않는다. 추가는 모두 사용자별 하루 30번·60초 10번(429 `오늘 채널 추가는 30번까지…`)으로 세고, 처음 보는 채널은 전체 예산(넘으면 503 `지금은 채널을 추가할 수 없어요.`)과 링크 가져오기와 같은 `link_fetch` 한도(60초 5번·하루 50번) 안에서 `channels.list`로 찾고, 받은 적 없는 채널이면 바로 영상을 받는다(3 units, 예산 안에서). 같은 새 채널을 두 사용자가 동시에 추가하면 먼저 만든 행을 쓴다. 내 채널 개수 확인·추가는 PostgreSQL 사용자별 잠금으로 한 줄로 세운다. 400 `채널 링크를 다시 확인해주세요. youtube.com/@이름 또는 youtube.com/channel/… 모양의 주소를 붙여 넣어주세요.`·`이미 추가한 채널이에요.`·`기본 채널에 이미 있어요.`(숨겨 뒀으면 다시 보이게 200)·`채널은 30개까지 추가할 수 있어요.`, 404 `채널을 찾을 수 없어요.`, 502 `채널 정보를 가져오지 못했어요. 잠시 후 다시 시도해주세요.`, 키 없음 503 `지금은 채널을 추가할 수 없어요.`. `PATCH /api/channels/<id> {hidden}`(기본 채널만)·`DELETE /api/channels/<id>`(내 채널만, 채널·영상 행은 남김) 키 없음 503 `지금은 채널을 바꿀 수 없어요.`. 키 없는 운영은 목록·보기·채널 목록 503 `영상을 지금은 볼 수 없어요.`, `/api/me` `videos: on|sample|off`. 예시 모드는 시안 제목 5개·채널 5개(내 채널 2, 기본 3 중 1개 숨김), 썸네일 없음. `flask seed-default-channels`는 `app/data/default_channels.json`대로 기본 채널을 맞추고, 키가 있으면 6시간 안에 받지 않은 채널만 새로 받는다(2026-09-14 사용자 확정: 자취요리신 simple cooking(박무땡)·만개의레시피·백종원 PAIK JONG WON·편스토랑X(KBS)·집나간아들·1분요리 뚝딱이형·김대석 셰프TV·딸을 위한 레시피·엄마의집밥·요리왕비룡 셰프TV·하루한끼·정호영의 오늘도 요리·1분다이어터·유지만 = 14개, 채널 ID는 유튜브 채널 페이지에서 확인).

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
- **장보기 메모** `shopping_notes`: id, user_id, client_id(선택, 16절과 같음), body(최대 2000자), ~~planned_on(선택)~~, place(선택, 최대 30자, 예: `이마트 성수점`), created_at, updated_at.
  장보기 화면 상단에 메모 카드. 목록 항목과 별개로 자유롭게 적는다(예: "세일 수요일까지").
  **(2026-09-14, 시안 승인 `MemoPage`)** 카드(`메모 · 이마트 성수점`, 본문 첫 줄, 사진 썸네일)를 누르면 별도 화면 `장보기 메모`: `어디서` · `메모` · `사진 N / 10`(사진 추가) · `사진에서 살 것 뽑기` · 맨 아래 연빨강 배경·테두리 `메모 삭제`. 저장 버튼 없이 입력하면 자동 저장. 메모는 여러 개(사용자당 20개), 카드는 가장 최근 1개 + `메모 N개 더 보기`. 시안에 날짜 칸이 없어 `planned_on`은 두지 않는다.
  **(2026-09-15) 빈 메모는 화면을 나갈 때 지우고, 하루 넘은 빈 메모는 목록을 받을 때 지운다.** 빈 메모 = 장소가 비었고(공백만 포함) 글이 비었고(공백·줄바꿈만 포함) 사진(보내기 전 사진 포함)이 없는 메모. 메모 화면은 나갈 때(뒤로·탭 바·다른 화면) 지금 보이는 내용으로 판단해 `note_delete`를 대기열에 넣고(안 보낸 메모 추가면 요청 없이 사라진다), 사진을 기기에 넣는 중이면 지우지 않는다. `새 메모`는 메모가 기기에 들어간 뒤 메모 화면을 열고, 그 전에 나갔으면 지운다. 새로고침·앱 닫기로 나가면 화면이 지우지 못하므로 `GET /api/shopping`이 사용자 잠금 안에서 만든 시각·고친 시각이 모두 하루 넘은 빈 메모를 지운다(다른 오프라인 기기에서 채우는 중일 수 있어 하루를 둔다).
- **사진 첨부** `shopping_note_photos`: id, note_id(CASCADE), client_id(선택), photo_key, created_at. 메모당 최대 10장. 손메모·전단지·상품 사진.
  카메라 촬영(`<input type="file" accept="image/*" capture="environment">`) 또는 앨범 선택, 브라우저에서 긴 변 1568px로 축소 후 업로드(R2, 3절 — 운영에서 R2가 없으면 503). 보기는 `/api/photos/<key>`(소유자 확인).
- **사진 → AI 목록 변환**: `/api/scan?kind=memo`(손메모·전단지) → 품목 추출 → 확인 화면 → `shopping_items` 일괄 추가(source `memo`, 이미 목록에 있는 이름은 건너뜀). AI 일일 한도 scan 그룹. 입구는 메모 화면의 `사진에서 살 것 뽑기`(2026-09-14, 시안 승인).
  (2026-09-14, 사용자 결정) 메모 사진은 식품과 생활용품을 함께 뽑고 줄마다 `household`(bool)를 붙인다(16절). 확인 화면은 그 값을 일괄 추가 줄에 그대로 보낸다.
- **인터넷 없이 보기·체크**(마트 지하 등):
  - 서비스 워커로 앱 화면(정적 파일) 캐시, 장보기 목록·메모는 마지막으로 받은 내용을 IndexedDB에 저장해 오프라인에서도 열린다.
    (2026-09-14) 지금 `sw.js`는 `/`만 캐시해 오프라인으로 열면 JS·CSS가 없다 → 같은 오리진 `/assets/*`(해시 파일·글꼴 조각)도 캐시한다. `/api`는 서비스 워커가 다루지 않고 화면이 IndexedDB로 보관한다. ~~글꼴(IBM Plex Sans KR)은 자체 호스팅해 오프라인에서도 같게 보인다.~~ **(2026-09-14 Task 7, 리드 결정)** 글꼴 파일을 내려받아 넣지 않고(새 의존성·네트워크 내려받기 없음) 서비스 워커가 Google Fonts 응답을 기기에 보관한다 — 한 번 온라인으로 연 뒤부터 오프라인에서도 같은 글꼴, 그 전에는 시스템 글꼴(`Apple SD Gothic Neo`·`Noto Sans KR`)로 보인다. 네트워크가 없을 때 마지막 로그인 사용자를 기기에 기억해 앱을 열고, 로그아웃하면 기기 데이터를 지운다.
  - 오프라인 중 체크·항목 추가·메모 수정·사진 촬영은 기기 대기열에 쌓고, 연결되면 순서대로 서버에 반영(화면 안에서 `online`·앱 열기·변경 직후에 보냄, 다시 보내도 `client_id`로 한 번만 생김).
  - 충돌 규칙: 항목 체크는 ~~`done_at` 타임스탬프 기준~~ **체크·해제한 기기 시각(`done_changed_at`) 기준** 마지막 변경 우선(2026-09-14 — 해제는 done_at이 비어 비교할 수 없음), 메모 본문은 ~~`updated_at` 기준~~ **기기가 보낸 저장 시각(`edited_at`)과 서버 `updated_at`을 비교해** 마지막 저장 우선(서버가 더 늦으면 409, 받아들이면 `updated_at = edited_at`이라 다시 보내도 같다)(덮어쓰기 전 기기 쪽 사본 보관 — `다른 기기에서 고친 메모가 있어서 이 기기에서 쓴 내용을 따로 보관했어요`). 기기 시계가 크게 틀리면 순서가 틀릴 수 있다(허용).
  - 화면에 `오프라인 · 연결되면 저장돼요` 표시, 대기 중 건수 표시(시안 `ShoppingOffline`: `기다리는 중 N건`, 장보기 탭).
  - 앱 모드(PWA standalone)·서비스 워커는 HTTPS에서만 동작 → 배포 이후 동작 확인. 로컬 폰 확인은 USB 디버깅 `adb reverse tcp:5180 tcp:5180` 후 `http://localhost:5180`.

## 20. 4b단계: 식단 짜기 (추가: 2026-09-13)
- `meal_plans`: id, user_id, name(예: `9월 둘째 주`), start_on, days(7 또는 30 등 1~31), goal(선택: `kcal_per_day` int, `note` ≤100자), created_at.
- `meal_slots`: id, plan_id(CASCADE), date, meal(`breakfast`|`lunch`|`dinner`|`snack`), recipe_id(선택, SET NULL), title(레시피가 없을 때 자유 입력), servings(기본 1), est_kcal(선택, AI 추정).
- **셀프**: 달력(주 보기 기본, 월 보기)에서 칸을 눌러 내 레시피·저장된 링크 레시피·자유 입력으로 채움. 주 단위 복사, N주 반복.
- **다이어트 AI 초안**: 목표(하루 kcal, 단백질 위주 등 메모)와 기간 → Claude가 보유·임박 재료를 우선 써서 끼니별 레시피 초안(구조화 출력, 끼니별 추정 kcal). 확인 화면에서 칸별 수락/교체. kcal은 **AI 추정치**라고 화면에 명시.
  정확한 영양성분(식약처 식품영양성분 DB 연동)은 범위 밖, 필요해지면 추가. AI 일일 한도 recipe 그룹.
- **유튜브 인기 레시피**: ~~YouTube Data API v3 `search.list`(q=`레시피`, regionCode=KR, order=viewCount, publishedAfter=최근 30일, type=video)~~ → 17절 요리 채널 영상 캐시(최신순·제목 검색)를 쓴다(`search.list` 100 units는 쓰지 않음) (2026-09-14, 시안 승인). 결과를 목록으로 보여주고,
  고른 영상은 17절 링크 가져오기로 레시피화해 식단 칸에 넣는다(`YOUTUBE_API_KEY`, 채널 캐시를 그대로 쓴다).
  인스타그램·틱톡은 인기 목록 공개 API가 없어 링크 공유로만 추가(17절).
- **장보기 자동 생성**: 식단 기간의 레시피 재료 합산 → 냉장고 재고와 이름 매칭(4절)해 없는 것만 → `shopping_items`(source `meal_plan`, planned_on=해당 끼니 전날) 미리보기 후 추가.
- 순서: 4단계(장보기) 다음, 5단계(조리 기록) 앞.
- **화면 (2026-09-14, 시안 승인 — `docs/design/meals-4b/` 15장):**
  - 식단 탭: 제목 아래 식단 고르기 버튼(`9월 셋째 주 ⌄`)과 주/월 전환, 오른쪽 `AI 초안`·`⋯`(이번 주 복사, 식단 이름·기간 고치기, 맨 아래 `식단 지우기`). 주 보기는 하루 카드 한 장에 채운 끼니만 아침·점심·저녁·간식 순서로 줄(제목 아래 `2인분 · 두부 마저 써요`, 마저 써요만 주황 글자), 빈 끼니는 카드 맨 아래 칩 한 줄(`+ 점심`, 누르면 채우기), 오늘은 초록 테두리(2026-09-15 사용자 선택, 시안 B). 월 보기는 월요일 시작, 날짜마다 끼니 점 4개, 누르면 그 주로. 하단 `장보기 목록 만들기`.
  - 칸 채우기 시트: `내 레시피`(검색·재료 일치 줄) · `영상`(채널 영상 캐시 검색) · `직접 쓰기`, 인분은 식단 기본 인분으로 시작. 직접 쓰기 칸은 재료가 없어 장보기에 들어가지 않는다.
  - 칸 상세 시트: 인분 −/+ 는 바로 저장, `레시피 보기`, `다른 걸로 바꾸기`, 맨 아래 `칸 비우기`(배경+테두리).
  - `내 몸 정보·목표` 카드(21절)는 영양 단계에서 제목 아래에 넣는다.
- **결정 (2026-09-14, 사용자 선택):**
  - 주 복사: 1~4주, **빈 칸만 채우고 채운 칸은 묻지 않고 그대로 둔다.** 복사가 식단 기간을 넘으면 식단 기간을 최대 31일까지 자동으로 늘린다(넘는 주 수는 고를 수 없게 막는다).
  - 영상으로 채우기: 17절 링크 가져오기의 확인 화면을 **거치지 않고** 시트 안에서 정리 → 내 레시피에 저장 → 칸에 넣는다(AI 레시피 한도 공유). 틀린 곳은 레시피에서 고친다. 이 경로만 17절 확인 화면 규칙의 예외다.
  - 장보기 살 날: 끼니 전날, 그 날이 이미 지났으면 **오늘**.
  - AI 초안: 빈 칸만 채운다. 칸마다 후보 2개를 **초안과 함께 미리 받아** `다른 걸로`는 AI를 다시 부르지 않는다. kcal은 1인분 기준 AI 추정치로 표시. 내 레시피에 없는 요리는 `새 레시피` 표시, 넣으면 내 레시피에 저장.
  - 장보기 미리보기(23절 D4): `모자란 만큼 담아요`(자동 체크) · `단위가 달라요 · 직접 골라주세요`(체크 없음) · `담지 않아요`(`목록에 있어요`·`충분해요`) 세 묶음, 줄마다 살 날·`식단` 표시.

**구현 세부 (2026-09-14, 4b-1 Task 1):**

- **테이블:**
  - `meal_plans`: id, user_id(FK `users` CASCADE, 인덱스), name(String(30)), start_on(Date), days(Integer 1~31), default_servings(Integer 1~20, 기본 1, 23절 D5), goal_kcal(Integer 500~5000, 선택), goal_note(String(100), 선택), created_at, updated_at(onupdate). `slots` 관계(`order_by=(date, id)`, `cascade="all, delete-orphan"`, `passive_deletes=True`).
  - `meal_slots`: id, plan_id(FK `meal_plans` CASCADE, 인덱스), date(Date), meal(String(10), `breakfast`|`lunch`|`dinner`|`snack`), recipe_id(FK `recipes` SET NULL, 인덱스, 선택), title(String(60) — 레시피 칸도 제목을 복사해 두어 레시피를 지우면 직접 쓰기 칸처럼 남는다), servings(Integer 1~20, 기본 1), est_kcal(Integer 1~3000, 선택 — AI 초안으로 채운 칸만), created_at. `UNIQUE(plan_id, date, meal)`.
  - Alembic `d1m1e1a1l1s1`(down_revision `c2h2o2u2s2e2`).
- **재고 일치 요약(`recipes.py`):** `stock_context(user_id)` → `(준비된 재고, 빨리 먹어야 할 재고 이름 집합)`(요청당 한 번). `match_summary(ingredients, prepared_stock, urgent)` → `{have_count, total_count, urgent_names}`(추천과 같은 매칭 규칙, 겹치는 재료가 없어도 빼지 않는다).
- **`GET /api/recipes/choices?q=`:** 최근 200개(`updated_at`·id 내림차순) 후보를 `match_summary`로 요약해 점수(`have/total + 0.1 × len(urgent_names)`) 내림차순 → 원래 순서로 최대 50개. `q`는 앞뒤 공백 뺀 50자까지(넘으면 앞 50자), 있으면 제목 부분 일치(`Recipe.title.contains(q, autoescape=True)`)로 미리 거른다.
- **식단·칸 API(`meals.py`, 모두 로그인):**
  - `GET /api/meal-plans` → `{items:[plan_summary…], default_servings}`(start_on·id 내림차순, 50개 상한, 페이지 없음). `default_servings`는 가장 최근에 만든(created_at·id 최대) 식단의 값, 없으면 1.
  - `POST /api/meal-plans` `{name, start_on, days, default_servings}` → 201 `plan_json`. 검증: `text(name, "식단 이름은", 30)`, `iso_date(start_on)` 없으면 400 `시작일을 골라주세요.`, `integer(days, "기간은", 1, 31)`, `integer(default_servings, "기본 인분은", 1, 20)`. 50개 상한 → 400 `식단은 50개까지 만들 수 있어요. 지난 식단을 지워주세요.`
  - `GET /api/meal-plans/<id>` → `plan_json`(칸은 `selectinload(MealSlot.recipe)`로 N+1 없이). 남의 것 404.
  - `PATCH /api/meal-plans/<id>` — 보낸 칸만 검증·반영. `goal_kcal`은 `null` 또는 `integer(…, "하루 목표 칼로리는", 500, 5000)`, `goal_note`는 `null`/빈 문자열(공백만도 포함) → `null`, 아니면 앞뒤 공백 뺀 100자까지(넘으면 400 `메모는 100자까지 입력해주세요.`). `start_on`·`days`가 바뀌면 새 기간 밖의 칸을 같은 커밋에서 지운다(결정 1).
  - `DELETE /api/meal-plans/<id>` → 204(칸은 CASCADE).
  - `PUT /api/meal-plans/<id>/slots` `{date, meal, recipe_id?, title?, servings?}` → 200 `slot_json`(없던 칸이면 만들고, 있으면 덮어쓴다). 검증 순서: 기간 밖 날짜 → 400 `식단 기간 밖의 날짜예요.`, meal 목록 밖 → 400, servings 없으면 `plan.default_servings`, `recipe_id` 있으면 `get_owned_or_404`로 확인하고 `title`은 레시피 제목으로 덮어쓴다(보낸 title 무시), 없으면 `text(title, "무엇을 먹을지는", 60)`. 덮어쓸 때 `est_kcal`은 비운다. 동시에 같은 칸을 처음 채워 UNIQUE 충돌 시 400 `방금 채운 칸이에요. 다시 불러와주세요.`
  - `PATCH /api/meal-slots/<id>` `{servings}` → 200 `slot_json`. `DELETE /api/meal-slots/<id>` → 204(칸 비우기). 칸 → 식단 → `user_id` 확인, 아니면 404.
  - `POST /api/meal-plans/<id>/copy-week` `{from_on, weeks}` → 200 `{plan: plan_json, copied, kept}`(결정 2026-09-14). `from_on`은 `iso_date`이고 `start_on ≤ from_on ≤ end_on`이며 `(from_on - start_on).days % 7 == 0`(주 보기는 시작일부터 7일씩 나눈다) — 아니면 400 `잘못된 요청이에요.`. `weeks`는 `integer(weeks, "복사할 주는", 1, 4)`. 원본은 `from_on ~ from_on+6` 사이의 칸, 없으면 400 `이번 주에 채운 칸이 없어요.`. 필요한 끝 날짜 `need_end = from_on + 7 × (weeks + 1) - 1`. `(need_end - start_on).days + 1 > 31`이면 400 `식단은 31일까지라 {가능한 주}주까지 복사할 수 있어요.`(가능한 주 = `(start_on + 30 - (from_on+6)).days // 7`, 0 이하면 `이 주는 더 복사할 수 없어요.`). `need_end > end_on`이면 `plan.days`를 늘린다. 원본 칸마다 `k = 1..weeks`로 `date + 7k`, 같은 `meal`에 칸이 없을 때만 `recipe_id`·`title`·`servings`·`est_kcal`을 복사(`copied` 증가), 있으면 그대로 두고 `kept` 증가. 한 커밋, 동시 요청으로 UNIQUE에 걸리면 `commit_or_duplicate(SLOT_TAKEN)`.
  - 칸 저장마다 `plan_json` 전체가 아니라 칸 하나만 돌려준다(ponytail) — 화면은 받은 칸을 자기 목록에 바꿔 끼운다.
- **AI 식단 초안 (2026-09-14, 4b-1 Task 3 — 결정 5·8을 따른다, `meals.py`·`ai.py`):**
  - `POST /api/meal-plans/<id>/ai-draft` `{start_on, days, meals, goal_kcal?, goal_note?}` → 200 `{dishes, slots, kept, sample}`. 검증 순서: 남의 식단 404 → `integer(days, "기간은", 1, 7)`(결정 5) → `start_on`이 날짜가 아니거나 `start_on < plan.start_on`이거나 `start_on + days - 1 > end_on`이면 400 `식단 기간 밖의 날짜예요.` → `meals`는 `MEALS` 안의 서로 다른 값 1~4개(아니면 400 `끼니를 하나 이상 골라주세요.`) → 목표 두 칸은 PATCH와 같은 검증(`_apply_goals` 공통). 빈 칸 = 날짜 × 고른 끼니 − 이미 있는 칸(날짜 → `MEALS` 순), 0개면 400 `채울 빈 칸이 없어요.`. `kept`는 그 범위·끼니의 채운 칸 `[{date, meal, title}]`. 재고가 비어도 진행한다. 목표 두 칸은 AI 모드를 보기 전에 커밋한다(키 없는 운영 503에서도 남는다).
  - 모드: 키 없는 운영 503 `AI 식단 초안을 지금은 쓸 수 없어요.` / 예시(`ai.sample_meal_draft`, 요리 6개를 칸마다 `i, i+1, i+2 (mod 6)`, 한도·기록 없음) / AI — AI 레시피와 같은 한도(`check_ai_limits(RECIPE_KINDS, AI_DAILY_RECIPE_LIMIT, "AI 레시피는")`) → `ai_calls.kind = meal` 기록 → `ai.draft_meals` → 실패 502 `식단 초안을 만들지 못했어요. 잠시 후 다시 시도해주세요.`(기록은 남고 토큰 없음).
  - 프롬프트(`ai.MEAL_PROMPT`) 뒤에 `<빈 칸>`(`날짜 끼니`)·`<재고>`(`이름 (빨리)`, 같은 줄 한 번, 100줄)·`<내 레시피>`(`id: 제목`, 최근 수정 순 100개)·`<이미 정한 끼니>`(`날짜 끼니 제목`)·`<목표>`(`하루 Nkcal`, 없으면 빈 묶음)·`<메모>`(없으면 태그째 뺀다)를 태그로 감싸 붙인다. 구조화 출력 `MealDraft{dishes:[MealDish{mine_id, title, servings, kcal_per_serving, ingredients, steps}], slots:[MealPick{date, meal, dishes}]}`, `max_tokens 16000`, 클라이언트 `timeout 90`(다른 AI 호출은 45 그대로).
  - 정리(`clean_meal_draft`, 모델 출력은 믿지 않는다): dishes는 앞 30개까지 번호를 유지해 읽는다. `mine_id`가 이번 요청에 보낸 내 레시피면 그 레시피의 제목·인분·사진(`ingredients`·`steps`는 빈 배열), 아니면 `clean_draft`가 되는 새 요리(사진은 `similar_public_image`), 둘 다 아니면 못 쓰는 번호. `est_kcal`은 1~3000 정수만, 아니면 null(결정 8: 1인분 추정). `urgent_names`는 `match_summary`로 붙인다. slots는 빈 칸이고 처음 나온 `(date, meal)`만, `dishes`에서 정수·범위 안·쓸 수 있는·겹치지 않는 번호를 앞에서 3개까지, 0개면 그 칸을 뺀다. 칸을 날짜 → `MEALS` 순으로 정렬한 뒤 쓰인 요리만 처음 쓰인 순서로 0부터 번호를 다시 매긴다. 남은 칸이 없으면 502(위 문구). 응답 `dishes:[{recipe_id, title, servings, est_kcal, ingredients, steps, urgent_names, image_url}]`, `slots:[{date, meal, options:[번호 1~3개]}]` — 첫 번호가 추천, 나머지는 `다른 걸로` 후보(AI를 다시 부르지 않는다).
  - `POST /api/meal-plans/<id>/ai-draft/apply` `{dishes:[{recipe_id} | {title, servings, ingredients, steps}] 1~30, slots:[{date, meal, dish, est_kcal?}] 1~28}` → 201 `{filled, kept, created_recipes}`. 칸마다 기간 안 날짜·`MEALS`·범위 안 정수 `dish`·`est_kcal`(null 또는 1~3000 정수), 같은 `(date, meal)` 두 번 — 아니면 400 `잘못된 요청이에요.`. 칸이 쓰는 요리만 본다: `recipe_id` 요리가 내 레시피가 아니면 400 `레시피가 방금 바뀌었어요. 초안을 다시 만들어주세요.`, 새 요리는 `parse_recipe` 문구 그대로 400. 새 요리를 쓰는 칸이 하나라도 아직 비었을 때만 그 요리를 **한 번** `Recipe(source="ai", image_url=similar_public_image)`로 만들고(모든 칸이 찼으면 만들지 않는다), 만들 수만큼 `check_recipe_cap(n)`(400 `레시피는 1000개까지 저장할 수 있어요.`). 빈 칸은 `MealSlot(recipe_id, title=레시피 제목, servings=plan.default_servings, est_kcal)`, 이미 찬 칸은 그대로 두고 `kept += 1`. 레시피·칸은 한 커밋, UNIQUE 충돌은 400 `방금 채운 칸이에요. 다시 불러와주세요.`(레시피도 함께 되돌린다). 한도·기록 없음.
- **장보기 미리보기 (2026-09-14, 4b-1 Task 4 — 결정 2·6을 따른다, `app/amounts.py`·`meals.py`):**
  - `app/amounts.py`의 `parse_amount(text)`는 레시피 재료 양 글자를 `(수량, 단위)`로 규칙 기반 파싱한다(순수 함수, 숟가락 단위 `kg`→`g`·`L`→`ml`로 환산). 셀 수 없는 양(`약간`·`10~15개`·`세트` 등)은 `None`. `is_spoon(unit)`은 계량스푼류(큰술·작은술·컵·꼬집 등) 여부.
  - `meals.shopping_rows(needs, stock, listed, today)`(순수, DB 없이 테스트): `needs = [(이름, 양 글자, 인분 배율, 끼니 날짜)]`, `stock = [(이름, 수량, 단위)]`, `listed = [장보기 목록(stocked_at NULL) 이름]`. `recipes.ALWAYS_HAVE`(물)는 뺀다. 이름을 `matching.normalize`로 묶어(정규화가 비면 원래 이름으로) 묶음마다 `planned_on = max(today, min(날짜) - 1일)`(결정 2026-09-14: 끼니 전날, 지났으면 오늘)을 구하고, 파싱되고 숟가락 단위가 아닌 양은 `× 인분 배율`해 단위별로 더해 `need`, 못 읽거나 숟가락 단위인 원래 글자는 `need_extra`(겹치면 한 번). 재고는 `matching.match_prepared`로 이름이 맞는 행을 찾아(`has_stock`) 그 수량·단위를 `parse_amount(f"{quantity:g}{unit}")`로 읽어 단위별로 더한다(`have`, 못 읽는 재고 단위는 `have`에서 뺀다). 분류는 순서대로 목록에 있음(`skip listed`) → `need` 없음(`has_stock`이면 `skip enough`, 아니면 `manual` 1개) → `need` 단위 둘 이상(`manual`, 첫 단위) → 단위 하나 `U`(`have[U]`가 없고 다른 단위 재고가 있으면 `manual`, 아니면 `short = round(need[U] - have.get(U, 0), 2)`가 0보다 크면 `buy`, 아니면 `skip enough`)(23절 D4, fix round 1: 반올림을 먼저 해서 부동소수점 오차로 `buy` 수량이 0.0이 되는 걸 막는다). `skip`·`manual` 행도 `quantity`·`unit`을 null로 두지 않는다(Task 9 `MealShoppingRow` 계약) — `skip`은 `need`의 첫 단위·그 양(없으면 1개, `manual`의 빈 `need`와 같은 값)을 그대로 보여 주고, `manual`은 같은 값을 반올림 뒤 최소 0.01로 올려(`POST /api/shopping/items/bulk`가 수량 0 이하를 통째로 거부하는 것을 막는다) 담는다. 결과는 `{"buy": [...], "manual": [...], "skip": [...]}`, 묶음 안은 `planned_on` → 처음 나온 순서.
  - `GET /api/meal-plans/<id>/shopping-preview` → `{start_on, end_on, recipe_slot_count, buy, manual, skip}`. `start_on = max(seoul_today(), plan.start_on)`(결정 2: 오늘 이후 끼니만), `end_on`은 식단 종료일. `start_on` 이후(포함)이고 레시피가 있는 칸만 `recipe_slot_count`에 세고, 칸마다 `ratio = slot.servings / max(recipe.servings, 1)`(방어)로 `needs`를 만든다. 재고·장보기 목록은 이 사용자 것만. 기간이 모두 지나 셀 칸이 없으면 `recipe_slot_count 0`·빈 묶음(오류 아님). 담기는 이 API가 하지 않는다 — 화면이 `POST /api/shopping/items/bulk` `{source: "meal_plan", source_label, items:[{name, quantity, unit, planned_on}]}`로 담는다(목록에 있는 이름은 서버가 또 건너뛴다).
- **장보기 목록 만들기 화면 (2026-09-15, 4b-1 Task 9, 시안 ShoppingPreview·ShoppingPreviewBottom):**
  - 경로 `#/meals/<id>/shopping`. 식단 주·월 보기 하단 `cart 장보기 목록 만들기`로 연다. 부제 `9월 15일–21일 · 레시피가 있는 칸 N개의 재료예요`(미리보기의 `start_on`~`end_on`).
  - 세 묶음(빈 묶음은 숨김): `모자란 만큼 담아요`(체크 기본 켬, 오른쪽 `1모 담기`) · `단위가 달라요 · 직접 골라주세요`(체크 기본 끔, 오른쪽 `2판`) · `담지 않아요`(체크 없음, `목록에 있어요`/`충분해요`). 줄 설명은 `plan.ts previewDetail`, 살 날 태그는 `buyDayText`(오늘·지남 `오늘 사요`, 아니면 `16일(수)에 사요`) + `식단` 태그. 체크는 사용자가 바꾼 것만 기억해 캐시로 먼저 보인 미리보기가 새로 와도 어긋나지 않는다.
  - 레시피 칸이 없으면 `레시피가 있는 칸이 없어요` / `레시피로 칸을 채우면 필요한 재료를 계산해줘요`(기간이 모두 지나 `start_on > end_on`이면 `지난 끼니는 계산하지 않아요`) + `식단으로 돌아가기`.
  - **담기:** 온라인에서만(`navigator.onLine`이 false거나 요청이 끊기면 `인터넷이 연결되면 담을 수 있어요`). 체크한 줄을 50개씩 `POST /api/shopping/items/bulk`(`source: meal_plan`, `source_label`: 식단 이름 60자, 줄마다 이름 50자·`quantity`·`unit`·`planned_on`) — 이미 목록에 있는 이름은 서버가 건너뛴다. 모두 끝나면 미리보기 캐시를 지우고 `#/shopping`으로 바꿔 간다(뒤로가기는 식단). 실패하면 CTA 위 `.error`(앞 묶음을 담았으면 `N개는 담았어요 · 문구`).
  - 장보기 탭 태그: `source = meal_plan`이면 `식단`(초록, `sourceTag`).
- **계획하며 정한 것 (스펙·시안에 없던 빈틈, 사용자 확인 대상):**
  1. 기간을 줄이거나 시작일을 옮기면 새 기간 밖의 칸은 지운다. 화면은 저장 전에 `기간 밖에 채운 칸 N개는 지워져요.`를 보여준다(채운 칸이 있을 때만).
  2. 장보기 미리보기는 오늘 이후 끼니만 계산한다(지난 끼니 재료를 오늘 사라고 하지 않게). 부제의 기간도 `max(오늘, 시작일)`부터.
  3. 식단 고르기 시트(제목 아래 `9월 셋째 주 ⌄`): 시안 프레임이 없어 기존 시트 모양으로 `식단 고르기` — 행마다 이름·기간(선택한 식단에 `check`), 맨 아래 `+ 새 식단 만들기`.
  4. `1달` 칩은 30일(스펙 `days(7 또는 30 등 1~31)`). `직접`은 1~31일 −/+.
  5. AI 초안은 한 번에 보고 있는 한 주(최대 7일, 28칸)만 채운다(시안 `기간 · 이번 주`). 출력이 길어지는 것을 막고 90초 안에 끝나게 한다.
  6. 숟가락 단위(`큰술`·`작은술`·`컵`·`꼬집` 등)나 `약간`처럼 양을 셀 수 없는 재료는 재고에 같은 이름이 있으면 `충분해요`, 없으면 `단위가 달라요 · 직접 골라주세요` 묶음(체크 없음, 담으면 `1개`)으로 보낸다. 간장 2큰술 때문에 간장 한 병을 자동으로 담지 않게.
  7. 식단은 사용자당 50개(목록은 페이지 없이 한 번에, 26절 표에 한 줄 추가).
  8. 칸의 `est_kcal`은 1인분 추정치(AI 초안으로 채운 칸만). 직접·레시피·영상으로 채우면 비운다.

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
- 레시피 탭 안 `양념 비율` 칸(추천 · 내 레시피 · 영상 · 양념 비율). 불고기·제육볶음·간장조림·초고추장·쌈장·갈비 양념 등 기본 양념을 제공하고 사용자가 추가·수정("내 비율").
- `seasonings`(사용자 "내 비율"만): id, user_id(NOT NULL, CASCADE), name(1~30자, UNIQUE(user_id, name)), basis(`main_weight`|`servings`|`yield`), basis_amount(예: 600), basis_unit(`g`|`인분`|`컵`|`ml`), main_ingredient(선택, `main_weight`일 때만, 예: `돼지고기`), items(JSON `[{name, amount(float), unit(`큰술`|`작은술`|`컵`|`ml`|`g`|`개`|`꼬집`)}]` 1~30개, 순서 = 표시 순서), created_at, updated_at. 사용자당 100개 (2026-09-14, 시안 승인).
- **기본 양념은 DB가 아니라 화면 데이터 파일**(`frontend/src/data/seasoningPresets.ts`, 출처 메모 포함) (2026-09-14, 시안 승인). ~~user_id NULL 기본 행, `source`·`source_note` 칸, `seasoning_items` 테이블~~ — 운영자가 바꾸는 고정값이라 시드·마이그레이션이 필요 없고, 줄은 3a `recipes.ingredients`처럼 JSON이 단순하다. 기본 양념을 고치려면 `이 비율 고쳐서 내 비율로`(복사).
- API: `GET/POST /api/seasonings`, `GET/PUT/DELETE /api/seasonings/<id>`.
- 기준(사용자 결정, 모두 지원): 주재료 무게당(예: 고기 100g당), 인분(예: 2인분), 완성량(예: 양념장 1컵).
- 계산: 입력량 ÷ basis_amount 배율로 각 재료 양을 늘리고 줄인다.
- **숟가락 단위(사용자 강조):** 기준은 계량스푼(1큰술 15ml, 1작은술 5ml, 1컵 200ml). 결과는 실제로 뜰 수 있는 분수로 반올림해 표시(¼·⅓·½·⅔·¾, 예: `3½큰술`, `⅓작은술`), 큰술이 너무 작으면 작은술로 자동 환산(1큰술 = 3작은술).
  집에서 쓰는 **밥숟가락 환산을 함께 표시** — 밥숟가락 1개 용량 기준치는 구현 시 출처를 확인해 정한다(확인 전 12ml).
  표시 (2026-09-14, 시안 승인): 계량 양을 굵게, 그 아래 회색 줄에 `밥숟가락 약 4개`(정수 반올림). 결과가 작은술이면 회색 줄에 큰술 환산(`1½작은술` / `½큰술`). ½컵(100ml) 이상은 컵, ¼작은술 미만은 `약간`.
- 기본 비율 수치는 레시피마다 차이가 크므로 구현 시 신뢰할 수 있는 출처 여러 곳을 비교해 정하고 `source_note`에 남긴다. "취향에 따라 조절" 안내.
  **출처 현황 (2026-09-14, 3c 태스크 1):** 밥숟가락 1개는 **시안 기준 12ml, 출처 미확인**(`seasoning.ts` `RICE_SPOON_ML`). 기본 양념 6개(제육볶음 돼지고기 600g, 불고기 소고기 600g, 간장조림 2인분, 초고추장 완성 ½컵, 쌈장 완성 ½컵, 갈비 소갈비 1kg)는 흔히 쓰는 집밥 비율로 넣은 **출처 확인 전 임시값**이다(`source_note`에 표시). 출처 두 곳 이상과 비교해 사용자 확인을 받으면 수치와 `source_note`(출처 이름·날짜)를 바꾼다.
- **화면 (2026-09-14, 시안 승인):** 목록은 `내 비율`이 `기본 양념` 위, 보조 줄에 기준(`돼지고기 600g 기준 · 재료 6개`, `2인분 기준`, `완성 ½컵 기준`), 아래 `내 비율 만들기`. 계산 화면은 `돼지고기 얼마나 써요?` + 배율 배지(`×1.5`) + −/+ 스테퍼 + 빠른 칩(`300g · 600g · 900g · 1kg · 1.2kg`), `양념 · 계량스푼 기준` 목록, 안내 `1큰술은 15ml예요. 밥숟가락은 집마다 달라서 대략으로 보여줘요. 입맛에 맞게 조절해주세요.`, 버튼 `이 비율 고쳐서 내 비율로`. 폼은 이름, `무엇을 기준으로 할까요?`(주재료 무게·인분·완성량), 기준 재료·양, 양념 줄(이름·양·단위 고르기·빼기), `재료 추가`, 하단 `취소`/`저장`.
- 연결: 레시피 재료로 가져오기(시안에 없어 3c 뒤로 미룸), 없는 양념 재료는 장보기 목록에 담기(4단계).

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
  단위가 다르거나 파싱 불가면 미리보기에 `있음 2개 · 필요 12개`처럼 보여 주고 사용자가 체크해 담는다. 20절의 "없는 것만"은 이 방식으로 대체한다. (구현: `app/amounts.py`·`meals.shopping_rows`)
- 공통 전제: 이름 매칭 오탐(짧은 이름) 수정은 지금 화면 개선(사용성 개선 단계)에서 `names_match` 한곳에 적용하므로 3·4·4b단계 매칭에도 그대로 쓰인다.
- 나머지 설계 발견(D6~D18)은 사용성 리포트 페이지에서 사용자가 체크하면 이 절에 추가한다.

## 24. 4b단계 추가: 먹은 기록 달력 (추가: 2026-09-13, 사용자 선택)
식단 탭(계획)과 분리한 음식 일기. 21절 `먹은 것 기록`을 달력으로 모아 본다.

- **위치:** 더보기 > `먹은 기록`(해시 경로 `#/food-log`). 식단 탭과 따로 둔다(사용자 결정).
- **월 달력:** 좌우로 달 이동, 오늘 강조. 날짜 칸에 그날 기록을 요약한다.
  - 사진이 있으면 첫 사진 썸네일, 없으면 끼니 수만큼 점.
  - 하루 kcal 합계. 추정값이 섞이면 `약 1,850kcal`처럼 표시.
  - 요리 기록이 있는 날은 작은 `요리함` 표시(5단계 연결 후).
- **날짜 상세(시트):** 끼니(아침·점심·저녁·간식)별 목록과 `+ 먹은 것 추가`.
  - 항목: 음식 이름, 양(인분 또는 g), kcal·당류(21절 계산, 추정이면 `추정`), 사진, 메모, 만족도.
  - 사진만 먼저 남기고 음식·양은 나중에 채울 수 있다(이름이 없으면 `사진 기록`으로 보여준다).
- **데이터(21절 `food_logs` 확장):** `photo_key`(선택), `memo`(≤200자, 선택), `rating`(1~5, 선택), `place`(`home`|`out`|null), `source`(`manual`|`meal_plan`|`cook_log`).
  - 사진 저장은 5단계 조리 기록 사진과 같은 방식(R2, 키가 없으면 로컬 `uploads/`), 조회는 소유자 확인 후(`/api/photos/<key>`).
  - 사진은 브라우저에서 긴 변 1568px JPEG로 줄여 올린다(2단계 스캔과 같은 처리). 파일 서명 검사·10MB 한도도 같다.
- **요리 기록 자동 표시(5단계):** `cook_logs`는 따로 저장하고, 달력 조회 때 같은 날짜에 합쳐 보여준다(중복 저장하지 않음).
  `요리했어요` 폼에 `먹은 기록에도 남기기`(기본 켜짐)를 두어 켜면 `food_logs`(source `cook_log`, place `home`)를 함께 만든다.
- **월 요약:** 달력 위에 이번 달 기록한 날 수, 하루 평균 kcal(기록한 날 기준), 집밥/외식 비율(`place` 기준, 미지정 제외).
- **개인정보:** 사진·먹은 기록은 본인만 조회, 계정 삭제 시 함께 삭제. 의료 조언이 아니라 참고용 문구는 21절과 같다.
- **순서:** 달력·먹은 기록·사진·메모·만족도는 4b단계에서 만들고, 요리 기록 합치기는 5단계에서 연결한다.

## 25. 수익화 방향 (추가: 2026-09-13, 기획만 — 구현하지 않음)

순서: 배포 → AI 원가 측정(`ai_calls` 토큰, 구현됨) → 4단계에서 제휴 링크(16절) → 아래 두 가지는 조건이 되면 그때 설계한다.

- **구독 결제** — 매주 쓰는 사용자가 생기면 붙인다.
  - 무료/유료 경계는 **AI 한도**(스캔·AI 레시피·식단 AI 횟수)로 둔다. 비용이 드는 곳이 경계다. 레시피 등록 개수 제한은 원가가 거의 없고 초기 사용자를 떠나게 해서 쓰지 않는다.
  - 유료 후보: AI 한도 상향, 식단 AI 초안·1달 달력(4b), 가족 공유 냉장고(13절 범위 밖에서 승격).
  - 가격은 `ai_calls` 토큰으로 사용자당 월 AI 원가를 잰 뒤 정한다. 무료 한도(지금 스캔·레시피 하루 10회)도 그때 다시 정한다.
  - 웹(PWA) 결제대행(토스페이먼츠·포트원 등)이라 앱스토어 수수료가 없다. 필요: 사업자등록, 통신판매업 신고, 환불 규정, 개인정보처리방침.
- **식품 브랜드 협찬 레시피** — 사용자가 더 모이면 제안한다. 추천 목록에 `광고` 표시를 달고 섞는다.
- 하지 않음: 배너 광고(수익 적고 디자인 방향과 안 맞음), 사용자 재고·식습관 데이터 판매.
- 유료화 전에 확인: 식약처 공공 레시피 상업 이용 조건·출처 표시, 유튜브·인스타그램 가져오기는 링크·요약만(본문·사진 저장 안 함), `갈무리부엌` 상표(KIPRIS).

## 26. 목록 페이지네이션·무한 스크롤 (추가: 2026-09-13, 사용자 요구, 3a fix round 1)

목록마다 크기와 쓰임에 맞춰 페이지 방식을 고른다.

| 목록 | 최대 크기 | 방식 |
|---|---|---|
| 추천(공공 레시피) | ~1,100 | 서버 페이지(offset) + 무한 스크롤, 20개씩 |
| 추천(내 레시피 섹션) | 1,000 | 첫 응답에 상위 10개만, 더 있으면 "내 레시피에서 더 보기" 링크 |
| 내 레시피 | 1,000 | 서버 커서 페이지 + 무한 스크롤, 30개씩 |
| 재고 | 2,000 | 서버는 전체(검색·필수품 매칭·요약에 필요), 화면은 50개씩 점진 렌더(무한 스크롤) |
| 주방 도구·보관 위치·필수품·품목별 규칙 | 수십 개 | 페이지 없음 |
| 장보기 목록·메모 (2026-09-14, 시안 승인) | 목록 300개(산 것 제외)·메모 20개 | 페이지 없음 — 오프라인에서 전체를 기기에 보관하고 날짜 묶음을 화면에서 만들어야 해서 한 번에 받는다(16·19절) |
| 식단 목록 (2026-09-14, 4b-1 Task 1) | 50 | 페이지 없음 |
| 앞으로(먹은 기록·조리 기록) | 커짐 | 서버 커서 페이지 + 무한 스크롤을 기본으로 한다 |

무한 스크롤은 항상 접근성 대안을 둔다: 목록 끝에 보이는 `더 보기` 버튼(IntersectionObserver가 화면에 들어오면 자동으로 불러오고, 버튼은 그것 없이도 동작), 불러오는 중 표시, 끝 상태(`다 봤어요`, 한 페이지에 다 들어가면 숨김), 오류 시 `다시 불러오기`.

**백엔드(3a fix round):**

- `GET /api/recommendations`: `section`(`all` 기본 | `public`), `offset`(0 이상, 기본 0, 음수는 0으로), `limit`(1~50, 기본 20). `section=all`이면 `{mine: 내 레시피 상위 10개, mine_total, public: public[offset:offset+limit], public_total, next_offset, sample, inventory_count}`. `section=public`이면 `mine`·`mine_total` 없이 공공 레시피만 계산한다(내 레시피는 아예 계산하지 않는다). `next_offset`은 더 있으면 `offset+limit`, 없으면 `null`.
  - **사용자별 순위 캐시**(재고가 클수록 매 요청 계산 비용이 커지는 문제 해결): 서명(오늘 날짜, 재고 이름·임박 여부, 내 레시피 개수·최대 id·최신 수정 시각, 공공 레시피 개수·최대 id·최신 수정 시각)이 그대로면 120초(TTL) 안에는 다시 계산하지 않는다. 프로세스별 캐시이고(여러 인스턴스로 늘면 Redis로 옮긴다), 500명분을 넘으면 오래된 것부터 지운다.
- `GET /api/recipes`(내 레시피 목록): `limit`(1~50, 기본 30), `cursor`(불투명 문자열, 잘못됐으면 400). `updated_at`·id 내림차순 커서 페이지. 응답 `{items:[...], next_cursor}`(이전의 배열 응답에서 바뀜).

**화면(3a 세 번째·네 번째 작업에서 연결):** `useInfiniteList` 훅과 `InfiniteSentinel` 컴포넌트로 공통화한다. 추천 탭은 첫 화면에서 `section=all`, 이후 `section=public`+offset으로 더 불러온다. 내 레시피 탭은 커서로 이어 붙인다.

## 27. 더보기 구성 (추가: 2026-09-14, 사용자 선택)
재고 화면 톱니바퀴 안에 숨어 있던 설정과 앞으로 생길 기능을 더보기에 묶음별로 모은다. 묶음 제목은 작은 회색 글씨, 항목은 기존 목록 행(아이콘·제목·한 줄 설명·오른쪽 화살표).

| 묶음 | 항목 | 만드는 시점 |
|---|---|---|
| **기록** | 먹은 기록(24절 달력) · 요리 기록(5단계) · 집밥 리포트 | 4b · 5 · 집밥 리포트는 5단계 뒤 |
| **우리 부엌** | 보관 위치 · 필수품 · 품목별 경고 · 주방 도구 | 지금 있는 기능 — 3a 다음 정리 작업에서 옮김 |
| **나** | 내 몸 정보·목표(21절) · AI 사용량(오늘 사진 인식 N/10회, AI 레시피 N/10회) | 4b · AI 사용량은 3b |
| **함께** | 가족과 함께 쓰기(기획만) · 친구 초대 · 의견 보내기 | 친구 초대·의견은 배포 무렵, 가족은 기획만 |
| **앱** | 홈 화면에 앱 설치(있음) · 화면 테마(시스템/밝게/어둡게) · 알림 설정(임박 재료) · 데이터 내보내기(재고·내 레시피·내 양념 비율·장보기) | 테마·내보내기는 3a 다음 정리 작업, 알림은 배포 후 |
| **도움말·정보** | 사용 방법 · 공지 · 문의하기 · 이용약관 · 개인정보처리방침 · 데이터 출처 · 앱 정보(버전) | 배포 전 |
| **계정** | 로그인 계정(카카오/네이버/구글 표시) · 로그아웃 · 회원 탈퇴 | 로그아웃 이동은 정리 작업, 탈퇴는 배포 전 |

- **재고 화면 톱니바퀴:** 우리 부엌 묶음으로 옮긴 뒤에는 재고 화면에서 `보관 위치`·`필수품` 바로가기만 남기고(자주 씀), 나머지는 더보기로 보낸다.
- **AI 사용량:** `ai_calls`에서 오늘(서울 날짜) 묶음별 횟수와 한도를 보여준다. 원가(토큰)는 사용자에게 보여주지 않는다.
- **화면 테마:** 기본은 시스템 설정을 따른다. 사용자가 고르면 기기에 저장(localStorage)하고 `<html data-theme>`로 적용한다. 서버 저장은 하지 않는다.
- **데이터 내보내기:** 재고·내 레시피·내 양념 비율·장보기(목록·최근 산 것·메모)를 CSV로 묶어 내려받는다(zip 하나). 먹은 기록·요리 기록은 기능이 생기면 추가한다. 사진은 넣지 않는다(레시피 사진 주소, 메모 사진 파일 이름만 적는다). 하루 5회 제한.

- **집밥 리포트(월간, 이름 2026-09-14 사용자 결정):** 이번 달 기록한 날, 요리한 횟수, 집밥/외식 비율(24절), **버린 재료 수**, **아낀 돈**. 버린 재료를 세려면 재료를 지울 때 이유(`다 먹었어요`/`버렸어요`)를 고를 수 있게 한다(선택, 기본은 이유 없음).
- **아낀 돈(추가 2026-09-14, 사용자 제안·선택):** 요리 기록(5단계) 한 건마다 `사 먹으면 얼마 − 집밥 재료비 = 아낀 돈`을 계산해 집밥 리포트에서 합산한다. 예: "이번 달 집밥 12번으로 약 86,000원 아꼈어요 · 부대찌개 12,000원 − 재료비 4,300원 = 7,700원".
  - **사 먹으면 얼마(외식 가격) 우선순위:** ① 레시피에 사용자가 직접 입력한 값(`recipes.eat_out_price`, 원, 선택) → ② 한국소비자원 참가격 외식비(대표 외식 8품목 지역별 평균, 레시피 이름이 품목과 맞을 때, 월 1회 캐시) → ③ AI 추정(레시피 이름·인분으로 요즘 외식 가격 추정, 결과를 레시피에 저장해 다시 묻지 않음, AI 일일 한도 recipe 그룹). ②③은 화면에 `참가격 평균`/`추정` 표시. 배달앱 가격은 공개 API가 없어 쓰지 않는다. 참가격 API 이용 조건은 구현 시 확인.
  - **집밥 재료비:** 재료의 구입 가격(`ingredients.price`, 원, 선택)을 **사용량 비율**로 나눈다(예: 깐마늘 300g 4,980원 중 30g → 498원, 단위가 같을 때 `사용량 ÷ 구입 수량`). 가격이 없으면 KAMIS(농산물유통정보) 소매가격으로 추정(`추정` 표시, 채소·과일·축산물 위주, 이용 조건 구현 시 확인). 둘 다 없거나 단위가 달라 비율을 못 구하면 그 재료는 `가격 모름`으로 빼고, 결과에 "재료 N개 가격 제외"를 함께 보여준다. 양념 등 조금 쓰는 재료(조미료 분류 필수품)는 기본 제외.
  - 아낀 돈이 0 이하이면(사 먹는 게 더 싸면) 그대로 보여주되 합계에서 음수도 반영한다. 의료·재무 조언이 아닌 참고용 표시.
  - **가격 수집(선행, 사용자 결정 "지금 넣기"):** 영수증·주문 캡처 스캔이 품목별 **결제 금액**(할인 반영 후 가능하면)을 함께 읽어 `ingredients.price`로 저장한다. 확인 화면에서 가격을 보고 고칠 수 있고, 직접 추가·수정 폼에도 가격(선택) 칸을 둔다. 냉장고 사진 스캔은 가격이 없다. 3a 레시피 작업 사이에 별도 작은 작업으로 넣는다.
- **가족과 함께 쓰기(기획만):** 초대 코드로 한 냉장고(재고·필수품·장보기)를 여러 계정이 함께 쓰는 구조. 데이터 소유가 사용자 단위에서 `household` 단위로 바뀌는 큰 변경이라 지금은 설계만 적고 구현하지 않는다. 필요해지면 별도 설계를 먼저 쓴다.
- **친구 초대:** 공유 시트(Web Share API, 안 되면 링크 복사)로 앱 주소를 보낸다. 보상·추적은 하지 않는다.
- **의견 보내기:** 짧은 글(≤1000자)과 선택 사진 1장, 앱 버전·기기 정보(브라우저 UA)를 함께 보낸다. 서버 `feedback` 테이블에 저장하고 하루 5회 제한.
- **데이터 출처:** 식약처 조리식품 레시피 DB·식품영양성분 DB, 유튜브 등 사용하는 공공·외부 데이터의 이름과 이용 조건 링크를 표시한다(25절 유료화 전 확인 사항과 연결).
- **회원 탈퇴:** 확인 문구 입력 후 계정과 모든 사용자 데이터(재고·레시피·기록·사진·AI 호출 기록)를 삭제한다. 소셜 로그인 연결 해제(카카오·네이버·구글 API)도 시도하고, 실패해도 우리 쪽 데이터는 지운다. 사진 파일(R2·로컬 `uploads/`의 `shopping/<user_id>/` 등)은 DB CASCADE로 지워지지 않으므로 탈퇴 처리에서 접두사로 따로 지운다(2026-09-14, 4단계에서 사진 저장 시작). 삭제는 되돌릴 수 없다고 명확히 안내한다(삭제 버튼 규칙: 연빨강 배경·테두리).

### 정리 작업 결정 (추가: 2026-09-14, 시안 승인)
- **아직 없는 기능은 만들 때 넣는다.** 표의 항목 중 기능이 없는 행(먹은 기록·요리 기록·집밥 리포트·알림 등)은 지금 더보기에 자리만 만들지 않는다.
- **재고 화면 톱니바퀴:** `보관 위치`·`필수품`만 남긴다.
- **재료 삭제 이유:** 삭제 확인에서 `다 먹었어요`/`버렸어요`를 고른 뒤 지운다(선택, 안 고르면 이유 없이 삭제). 서버는 `DELETE /api/ingredients/<id>?reason=eaten|discarded`로 받아 `ingredient_removals`(4절)에 이름·이유를 남긴다.
- **내보내기 내용:** 지금은 재고·내 레시피·내 양념 비율·장보기. 먹은 기록·요리 기록은 기능이 생기면 CSV를 추가한다. `GET /api/export/summary`·`GET /api/export`(5절).
  - `ingredients.csv`: 이름, 수량, 단위, 보관 위치, 구입일, 유통기한, 가격(원)
  - `recipes.csv`(레시피 한 줄): 제목, 인분, 재료(`두부 1모; 대파 1/2대`), 만드는 법(칸 안 줄바꿈 `1. …`), 출처, 출처 링크, 사진 주소(주소만, 사진 파일은 넣지 않음)
  - `seasonings.csv`: 이름, 기준, 기준 양, 기준 단위, 주재료, 양념(`고추장 2큰술; 설탕 0.5큰술`)
  - `shopping.csv`: 이름, 수량, 단위, 생활용품(`예`/빈칸, 2026-09-14 사용자 결정), 살 날, 넣을 위치, 체크, 산 날(재고에 넣은 날), 출처, 출처 이름, 담은 날. 목록(산 것 아님)과 최근 7일 안에 산 것(28절 `STOCKED_KEEP_DAYS`)만 담는다.
  - `shopping_memos.csv`: 장소, 메모, 사진 수, 사진 파일 이름(파일 이름만 `;`로 이어 붙임, 사진 바이트는 넣지 않음), 고친 시각
  - 엑셀 수식 주입 방지: `=` `+` `-` `@` 탭·CR(전각 `＝＋－＠` 포함, 앞 공백은 건너뛰고 봄)로 시작하는 칸은 앞에 `'`를 붙인다. 숫자는 정수면 정수로, 아니면 반올림 없이 적는다.
  - 하루 5회는 `ai_calls.kind = export`로 세고(AI 사용량·원가에 안 셈), 한도에 걸린 요청은 기록하지 않는다. 기록은 zip을 만들기 전에 하므로 만들다 실패해도 한 번으로 센다.
  - 두 API 모두 GET이지만 한도를 쓰므로 `X-Requested-With: fetch`가 없으면 400(다른 사이트 링크로 한도를 쓰지 못하게). 응답은 `Cache-Control: no-store`·`X-Content-Type-Options: nosniff`.

## 28. 4단계 구현 세부 (추가: 2026-09-14)

### 장보기 항목 (Task 1)
- 테이블 `shopping_items`(16절). UNIQUE(user_id, client_id) — client_id가 NULL인 행끼리는 겹쳐도 된다. `location_id`는 보관 위치를 지우면 DB가 NULL로 바꾼다(`locations.delete_location`은 재료만 막는다). 사용자 삭제 때 CASCADE.
- 상한: 사용자당 목록 **300개**(`stocked_at`이 있는 산 것은 세지 않음), 넘으면 400 `장보기 목록은 300개까지 담을 수 있어요. 필요 없는 항목을 빼주세요.` 일괄 담기는 건너뛴 것을 뺀 **만들 개수**로 센다. PostgreSQL은 사용자별 트랜잭션 잠금(`pg_advisory_xact_lock`)으로 client_id 확인·개수 확인·추가를 한 줄로 세운다. 가득 차도 이미 있는 `client_id`를 다시 보내면 그 항목 200. 산 것은 따로 300개(`MAX_STOCKED_ITEMS`) — 산 것을 만드는 Task 2 재고에 넣기에서 넘으면 오래된 산 것부터 지운다.
- `GET /api/shopping` → `{items, stocked, notes, today}`. `items`는 산 것이 아닌 항목(created_at·id 오름차순, 날짜 묶음은 화면이 만든다), `stocked`는 최근 7일 산 것(stocked_at 내림차순), `notes`는 장보기 메모(updated_at·id 내림차순, 사진 포함), `today`는 서울 날짜. 요청 때 7일 지난 산 것과 하루 넘은 빈 메모(19절)를 먼저 지운다(크론 없음). 응답은 `Cache-Control: no-store`.
- 항목 모양: `{id, client_id, name, quantity, unit, planned_on, location_id, location_name, source, source_label, household, done_at, done_changed_at, stocked_at, created_at}`.
- **생활용품 `household` (2026-09-14, 사용자 결정, 마이그레이션 `c2h2o2u2s2e2`):** 추가·일괄 담기 줄은 `household?`(참/거짓, 아니면 400 `잘못된 요청이에요.`)를 받고, 안 보내면 `is_household(name)`(이름을 `normalize`한 뒤 낱말 목록: 두 글자 이상은 포함, 한 글자 `랩`은 같을 때만 — `크랩`은 식품). 고치기(PATCH)는 보낼 때만 바꾸고 이름을 바꿔도 다시 짐작하지 않는다(체크 모양과 섞으면 400). 짐작 목록은 틀릴 수 있어(`수세미오이` 등) 재고에 넣기에서 줄마다 바꾼다. 메모 스캔(`kind=memo`)만 스키마 `MemoScanResult`(줄마다 `household: bool`)로 부르고, `clean_result`가 참/거짓이 아닌 값은 이름으로 짐작한다. fridge·receipt·order 응답에는 `household`가 없다.
- `POST /api/shopping/items` `{name, quantity?, unit?, planned_on?, location_id?, source?, source_label?, client_id?}` → 201. 같은 사용자에게 같은 `client_id`가 있으면 새로 만들지 않고 그 항목을 200으로 돌려준다(오프라인에서 다시 보내도 하나). `client_id`가 있는 요청(기기에서 담은 것)의 위치가 그사이 지워졌거나 내 것이 아니면 400 대신 위치를 비우고 담는다 — 오프라인에서 담은 것을 잃지 않게. `client_id`가 없는 요청과 일괄 담기는 400 그대로.
  - 검증: 이름 1~50자 `이름은 1~50자로 입력해주세요.` · 수량은 0보다 큰 숫자(참/거짓·문자열 불가) `수량은 0보다 커야 해요.` · 단위 10자(비면 `개`) · 날짜 `YYYY-MM-DD` `날짜 형식이 올바르지 않아요.` · source는 `manual|recipe|staple|urgent|meal_plan|memo`(기본 manual) · source_label 60자 `출처 이름은 1~60자로 입력해주세요.`(공백뿐이면 비움) · 남의/없는 위치 `보관 위치를 다시 선택해주세요.` · client_id는 1~36자 영문·숫자·`-`. 그 밖의 모양 오류는 `잘못된 요청이에요.`
- `POST /api/shopping/items/bulk` `{source, source_label?, items:[{name, quantity?, unit?, planned_on?, location_id?}] 1~50}` → 201 `{created:[…], skipped:["대파"]}`. 목록에 있는 항목(체크했어도, 산 것 제외)과 `names_match`되는 이름, 요청 안에서 앞 항목과 겹치는 이름은 건너뛴다. 하나라도 틀리면 아무것도 만들지 않고 400 `{error: "N번째 재료: …", errors:[{index, error}]}`. 불러온 뒤 위치가 지워지면 400 `선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요.`
- `PATCH /api/shopping/items/<id>` 두 모양(섞거나 체크 모양이 틀리면 400 `잘못된 요청이에요.`):
  - 고치기 `{name?, quantity?, unit?, planned_on?, location_id?}` — 보낸 칸만, 도착 순서대로 덮어쓴다. `planned_on`·`location_id`는 null로 비운다.
  - 체크 `{done: bool, changed_at: 시간대가 붙은 ISO 시각(`Z` 가능)}` — 행을 잠그고(PostgreSQL `FOR UPDATE`) 비교한다. `changed_at`이 저장된 `done_changed_at`보다 이르거나 항목을 만든 시각보다 하루 넘게 이르면(틀린 기기 시계) 바꾸지 않고 현재 항목을 200. 같은 시각이면 나중에 도착한 것을 따른다. 아니면 `done_at = done ? changed_at : null`, `done_changed_at = changed_at`. 서버 시각보다 10분 넘게 미래면 서버 시각으로 자른다(그래서 잘린 체크가 그 뒤 몇 분 안의 더 이른 기기 시각 변경을 이길 수 있다). 기기 시계 차이만큼 순서가 틀릴 수 있다(허용, 문제되면 서버 수신 순서로).
- `DELETE /api/shopping/items/<id>` → 204. 남의 것·없는 것은 PATCH·DELETE 모두 404. 산 것(`stocked_at` 있음)은 PATCH 404(`다시 담기`는 새로 추가).

### 서비스 워커·기기 저장소 (Task 7, `frontend/public/sw.js`, `src/shopping/idb.ts`·`useShopping.ts`)
- **화면 파일 미리 받기:** 빌드 끝에 `vite.config.ts` 플러그인(`scripts/sw-precache.mjs`, 검사 `check-sw-precache.mjs`)이 `dist` 파일 전체(`index.html`은 `/`, `sw.js`·소스맵 제외) 목록과 이름·내용 해시를 `dist/sw.js`의 `VERSION`·`PRECACHE`에 넣는다. 캐시 이름 `galmuri-shell-<해시>` — 화면 파일이 하나라도 바뀌면 새 캐시(sw.js만 바뀌면 이름 그대로), activate 때 옛 `galmuri-shell-*`를 지워 배포마다 쌓이지 않는다. 개발 서버에서는 목록이 비어 `/`만 캐시한다.
- **가로채기:** 화면 이동은 네트워크 우선 → 실패하거나 3초 안에 응답이 없으면 캐시한 `/`(캐시도 없으면 네트워크를 끝까지 기다림). 미리 받은 같은 오리진 파일은 캐시 우선. `/api`·`/auth`·GET 아닌 요청은 가로채지 않는다(데이터는 IndexedDB).
- **글꼴:** `fonts.googleapis.com` CSS는 stale-while-revalidate, `fonts.gstatic.com` 파일은 캐시 우선, `galmuri-fonts-v1`(배포와 무관하게 유지, 200개 넘으면 먼저 넣은 것부터 삭제). CSS 링크에 `crossorigin`을 붙여 CORS 응답으로 받는다(opaque 응답은 크롬 저장 용량 계산에서 크게 부풀려져 IndexedDB까지 밀어낼 수 있다 — opaque도 받아는 준다). 첫 방문 페이지는 서비스 워커가 아직 없어 그다음 방문부터 보관된다.
- **새 버전:** 설치 때 `skipWaiting`하지 않는다. 화면이 숨겨질 때(앱을 떠날 때) `SKIP_WAITING` 메시지로 바꾸고, 다음에 열면 새 화면.
- **기기 저장소 `idb.ts`:** DB `galmuri` v1, `kv`(`me`·`snapshot`·`queue`·`failed`·`backups`)·`blobs`(사진, 기기에서 찍은 것 `local:<client_id>` → 올린 뒤 `photo:<서버 id>`, 새로 받은 뒤 스냅숏·대기열이 가리키지 않는 `photo:*`는 삭제). kv에 `owner`(로그인 방법+id)·`fetched_at`도 둔다. 못 열거나(`onblocked` 포함) 쓰기가 실패한 값만 메모리에 둔다(앱을 닫으면 사라짐). `onversionchange`면 닫고 다음에 다시 연다.
- **`useShopping`:** 모듈 상태 + 구독. 보내기는 위 약속 그대로 한 번에 하나(`markAttempt` 저장 뒤 보냄 → `classify` → ok면 `applyServerResult`·`remapRef`·`removeOp`, drop이면 `dropWithDependents` + 실패 목록, 409·404 메모 충돌이면 기기 내용을 `backups`에, 5xx면 `markServerError`, 401이면 멈춤). 요청 모양은 `opRequest`(순수, 검사 있음). 트리거: 로그인 확인 뒤 앱 시작, `online`, 화면이 다시 보일 때, 변경 직후, 다시 시도(`retryDelay` 2초부터 두 배·5분까지). 앱 열기·다시 보일 때 `GET /api/shopping`은 60초에 한 번(`shouldRefresh` — 대기열이 있거나 장보기 화면이 열려 있거나 보낸 직후면 늘). 탭 여러 개: Web Locks `galmuri-shopping`(기기 저장소를 다시 읽고 고치고 저장, qid도 여기서) · `galmuri-shopping-send`(보내기·새로 받기는 한 탭만). Web Locks가 없으면 잠그지 않는다(`ponytail:`). `navigator.onLine`이 false면 보내지 않는다(보낸 횟수가 붙으면 뒤 변경과 합칠 수 없어서). 대기열이 비면 새로 받고, 받는 사이 서버에 반영된 변경이 있으면 받은 것은 버린다.
- **오프라인으로 열기(App):** `/api/me` 성공 → 기기에 기억. 기기 데이터 주인(`owner`: 로그인 방법+id)이 다르면 기기 장보기 데이터를 먼저 모두 지운다. 네트워크 0이나 5xx이고 기억한 사용자가 있으면 그 사용자로 연다(없을 때만 `서버에 연결할 수 없어요.`).
- **401(세션 만료):** 로그인 화면으로 가고 보내기를 멈추며 기억한 사용자(`me`)만 지운다. 대기열·목록·사진은 `owner`와 함께 남아 **같은 사람이 다시 로그인하면 이어서 보낸다**(다른 사람이면 위 규칙대로 지움). **직접 로그아웃:** 못 보낸 변경이 있으면 `보내지 않은 변경 N개가 사라져요. 로그아웃할까요?`로 확인한 뒤 기기 데이터를 모두 지운다.

### 오프라인 장보기 순수 로직 (`frontend/src/shopping/sync.ts`, 검사 `scripts/check-shopping-sync.mjs`)
- 브라우저 API·현재 시각을 부르지 않는 순수 함수만 둔다(시각·client_id는 인자). IndexedDB·보내기(Task 7)가 이 위에 얹힌다.
- **대기열 합치기(`enqueue`):** 같은 대상 체크는 마지막 것만 / 안 보낸 추가 뒤 고치기는 추가에 합치고 체크는 뒤에 그대로 / 안 보낸 추가(메모 추가) 뒤 삭제는 그 대상 변경을 모두 지우고 삭제도 보내지 않음(메모 사진 blob도 버림) / 서버에 있는 대상 삭제는 앞의 고치기·체크(메모면 저장·사진)를 지우고 삭제만 보냄 / 같은 메모 저장은 마지막 내용·`edited_at` 하나(안 보낸 메모 추가면 거기에 합침) / 안 보낸 사진 추가 뒤 그 사진 삭제는 둘 다 없앰. 합친 변경은 처음 자리, 나머지는 들어온 순서.
  **한 번이라도 보낸 변경(`attempts`)은 합치거나 바꾸거나 지우지 않는다** — 서버에 닿았는데 응답만 못 받았을 수 있다(보낸 추가는 서버가 `client_id`로 기존 항목만 돌려주고 내용을 무시하므로, 뒤 고치기·삭제는 따로 보내고 추가 성공 뒤 서버 id로 바꿔 보낸다).
- **화면용 목록(`applyQueue`):** 스냅숏 위에 대기 변경을 얹고, 안 보낸 항목·메모·사진은 `pending`. 서버에 이미 같은 `client_id`가 있으면(보냈지만 응답을 못 받음) 다시 만들지 않는다. 서버의 `done_changed_at`이 기기 체크 시각보다 늦으면 서버가 무시하므로 화면도 서버 값. 메모는 `updated_at` 내림차순.
- **보내기 순서:** 맨 앞 하나를 보낸 횟수를 저장한 뒤 보낸다. 대기열 안 번호(`qid`)로 찾고 뺀다(자리로 찾지 않음). 성공하면 응답을 스냅숏에 반영(`applyServerResult`, 안 하면 새로 받을 때까지 화면에서 사라짐)하고, 추가였으면 뒤 변경의 `client_id` 참조를 서버 id로 바꾼다(`remapRef`).
- **보낸 결과(`classify`):** 2xx ok / 네트워크 0·408·429는 끝없이 다시 시도(멈춤) / 5xx는 5번째까지 다시 시도, 그 뒤 실패 목록 / 401 멈춤 / 체크·삭제의 404는 이미 없으니 ok / `note_save` 409(다른 기기가 먼저 고침)·404(다른 기기가 지움)는 충돌 / 사진 추가 503(사진 저장소 꺼짐)과 나머지 4xx는 실패 목록. 실패로 버린 추가는 그 대상을 가리키는 뒤 변경도 함께 뺀다(`dropWithDependents`, 사진 blob도 버림) — 실패 목록은 화면에 보여준다.
- **client_id:** `newClientId()` — `crypto.randomUUID`(보안 컨텍스트), 없으면 같은 모양의 대체값. 서버 형식 `[A-Za-z0-9-]{1,36}`.
- **메모 충돌(19절):** 충돌(409·404)이면 호출 측이 기기에서 쓴 내용을 기기에 따로 보관하고 서버 메모를 받아들인다. 기기 `edited_at`이 더 늦으면 서버가 받아들이므로 충돌이 아니고, 그때는 보내기 직전 스냅숏 본문(덮어쓴 서버 쪽)을 한 번 남긴다.
- **날짜 묶음(`groupItems`):** 서울 날짜 문자열로 `planned_on ≤ 오늘` 오늘(지난 날짜 포함) · `≤ 오늘+6` 이번 주 · 그 뒤 나중에 · 없음 날짜 미정. 묶음 안은 날짜·만든 시각 순, 체크는 자리에 영향 없음, 빈 묶음은 뺀다. `이번 주` 칩은 오늘+6으로 저장.
- **수량 한 칸(`parseQuantityText`):** `1모`·`30구`·`½봉`·`1/2대`, 숫자만이면 `개`, 단위만이면 1. 숫자 범위는 양념 입력과 같다(0.01~10000), 단위 10자까지. 표시(`quantityText`)는 되읽어도 같은 값.

### 장보기 메모·사진 (Task 3)
- 테이블 `shopping_notes`(id, user_id CASCADE, client_id, place ≤30, body Text ≤2000, created_at, updated_at, UNIQUE(user_id, client_id)), `shopping_note_photos`(id, note_id CASCADE, client_id, photo_key UNIQUE, size(바이트), created_at, UNIQUE(note_id, client_id)). 사용자당 메모 20개, 메모당 사진 10장, 사진 한 장 3MB, 사용자당 사진 합계 200MB.
- 메모 모양 `{id, client_id, place, body, updated_at, photos:[{id, client_id, url: "/api/photos/<key>"}]}`.
- `POST /api/shopping/notes` `{place?, body, client_id?, edited_at?}` → 201(같은 `client_id`면 그 메모 200, 가득 차도). body는 문자열(빈 문자열 허용, 앞뒤 공백 그대로 — 자동 저장 중인 글, NUL 글자는 400 — PostgreSQL이 받지 않아 기기가 끝없이 다시 보내지 않게), place는 앞뒤 공백을 빼고 비면 null. `edited_at`(시간대가 붙은 ISO 시각)을 주면 `updated_at`이 그 시각 — 오프라인에서 만들고 고친 메모가 늦게 도착한 만들기 때문에 409가 나지 않게. 오류: `메모는 20개까지 둘 수 있어요.` · `메모는 2000자까지 쓸 수 있어요.` · `장소는 30자까지 입력해주세요.` · 그 밖의 모양 `잘못된 요청이에요.`
- `PUT /api/shopping/notes/<id>` `{place?, body, edited_at}` → 서버 `updated_at`이 `edited_at`보다 늦으면 409 `{error: "다른 기기에서 먼저 고친 메모가 있어요.", note}`(바꾸지 않음, 기기는 자기 글을 따로 보관 — 19절). 아니면 place·body를 바꾸고 `updated_at = edited_at`(같은 요청을 다시 보내도 200). `edited_at`이 10분 넘게 미래면 서버 시각. 기기 시계 비교라 체크와 같은 한계. 사진 추가·삭제는 `updated_at`을 바꾸지 않는다.
- `DELETE /api/shopping/notes/<id>` → 204. 사진 올리기와 같은 사용자 잠금을 먼저 잡고 사진 목록을 읽어, 커밋 뒤 사진 파일 삭제(실패는 로그만).
- `POST /api/shopping/notes/<id>/photos` multipart `image`, `client_id?` → 201 사진 모양(같은 `client_id`면 200). 순서: 저장소가 로컬이 아니면 503 `사진을 지금은 올릴 수 없어요.` → 남의/없는 메모 404 → 10MB 초과 413 → 사진 없음 400 `사진을 올려주세요.` → 3MB 초과 413 `사진이 너무 커요.` → 서명이 JPG·PNG·WEBP 아님 415 `사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.` → 10장 400 `사진은 메모 하나에 10장까지 넣을 수 있어요.` → 사용자 합계 200MB 초과 400 `사진 저장 공간이 가득 찼어요. 오래된 메모 사진을 지워주세요.` → 키 `shopping/<user_id>/<uuid4 hex>.<jpg|png|webp>`(확장자는 서명으로) 저장 → 행 커밋(실패하면 방금 저장한 파일 삭제). EXIF는 서버가 지우지 않는다 — 화면(Task 10)이 캔버스로 다시 인코딩해 올려 빠진다(필요하면 나중에 서버에서 다시 저장).
- `DELETE /api/shopping/notes/<id>/photos/<photo_id>` → 204, 커밋 뒤 파일 삭제. 다른 메모의 사진 id는 404.
- 저장소 `app/storage.py`: `mode()` — R2 값 네 개가 모두 있으면 `r2`, 없고 `DEV_MODE`면 `local`, 아니면 `off`(닫힌 쪽이 기본)(`local`은 `backend/uploads/`, 키는 `safe_join`으로 `..`·앞 `/` 거부). R2는 boto3(`put_object`·`delete_objects`·`get_object` 스트리밍, 연결 3초·읽기 10초, 한 번 다시 시도). R2 오류는 올리기 503 `사진을 지금은 올릴 수 없어요.`, 보기 503, 지우기는 로그만(키·비밀값은 로그에 남기지 않음). `off`는 사진 올리기·보기 503. (2026-09-14 연결)
- 회원 탈퇴 때 `shopping/<user_id>/` 파일을 따로 지운다(27절, 탈퇴 태스크).

### 재고에 넣기 (Task 2)
- `GET /api/shopping/stock-draft` → `{purchased_on: 오늘(서울), items:[{id, name, quantity, unit, household, location_id, location_reason}]}`. 체크했고(`done_at` 있음) 아직 안 넣은(`stocked_at` 없음) 항목만, 목록 순서(created_at·id). 위치 프리필(23절 D3)과 이유: 항목에 정한 위치 `item` → 이름을 `normalize`한 값이 같은 재료 중 가장 최근에 만든 것의 위치 `same_name`(시안 `같은 이름 재료가 있던 곳`, 예: 재료 `대파 (국산)` ↔ 항목 `대파`) → 첫 냉장 위치(없으면 첫 위치) `default` → 보관 위치가 하나도 없으면 `location_id: null`·`none`(화면이 위치를 고르게 한다). 응답은 `Cache-Control: no-store`.
- `POST /api/shopping/items/stock` `{purchased_on, items:[{id, name, quantity, unit, location_id}] 1~300}`(체크한 항목은 목록 상한 300개까지 있을 수 있어 한 번에, 재료 2000개 상한은 그대로) → 201 `{created: N}`. 산 날은 하나(`YYYY-MM-DD`, `날짜 형식이 올바르지 않아요.`, 오늘보다 뒤면 `산 날은 오늘보다 뒤일 수 없어요.`). 시안 `StockIn`에 유통기한·가격 칸이 없어 그 칸은 보내도 무시한다(`유통기한은 재고에서 고칠 수 있어요`). 한 트랜잭션에서 차례로:
  1. 사용자 잠금(`pg_advisory_xact_lock`) → 항목 행 잠금(id 순, PostgreSQL `FOR UPDATE`) 순서로 잡고(스냅숏의 7일 정리·산 것으로 옮기기도 사용자 잠금을 먼저 잡는다), 모든 `id`가 내 항목·체크됨·안 넣음인지 본다. 모든 `id`가 내 항목이고 이미 넣었으면(응답을 못 받은 기기가 다시 보냄) 아무것도 하지 않고 200 `{created: 0}`. 그 밖에(일부만 넣음·안 체크·없음·남의 것) 400 `목록이 방금 바뀌었어요. 다시 불러와주세요.` 동시에 두 번 보내도 재고에 한 번만 들어간다. `id`가 정수가 아니거나 겹치면 `잘못된 요청이에요.`
  2. 각 줄을 재고 `parse_fields`로 검증(수량·단위·위치 규칙과 문구는 재고와 같음, 거대한 정수 수량도 400 `수량은 0보다 커야 해요.`, 위치가 null이면 첫 냉장 위치). 보관 위치가 하나도 없으면 400 `보관 위치를 먼저 만들어주세요.`. 틀리면 아무것도 만들지 않고 400 `{error: "N번째 재료: …", errors}`.
  3. 재료 2000개 상한(`check_ingredient_cap`, 문구 그대로).
  4. 재료를 만들고 항목 `stocked_at = 지금` → 커밋. 불러온 뒤 위치가 지워지면 400 `선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요.`
  - **(2026-09-14, 사용자 결정) 산 것으로만 줄:** `items`에 `{id, skip: true}`를 섞어 보낼 수 있다 — 재료를 만들지 않고 같은 트랜잭션에서 `stocked_at`만 적는다(체크·안 넣음 확인, 다시 보냄 200은 위와 같음). `skip`이 참/거짓이 아니면 400 `잘못된 요청이에요.`. 오류 `index`는 skip 줄을 포함한 자리. 모든 줄이 skip이면 보관 위치가 없어도 된다. `created`는 만든 재료 수. 화면: 줄마다 `재고에 넣기` 스위치(생활용품 기본 끔, 끄면 위치 칸 대신 `산 것으로만 옮겨요`), 버튼 `N개 넣기` / `N개 넣기 · M개는 산 것으로만` / `M개 산 것으로 옮기기`(`sync.ts` `stockButtonText`).
- `POST /api/shopping/items/match` `{names:[문자열 50자 이하] 1~50}` → `{items:[{id, name}]}` — 목록에 있는 항목(체크했어도, 산 것 제외, 목록 순서) 중 `names_match`되는 것. 영수증·주문 스캔으로 재고에 넣은 뒤 `장보기 목록에 있던 우유·양파도 샀나요?` 제안용(16절).
- `POST /api/shopping/items/mark-stocked` `{ids:[정수] 1~300}` → 204 — 내 목록 항목만 `stocked_at = 지금`(재고는 스캔으로 이미 넣었으므로 재료를 만들지 않음). 없는 id·남의 것·이미 산 것은 조용히 넘긴다.
- 산 것 기록은 `stocked_at` 칸 하나로 7일만 둔다(따로 기록 테이블 없음, 월간 리포트 등에서 구매 기록이 필요해지면 그때 늘린다). 산 것은 사용자당 300개(`MAX_STOCKED_ITEMS`) — 재고에 넣기·산 것으로 옮기기에서 넘으면 같은 트랜잭션에서 오래된 것(stocked_at·id 순)부터 지운다.
