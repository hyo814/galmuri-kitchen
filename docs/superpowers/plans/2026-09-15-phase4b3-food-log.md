# 4b-3단계(먹은 기록 달력) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 더보기 > `먹은 기록`(`#/food-log`)에서 한 달을 달력으로 보고(이번 달 요약·첫 사진 또는 끼니 점·하루 kcal), 날짜를 누르면 끼니별로 먹은 것·사진(기록당 4장)·집밥/외식·만족도·메모를 남긴다. 무엇은 `식단에서 · 내 레시피 · 음식 찾기 · 직접` 네 갈래이고 kcal은 4b-2 영양 계산을 그대로 쓴다(외식은 식품영양성분 DB `음식` 행). 먹기 전에 사진만 먼저 남길 수 있고, 식단 칸 상세의 `먹었어요`로 한 번에 기록한다.

**Architecture:** 서버는 `app/food_logs.py` 한 파일(기록 CRUD·하루·한 달·사진·사진만 먼저)에 모은다. 영양은 **저장할 때 계산한 스냅숏**을 행에 넣고(레시피 = 4b-2 `NutritionContext`, 식단 칸 = `meals.slot_nutrition`, 음식 = `food_nutrients` 100g당 × g), 레시피 계산이 아직 `pending`이면 표시해 두었다가 하루 GET이 캐시로 다시 계산한다(외부 요청·AI는 화면이 기존 `POST /api/nutrition/fill`로만). 사진은 장보기 메모 사진과 같은 저장소(`storage.py`)·같은 검사(`photos.read_image`로 뽑아 함께 씀)를 쓰고 `food_log_photos` 행으로 소유를 확인한다. 화면은 달력 페이지 `pages/FoodLog.tsx` + 날짜 상세 시트 + 추가·고치기 시트 세 부분이고, 표시 수식은 브라우저 API 없는 `src/foodlog/log.ts`로 떼어 `scripts/check-foodlog.mjs`로 고정한다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, boto3(기존 `storage.py`), pytest 9.1.1 / React 19 + TypeScript + Vite 8, Node 24(`.ts` 직접 실행 검사 스크립트). **새 의존성 없음. 새 AI 호출 없음.**

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` **24절(먹은 기록 달력, `2026-09-15 화면·결정` 줄 모두)**, 21절(`먹은 것 기록` 원안 `food_logs`, 참고용 문구, `구현 세부 (4b-2)`), 20절(식단 칸·칸 상세 시트·`구현 세부`), 26절(목록 페이지 방식), 27절(더보기 `기록` 묶음, 데이터 내보내기, 회원 탈퇴 사진 접두사), 4절(데이터 모델), 5절(API 표), 8절(업로드 오류), 9절(체험 계정), 28절(장보기 메모 사진 저장·검사), 29절(5단계 요리 일기 — `food_logs.source = cook_log`와 달력 `요` 표시는 **5단계에서** 넣으므로 자리만 남긴다). **디자인: `docs/design/foodlog-4b3/index.html`(사용자 승인 2026-09-15, 결정 A~D 수락).** 화면 태스크는 프레임 문구·배치·버튼을 그대로 따른다.

시안 프레임: 1 `MONTH`(먹은 기록 달력) · 2 `DAY`(날짜 상세) · 3 `ADD`(먹은 것 추가) · 4 `PHOTO FIRST`(사진만 먼저) · 5 `FROM MEAL PLAN`(식단 칸 → 먹었어요) · 6 `MORE ENTRY`(더보기 입구).

**4b-2와의 관계:** 이 계획은 `docs/superpowers/plans/2026-09-15-phase4b2-nutrition.md`(개정 1 포함)가 만든 이름을 **그대로** 쓴다 — `foods.nutrition_mode`·`search_and_cache`·`search_items`·`name_parts`·`query_key`·`NUTRIENTS`·`OFF`, `FoodNutrient`·`FoodSearch`, `nutrition.NutritionContext(user, recipes).recipe(recipe)`(결과 `per_serving`·`approx`·`usable`·`pending`), `meals.nutrition_results(recipes)`·`meals.slot_nutrition(slot, result)`, `POST /api/nutrition/fill`, 화면 `nutrition/body.ts`(`dailyTarget`·`kcalNumber`)·`nutrition/day.ts`(`meterPercent`·`sodiumDay`)·`.nt-*` 스타일. 4b-2 모듈에 더하는 것은 새 함수로만 적는다(Task 1 `foods.serving_grams`·`dish_items`·`food_by_code`).

## 개정 1 (2026-09-15, 사전 점검 반영)

사전 점검 `.superpowers/sdd/2026-09-15-phase4b3-food-log/preflight.md`의 고침·주의 규칙을 각 태스크 본문에 넣었다. 한 줄씩(괄호는 점검 표 번호):

- 전체: **시작 조건** = 4b-2 Task 8(FoodPickSheet 아래 고정 버튼 줄 `.scan-foot`, `nutrition/day.ts` `closestMatch(item, query)`가 `sameName` 대신, `focusTitle` 시트, `App.resetScreens`의 `resetRecipeNutrition()`) 병합 뒤 Task 1 시작(P22·S12). 화면 확인은 커밋 안 하는 worktree Vite 설정(자기 `cacheDir`, `/api`→5181 프록시)으로, 실제 채우기·AI 요청은 화면 태스크마다 2번까지, 나머지는 CDP로 가짜 응답(Global Constraints).
- T1: 테스트 행 `item(..., serving="400g")`(S6), `test_foods.py` 기대 dict에 `serving_g: None`(S7), 캐시 헬퍼는 `tests.test_nutrition`의 `cached`·`add_foods`(D11), 빈 검색어 판정은 `query_key`(S4), `dish_items`는 `search_items`와 같은 정규화 키·이스케이프 LIKE(S5), `nutrition.put_food_match`도 `food_by_code`(D5).
- T2: `create_log(data)` 하나로 만들기(P5·D1), 관계 객체로만 넣고 빼기·`fill_snapshots`는 객체로 읽기(D2), `no_autoflush` + flush·commit 한 try(D3), 연결이 사라진 기록은 다시 계산하지 않고 인분 비율만(D4), 양 칸 하나를 보내면 다른 칸 `None`(P9), `scaled`는 `_round0/_round1`(S2), `test_caps` 날짜 9/12(④), 칸 연결을 끊어도 `source` 유지(⑤), GET 쓰기 멱등 주석(D10), 스펙 24절 `1인분` 문구는 이미 반영(S11).
- T3: 장보기 `_client_id`는 `read_image` 앞(P11·S13), `_store_photo` 실패는 `raise`(①), 바이트 상한은 모듈마다 두고 주석(D6).
- T4: `_MONTH.fullmatch`(D12), 첫 사진 = 사진이 **있는** 첫 기록(결정 11 문구 고침).
- T5: 칸 규칙 복사 대신 T2 `create_log` 호출(이미 있으면 200, 경합도 200)(P5·D1·D3), 스펙 5절 표 병합 충돌은 두 쪽 행 모두 남김(P17).
- T6: 내보내기 zip 정확 비교 테스트 2개 갱신(S8), 체험 계정 pending 단언은 `DEV_MODE=True` 앱에서·`demo_app`(off)은 pending 꺼짐 단언(P6·S9).
- T7: 페이지 컴포넌트 이름 `FoodLogPage`(D9), `FoodLogNutrition = Omit<SlotNutrition, "approx" | "source">`(D8), `›` 막기·오늘 원은 응답 `today`(P14), `resetFoodLogView`는 `resetRecipeNutrition()` 옆.
- T8: `DayTotals.unnamed` 삭제(D7), 채우기는 레시피 id별 모듈 `fillAttempted` Set(요청 전 표시, `resetFoodLogView`가 비움)(S10).
- T9: 음식 찾기 2글자 이상·600ms(Enter는 바로)(P2), `식단에서` 미리보기 비움(P10), `scaleNutrition`의 거짓 반올림 주석 삭제(S3), `Per` 대신 `FoodLogNutrition`(D8), import 맨 위로, 레시피 채우기는 T8 `fillAttempted` 공유(S10), 검색 칸·후보·버튼 줄은 4b-2 T8 병합본 `.nt-food-search`·`.nt-cand`·`.nt-radio`·`.nt-pick-actions`·`.nt-invalid`·`.scan-foot` 재사용.
- T11: Files·브랜치 표에 `styles.css`(식단 묶음 한 줄)(T11 행), 브라우저 확인에서 "고치기 시트 열림"은 빼고 T12에서(P21).
- T12: Step 3에 `기록 보기` → 고치기 시트까지 열리는지 확인 추가(P21).

## Global Constraints

- **시작 조건(개정 1):** 4b-3 실행은 4b-2 Task 8이 main에 병합된 뒤 시작한다(`git log main`에 그 병합 확인). 4b-2 Task 8 병합본이 만든 것: `components/FoodPickSheet.tsx`(검색 칸 `div.input-suffix.nt-food-search`, 후보 `label.nt-cand`(+`.on`)·`span.nt-radio`, 아래 고정 버튼 줄 `div.scan-foot` > `div.nt-pick-actions`, `focusTitle`), `nutrition/day.ts` `closestMatch(item, query)`(예전 `sameName` 대신), `components/RecipeNutrition.tsx` 모듈 `filled` Set과 `App.resetScreens`의 `resetRecipeNutrition()`, `components/LoadError.tsx`(`Meals.tsx`도 다시 내보냄), `api.ts` `RecipeNutrition`·`FoodSearchResult`. 병합본에서 이름이 바뀌었으면 병합본 이름을 따른다.
- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다. 태스크 작업은 태스크마다 git worktree에서 한다(메인 작업 폴더에서 직접 고치지 않는다).
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. SQLite와 PostgreSQL 둘 다 실패 0, 경고 0. **PostgreSQL DB는 에이전트(태스크)마다 따로 만든다**(`<N>` = 태스크 번호, 같은 태스크를 다시 돌리는 에이전트는 `fl<N>b`처럼 뒤에 글자를 붙인다): `createdb recipe_ai_test_fl<N>` · `createdb recipe_ai_migrate_fl<N>` → `TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test_fl<N> TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate_fl<N>` → 끝나면 `dropdb` 두 개(병렬 태스크가 같은 DB를 지우지 않게).
- 프론트 태스크는 `cd frontend && npm run check && npm run build`가 오류 없이 끝나야 한다. Task 7에서 `check` 스크립트 끝에 `&& node scripts/check-foodlog.mjs`를 붙인다. **테스트 러너(vitest 등)를 새로 들이지 않는다.**
- **테스트는 절대 네트워크를 부르지 않는다.** 기존 `conftest.py` `block_network` 그대로. 식품 DB는 `monkeypatch.setattr("app.foods.fetch_page", fake)`, 식품 캐시는 앱 컨텍스트에서 `FoodNutrient`·`FoodSearch` 행을 직접 넣는다. 사진은 `conftest.make_app`의 임시 `UPLOAD_DIR`(로컬 저장소).
- API 키는 `backend/.env`에만 있다. **`.env`는 읽거나 커밋하지 않는다**(값을 출력하지 않는다). 이번 단계는 새 환경변수가 없다. Task 1 Step 0의 실측 스크립트만 4b-2 Task 2 Step 0과 같은 방식(`dotenv_values`로 변수에만, 출력·기록 금지, 주소는 `REDACTED`)으로 키를 쓴다. 예외는 로그에 `type(e).__name__`만, 사진 키·비밀값은 로그에 남기지 않는다.
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정하고 남의 것은 404. 상태 변경은 `X-Requested-With: fetch`(기존 전역 검사). DB int 범위 밖 id는 404(`abort_if_id_too_big`/`get_owned_or_404`). 먹은 기록 GET 응답은 `Cache-Control: no-store`(건강·식습관 정보).
- 날짜·시각은 서울(`ingredients.SEOUL`, `seoul_today()`) 기준. 오늘보다 뒤 날짜는 남기지 않는다. 날짜 모양·범위 검사는 식단과 같은 `meals.meal_date`.
- 모바일 384px 기준(갤럭시 S22 Ultra). 터치 영역 44px 이상, 입력 글자 16px 이상. 아이콘은 이모지 대신 `Icon`(`calendar`·`camera`·`file`·`plus`·`minus`·`check`·`search`·`close`·`star`·`back`·`chevron`·`bowl`). 라이트·다크 모두 확인.
- **삭제 버튼은 연빨강 배경 + 테두리(`.btn.danger-text`)로 보이게, 다른 버튼 아래에 둔다(`기록 지우기`). 승인된 기존 화면 조정(칸 상세 `칸 비우기` 위치·모양 등)은 그대로 둔다.**
- 화면 문구는 시안 그대로. 시안에 없는 새 문구는 보조 용언을 붙여 쓴다(`보여줘요`, `골라주세요`, `채워요`, `남겨요`). 개발 용어(API, 캐시, 스냅숏, 동기화, 슬롯, 매칭, DB 코드)는 화면에 쓰지 않는다(`식품영양성분 DB`는 시안 문구라 그대로). kcal·당류·나트륨을 보여주는 곳(날짜 상세)에 `의료 조언이 아니라 참고용이에요.`를 둔다.
- 시안 `<style>`의 클래스는 `frontend/src/styles.css` 끝 `/* 먹은 기록 (4b-3) */` 묶음으로 `fl-` 접두사를 붙여 옮기되, 이미 있는 클래스(`btn`·`primary`·`secondary`·`outline`·`danger-text`, `chip`·`chips`, `segmented`, `stepper`·`icon-btn`, `field`·`field-label`·`input`·`input-suffix`, `badge`·`badge.info`·`badge.old`, `hint`, `summary`, `list`·`mo-group`·`mo-row`, `sh-photos`·`sh-photo`, 4b-2 `nt-card`·`nt-big`·`nt-link`·`nt-meter`·`nt-dmeter`·`nt-src`·`nt-kv`, 4b-2 Task 8 `nt-food-search`·`nt-cand`(+`.on`)·`nt-radio`·`nt-pick-actions`·`nt-invalid`·`scan-foot`, `error`)는 새로 만들지 않는다. 색은 CSS 변수만 쓴다. 새 토큰은 `--star`(시안 라이트 `#e0a100`, 다크 `#f5c542`) 하나를 `:root`, `@media (prefers-color-scheme: dark)`, `:root[data-theme="dark"]` 세 곳에 넣는다(Task 8).
- **포트:** 5173·5180·5181은 건드리지 않는다(공용 개발 서버는 끄거나 다시 켜지 않는다). 개발 DB(`backend/dev.sqlite3`)는 지우지 않는다. **서브에이전트는 `pkill`/`killall`을 쓰지 않는다. 직접 띄운 프로세스만 PID로 끈다.** **화면 확인(개정 1):** worktree `frontend/`에 커밋하지 않는 `vite.wt.config.ts`를 만든다 — `defineConfig({ plugins: [react()], cacheDir: "node_modules/.vite-wt-fl<N>", server: { port: 52<N 두 자리>, strictPort: true, proxy: { "/api": "http://localhost:5181", "/auth": "http://localhost:5181" } } })`(node_modules가 심링크로 공유돼 기본 설정을 쓰면 5180 개발 서버와 캐시·포트가 겹친다; 예: Task 7은 5207). `npx vite --config vite.wt.config.ts`로 띄우고 `http://127.0.0.1:52NN`에서 개발용 로그인으로 본 뒤 그 PID만 끈다. 커밋 전 `git status`에 `vite.wt.config.ts`가 스테이징되지 않았는지 확인한다. **실제 `POST /api/nutrition/fill`·식품 찾기(`/api/foods/dishes`·`/api/foods/search`)·AI 요청은 화면 태스크마다 합쳐 2번까지** 보내고, 나머지 흐름은 크롬 개발자 도구 프로토콜(CDP `Fetch.enable` + `Fetch.fulfillRequest`)로 가짜 응답을 준다(5181은 실제 키를 쓰는 공용 서버라 식품 요청 한도·AI 비용을 아낀다). 4b-3 백엔드(마이그레이션 포함)가 5181에 반영됐는지(`GET /api/food-logs/month?month=…` 200) 먼저 보고, 아니면 멈추고 컨트롤러에게 알린다.
- 마이그레이션 id·down_revision은 **구현 시점에 `ls backend/migrations/versions`와 `cd backend && .venv/bin/flask --app app db heads`로 다시 확인**한다(계획 작성 시 main head `e1p1u1r1c1h1` → 4b-2가 `f1b1o1d1y1p1`·`f2f2o2o2d2s2`를 더해 4b-3 시작 때 head `f2f2o2o2d2s2` 예정). head는 하나여야 한다. 다른 세션이 그사이 head를 옮겼으면 down_revision만 바꾸고 id는 그대로 둔다.
- 브랜치는 태스크마다 하나, 리뷰(백엔드: 코드·보안·테스트 설계 / 화면: 코드·UX·접근성) 통과 후 main에 `--no-ff` 병합. 배포(push)는 사용자 폰 확인(Task 12) 뒤 사용자가 고른 때에만 — 심사 기간에는 서비스 링크를 안정적으로 둔다.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음 한 줄만 붙인다:
  ```
  Claude-Session: https://claude.ai/code/session_01RfLBMnikALjpYKF3hjnepT
  ```

## 계획하며 정한 것 (스펙·시안에 없던 빈틈 — 사용자 확인 대상, 각 태스크 커밋 전에 스펙 24절 `구현 세부`에 적는다)

1. **테이블 두 개.** `food_logs`(한 줄 = 먹은 것 하나)와 `food_log_photos`(메모 사진과 같은 모양). 사진 키를 JSON 목록 칸으로 두지 않는다 — 소유 확인(`/api/photos`)·사용자 합계 크기·지우기가 행 단위라서. 24절의 `photo_key` 칸은 두지 않고 사진 테이블로 대신한다(4장). 21절 원안의 `amount_g`는 `grams`, `estimated`는 `approx`(4b-2 응답 이름과 같게)로 부른다.
2. **영양은 스냅숏.** 만들 때와 무엇·양을 고칠 때만 계산해 행에 넣는다(`kcal`·`carbs_g`·`protein_g`·`fat_g`·`sugars_g`·`sodium_mg`·`approx`). 레시피를 고치거나 지워도 지난 기록 kcal은 그대로다(일기라서). **(개정 1, D4)** 계산 출처(레시피·식단 칸)가 사라진 기록은 다시 계산하지 않는다 — 하루 GET은 pending만 끄고 값을 두며, 양(인분)만 고치면 기존 영양을 `새 인분 ÷ 옛 인분`으로 비율 조정한다. 레시피 계산이 `pending`(4b-2 찾아볼 재료·무게 추정이 남음)이면 `nutrition_pending = true`로 두고, **그날 상세 GET이 캐시만으로 다시 계산해** 값이 나오면 채우고 끈다. 외부 요청·AI는 화면이 응답의 `nutrition_pending_recipe_ids`로 기존 `POST /api/nutrition/fill`을 한 번 부른 뒤 다시 받는다(4b-2 결정 13과 같은 흐름). `ponytail:` GET이 행을 고친다 — 한 날짜 최대 20줄이라 가볍고, 따로 다시 계산 API를 두지 않는다. 한 달 GET은 다시 계산하지 않는다.
3. **무엇 네 갈래 → 서버 칸.** `식단에서` = `meal_slot_id`(제목·레시피·날짜·끼니를 칸에서 가져오고 `source = meal_plan`), `내 레시피` = `recipe_id`(제목 = 레시피 제목), `음식 찾기` = `food_code`(제목 = 식품 이름 60자), `직접` = `title`만. `meal_slot_id`·`recipe_id`·`food_code`는 하나만 받고, 셋 다 없으면 `title` 필수. **직접은 kcal을 비운다**(시안 결정 A `못 찾으면 비워 둔다`) — 직접 kcal 입력 칸은 두지 않는다(YAGNI, 시안에 없음).
4. **양.** 인분은 0.5~20, 0.5 단위(시안 `½인분`), 기본 1. g은 `음식 찾기`에서만 1~3000 정수. 음식 1인분 무게는 식품영양성분 DB `식품중량`을 새 칸 `food_nutrients.serving_g`에 받아 쓰고, 없는 음식은 g으로만 남긴다(`이 음식은 g으로 입력해주세요.`). 캐시에 이미 있는 행이 새 칸을 받도록 마이그레이션이 `food_searches.searched_at`을 2000-01-01로 돌린다(다음 찾기 때 다시 받음).
5. **kcal 계산(21절 계산 그대로).** 레시피 = `NutritionContext.recipe` `per_serving` × 인분(`approx` = 레시피 `approx` 또는 `usable` 아님). 식단 칸 = `meals.slot_nutrition(slot, result)`(4b-2 결정 16 — 계산값, 모자라면 AI 초안 추정 kcal) × 인분. 음식 = 100g당 × g ÷ 100이고 **늘 `approx = true`**(가게마다 양이 달라서, 시안 `약 400kcal`). 직접·사진 기록 = 없음. 반올림은 4b-2 결정 17(kcal·mg 정수, g 소수 첫째, **.5는 올림 — 서버는 `nutrition._round0`·`_round1`, 화면 `Math.round`와 같음**, 개정 1 S2). 영양 모드 `off`면 레시피·음식 계산을 하지 않고 식단 칸의 AI 추정 kcal만 쓴다. 값 없는 영양소(당류 등)는 `null`로 둔다(더할 때 화면이 0으로).
6. **식단 칸 `먹었어요` = 1인분.** 시안 날짜 상세가 `2인분 중 1인분`이라, 칸 인분(가족 수)이 아니라 먹은 사람 1인분으로 남기고 응답에 `slot_servings`(연결된 칸의 인분)를 붙여 보여준다. 24절 `2026-09-15` 줄에 이미 `1인분` 기록으로 적혀 있으므로 그 문구는 다시 고치지 않고 `구현 세부`만 적는다(개정 1 S11). 같은 칸은 한 번만(UNIQUE `meal_slot_id`, 다시 누르면 그 기록을 200으로), `place = home`. 칸을 다른 요리로 다시 채우면(PUT) 연결만 끊고 기록은 남긴다. 칸·식단을 지우면 FK `SET NULL`. 오늘보다 뒤 칸은 버튼을 숨기고 서버도 400.
7. **날짜.** 오늘(서울)보다 뒤는 400 `아직 오지 않은 날은 남길 수 없어요.`, 2000~2100년 밖은 `meals.meal_date`의 `날짜를 다시 확인해주세요.`. 달력의 미래 날짜 칸은 누를 수 없다. 고치기 시트는 끼니만 옮길 수 있고 날짜 옮기기 화면은 없다(API는 `eaten_on`을 받는다).
8. **사진만 먼저.** `POST /api/food-logs/photo` 한 요청에 사진과 기록을 함께 만든다(따로 보내면 사진 실패 때 빈 기록이 남아서). 끼니는 **서버 시각을 서울로 바꾼 시(時)**: 5–9시 아침 · 10–14시 점심 · 15–20시 저녁 · 그 밖 간식(24절 `아침 5–10시·점심 10–15시·저녁 15–21시`의 끝 시각은 다음 끼니). 날짜도 같은 시각의 서울 날짜(자정~5시 전은 그날 간식). 제목 없음 = 화면 `사진 기록`, 알약 `이름 없음`.
9. **사진.** 기록당 4장, 한 장 3MB, 사용자 합계 200MB(체험 계정 20MB) — 메모 사진과 같은 숫자이고 합계는 메모와 따로 센다. 키 `foodlog/<user_id>/<uuid4 hex>.<jpg|png|webp>`. 빈 파일·크기·파일 서명·저장소 `off` 503 검사는 장보기와 **같은 코드**(`photos.read_image`, 장보기 `upload_photo`도 이것으로 바꾼다). 첫 사진 = id가 가장 작은 사진(순서 바꾸기 없음). 기록·사진을 지우면 커밋 뒤 파일을 지운다. EXIF는 화면이 `resizeImage`(긴 변 1568px JPEG)로 다시 인코딩해 빠진다(28절과 같음).
10. **상한·페이지.** 하루 20개 `하루에 20개까지 남길 수 있어요.`, 사용자당 10,000개 `먹은 기록은 10000개까지 남길 수 있어요.` 먹은 기록은 **날짜 하나·달 하나 단위로만** 받으므로(한 달 최대 620줄) 커서 페이지가 필요 없다 — 26절 표의 `앞으로(먹은 기록·조리 기록)` 줄을 `먹은 기록: 날짜·달 단위, 페이지 없음(하루 20개)`으로 나눈다. `ponytail:` 상한 확인은 잠그지 않는다 — 동시에 보내면 한 개 넘을 수 있다.
11. **한 달 API 정의(24절 월 요약·결정 D).** 기록 있는 날만 돌려준다. 점 = 그날 기록이 있는 **끼니 수**(최대 4). 하루 kcal = kcal 있는 기록의 합(하나도 없으면 `null`), `약` = 더한 기록 중 `approx`가 하나라도 있으면(**kcal 없는 사진 기록은 `약`을 붙이지 않는다** — 시안 사진만 먼저 `310kcal`). 첫 사진 = 끼니 순(아침→간식) → 남긴 순(`created_at`, id)으로 **사진이 있는** 첫 기록의 첫 사진(개정 1 — 사진 없는 앞 기록은 건너뛴다). 요약: `기록한 날` = 기록 있는 날 수, `하루 평균 kcal` = kcal 있는 날의 합 ÷ 그 날 수(사진만 있는 날은 평균에서 뺀다, 반올림 정수, 섞이면 `약`), `집밥` 비율 = 집밥 기록 수 ÷ (집밥 + 외식)(어디서 안 고른 기록은 뺀다, 둘 다 0이면 `—`) — 시안 `집밥 18끼 · 외식 7끼`는 기록 수다.
12. **만족도·메모·어디서.** 만족도 1~5 정수·선택(별을 다시 누르면 지움), 메모 200자(앞뒤 공백 뺌, 비면 `null`, NUL 글자 400), 어디서 `home`·`out`·`null`(칩을 다시 누르면 해제). 추가 시트의 어디서 기본값: 식단에서·내 레시피를 고르면 `집밥`, 음식 찾기를 고르면 `외식`(사용자가 칩을 만졌으면 바꾸지 않음), 직접은 안 고름.
13. **음식 찾기(결정 A).** `GET /api/foods/dishes?q=`가 4b-2 `search_and_cache`로 찾은 뒤 캐시의 `음식` 행만 20개(`dish_items`) 돌려준다. 화면은 2글자 이상일 때 입력이 멈추고 600ms 뒤(Enter는 바로) 부른다(검색어마다 식품 DB 요청이 나가 체험 계정 하루 50번이 빨리 닳아서, 개정 1 P2). 찾는 음식이 없으면 `찾는 음식이 없어요. 이름만 남길 수 있어요` + `‘{검색어}’ 이름으로 남기기`(직접 칸으로 넘김). 영양 모드 `off`면 `음식 찾기` 칸을 숨긴다. 사진으로 AI 추정은 하지 않는다.
14. **날짜 상세의 식단 제안(결정 B).** 그날 내 모든 식단의 칸 중 아직 먹은 기록과 연결되지 않은 칸을 끼니 순으로 8개까지 `plan_slots`로 주고, 화면은 그 끼니 묶음 안에 `식단에 {제목}이 있었어요 · 먹었어요` 한 줄로 둔다(누르면 `POST /api/meal-slots/<id>/eaten`).
15. **날짜 상세 머리(24절 마지막 결정).** 설명 줄 `약 1,190 / 목표 1,294kcal · 당류 22g · 나트륨 2,380mg` — 목표는 **몸 정보 하루 칼로리 목표만**(식단 `goal_kcal`은 계획용이라 먹은 기록에는 쓰지 않는다). 목표가 있고 합계가 있으면 막대(넘으면 주황), 나트륨이 2,000mg을 넘으면 막대 아래 주황 글자 `나트륨 1일 기준치 넘었어요`(4b-2 `sodiumDay().text`). 당류·나트륨은 값 있는 기록만 더하고 0이면 뺀다. 이름 없는 사진 기록이 있으면 끝에 `이름을 넣으면 kcal을 계산해요`. 기록이 없으면 `아직 남긴 기록이 없어요`.
16. **체험 계정.** 예시 기록 3개를 함께 만든다 — 어제 저녁 `김치찌개`(예시 레시피, 집밥, ★5, `nutrition_pending = true`라 상세를 열면 계산), 어제 점심 `제육덮밥`(직접, 외식, ★3, 메모 `회사 앞 · 조금 짰어요`), 오늘 아침 `토스트`(직접, 집밥, ★4). 사진은 없다. 사진 한도 20MB, 체험 계정을 지울 때 사진 파일도 지운다.
17. **계정 삭제.** 회원 탈퇴 API는 아직 없다(27절 `배포 전` 항목, 이번 범위 밖). 이번에는 `food_logs`·`food_log_photos` CASCADE와 체험 계정 정리(`demo.delete_demo_users`)에서 사진 파일을 지우는 것까지 하고, 사용자들의 사진 키를 모으는 `photos.user_photo_keys(user_ids)`를 만들어 탈퇴를 만들 때 그대로 쓰게 한다(27절에 `foodlog/<user_id>/` 접두사 추가).
18. **내보내기 `food_logs.csv`(27절).** 칸: 날짜, 끼니, 무엇을 먹었나요(없으면 `사진 기록`), 어디서(`집밥`/`외식`/빈 칸), 인분, 먹은 양(g), kcal, 탄수화물(g), 단백질(g), 지방(g), 당류(g), 나트륨(mg), 추정(`예`/빈 칸), 만족도, 메모, 남긴 방법(`직접`/`식단`/`요리 일기`), 사진 수, 사진 파일 이름(`;`로 이어 붙임), 남긴 시각(서울). 날짜 → 끼니 → 남긴 순. 사진 바이트는 넣지 않는다. 요약 응답에 `food_logs`.
19. **5단계 자리.** `source`는 `manual`·`meal_plan`·`cook_log`를 담을 수 있지만 이번 API는 `manual`(직접·레시피·음식·사진)과 `meal_plan`(식단에서·먹었어요)만 만든다. 달력 `요` 표시·범례 `요 = 요리 일기 있음`은 5단계에서 한 달 API에 칸을 더할 때 넣는다(지금은 그리지 않는다).
20. **더보기 입구(프레임 6).** 새 `기록` 묶음을 `우리 부엌` 위에 두고 맨 위 `먹은 기록` 줄. 부제 = 오늘 기록이 있는 끼니 수 `오늘 N끼 남겼어요`, 없으면 `먹은 것·사진을 달력에 남겨요`. 데이터 내보내기 시트에 `먹은 기록 N개` 줄.
21. **식단 칸 표시(결정 B).** 주 보기 칸 줄 보조 글자 끝에 `· 먹었어요`, 칸 상세 맨 위 버튼은 기록 전 `먹었어요 · 먹은 기록에 남기기`(primary) → 기록 뒤 `먹었어요 · 기록 보기`(secondary, 누르면 `#/food-log`로 가서 그 날짜 상세와 그 기록을 연다). 4b-2 하루 영양 시트 끝 문구 `먹은 기록은 다음에 ‘먹은 기록’에서 남길 수 있어요.`는 `먹은 기록은 더보기 ‘먹은 기록’에서 남길 수 있어요.`로 바꾼다.
22. **달력.** 월요일 시작(식단 월 보기와 같은 `meals/plan.ts monthGrid`), 다른 달 날짜는 흐리게(누를 수 없음), `›` 다음 달은 이번 달까지. 보던 달은 화면 모듈에 기억해 상세를 다녀와도 그대로(`resetFoodLogView`가 로그아웃 때 비움).
23. **마이그레이션 id:** Task 1 `g1s1e1r1v1n1`(down `f2f2o2o2d2s2`), Task 2 `g2f2o2o2d2l2`(down `g1s1e1r1v1n1`), Task 3 `g3f3l3p3h3o3`(down `g2f2o2o2d2l2`) — **구현 시 head 확인.**
24. **실측 안 된 한 가지:** 식품영양성분 DB 한 행의 `식품중량` 필드 이름(`Z10500`으로 예상, 값 모양 `400g`)을 Task 1 Step 0에서 실제 키로 한 번 확인해 `foods.FIELDS["serving"]`과 스펙에 적는다. 필드가 없으면 `serving_g`는 늘 `null`이 되고 음식 찾기는 g으로만 남긴다(코드는 그대로 동작).

## 브랜치

| 브랜치 | 태스크 | 시작 시점 | 병렬 |
|---|---|---|---|
| `feature/foodlog-dishes` | 1 (음식 1인분 무게 칸·음식 찾기 API) | **4b-2 Task 8 병합 뒤 — 병합 전에는 시작하지 않는다**(개정 1 P22, 4b-2 Task 9 폰 확인과 겹쳐도 됨) | — |
| `feature/foodlog-api` | 2 (먹은 기록 테이블·만들기/고치기/지우기·하루 GET·영양 스냅숏·식단 제안) | 1 병합 뒤(마이그레이션 차례) | — |
| `feature/foodlog-photos` | 3 (사진 테이블·올리기/지우기·사진만 먼저·사진 보기 소유 확인·체험 계정 사진 정리) | 2 병합 뒤 | 5와 병렬 가능 |
| `feature/foodlog-month` | 4 (한 달 달력·요약 API) | 3 병합 뒤(`food_logs.py` 겹침) | 5와 병렬 가능 |
| `feature/foodlog-meal-eaten` | 5 (식단 칸 `먹었어요` API·칸 `eaten_log_id`·칸 덮어쓰기 연결 끊기) | 2 병합 뒤 | 3·4·6·7과 병렬 가능(파일: `meals.py`·`tests/test_meal_food_log.py`만; 스펙은 20절 줄과 5절 표 한 행 — 24절 줄은 병합 때 붙인다. 5절 표가 3·4·6과 충돌하면 두 쪽 행을 모두 남긴다, 개정 1 P17) |
| `feature/foodlog-export-demo` | 6 (내보내기 `food_logs.csv`·체험 계정 예시 기록) | 4 병합 뒤(`demo.py`는 3과 겹침) | 5와 병렬 가능 |
| `feature/foodlog-calendar-ui` | 7 (`log.ts`+검사, 달력 페이지·월 요약·경로·더보기 `기록` 줄·내보내기 줄) | 6 병합 뒤 | 5와 병렬 가능 |
| `feature/foodlog-day-ui` | 8 (날짜 상세 시트·목표 막대·식단 제안 먹었어요·채우기 호출) | 5·7 병합 뒤 | 11과 병렬 가능 |
| `feature/foodlog-add-ui` | 9 (먹은 것 추가·고치기 시트: 네 갈래·양·어디서·만족도·메모·지우기) | 8 병합 뒤 | 11과 병렬 가능 |
| `feature/foodlog-photo-ui` | 10 (시트 사진 4장·사진만 먼저 카메라 버튼) | 9 병합 뒤 | 11과 병렬 가능 |
| `feature/foodlog-meal-button-ui` | 11 (식단 칸 상세 `먹었어요` 버튼·주 보기 표시·하루 영양 시트 문구) | 5·7 병합 뒤 | 8·9·10과 병렬 가능(파일: `MealSlotSheet.tsx`·`Meals.tsx`·`DayNutritionSheet.tsx`·`styles.css` 식단 묶음 한 줄만; `기록 보기` → 고치기 시트 열림은 Task 9가 만들므로 12에서 확인, 개정 1 P21) |
| — | 12 (전체 검사·체험 계정·폰 확인·배포 준비) | 10·11 병합 뒤 | — |

## 파일 구조

```
backend/
  app/models.py                                          (수정, T2·T3) FoodLog / FoodLogPhoto, FoodNutrient.serving_g(T1)
  migrations/versions/g1s1e1r1v1n1_food_serving_grams.py (신규, T1) food_nutrients.serving_g + food_searches.searched_at 되돌림
  migrations/versions/g2f2o2o2d2l2_food_logs.py          (신규, T2)
  migrations/versions/g3f3l3p3h3o3_food_log_photos.py    (신규, T3)
  app/foods.py                                           (수정, T1) FIELDS serving, serving_grams, dish_items, food_by_code, GET /api/foods/dishes
  app/nutrition.py                                       (수정, T1) put_food_match가 foods.food_by_code 사용(개정 1 D5)
  app/data/sample_foods.json                             (수정, T1) 음식 행 serving_g, 예시 음식 3개
  app/food_logs.py                                       (신규, T2·T3·T4) 기록 CRUD·하루·사진·사진만 먼저·한 달
  app/photos.py                                          (수정, T3) read_image, user_photo_keys, foodlog 소유 확인
  app/shopping.py                                        (수정, T3) upload_photo가 photos.read_image 사용
  app/demo.py                                            (수정, T3·T6) 사진 키 모으기, 예시 기록
  app/meals.py                                           (수정, T5) POST /api/meal-slots/<id>/eaten, slot_json eaten_log_id, PUT 연결 끊기
  app/export.py                                          (수정, T6) food_logs.csv, summary food_logs
  app/__init__.py                                        (수정, T2) 블루프린트 food_logs
  tests/test_food_dishes.py (T1), test_food_logs.py (T2), test_food_log_photos.py (T3), test_food_log_month.py (T4), test_meal_food_log.py (T5)
  tests/test_migrations.py·test_demo.py·test_export.py·test_foods.py(T1)   (수정)
docs/superpowers/specs/2026-09-13-recipe-ai-design.md    (수정, T1~T12) 2·4·5·20·21·24·26·27절
frontend/
  package.json                                           (수정, T7) check에 check-foodlog.mjs
  scripts/check-foodlog.mjs                              (신규, T7~T9)
  src/foodlog/log.ts                                     (신규, T7~T9) 달력·하루·추가 시트 표시 순수 함수
  src/api.ts                                             (수정, T7) FoodLog 타입들, MealSlot.eaten_log_id, ExportSummary.food_logs
  src/pages/FoodLog.tsx                                  (신규, T7·T8·T9·T10) 달력 페이지 FoodLogPage(default), openFoodLog, resetFoodLogView
  src/components/FoodLogDaySheet.tsx                     (신규, T8)
  src/components/FoodLogSheet.tsx                        (신규, T9·T10)
  src/useHashRoute.ts, src/App.tsx                       (수정, T7) /food-log 경로, resetFoodLogView
  src/pages/More.tsx                                     (수정, T7) 기록 묶음, 내보내기 줄
  src/components/MealSlotSheet.tsx, src/pages/Meals.tsx, src/components/DayNutritionSheet.tsx (수정, T11)
  src/styles.css                                         (수정, T7~T10) /* 먹은 기록 (4b-3) */, (T11) 식단 묶음 .ml-eaten 한 줄
```

---

### Task 1: 음식 1인분 무게·음식 찾기 API

**Files:**
- Create: `backend/migrations/versions/g1s1e1r1v1n1_food_serving_grams.py`, `backend/tests/test_food_dishes.py`
- Modify: `backend/app/models.py`(`FoodNutrient.serving_g`), `backend/app/foods.py`, `backend/app/nutrition.py`(`put_food_match` 한 줄), `backend/app/data/sample_foods.json`, `backend/tests/test_migrations.py`, `backend/tests/test_foods.py`(기대 dict에 `serving_g`), 스펙(21절 `구현 세부`, 5절 표)

**Interfaces:**
- Consumes: 4b-2 `foods.nutrition_mode`·`search_and_cache`·`search_items`(정규화 키·이스케이프 LIKE 모양)·`search_foods`(검사 순서)·`name_parts`·`query_key`·`row_fields`·`_search_sample`·`NUTRIENTS`·`OFF`·`FIELDS`·`MAX_QUERY`·`SEARCH_LIMIT`·`bp`(url_prefix `/api`), `FoodNutrient`, `nutrition.put_food_match`, 테스트 헬퍼 `tests.test_nutrition.cached`·`add_foods`, `tests.test_foods.item`
- Produces:
  - `FoodNutrient.serving_g = db.Column(db.Float)` — 식품중량(1인분 g, 음식 행에만 있음, 없으면 NULL).
  - Alembic `g1s1e1r1v1n1`(down `f2f2o2o2d2s2`): `with op.batch_alter_table("food_nutrients") as b: b.add_column(sa.Column("serving_g", sa.Float(), nullable=True))` 뒤 `op.execute(sa.text("UPDATE food_searches SET searched_at = :old").bindparams(old=datetime(2000, 1, 1, tzinfo=timezone.utc)))`(결정 4 — 다음 찾기 때 식품중량과 함께 다시 받는다). downgrade는 칸만 뺀다.
  - `foods.py` 추가:
    ```python
    FIELDS["serving"] = "Z10500"  # 식품중량 '400g'. Task 1 Step 0 실측(결정 24)
    DISH_GROUP = "음식"
    MAX_SERVING_G = 5000


    def serving_grams(value):
        """'400g'·'400 g'·'1,000g'·'250ml'(1ml=1g, 4b-2 결정 5)·400 → float. bool·못 읽음·1~5000 밖이면 None."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            match = re.fullmatch(r"([\d,]+(?:\.\d+)?)\s*(g|ml)", value.strip().lower())
            if not match:
                return None
            number = float(match.group(1).replace(",", ""))
        else:
            return None
        return number if math.isfinite(number) and 1 <= number <= MAX_SERVING_G else None


    def food_by_code(code):
        """먹은 기록이 쓰는 식품 한 행(source != 'ai'). 문자열이 아니거나 없으면 None."""
        if not isinstance(code, str) or not 1 <= len(code) <= 80:
            return None
        return FoodNutrient.query.filter(FoodNutrient.food_code == code, FoodNutrient.source != "ai").first()


    def dish_items(q):
        """search_items와 같은 key = query_key(q)·이스케이프한 ilike(escape='\\')로 캐시에서 음식 행(group_name == DISH_GROUP,
        source != 'ai') 200개까지 → (key가 name_parts(이름)에 없음, 이름 길이, 이름) → 앞 SEARCH_LIMIT개.
        [{food_code, name, serving_g, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg}] — 100g당 원값(화면이 양으로 곱한다)."""
    ```
  - `nutrition.put_food_match`: `FoodNutrient.query.filter(FoodNutrient.food_code == food_code, FoodNutrient.source != "ai").first() is None` 조건을 `foods.food_by_code(food_code) is None`으로 바꾼다(문구 `식품을 다시 골라주세요.`·검사 순서 그대로, 개정 1 D5 — 같은 규칙 한 곳).
  - `row_fields`가 돌려주는 dict에 `"serving_g": serving_grams(item.get(FIELDS["serving"]))`를 더한다(`_upsert_food`가 dict 칸을 모두 쓰므로 그대로 저장됨). `_search_sample`의 `fields`에도 `"serving_g": serving_grams(row.get("serving_g"))`.
  - `GET /api/foods/dishes?q=`(로그인, `foods.bp`) → 200 `{items: dish_items(q), searched}`. 순서는 `search_foods`와 같다: mode off → 503 `OFF` / `q = (request.args.get("q") or "").strip()[:MAX_QUERY]` / `if not query_key(q)`(공백·괄호뿐인 입력 포함) → 400 `찾을 음식 이름을 입력해주세요.` / `searched = search_and_cache(q, g.user)` / `items = dish_items(q)`. 쪽 수 인자는 더하지 않는다(개정 1 P2 — 요청 횟수는 화면 디바운스로 줄인다).
  - `sample_foods.json`: 음식 행에 `serving_g` — `쌀밥 210`, `김치찌개_돼지고기 400`. 예시 음식 3개 추가(값은 화면 확인용 예시, `food_code, name, group, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg, serving_g`): `SAMPLE-18|제육덮밥|음식|185|22.0|8.5|6.8|5.5|410|400` · `SAMPLE-19|토스트|음식|282|35.0|9.0|12.5|6.0|380|110` · `SAMPLE-20|비빔밥|음식|150|24.0|5.5|3.8|3.0|260|450`. (시안 `제육덮밥 1인분(400g) 약 740kcal`, `½인분 약 370kcal · 당류 11g · 나트륨 820mg`, `토스트 310kcal`이 이 값으로 나온다.)

- [ ] **Step 0: 실제 응답 한 번 확인(테스트 아님, 커밋 안 함)** — 스크래치 디렉터리에 `backend/.venv/bin/python` 스크립트: `dotenv_values("backend/.env")["FOOD_NUTRITION_API_KEY"]`를 변수에만 두고(출력·파일 기록 금지), `제육덮밥`·`김치찌개`로 1쪽 20행 요청 → `DB_GRP_NM == "음식"`인 첫 행의 **키 이름 목록**과 `Z10500`(또는 이름에 `중량`이 들 만한 필드) 값 3개만 출력한다(주소는 `REDACTED`). 필드 이름이 다르면 `FIELDS["serving"]`을 실제 이름으로 쓰고 스펙 21절 `구현 세부`에 적는다(결정 24). 키가 없는 환경이면 건너뛰고 Task 12 Step 2에서 확인한다고 적는다.
- [ ] **Step 1: 브랜치·head** — worktree에서 main(4b-2 Task 8 병합 포함) 기준 `feature/foodlog-dishes`. `ls backend/migrations/versions`, `cd backend && .venv/bin/flask --app app db heads`(하나, `f2f2o2o2d2s2` 예정).
- [ ] **Step 2: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_food_serving_grams_migration` — `upgrade(revision="f2f2o2o2d2s2")` 뒤 `food_searches`에 행 하나(`searched_at` 2026-09-15) 넣기 → `upgrade(revision="g1s1e1r1v1n1")` → `food_nutrients` 컬럼에 `serving_g`, 그 행 `searched_at`이 2000-01-01 → `downgrade(revision="f2f2o2o2d2s2")` 뒤 `serving_g` 없음(기존 `test_body_profiles_migration_adds_and_removes_table` 모양).
  - `test_foods.py`(기존): `test_row_fields_normal_row`의 기대 dict에 `"serving_g": None`을 더한다(dict 전체 `==` 비교라 새 칸을 모르면 실패, 개정 1 S7).
  - `test_food_dishes.py`(캐시 행은 새 헬퍼를 만들지 않고 `from tests.test_nutrition import add_foods, cached` → `add_foods(app, cached("D1", "제육덮밥", 185, group="음식", source="api", serving_g=400), …)`; API 모양 행은 `from tests.test_foods import item`, 개정 1 D11):
    - `test_serving_grams` parametrize — `"400g"` 400.0, `"400 G"` 400.0, `"1,000g"` 1000.0, `"250ml"` 250.0, `400` 400.0, `"0g"` None, `"6000g"` None, `""` None, `None` None, `"1회"` None, `True` None.
    - `test_row_fields_reads_serving` — `item("D1", "제육덮밥", group="음식", serving="400g")`(헬퍼가 `FIELDS[key]`로 바꾸므로 키는 `serving`, 개정 1 S6) → `row_fields(...)["serving_g"] == 400.0`; `item("D1", "제육덮밥", group="음식")` → `None`.
    - `test_dish_items_only_dishes_in_order` — 캐시 `제육덮밥(음식, 400)`·`제육볶음(음식, None)`·`제육덮밥소스(가공식품)`·`ai:제육덮밥(source ai, group 추정)` → `dish_items("제육덮밥")` 이름 `["제육덮밥"]`; `dish_items("제육 덮밥")`(띄어 씀)도 `["제육덮밥"]`(정규화 키, 개정 1 S5); `dish_items("제육")` 이름 `["제육덮밥", "제육볶음"]`; `dish_items("100%")`는 오류 없이 `[]`(이스케이프); 첫 항목 키 집합 `{food_code, name, serving_g, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg}`·`kcal 185`(반올림 안 함 확인은 `kcal=185.4` 행으로 `185.4`).
    - `test_food_by_code` — api 행 → 그 행, ai 행 코드 → None, 없는 코드·`123`·`""` → None.
    - `test_dishes_endpoint` — 로그인 없음 401; `q=  `·`q=()` 400 `찾을 음식 이름을 입력해주세요.`(개정 1 S4); `DEV_MODE=False`·키 없음 앱 503 `영양 계산을 지금은 쓸 수 없어요.`; 키 없는 개발 앱(sample) `q=제육덮밥` → `items[0] == {"food_code": "SAMPLE-18", "name": "제육덮밥", "serving_g": 400.0, "kcal": 185.0, …}`, `searched true`, `AiCall` 0행, 가짜 `fetch_page` 안 불림.
    - `test_on_mode_stores_serving_from_api` — `FOOD_NUTRITION_API_KEY="k"` 앱, `monkeypatch.setattr("app.foods.fetch_page", fake)`가 `[item("D1", "제육덮밥", group="음식", kcal="185", serving="400g")]`, total 1 → `GET /api/foods/dishes?q=제육덮밥` → `items[0].serving_g 400.0`.
    - `test_sample_dishes_have_serving` — `SAMPLE_FILE` JSON의 `group == "음식"` 행은 모두 `serving_grams(row["serving_g"])`가 None이 아님.
- [ ] **Step 3: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 개발 DB가 아닌 스크래치 DB에서 `flask db upgrade`·`flask db check` 차이 없음. 4b-2 `test_foods.py`(위 기대 dict 한 줄만 고침)·`test_nutrition.py`(`PICK_AGAIN` 식품 코드 검사 포함)·`test_nutrition_fill.py` 그대로 통과.
- [ ] **Step 4: 스펙** — 21절 `구현 세부`에 `serving_g`(식품중량·Step 0 실측 결과·결정 4·24), `dish_items`·`GET /api/foods/dishes` 순서·문구, 예시 음식 3개. 5절 표에 `GET /api/foods/dishes` 행.
- [ ] **Step 5: 커밋** — `git add backend docs && git commit -m "feat: 음식 1인분 무게(식품중량)와 먹은 기록용 음식 찾기 API" -m "Claude-Session: https://claude.ai/code/session_01RfLBMnikALjpYKF3hjnepT"`

---

### Task 2: 먹은 기록 저장·하루 보기·영양 스냅숏

**Files:**
- Create: `backend/app/food_logs.py`, `backend/migrations/versions/g2f2o2o2d2l2_food_logs.py`, `backend/tests/test_food_logs.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`, `backend/tests/test_migrations.py`, 스펙(24절 `구현 세부` 신설, 4·5·26절)

**Interfaces:**
- Consumes: Task 1 `foods.food_by_code`, 4b-2 `foods.nutrition_mode`·`NUTRIENTS`, `nutrition._round0`·`_round1`(.5 올림 반올림), `sqlalchemy.exc.IntegrityError`, `meals.nutrition_results`·`meals.slot_nutrition`·`meals.MEALS`·`meals.meal_date`·`meals._owned_slot`(칸 → 식단 → 사용자 확인), `auth.login_required`·`get_owned_or_404`·`abort_if_id_too_big`, `validation.text`·`integer`·`iso_date`·`iso_datetime`, `ingredients.seoul_today`, `models.Recipe`·`MealSlot`·`MealPlan`
- Produces:
  - 모델(마이그레이션 `g2f2o2o2d2l2`, down `g1s1e1r1v1n1`):
    ```python
    class FoodLog(db.Model):
        """먹은 기록 한 줄(스펙 21·24절). 영양 칸은 저장할 때 계산한 스냅숏 — 레시피를 고쳐도 지난 기록은 그대로(결정 2).
        title이 NULL이면 사진만 먼저 남긴 '사진 기록'. meal_slot_id는 식단 칸 '먹었어요'(칸 하나에 기록 하나)."""

        __tablename__ = "food_logs"
        __table_args__ = (
            db.UniqueConstraint("meal_slot_id"),
            db.Index("ix_food_logs_user_id_eaten_on", "user_id", "eaten_on"),
        )

        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
        eaten_on = db.Column(db.Date, nullable=False)
        meal = db.Column(db.String(10), nullable=False)  # breakfast | lunch | dinner | snack
        source = db.Column(db.String(10), nullable=False, default="manual")  # manual | meal_plan | cook_log(5단계)
        title = db.Column(db.String(60))
        recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="SET NULL"), index=True)
        meal_slot_id = db.Column(db.Integer, db.ForeignKey("meal_slots.id", ondelete="SET NULL"))
        food_code = db.Column(db.String(80))  # food_nutrients.food_code — 공유 캐시라 FK 아님
        servings = db.Column(db.Float)
        grams = db.Column(db.Integer)
        place = db.Column(db.String(4))  # home | out
        rating = db.Column(db.Integer)
        memo = db.Column(db.String(200))
        kcal = db.Column(db.Integer)
        carbs_g = db.Column(db.Float)
        protein_g = db.Column(db.Float)
        fat_g = db.Column(db.Float)
        sugars_g = db.Column(db.Float)
        sodium_mg = db.Column(db.Integer)
        approx = db.Column(db.Boolean, nullable=False, default=False)
        nutrition_pending = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
        updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

        recipe = db.relationship("Recipe")
        meal_slot = db.relationship("MealSlot", backref=db.backref("food_log", uselist=False))
    ```
    제약 이름은 `NAMING_CONVENTION` 그대로(`pk_food_logs`, `fk_food_logs_user_id_users`, `fk_food_logs_recipe_id_recipes`, `fk_food_logs_meal_slot_id_meal_slots`, `uq_food_logs_meal_slot_id`, `ix_food_logs_recipe_id`, `ix_food_logs_user_id_eaten_on`).
  - `app/food_logs.py`(blueprint `food_logs`, `url_prefix="/api"`):
    ```python
    """먹은 기록(스펙 21·24절). 기록 CRUD·하루·한 달·사진. 영양은 저장할 때 스냅숏(결정 2·5)."""

    MAX_PER_DAY = 20
    MAX_LOGS = 10000
    PLACES = ("home", "out")
    MAX_MEMO = 200
    MAX_PLAN_SUGGESTIONS = 8
    BAD_REQUEST = "잘못된 요청이에요."
    FUTURE = "아직 오지 않은 날은 남길 수 없어요."
    SLOT_TAKEN = "이미 먹었어요로 남긴 칸이에요."
    SERVINGS_ERROR = "인분은 0.5~20 사이로 입력해주세요."
    GRAMS_ERROR = "먹은 양은 1~3000g 사이로 입력해주세요."
    FIELDS_WHAT = ("meal_slot_id", "recipe_id", "food_code", "title")
    FIELDS_AMOUNT = ("servings", "grams")


    def log_json(log):
        return {
            "id": log.id, "eaten_on": log.eaten_on.isoformat(), "meal": log.meal, "source": log.source,
            "title": log.title, "recipe_id": log.recipe_id, "meal_slot_id": log.meal_slot_id,
            "slot_servings": log.meal_slot.servings if log.meal_slot is not None else None,
            "food_code": log.food_code, "servings": log.servings, "grams": log.grams,
            "place": log.place, "rating": log.rating, "memo": log.memo,
            "nutrition": None if log.kcal is None else {k: getattr(log, k) for k in NUTRIENTS},
            "approx": log.approx, "nutrition_pending": log.nutrition_pending,
            "created_at": iso_datetime(log.created_at),
        }


    def eaten_date(value):
        """날짜 칸. 모양이 틀리면 400 '날짜를 골라주세요.', 2000~2100 밖은 meal_date 문구, 오늘(서울) 뒤면 FUTURE."""


    def check_caps(user_id, day, moving_from=None):
        """그날 기록이 MAX_PER_DAY개 이상이면 400 f'하루에 {MAX_PER_DAY}개까지 남길 수 있어요.', 전체가 MAX_LOGS개 이상이면
        f'먹은 기록은 {MAX_LOGS}개까지 남길 수 있어요.'(새로 만들 때만). moving_from은 PATCH로 날짜를 옮길 때 원래 날짜(같으면 세지 않음)."""


    def servings_value(value):
        """bool 아닌 0.5~20 숫자, 0.5 단위(value * 2가 정수). 아니면 400 SERVINGS_ERROR."""


    def apply_fields(log, data, creating):
        """보낸 칸을 검증해 log에 넣는다. 돌려주는 값: 무엇을 바꿨으면 'what', 양만 바꿨으면 'amount', 영양과 상관없으면 None.
        **관계는 언제나 객체로만 넣고 뺀다**(log.recipe = …/None, log.meal_slot = …/None — recipe_id·meal_slot_id FK 칸은 직접 쓰지 않는다.
        flush 전 FK가 None·옛 값이라 fill_snapshots가 틀린 값을 읽지 않게, 개정 1 D2).
        무엇(FIELDS_WHAT 중 하나라도 보냈거나 creating): meal_slot_id·recipe_id·food_code 중 둘 이상 null이 아니면 400 BAD_REQUEST →
          meal_slot_id: bool 아닌 int, _owned_slot(404) → slot.food_log가 있고 그게 log가 아니면 400 SLOT_TAKEN →
            log.meal_slot = slot, log.recipe = slot.recipe, eaten_on·meal·title을 칸에서(보낸 eaten_on·meal 무시), eaten_date(slot.date) 검사, source 'meal_plan', food_code None /
          recipe_id: bool 아닌 int, get_owned_or_404(Recipe) → log.recipe = recipe, title = recipe.title, food_code None, log.meal_slot = None /
          food_code: food_by_code → 없으면 400 '음식을 다시 골라주세요.' → title = food.name[:60], log.recipe = None, log.meal_slot = None /
          셋 다 없음: text(title, '무엇을 먹었는지는', 60), log.recipe = None, log.meal_slot = None, food_code None.
          (PATCH로 무엇을 바꾸면 칸 연결은 끊는다. source는 그대로 둔다 — 처음 어떻게 남겼는지 기록, 개정 1 T2⑤)
        날짜·끼니(creating이고 칸이 아닐 때 필수, PATCH는 보낸 것만): eaten_date(eaten_on), meal이 MEALS 밖이면 400 '끼니를 골라주세요.'
        양(무엇을 바꿨거나 FIELDS_AMOUNT 중 하나라도 보냈을 때, 사진 기록처럼 무엇이 없으면 둘 다 None):
          food_code: servings·grams 중 정확히 하나(둘 다 없으면 servings 1) → **보낸 쪽만 남기고 다른 쪽은 None**(개정 1 P9 — 둘 다 남으면
            fill_snapshots가 grams를 우선해 인분 변경이 무시됨) → grams는 bool 아닌 int 1~3000(아니면 GRAMS_ERROR),
            servings인데 food.serving_g가 None이면 400 '이 음식은 g으로 입력해주세요.' / 그 밖: grams를 보내면 400 BAD_REQUEST, servings_value(없으면 1), grams None.
        place: None 또는 PLACES(아니면 BAD_REQUEST). rating: None 또는 integer(rating, '만족도는', 1, 5).
        memo: None 또는 문자열(아니면 BAD_REQUEST), NUL 글자 BAD_REQUEST, strip 뒤 비면 None, 200자 넘으면 400 '메모는 200자까지 입력해주세요.'
        body가 dict가 아니면 400 BAD_REQUEST(호출 측)."""


    def scaled(per, factor):
        """per(영양소 dict, 값 None 가능) × factor. kcal·sodium_mg는 _round0, 나머지 _round1(.5 올림 — 화면 Math.round와 같게, 개정 1 S2).
        per가 None이면 모두 None."""
        return {k: None if per is None or per.get(k) is None else (_round0(per[k] * factor) if k in ("kcal", "sodium_mg") else _round1(per[k] * factor)) for k in NUTRIENTS}


    def has_source(log):
        """다시 계산할 출처(레시피·식단 칸·음식 코드)가 하나라도 남았나. 없는데 kcal이 있으면 출처가 지워진 기록(개정 1 D4)."""
        return log.recipe is not None or log.meal_slot is not None or log.food_code is not None


    def rescale(log, factor):
        """출처가 사라진 기록의 양만 바뀌었을 때: 기존 영양 × factor(새 인분 ÷ 옛 인분), pending 끔. approx는 그대로(결정 2)."""
        for key, value in scaled({k: getattr(log, k) for k in NUTRIENTS}, factor).items():
            setattr(log, key, value)
        log.nutrition_pending = False


    def create_log(data):
        """POST /api/food-logs와 칸 먹었어요(Task 5)가 함께 쓰는 만들기(개정 1 P5·D1·D3). 커밋까지 한다.
        같은 칸 UNIQUE 경합(그 밖 IntegrityError 포함)이면 rollback 뒤 None — 호출 측이 400 SLOT_TAKEN 또는 기존 기록 200."""
        log = FoodLog(user_id=g.user.id, source="manual")
        with db.session.no_autoflush:  # 검사·계산 쿼리가 반쯤 찬 행을 먼저 INSERT하지 않게
            apply_fields(log, data, creating=True)
            db.session.add(log)
            check_caps(g.user.id, log.eaten_on)
            fill_snapshots([log])
        try:
            db.session.flush()
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return None
        return log


    def fill_snapshots(logs):
        """무엇·양이 바뀐 기록들의 영양 칸을 채운다(결정 5, 커밋은 호출 측). g.user로 계산한다.
        관계 객체(log.recipe·log.meal_slot)로만 읽는다 — FK 칸은 flush 전 값이 틀릴 수 있다(개정 1 D2)."""
        results = meals.nutrition_results([log.recipe for log in logs if log.recipe is not None])  # off면 {}
        mode = nutrition_mode(g.user)
        for log in logs:
            per, factor, approx, pending = None, 1, False, False
            if log.food_code is not None:
                food = food_by_code(log.food_code) if mode != "off" else None
                grams = log.grams if log.grams is not None else ((food.serving_g or 0) * (log.servings or 0) if food else 0)
                if food and grams:
                    per, factor, approx = {k: getattr(food, k) for k in NUTRIENTS}, grams / 100, True
            elif log.recipe is not None or log.meal_slot is not None:
                result = results.get(log.recipe.id) if log.recipe is not None else None
                slot = log.meal_slot if log.meal_slot is not None and log.meal_slot.recipe is log.recipe else None
                if slot is not None:
                    slot_per = meals.slot_nutrition(slot, result)
                elif result and result["per_serving"]:
                    slot_per = {**result["per_serving"], "approx": result["approx"] or not result["usable"]}
                else:
                    slot_per = None
                if slot_per:
                    per, factor, approx = slot_per, log.servings or 1, slot_per["approx"]
                pending = bool(result and result["pending"])
            values = scaled(per, factor)
            for key, value in values.items():
                setattr(log, key, value)
            log.approx = approx and values["kcal"] is not None
            log.nutrition_pending = pending
    ```
  - API(모두 로그인):
    - `GET /api/food-logs?date=YYYY-MM-DD` → 200 `{date, logs, plan_slots, nutrition_pending_recipe_ids}`, `Cache-Control: no-store`. `date`가 `iso_date` None이면 400 `날짜를 다시 확인해주세요.`(범위 밖도 같은 문구, 미래 날짜는 빈 목록). `logs`는 내 기록(끼니 `MEALS` 순 → `created_at` → id). `nutrition_pending`인 기록이 있으면 `has_source`가 없는 기록은 다시 계산하지 않고 `nutrition_pending = False`만(값 유지, 개정 1 D4), 나머지는 `fill_snapshots(그 기록들)` 후 바뀐 게 있으면 커밋(결정 2). 그 자리 `ponytail:` 주석에 `멱등 — 서버 캐시만 읽어 같은 값을 채우므로 GET이 여러 번 와도 결과가 같다`를 한 줄 더한다(개정 1 D10). `nutrition_pending_recipe_ids` = 여전히 pending인 기록의 `recipe_id`(중복 없이, 오름차순). `plan_slots` = 내 식단(`MealPlan.user_id`)의 그날 칸 중 `~MealSlot.food_log.has()`인 것, 끼니 순 → 식단 `start_on` 내림차순 → 칸 id, 8개 `[{id, meal, title, servings, recipe_id}]`, 날짜가 오늘(서울) 뒤면 `[]`(결정 14).
    - `POST /api/food-logs` `{eaten_on, meal, meal_slot_id? | recipe_id? | food_code? | title?, servings?, grams?, place?, rating?, memo?}` → 201 `log_json`. 순서: body dict 아님 400 → `log = create_log(data)`(apply_fields → add → check_caps → fill_snapshots를 `no_autoflush` 안에서, flush+commit 한 try) → `None`이면 400 `SLOT_TAKEN`. `source`는 칸이면 `meal_plan`, 아니면 `manual`(보낸 `source`는 무시).
    - `PATCH /api/food-logs/<int:log_id>` → 200 `log_json`. `get_owned_or_404(FoodLog)` → body dict 아님 400 → `old_servings = log.servings` → `with db.session.no_autoflush:` `changed = apply_fields(log, data, creating=False)` → 날짜가 바뀌었으면 그날 `check_caps(..., moving_from=원래 날짜)`(전체 상한은 세지 않음) → `changed == "what"`이면 `fill_snapshots([log])` / `changed == "amount"`이면 `has_source(log)`면 `fill_snapshots([log])`, 아니고 `log.kcal`·`old_servings`·`log.servings`가 있으면 `rescale(log, log.servings / old_servings)`(개정 1 D4) → flush+commit을 한 try에서, IntegrityError면 rollback 뒤 400 `SLOT_TAKEN`(개정 1 D3).
    - `DELETE /api/food-logs/<int:log_id>` → 204(Task 3에서 사진 파일 삭제를 더한다).
  - `app/__init__.py`에 `from .food_logs import bp as food_logs_bp` 등록.
  - `ponytail:` 상한 확인은 잠그지 않는다(결정 10) — 동시에 보내면 하루 21개가 될 수 있다. 문제되면 `shopping._lock_user_items`처럼 사용자 잠금을 더한다.

- [ ] **Step 0: 브랜치·head** — main(Task 1 병합)에서 `feature/foodlog-api`, head `g1s1e1r1v1n1` 확인.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_food_logs_migration_adds_and_removes_table` — `upgrade(revision="g2f2o2o2d2l2")` 뒤 컬럼 집합(모델 칸 전부), FK `{users: CASCADE, recipes: SET NULL, meal_slots: SET NULL}`, UNIQUE `("meal_slot_id",)`, 인덱스 `ix_food_logs_recipe_id`·`ix_food_logs_user_id_eaten_on` → `downgrade(revision="g1s1e1r1v1n1")` 뒤 테이블 없음.
  - `test_food_logs.py`(헬퍼: `from tests.test_meals import add_recipe, make_plan, put_slot`; 캐시 행은 `from tests.test_nutrition import add_foods, cached` → `add_foods(app, cached(code, name, kcal, group="음식", source="api", serving_g=…, sugars_g=…))`(새 `food` 헬퍼 만들지 않음, 개정 1 D11); `post_log(client, **body)`는 기본 `{"eaten_on": "2026-09-14", "meal": "lunch"}`에 합쳐 보냄; 오늘 고정 `monkeypatch.setattr("app.food_logs.seoul_today", lambda: date(2026, 9, 15))` 픽스처 `today`):
    - `test_requires_login_and_csrf` — GET 401, `raw_client` POST 400.
    - `test_create_text_log_and_day_list` — `title " 제육덮밥 "`, `place "out"`, `rating 3`, `memo "회사 앞 · 조금 짰어요"` → 201 `title "제육덮밥"`·`servings 1.0`·`grams None`·`nutrition None`·`approx False`·`source "manual"`·`slot_servings None` → `GET ?date=2026-09-14` `logs` 1개, `Cache-Control` `no-store`; `?date=2026-09-13` → `logs []`; `?date=2026-9-1` 400 `날짜를 다시 확인해주세요.`
    - `test_create_food_log_serving_and_grams` — 캐시 `D1 제육덮밥 185kcal serving 400 carbs 22.0 sugars 5.5 sodium 410 protein None` → `{food_code: "D1", servings: 0.5, title: "무시"}` → `title "제육덮밥"`, `nutrition == {kcal: 370, carbs_g: 44.0, protein_g: None, fat_g: …, sugars_g: 11.0, sodium_mg: 820}`, `approx True` → `{food_code: "D1", grams: 300}` → `kcal 555`, `servings None` → 캐시 `D2 떡볶이 serving None` `servings 1` → 400 `이 음식은 g으로 입력해주세요.`, `grams 200` → 201.
    - `test_create_recipe_log_uses_per_serving` — 4b-2 Task 5 `test_recipe_slot_uses_calculated_per_serving`과 같은 캐시(2인분 `[두부 1모, 간장 2큰술]`, `두부 84`·`간장 53`·`FoodSearch` 둘·`UnitWeightEstimate(두부, 모, 300, sample)`) → `{recipe_id, servings: 1.5}` → `title` 레시피 제목, `nutrition.kcal == round(134 * 1.5) == 201`, `approx True`, `nutrition_pending False`.
    - `test_pending_recipe_is_recomputed_on_day_get` — 찾아본 적 없는 재료 레시피 `[양배추 100g]` → 기록 `nutrition None`·`nutrition_pending True` → GET 하루 `nutrition_pending_recipe_ids == [rid]` → 앱 컨텍스트에서 `FoodSearch("양배추")`·`FoodNutrient(양배추, 원재료성, 31)` 넣기 → GET 하루 `logs[0].nutrition.kcal == 31`·`nutrition_pending False`·`nutrition_pending_recipe_ids []`.
    - `test_snapshot_kept_when_recipe_changes_or_is_deleted` — 레시피 기록 뒤 `PUT /api/recipes/<id>`로 재료를 바꿔도 하루 GET kcal 그대로 → 레시피 DELETE → `recipe_id None`, `title`·`nutrition` 그대로 → PATCH `{servings: 2}` → `kcal` 두 배(비율 조정), `approx` 그대로. 그리고 pending 기록(일부 값 있음) + 레시피 DELETE → 하루 GET 뒤 값 유지·`nutrition_pending False`·`nutrition_pending_recipe_ids []`(개정 1 D4).
    - `test_create_from_meal_slot` — 식단(시작 9/14)·칸 9/14 저녁 레시피 인분 2 → `{meal_slot_id, eaten_on: "2026-09-01", meal: "snack"}` → 201 `eaten_on "2026-09-14"`·`meal "dinner"`·`source "meal_plan"`·`recipe_id`·`slot_servings 2`·`servings 1.0` → 같은 칸으로 또 POST → 400 `이미 먹었어요로 남긴 칸이에요.` → 칸 날짜 9/16 칸 → 400 `아직 오지 않은 날은 남길 수 없어요.` → 남의 칸 id 404.
    - `test_create_slot_race_400` — `test_meals.race_same_slot` 방식: `monkeypatch.setattr("app.food_logs.fill_snapshots", racing)`에서 진짜 `fill_snapshots`를 부른 뒤 같은 `meal_slot_id`의 `FoodLog`를 `db.session.add`(다른 요청이 먼저 남긴 것처럼) → POST `{meal_slot_id}` 400 `SLOT_TAKEN`(500 아님)·`FoodLog` 0행(개정 1 D3).
    - `test_patch_fields_and_recompute` — 음식 기록 `servings 1` → PATCH `{servings: 2}` kcal 두 배 → PATCH `{grams: 300}` → `servings None` → PATCH `{servings: 1}` → `grams None`·kcal = 1인분 값(개정 1 P9) → PATCH `{rating: null, memo: "  ", place: null}` → 셋 다 None, kcal 그대로 → PATCH `{title: "샐러드"}` → `food_code None`·`nutrition None`·`approx False` → PATCH `{meal: "dinner", eaten_on: "2026-09-13"}` → 옮겨짐 → 칸 기록에 PATCH `{title: "요거트"}` → `meal_slot_id None`.
    - `test_validation` parametrize(만들기, 모두 행이 생기지 않음) — `eaten_on` 없음 `날짜를 골라주세요.` · `"2026-09-16"` `아직 오지 않은 날은 남길 수 없어요.` · `"1999-12-31"` `날짜를 다시 확인해주세요.` · `meal "brunch"` `끼니를 골라주세요.` · `recipe_id`+`food_code` 둘 다 `잘못된 요청이에요.` · `title ""`·61자 `무엇을 먹었는지는 1~60자로 입력해주세요.` · `food_code "없는코드"` `음식을 다시 골라주세요.` · `recipe_id "1"`·`True` `잘못된 요청이에요.` · `servings 0`·`0.3`·`20.5`·`True`·`"1"` `인분은 0.5~20 사이로 입력해주세요.` · 제목 기록에 `grams 100` `잘못된 요청이에요.` · 음식 기록 `grams 0`·`3001`·`1.5` `먹은 양은 1~3000g 사이로 입력해주세요.` · `place "cafe"` `잘못된 요청이에요.` · `rating 0`·`6`·`True` `만족도는 1~5 사이 정수로 입력해주세요.` · `memo` 201자 `메모는 200자까지 입력해주세요.` · `memo "a\x00"`·`123` `잘못된 요청이에요.` · body `[]` `잘못된 요청이에요.`
    - `test_ownership` — 남의 레시피 `recipe_id` 404, 남의 기록 PATCH·DELETE 404, `/api/food-logs/2147483648` 404, 남의 기록은 하루 GET에 없음.
    - `test_caps` — 9/14에 20개 → 21번째 400 `하루에 20개까지 남길 수 있어요.`, 9/13은 201 → `monkeypatch.setattr("app.food_logs.MAX_LOGS", 21)` → **9/12로** 보낸 다음 기록 400 `먹은 기록은 21개까지 남길 수 있어요.`(9/14로 보내면 하루 문구가 먼저, 개정 1 T2④) → 9/13 기록을 PATCH로 9/14(가득)로 옮기면 400 하루 문구.
    - `test_day_plan_slot_suggestions` — 내 식단 칸 9/14 `lunch 김치찌개`(레시피)·`snack 요거트`(직접)·`dinner`(이미 `meal_slot_id`로 기록됨), 남의 식단 9/14 칸 → `plan_slots` 제목 `["김치찌개", "요거트"]`(끼니 순), 키 `{id, meal, title, servings, recipe_id}`; `?date=2026-09-16`(미래) `plan_slots []`.
    - `test_delete_and_cascades` — DELETE 204 → 하루 GET 없음; 사용자 행 삭제 → FoodLog 0; 칸 기록 뒤 `DELETE /api/meal-slots/<id>` → 기록 남고 `meal_slot_id None`; 식단 DELETE도 같음.
    - `test_nutrition_off_mode` — `DEV_MODE=False`·키 없음 앱: 레시피 기록 `nutrition None`·`nutrition_pending False`; AI 초안 넣기(`ai-draft/apply`, `est_kcal 420`)로 채운 칸에서 `meal_slot_id` 기록 → `nutrition.kcal 420`·`approx True`(`slot_nutrition` AI 추정 kcal) → 그 칸 기록에 PATCH `{title: "요거트"}` → `nutrition None`·`meal_slot_id None`·`recipe_id None`·`source "meal_plan"` 그대로(관계 객체를 비워 남은 `log.meal_slot`으로 계산하지 않음, 개정 1 D2·T2⑤).
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 스크래치 DB `flask db upgrade`·`flask db check`. 기존 `test_meals.py`·`test_meal_nutrition.py`(4b-2) 그대로 통과(backref만 더함).
- [ ] **Step 3: 스펙** — 24절 끝에 `**구현 세부 (2026-09-xx, 4b-3):**`를 만들고 `food_logs` 칸·API·검증 순서와 문구·결정 1~7·10·12·14(`create_log` 공용·출처가 사라진 기록은 비율 조정 포함)를 적는다. 24절 `2026-09-15` 줄의 `1인분` 문구는 이미 있으므로 고치지 않는다(개정 1 S11). 4절 목록에 `food_logs(21·24절)`, 5절 표에 `GET/POST /api/food-logs`·`PATCH/DELETE /api/food-logs/<id>` 행, 26절 표 `앞으로` 줄을 `먹은 기록: 날짜·달 단위로 받아 페이지 없음(하루 20개, 24절)` / `조리 기록: 서버 커서 페이지 + 무한 스크롤`로 나눈다. 21절 `먹은 것 기록` 원안 줄 끝에 `(구현 이름은 24절 구현 세부)`.
- [ ] **Step 4: 커밋** — `feat: 먹은 기록 저장·하루 보기 API(식단 칸·레시피·음식·직접, 저장할 때 영양 계산)`

---

### Task 3: 먹은 기록 사진·사진만 먼저

**Files:**
- Create: `backend/migrations/versions/g3f3l3p3h3o3_food_log_photos.py`, `backend/tests/test_food_log_photos.py`
- Modify: `backend/app/models.py`, `backend/app/food_logs.py`, `backend/app/photos.py`, `backend/app/shopping.py`, `backend/app/demo.py`, `backend/tests/test_migrations.py`, `backend/tests/test_demo.py`, 스펙(24절 `구현 세부`, 5·27·28절)

**Interfaces:**
- Consumes: Task 2 `FoodLog`·`log_json`·`check_caps`·`BAD_REQUEST`, `storage.mode`·`put`·`delete`·`photo_response`·`UPLOAD_UNAVAILABLE`, `scan.sniff_image_type`, `ingredients.SEOUL`, `models.utcnow`, `ShoppingNote`·`ShoppingNotePhoto`
- Produces:
  - 모델(마이그레이션 `g3f3l3p3h3o3`, down `g2f2o2o2d2l2`):
    ```python
    class FoodLogPhoto(db.Model):
        """먹은 기록 사진(기록당 4장, 결정 9). 파일은 storage(photo_key). 행이 지워져도 DB가 파일을 지우지 않으므로 지우는 곳에서 storage.delete."""

        __tablename__ = "food_log_photos"

        id = db.Column(db.Integer, primary_key=True)
        log_id = db.Column(db.Integer, db.ForeignKey("food_logs.id", ondelete="CASCADE"), nullable=False, index=True)
        photo_key = db.Column(db.String(200), nullable=False, unique=True)
        size = db.Column(db.Integer, nullable=False)
        created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ```
    `FoodLog.photos = db.relationship("FoodLogPhoto", order_by="FoodLogPhoto.id", cascade="all, delete-orphan", passive_deletes=True)`.
  - `photos.py` 추가(장보기와 함께 쓴다):
    ```python
    EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


    def read_image(max_bytes):
        """request.files['image'] → (data, media_type, ext). 10MB 초과는 파일을 읽을 때 413(MAX_CONTENT_LENGTH).
        없음·빈 파일 400 '사진을 올려주세요.' → max_bytes 초과 413 '사진이 너무 커요.' → 서명이 JPG·PNG·WEBP 아님 415 '사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.'"""


    def user_photo_keys(user_ids):
        """이 사용자들의 모든 사진 키(장보기 메모 + 먹은 기록). 체험 계정 정리·회원 탈퇴가 커밋 뒤 storage.delete에 넘긴다(결정 17)."""
    ```
    `photo(key)` 소유 확인: `shopping/{uid}/`는 지금 규칙 그대로, `foodlog/{uid}/`는 `FoodLogPhoto.query.join(FoodLog).filter(FoodLogPhoto.photo_key == key, FoodLog.user_id == g.user.id)`. `ponytail:` 주석을 `5단계 조리 기록 사진은 접두사와 행 확인을 여기에 더한다`로 줄인다.
  - `shopping.upload_photo`: `image`·`data`·빈 파일·3MB·서명 줄을 `data, media_type, ext = photos.read_image(MAX_PHOTO_BYTES)`로 바꾼다. **지금 응답 순서를 지킨다: 저장소 off 503 → 메모 404 → `client_id = _client_id(request.form.get("client_id"))`(400) → `read_image`(빈 파일 400 → 3MB 413 → 서명 415) → 잠금·같은 client_id …**(`_client_id`가 `read_image` 앞, 개정 1 P11·S13 — 잘못된 client_id + 빈 파일 요청의 문구가 바뀌지 않게. 10MB 초과 413은 `request.form` 접근에서 먼저 난다). 코드 안 `ext = {...}[media_type]` dict는 지우고 `read_image`가 준 `ext`를 쓴다. `from .scan import sniff_image_type` import가 안 쓰이면 뺀다. 바이트 상한(`MAX_PHOTO_BYTES`·합계·체험)은 `shopping.py`에 그대로 둔다(D6).
  - `demo.delete_demo_users`: 메모 사진 쿼리를 `keys = photos.user_photo_keys(ids)`로 바꾼다(docstring `(지운 수, 사진 키)`).
  - `food_logs.py` 추가:
    ```python
    MAX_PHOTOS = 4
    # 장보기 메모 사진과 같은 숫자(결정 9). 테스트가 app.shopping.*·app.food_logs.*를 따로 monkeypatch하고 합계도 따로 세서 공유하지 않는다(개정 1 D6)
    MAX_PHOTO_BYTES = 3 * 1024 * 1024
    MAX_USER_PHOTO_BYTES = 200 * 1024 * 1024
    MAX_DEMO_PHOTO_BYTES = 20 * 1024 * 1024
    PHOTO_FULL = "사진 저장 공간이 가득 찼어요. 오래된 기록 사진을 지워주세요."


    def meal_for_time(moment):
        """결정 8: 서울 시(時) 5–9 아침 · 10–14 점심 · 15–20 저녁 · 그 밖 간식."""
        hour = moment.astimezone(SEOUL).hour
        return "breakfast" if 5 <= hour < 10 else "lunch" if 10 <= hour < 15 else "dinner" if 15 <= hour < 21 else "snack"


    def photo_json(photo):
        return {"id": photo.id, "url": f"/api/photos/{photo.photo_key}"}


    def _check_photo_room(log, size):
        """기록당 MAX_PHOTOS장(400 '사진은 기록 하나에 4장까지 넣을 수 있어요.'), 사용자 먹은 기록 사진 합계(체험은 20MB, 400 PHOTO_FULL)."""


    def _store_photo(log, data, media_type, ext):
        """키 foodlog/<uid>/<hex>.<ext>로 storage.put → FoodLogPhoto 추가 → 커밋. 커밋이 실패하면 방금 올린 파일을 지우고
        IntegrityError면 400 BAD_REQUEST(그사이 기록이 지워짐), 그 밖 예외는 `raise`로 다시 던진다(파일을 다시 올리는 게 아님 —
        shopping.upload_photo의 except 블록과 같은 모양, 개정 1 T3①)."""
    ```
    `log_json`에 `"photos": [photo_json(p) for p in log.photos]`. 하루 GET은 `selectinload(FoodLog.photos)`·`selectinload(FoodLog.meal_slot)`.
  - API(모두 로그인):
    - `POST /api/food-logs/<int:log_id>/photos` multipart `image` → 201 `photo_json`. 순서: `storage.mode() == "off"` 503 `사진을 지금은 올릴 수 없어요.` → `get_owned_or_404(FoodLog)` → `read_image(MAX_PHOTO_BYTES)` → `_check_photo_room` → `_store_photo`.
    - `DELETE /api/food-logs/<int:log_id>/photos/<int:photo_id>` → 204. 다른 기록의 사진 id·범위 밖 id 404. 커밋 뒤 `storage.delete([key])`.
    - `DELETE /api/food-logs/<int:log_id>`: 사진 키를 모은 뒤 삭제·커밋 → `storage.delete(keys)`.
    - `POST /api/food-logs/photo` multipart `image` → 201 `log_json`(결정 8). 순서: 저장소 off 503 → `read_image` → `now = utcnow()`, `day = now.astimezone(SEOUL).date()`, `check_caps(g.user.id, day)` → 합계 크기(체험 20MB) → `FoodLog(user_id, eaten_on=day, meal=meal_for_time(now), source="manual")` 추가·flush → `_store_photo`(실패하면 기록도 함께 되돌림). `food_logs.utcnow`를 테스트가 바꾼다.
  - `ponytail:` 사진 수·합계 확인은 잠그지 않는다 — 동시에 올리면 5장이 될 수 있다(메모 사진은 사용자 잠금을 쓰지만 먹은 기록은 오프라인 재전송이 없어 드묾).

- [ ] **Step 0: 브랜치·head** — main(Task 2 병합)에서 `feature/foodlog-photos`, head `g2f2o2o2d2l2`.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_food_log_photos_migration_adds_and_removes_table` — 컬럼 `{id, log_id, photo_key, size, created_at}`, FK `{food_logs: CASCADE}`, UNIQUE `("photo_key",)`, 인덱스 `ix_food_log_photos_log_id` → downgrade `g2f2o2o2d2l2` 뒤 없음.
  - `test_food_log_photos.py`(`from tests.test_shopping_notes import JPEG, PNG, photo_path`; 헬퍼 `upload(client, log_id, data=JPEG)`·`new_log(client)` = Task 2 `post_log`에 `title "토스트"`, 오늘 고정 픽스처):
    - `test_upload_serves_to_owner_only` — 201 `url`이 `/api/photos/foodlog/{user_id}/`로 시작·`.jpg`로 끝남, 파일 바이트 == JPEG → `GET url` 200 `image/jpeg`·`Content-Security-Policy "default-src 'none'; sandbox"`·`private, max-age=3600` → PNG 올리면 `.png` → 하루 GET `logs[0].photos` 두 개(id 순) → 다른 사용자로 같은 `url` 404, 그 기록에 올리기 404.
    - `test_upload_errors` — 파일 없음·빈 바이트 400 `사진을 올려주세요.`, `JPEG[:4] + b"0" * (3 * 1024 * 1024 - 3)` 413 `사진이 너무 커요.`, `b"hello"` 415 `사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.`, 4장 뒤 5번째 400 `사진은 기록 하나에 4장까지 넣을 수 있어요.`, `DEV_MODE=False`·R2 없는 앱 503 `사진을 지금은 올릴 수 없어요.`, `raw_client` 400 — 실패한 요청은 파일·행을 남기지 않음(`UPLOAD_DIR/foodlog` 파일 수 확인).
    - `test_photo_bytes_caps` — `monkeypatch.setattr("app.food_logs.MAX_USER_PHOTO_BYTES", len(JPEG) * 2)` → 세 번째 400 `사진 저장 공간이 가득 찼어요. 오래된 기록 사진을 지워주세요.`(장보기 메모 사진은 합계에 안 셈: 메모 사진 두 장이 있어도 첫 두 장은 201); 체험 사용자(`provider="demo"`)는 `MAX_DEMO_PHOTO_BYTES = len(JPEG)`에서 두 번째 400.
    - `test_delete_photo_and_log_remove_files` — 사진 DELETE 204 → 파일 없음·`url` 404 → 다른 기록의 사진 id로 DELETE 404 → 사진 2장 기록 DELETE 204 → 두 파일 모두 없음, `FoodLogPhoto` 0행.
    - `test_photo_first_meal_by_seoul_time` parametrize(`monkeypatch.setattr("app.food_logs.utcnow", lambda: 시각)`) — `2026-09-14T21:30Z`(서울 9/15 06:30) → `breakfast`·`eaten_on "2026-09-15"` · `01:00Z`(10:00) `lunch` · `05:59Z`(14:59) `lunch` · `06:00Z`(15:00) `dinner` · `11:59Z`(20:59) `dinner` · `12:00Z`(21:00) `snack` · `2026-09-14T19:59Z`(서울 9/15 04:59) `snack`·`eaten_on "2026-09-15"` — 모두 201 `title None`·`source "manual"`·`photos` 1장·`nutrition None`.
    - `test_photo_first_errors_leave_nothing` — `b"hello"` 415 → `FoodLog` 0행; 그날 20개 → 400 `하루에 20개까지 남길 수 있어요.`·파일 없음; 저장소 off 503.
    - `test_photo_owner_check_keeps_shopping` — `photos.user_photo_keys([uid])`가 메모 사진 키와 기록 사진 키를 모두 돌려줌(단언은 이것만; 기존 `test_shopping_notes.py` 통과는 Step 2 전체 테스트가 확인한다).
  - `test_demo.py`: `test_purge_deletes_food_log_photo_files` — `demo_photo`와 같은 방식으로 체험 계정에 기록+사진 → `created_at`을 25시간 전으로 → `purge-demo-users` → 파일 없음, 새 체험 계정 사진은 남음.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — `test_shopping_notes.py`·`test_demo.py` 전체 포함.
- [ ] **Step 3: 스펙** — 24절 `구현 세부`에 사진 테이블·키·검사 순서·문구·결정 8·9·17, 사진만 먼저 API. 5절 표에(Task 5와 병렬이라 병합 충돌이 나면 두 쪽 행 모두 남긴다, 개정 1 P17) `POST/DELETE /api/food-logs/<id>/photos…`·`POST /api/food-logs/photo`, `GET /api/photos/<key>` 줄에 `foodlog/` 접두사. 27절 회원 탈퇴 줄 `shopping/<user_id>/` 뒤에 `·foodlog/<user_id>/`(`photos.user_photo_keys`). 28절 메모 사진 줄 끝에 `(검사는 photos.read_image, 먹은 기록과 같음)`.
- [ ] **Step 4: 커밋** — `feat: 먹은 기록 사진 4장·사진만 먼저 남기기(시간으로 끼니 정함)와 사진 검사 공용화`

---

### Task 4: 한 달 달력·요약 API

**Files:**
- Create: `backend/tests/test_food_log_month.py`
- Modify: `backend/app/food_logs.py`, 스펙(24절 `구현 세부`, 5절 표)

**Interfaces:**
- Consumes: Task 2·3 `FoodLog`·`FoodLogPhoto`·`photo_json`, `meals.MEALS`, `ingredients.seoul_today`
- Produces:
  ```python
  _MONTH = re.compile(r"(\d{4})-(\d{2})")  # 반드시 _MONTH.fullmatch(value) — match면 "2026-09-01"이 통과한다(개정 1 D12)


  def month_start(value):
      """'2026-09' → date(2026, 9, 1). 문자열이 아니거나 _MONTH.fullmatch가 None이거나 달이 1~12 밖이면 400 BAD_REQUEST, 2000-01~2100-12 밖이면 400 '날짜를 다시 확인해주세요.'"""


  def month_json(user_id, first):
      """결정 11. 그 달 내 기록(끼니 순 → created_at → id, 사진 selectinload)을 날짜별로 묶는다."""
      # days: [{date, meals(끼니 수), count, kcal(int|None), approx, photo_url(str|None)}] — 기록 있는 날만, 날짜 순
      # summary: {logged_days, avg_kcal(int|None), avg_approx, home, out, home_percent(int|None)}
  ```
  - `GET /api/food-logs/month?month=YYYY-MM`(로그인) → 200 `{month, today, days, summary}`, `Cache-Control: no-store`. `today`는 서울 오늘. 미래 달도 빈 결과로 받는다(화면이 막는다).
  - 계산: 하루 `kcal` = `kcal is not None`인 기록 합(없으면 `None`), `approx` = 더한 기록 중 `approx`가 있으면. `photo_url` = 정렬 순서로 **사진이 있는** 첫 기록의 `photos[0]` url(사진 없는 앞 기록은 건너뜀 — 결정 11 문구와 같음, 개정 1). `avg_kcal` = `round(sum(하루 kcal) / kcal 있는 날 수)`(없으면 `None`), `avg_approx` = kcal 있는 날 중 `approx`가 있으면. `home`/`out` = `place`별 기록 수, `home_percent` = `round(home * 100 / (home + out))`(둘 다 0이면 `None`).
  - `ponytail:` 한 달 기록을 파이썬에서 묶는다(최대 620줄). 느리면 날짜별 `GROUP BY` 쿼리와 첫 사진 서브쿼리로 바꾼다.

- [ ] **Step 0: 브랜치** — main(Task 3 병합)에서 `feature/foodlog-month`.
- [ ] **Step 1: 실패하는 테스트 작성** (`test_food_log_month.py`, 기록은 앱 컨텍스트에서 `FoodLog` 행을 직접 넣고 사진은 `FoodLogPhoto(photo_key="foodlog/<uid>/a.jpg", size=1)` 행만 — 파일 불필요)
  - `test_month_days_and_summary` — 9/1 `breakfast 700 home`·`lunch 720 home`, 9/2 `dinner 1780 approx out` + 사진 2장(`b.jpg` 먼저), 9/3 `lunch` 사진 기록(`kcal None`, place None, 사진 `c.jpg`), 8/31·10/1 기록(빠짐) → `?month=2026-09` → `days` 날짜 `["2026-09-01", "2026-09-02", "2026-09-03"]`; 9/1 `{meals: 2, count: 2, kcal: 1420, approx: False, photo_url: None}`; 9/2 `photo_url "/api/photos/foodlog/<uid>/b.jpg"`·`approx True`; 9/3 `kcal None`·`approx False`·`meals 1`; `summary == {logged_days: 3, avg_kcal: 1600, avg_approx: True, home: 2, out: 1, home_percent: 67}`; `today` 문자열; `Cache-Control no-store`.
  - `test_first_photo_follows_meal_order` — 같은 날 저녁 기록(사진 `x.jpg`, `created_at` 더 이름)·점심 기록(사진 `y.jpg`)·아침 기록(사진 없음) → `photo_url`이 `y.jpg`.
  - `test_same_meal_counts_once_for_dots` — 같은 날 점심 기록 3개 → `meals 1`·`count 3`.
  - `test_empty_month_and_other_users` — 남의 기록만 있는 달 → `{days: [], summary: {logged_days: 0, avg_kcal: None, avg_approx: False, home: 0, out: 0, home_percent: None}}`.
  - `test_month_validation` parametrize — `month` 없음·`"2026-9"`·`"2026-13"`·`"abcd-ef"`·`"2026-09-01"` → 400 `잘못된 요청이에요.`; `"1999-12"`·`"2101-01"` → 400 `날짜를 다시 확인해주세요.`; 로그인 없음 401.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 24절 `구현 세부`에 응답 모양·결정 11(첫 사진 = 끼니 순·남긴 순으로 사진이 있는 첫 기록의 첫 사진)·19(`요` 표시는 5단계). 5절 표 `GET /api/food-logs/month`(Task 5와 충돌하면 두 쪽 행 모두 남김, 개정 1 P17).
- [ ] **Step 4: 커밋** — `feat: 먹은 기록 한 달 달력·요약 API(첫 사진·끼니 수·하루 kcal·집밥 비율)`

---

### Task 5: 식단 칸 `먹었어요` API

**Files:**
- Create: `backend/tests/test_meal_food_log.py`
- Modify: `backend/app/meals.py`, 스펙(20절 `구현 세부`에 줄 추가 — 24절 줄은 병합 때 24절 `구현 세부`에 붙인다)

**Interfaces:**
- Consumes: Task 2 `FoodLog`(backref `MealSlot.food_log`)·`food_logs.create_log`·`log_json`·`BAD_REQUEST`(칸 규칙·미래 검사·상한·스냅숏·경합 처리는 모두 `create_log` 안 — 여기서 복사하지 않는다, 개정 1 P5·D1), `meals._owned_slot`·`_owned_plan_with_slots`·`slot_json`·`put_meal_slot`
- Produces:
  - `slot_json` 끝에 `"eaten_log_id": slot.food_log.id if slot.food_log is not None else None`(4b-2 Task 5가 넣은 `nutrition` 칸·인자는 그대로).
  - `_owned_plan_with_slots`: `options(selectinload(MealPlan.slots).selectinload(MealSlot.recipe), selectinload(MealPlan.slots).selectinload(MealSlot.food_log))`(N+1 없음).
  - `put_meal_slot`: 이미 있는 칸을 덮어쓸 때 `slot.food_log = None`(결정 6 — 다른 요리로 바꾸면 연결만 끊고 기록은 남긴다). 새 칸은 그대로.
  - 새 API:
    ```python
    @bp.post("/meal-slots/<int:slot_id>/eaten")
    @login_required
    def mark_slot_eaten(slot_id):
        """결정 6: 칸의 날짜·끼니·요리를 1인분·집밥으로 먹은 기록에 남긴다. 이미 남겼으면 그 기록 200."""
        from .food_logs import BAD_REQUEST, FoodLog, create_log, log_json  # food_logs가 meals를 import해서 함수 안에서

        slot = _owned_slot(slot_id)
        if slot.food_log is not None:
            return jsonify(log_json(slot.food_log))
        # 칸에서 날짜·끼니·제목·레시피를 가져오고 미래 400·하루 상한·스냅숏은 create_log(apply_fields)가 POST와 같은 규칙으로 한다. servings 기본 1
        log = create_log({"meal_slot_id": slot.id, "place": "home"})
        if log is None:  # 같은 칸을 동시에 두 번 눌렀다(create_log가 rollback함)
            existing = FoodLog.query.filter_by(meal_slot_id=slot_id).one_or_none()
            if existing is None:
                abort(400, BAD_REQUEST)
            return jsonify(log_json(existing))
        return jsonify(log_json(log)), 201
    ```
  - `ponytail:` 칸 저장 응답(`PUT …/slots`·`PATCH /api/meal-slots/<id>`)은 `slot.food_log`를 지연 로딩한다(칸 하나라 한 쿼리).

- [ ] **Step 0: 브랜치** — main(Task 2 병합)에서 `feature/foodlog-meal-eaten`.
- [ ] **Step 1: 실패하는 테스트 작성** (`test_meal_food_log.py`, `from tests.test_meals import add_recipe, make_plan, put_slot`, 오늘 고정은 `monkeypatch.setattr("app.meals.seoul_today", …)`·`"app.food_logs.seoul_today"` 둘 다 9/15)
  - `test_eaten_creates_log_once` — 식단 시작 9/14, 칸 9/14 저녁 레시피 인분 2 → POST eaten 201 `{source: "meal_plan", place: "home", servings: 1.0, eaten_on: "2026-09-14", meal: "dinner", title: 레시피 제목, recipe_id, meal_slot_id, slot_servings: 2}` → 다시 POST 200 같은 `id` → `FoodLog.query.count() == 1` → `GET /api/meal-plans/<id>` 그 칸 `eaten_log_id == id`, 다른 칸 `None` → `GET /api/food-logs?date=2026-09-14` `plan_slots`에 그 칸 없음.
  - `test_eaten_snapshot_uses_slot_nutrition` — 4b-2 Task 5 `test_mostly_missing_recipe_falls_back_to_est_kcal`처럼 AI 초안 넣기(`est_kcal 420`)로 채운 칸 → eaten → `nutrition.kcal == 420`·`approx True`.
  - `test_future_slot_rejected` — 칸 9/16 → 400 `아직 오지 않은 날은 남길 수 없어요.`, 행 없음.
  - `test_overwrite_slot_unlinks_log` — eaten 뒤 `PUT …/slots`로 같은 날짜·끼니에 다른 레시피 → 응답 `eaten_log_id None`, 기록은 남고 `meal_slot_id None`·옛 제목 → 다시 eaten → 새 기록 201.
  - `test_delete_slot_or_plan_keeps_log` — `DELETE /api/meal-slots/<id>` → 기록 `meal_slot_id None`; 다른 칸 eaten 뒤 `DELETE /api/meal-plans/<id>` → 기록 남음.
  - `test_ownership_and_csrf` — 남의 칸 404, `2**31` 404, `raw_client` 400, 로그인 없음 401.
  - `test_slot_responses_have_eaten_key` — `PUT …/slots` 응답·`PATCH /api/meal-slots/<id>` 응답·`copy-week` 응답 칸 모두 `eaten_log_id` 키(복사된 칸은 `None`).
  - `test_caps_apply` — `monkeypatch.setattr("app.food_logs.MAX_PER_DAY", 1)`, 9/14 기록 하나 → eaten 400 `하루에 1개까지 남길 수 있어요.`
  - `test_eaten_race_returns_existing` — 경합 분기 두 갈래(개정 1 D3): ① 가짜 `create_log`(`monkeypatch.setattr("app.food_logs.create_log", fake)`)가 그 칸에 연결된 `FoodLog`를 넣고 커밋한 뒤(다른 요청이 먼저 남긴 것처럼) `None` → 200 그 기록 id·`FoodLog` 1행; ② 아무것도 넣지 않고 `None` → 400 `잘못된 요청이에요.`
  - 기존 `test_meals.py`·`test_meal_ai.py`·`test_meal_shopping.py`·`test_meal_nutrition.py`·`test_export.py` 그대로 통과.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 20절 `구현 세부` 칸 JSON 줄에 `eaten_log_id`(24절 참고), `PUT …/slots` 줄에 `덮어쓰면 먹은 기록 연결을 끊는다`, 5절 표에 `POST /api/meal-slots/<id>/eaten`(Task 3·4·6과 병렬이라 병합 충돌이 나면 두 쪽 행 모두 남긴다, 개정 1 P17). 24절 `구현 세부` 결정 6 줄은 Task 2~4와 겹치지 않게 병합 때 붙인다(24절 `2026-09-15` 줄의 `1인분` 문구는 이미 있어 고치지 않음, S11).
- [ ] **Step 4: 커밋** — `feat: 식단 칸 먹었어요(1인분·집밥으로 한 번만 기록)와 칸의 먹은 기록 표시`

---

### Task 6: 내보내기 `food_logs.csv`·체험 계정 예시 기록

**Files:**
- Modify: `backend/app/export.py`, `backend/app/demo.py`, `backend/tests/test_export.py`, `backend/tests/test_demo.py`, 스펙(27절 내보내기·9절 체험 계정 줄·24절 `구현 세부`)

**Interfaces:**
- Consumes: Task 2·3 `FoodLog`·`FoodLogPhoto`, `export.write_csv`·`safe`·`number`·`seoul_time`·`MEAL_LABELS`·`owned`·`BATCH`, `demo.seed_demo_data`의 `recipe_rows`·`today`, `meals.MEALS`
- Produces:
  - `export.py`:
    ```python
    PLACE_LABELS = {"home": "집밥", "out": "외식"}
    FOOD_LOG_SOURCE_LABELS = {"manual": "직접", "meal_plan": "식단", "cook_log": "요리 일기"}
    FOOD_LOG_HEADER = ["날짜", "끼니", "무엇을 먹었나요", "어디서", "인분", "먹은 양(g)", "kcal", "탄수화물(g)", "단백질(g)", "지방(g)",
                       "당류(g)", "나트륨(mg)", "추정", "만족도", "메모", "남긴 방법", "사진 수", "사진 파일 이름", "남긴 시각"]


    def food_log_rows():
        """food_logs.csv에 담는 내 먹은 기록: 날짜 → 끼니(MEALS 순) → 남긴 순(created_at, id)."""
    ```
    한 줄: `[log.eaten_on, MEAL_LABELS[log.meal], log.title or "사진 기록", PLACE_LABELS.get(log.place, ""), "" if log.servings is None else number(log.servings), "" if log.grams is None else log.grams, 영양 여섯 칸(없으면 "", 있으면 number), "예" if log.approx else "", "" if log.rating is None else log.rating, log.memo or "", FOOD_LOG_SOURCE_LABELS.get(log.source, log.source), len(log.photos), "; ".join(os.path.basename(p.photo_key) for p in log.photos), seoul_time(log.created_at)]`. `meals.csv` 뒤에 쓴다(`selectinload(FoodLog.photos)`, `yield_per(BATCH)`). `summary`에 `food_logs=owned(FoodLog).count()`.
  - `demo.py`:
    ```python
    # (며칠 전, 끼니, 예시 레시피 제목 또는 None, 직접 쓴 이름, 어디서, 만족도, 메모) — 결정 16
    FOOD_LOGS = [
        (1, "dinner", "김치찌개", None, "home", 5, None),  # recipe_rows에서 제목이 같은 예시 레시피
        (1, "lunch", None, "제육덮밥", "out", 3, "회사 앞 · 조금 짰어요"),
        (0, "breakfast", None, "토스트", "home", 4, None),
    ]
    ```
    `seed_demo_data` 끝(식단 뒤)에 `recipe = next(r for r in recipe_rows if r.title == 제목)`(제목이 None이면 None)으로 `FoodLog(user_id, eaten_on=today - timedelta(days=n), meal, source="manual", title=recipe.title if recipe else name, recipe=recipe, servings=1.0, place, rating, memo, nutrition_pending=recipe is not None)`. 영양은 계산하지 않는다(요청 사용자 `g.user`가 없어서 — 상세를 열 때 결정 2 흐름으로 채움).

- [ ] **Step 0: 브랜치** — main(Task 4 병합)에서 `feature/foodlog-export-demo`.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_export.py`: `test_export_includes_food_logs_csv` — 내 기록 3개(9/14 저녁 음식 기록 `servings 0.5, kcal 370, sugars_g 11.0, approx True, place out, rating 3, memo "=1+1"` + 사진 행 2개 `foodlog/<uid>/a.jpg`·`b.png`, 9/14 아침 사진 기록 `title None`, 9/13 간식 식단 기록 `source meal_plan`)와 남의 기록 1개 → zip `food_logs.csv` 머리글 == `FOOD_LOG_HEADER`, 줄 순서 9/13 간식 → 9/14 아침 → 9/14 저녁, 아침 줄 `무엇을 먹었나요 "사진 기록"`, 저녁 줄 `인분 "0.5"`·`kcal "370"`·`당류(g) "11"`·`추정 "예"`·`어디서 "외식"`·`메모 "'=1+1"`·`사진 수 "2"`·`사진 파일 이름 "a.jpg; b.png"`·`남긴 방법 "직접"`, 간식 줄 `남긴 방법 "식단"`.
  - `test_summary_counts_only_my_data`(기존) — 기대 dict에 `food_logs` 키를 더한다(내 기록 수만).
  - `test_export_empty_data_has_header_only_csvs`(기존, zip dict 전체 비교) — 기대에 `"food_logs.csv": [FOOD_LOG_HEADER]`를 더한다(개정 1 S8).
  - `test_export_zip_contents`(기존, `set(files) == {…6개}`) — 파일 집합에 `food_logs.csv`를 더한다(개정 1 S8).
  - `test_demo.py`: `test_demo_login_seeds_food_logs` — 체험하기 → 먹은 기록 3개, 어제 저녁 `title "김치찌개"`·`recipe_id` 있음·`nutrition_pending True`, 어제 점심 `memo "회사 앞 · 조금 짰어요"`·`place "out"`, 오늘 아침 `토스트`; 다른 체험 계정과 섞이지 않음. 하루 GET 단언은 모드별로 둘(개정 1 P6·S9): ① 기존 `demo_app`(`DEV_MODE=False`, 키 없음 = 영양 off) → `GET /api/food-logs?date=<어제>` 200, 김치찌개 기록 `nutrition None`·`nutrition_pending False`, `nutrition_pending_recipe_ids []`(off면 `nutrition_results`가 `{}`라 pending이 꺼짐); ② `make_app(DEMO_LOGIN=True, DEV_MODE=True, DEMO_IP_HOURLY_LIMIT=3, DEMO_IP_DAILY_LIMIT=10)`(sample) → 같은 GET에서 `nutrition_pending_recipe_ids`에 김치찌개 id(캐시에 `FoodSearch`가 없어 찾아볼 재료가 남음).
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 27절 내보내기 목록에 `food_logs.csv` 칸(결정 18), `먹은 기록·요리 기록은 기능이 생기면 추가한다` 문장을 `요리 기록은 5단계에서 추가한다`로, 5절 표 `GET /api/export/summary` 모양에 `food_logs`·`GET /api/export` 파일 목록에 `food_logs.csv`(Task 5와 충돌하면 두 쪽 모두 남김, 개정 1 P17). 9절 체험 계정 줄에 `먹은 기록 예시 3개`. 24절 `구현 세부`에 결정 16.
- [ ] **Step 4: 커밋** — `feat: 먹은 기록 내보내기(food_logs.csv)와 체험 계정 예시 기록`

---

### Task 7: 달력 페이지·월 요약·더보기 `기록` 줄

**Files:**
- Create: `frontend/src/foodlog/log.ts`, `frontend/scripts/check-foodlog.mjs`, `frontend/src/pages/FoodLog.tsx`
- Modify: `frontend/package.json`, `frontend/src/api.ts`, `frontend/src/useHashRoute.ts`, `frontend/src/App.tsx`, `frontend/src/pages/More.tsx`, `frontend/src/styles.css`, 스펙(24절 `화면` 줄, 27절 `기록` 묶음)

**Interfaces:**
- Consumes: Task 4 `GET /api/food-logs/month`, Task 2 `GET /api/food-logs?date=`, Task 6 `summary.food_logs`, `meals/plan.ts` `monthGrid`·`slotDateText`, 4b-2 `nutrition/body.ts` `kcalNumber`, 4b-2 `api.ts` `SlotNutrition`, 4b-2 Task 8 `components/LoadError.tsx`·`App.resetScreens`의 `resetRecipeNutrition()`, `useResource`·`forgetResources`, `localToday`, `navigate`·`goBack`, `Icon`
- Produces:
  - `api.ts`(Task 8~11이 이 타입을 그대로 쓴다 — 뒤 태스크는 `api.ts`를 고치지 않는다):
    ```ts
    // ---- 먹은 기록(스펙 24절, 4b-3) ----
    export type FoodPlace = "home" | "out";
    /** 칸 1인분 영양에서 approx·source만 뺀 모양(타입 한 벌, 개정 1 D8) — Task 9 scaleNutrition 인자도 이것 */
    export type FoodLogNutrition = Omit<SlotNutrition, "approx" | "source">;
    export interface FoodLogPhoto { id: number; url: string }
    export interface FoodLog {
      id: number; eaten_on: string; meal: MealKind; source: "manual" | "meal_plan" | "cook_log";
      /** null이면 사진만 먼저 남긴 `사진 기록` */
      title: string | null; recipe_id: number | null; meal_slot_id: number | null; slot_servings: number | null;
      food_code: string | null; servings: number | null; grams: number | null;
      place: FoodPlace | null; rating: number | null; memo: string | null;
      nutrition: FoodLogNutrition | null; approx: boolean; nutrition_pending: boolean; created_at: string; photos: FoodLogPhoto[];
    }
    export interface FoodLogPlanSlot { id: number; meal: MealKind; title: string; servings: number; recipe_id: number | null }
    export interface FoodLogDay { date: string; logs: FoodLog[]; plan_slots: FoodLogPlanSlot[]; nutrition_pending_recipe_ids: number[] }
    export interface FoodLogMonthDay { date: string; meals: number; count: number; kcal: number | null; approx: boolean; photo_url: string | null }
    export interface FoodLogMonthSummary { logged_days: number; avg_kcal: number | null; avg_approx: boolean; home: number; out: number; home_percent: number | null }
    export interface FoodLogMonth { month: string; today: string; days: FoodLogMonthDay[]; summary: FoodLogMonthSummary }
    export interface DishItem { food_code: string; name: string; serving_g: number | null; kcal: number; carbs_g: number | null; protein_g: number | null; fat_g: number | null; sugars_g: number | null; sodium_mg: number | null }
    export interface DishSearchResult { items: DishItem[]; searched: boolean }
    ```
    `MealSlot`에 `/** 먹었어요로 남긴 먹은 기록 id(24절) */ eaten_log_id: number | null;`, `ExportSummary`에 `food_logs: number;`.
  - `src/foodlog/log.ts`(브라우저 API 없음, 오늘은 인자):
    ```ts
    import type { FoodLog, FoodLogMonthDay, FoodLogMonthSummary, FoodPlace } from "../api";
    import { slotDateText } from "../meals/plan.ts";
    import { kcalNumber } from "../nutrition/body.ts";

    export const PLACE_LABEL: Record<FoodPlace, string> = { home: "집밥", out: "외식" };
    export const monthOf = (iso: string) => iso.slice(0, 7);
    /** "2026-01", -1 → "2025-12" */
    export function shiftMonth(month: string, delta: number): string {
      const [y, m] = month.split("-").map(Number);
      const total = y * 12 + (m - 1) + delta;
      return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
    }
    /** "2026-09" → "2026년 9월" */
    export const monthLabel = (month: string) => `${Number(month.slice(0, 4))}년 ${Number(month.slice(5, 7))}월`;
    /** 달력 칸 작은 kcal "1,420" · "약 1,780" · "" */
    export const cellKcalText = (day: Pick<FoodLogMonthDay, "kcal" | "approx"> | undefined) =>
      day?.kcal == null ? "" : `${day.approx ? "약 " : ""}${kcalNumber(day.kcal)}`;
    /** 칸 버튼 이름 "9월 14일 월요일, 끼니 3개, 약 1,190kcal, 사진 있음" / "9월 15일 화요일 · 오늘, 기록 없음" */
    export function cellLabel(date: string, day: FoodLogMonthDay | undefined, today: string): string {
      const base = slotDateText(date, today);
      if (!day) return `${base}, 기록 없음`;
      return [base, `끼니 ${day.meals}개`, day.kcal != null && `${cellKcalText(day)}kcal`, day.photo_url && "사진 있음"].filter(Boolean).join(", ");
    }
    /** 월 요약 카드(시안 MONTH) */
    export function summaryView(s: FoodLogMonthSummary) {
      return {
        days: `${s.logged_days}일`,
        kcal: s.avg_kcal == null ? "—" : `${s.avg_approx ? "약 " : ""}${kcalNumber(s.avg_kcal)}`,
        home: s.home_percent == null ? "—" : `${s.home_percent}%`,
        split: s.home_percent == null ? null : ([s.home_percent, 100 - s.home_percent] as [number, number]),
        note: s.home + s.out ? `집밥 ${s.home}끼 · 외식 ${s.out}끼 · 기록한 날 기준이에요` : "집밥·외식을 고르면 비율을 보여줘요",
      };
    }
    /** 더보기 줄 부제(결정 20). 아직 못 받았으면 "" */
    export function todayRowSub(logs: Pick<FoodLog, "meal">[] | undefined): string {
      if (!logs) return "";
      const meals = new Set(logs.map((l) => l.meal)).size;
      return meals ? `오늘 ${meals}끼 남겼어요` : "먹은 것·사진을 달력에 남겨요";
    }
    ```
  - `check-foodlog.mjs`(`node:assert/strict`, Task 8·9가 이어 붙인다): `shiftMonth("2026-01", -1) === "2025-12"`, `("2026-12", 1) === "2027-01"`, `("2026-09", 0) === "2026-09"`; `monthLabel("2026-09") === "2026년 9월"`; `cellKcalText({kcal: 1780, approx: true}) === "약 1,780"`, `({kcal: 1420, approx: false}) === "1,420"`, `({kcal: null, approx: false}) === ""`, `(undefined) === ""`; `cellLabel("2026-09-14", {date: "2026-09-14", meals: 3, count: 3, kcal: 1190, approx: true, photo_url: "/api/photos/x"}, "2026-09-15") === "9월 14일 월요일, 끼니 3개, 약 1,190kcal, 사진 있음"`, `cellLabel("2026-09-15", undefined, "2026-09-15") === "9월 15일 화요일 · 오늘, 기록 없음"`, kcal 없는 날 `"…, 끼니 1개"`; `summaryView({logged_days: 12, avg_kcal: 1640, avg_approx: true, home: 18, out: 7, home_percent: 72})` → `{days: "12일", kcal: "약 1,640", home: "72%", split: [72, 28], note: "집밥 18끼 · 외식 7끼 · 기록한 날 기준이에요"}`, 빈 요약 → `kcal "—"`·`home "—"`·`split null`·`note "집밥·외식을 고르면 비율을 보여줘요"`; `todayRowSub([{meal: "breakfast"}, {meal: "breakfast"}, {meal: "lunch"}]) === "오늘 2끼 남겼어요"`, `([]) === "먹은 것·사진을 달력에 남겨요"`, `(undefined) === ""`.
  - `pages/FoodLog.tsx`:
    ```ts
    /** 다른 화면(식단 칸 상세)에서 먹은 기록으로 올 때 열 날짜·기록. 화면이 읽고 비운다 */
    export function openFoodLog(target: { date: string; logId?: number }): void;
    /** 로그아웃: 보던 달·열 대상을 비운다 */
    export function resetFoodLogView(): void;
    /** 컴포넌트 이름은 FoodLogPage — 같은 파일이 `import type { FoodLog } from "../api"`를 쓰므로 `FoodLog`로 지으면 TS2440 이름 충돌(개정 1 D9) */
    export default function FoodLogPage({ user }: { user: User }): JSX.Element;
    ```
    - 모듈 상태 `let viewMonth: string | null`·`let pendingOpen: { date: string; logId?: number } | null`. 처음 달 = `pendingOpen?.date`의 달 → `viewMonth` → `monthOf(localToday())`. **오늘**은 받은 응답의 `today`(서울, 서버)를 쓰고, 받기 전에만 `localToday()`(개정 1 P14 — 기기 시계가 달라도 `›` 막기·오늘 원·미래 칸이 서버와 같게). `pendingOpen`이 있으면 그 날짜를 `selected`로(Task 8이 시트를 열고 Task 9가 기록을 연다) 두고 비운다.
    - `header.topbar.fl-top`: `button.icon-btn`(`aria-label="더보기로 돌아가기"`, `Icon back`, `goBack("/more")`) + `h1 먹은 기록`. (오른쪽 카메라 버튼은 Task 10.)
    - 월 요약 `section.nt-card.fl-summary`(`aria-label="{2026년 9월} 요약"`): `div.fl-stats` 세 칸 `b 12일`/`span 기록한 날`, `b 약 1,640`/`span 하루 평균 kcal`, `b 72%`/`span 집밥`; `split`이 있으면 `div.fl-split`(`role="img"`, `aria-label="집밥 72%, 외식 28%"`, `i style={{flex: 72}}` 두 개); `p.muted {note}`.
    - 달 이동 `div.fl-mnav`: `button.icon-btn`(`aria-label="지난달"`, `Icon back`) · `h2 aria-live="polite" {monthLabel}` · `button.icon-btn`(`aria-label="다음 달"`, `Icon chevron`, `month >= monthOf(today)`이면 `disabled`, `today` = 응답 `today ?? localToday()`). 바꾸면 `viewMonth`에도 넣는다.
    - 달력 `div.fl-cal`: `div.fl-dow` 월~일, `monthGrid(year, month)` 줄마다 `div.fl-wk`. 칸: 다른 달 날짜 `div.fl-cell.dim`(날짜만), 오늘 뒤 `div.fl-cell`(날짜만), 그 밖 `button.fl-cell`(`aria-label={cellLabel(...)}`, 오늘 `.today`, 고른 날 `.sel` + `aria-pressed`) 안에 `span.fl-d {일}` + 사진이 있으면 `img.fl-th`(`src={photo_url}`, `alt=""`, `loading="lazy"`, `decoding="async"`) 아니면 `span.fl-dots`(`i` × `meals`) + `span.fl-kc {cellKcalText}`. 누르면 `setSelected(date)`.
    - 범례 `p.fl-legend` `● 끼니 기록 · 사진 = 첫 사진`(결정 19 — `요` 범례는 5단계).
    - 데이터 `useResource<FoodLogMonth>(`/api/food-logs/month?month=${month}`)`. 처음 받기 전 `p.muted 불러오는 중…`, 오류는 `<LoadError error onRetry>`(4b-2 Task 8의 `components/LoadError.tsx`).
  - `useHashRoute.ts` `ROUTES`에 `"/food-log"`, `App.tsx` `import FoodLogPage, { resetFoodLogView } from "./pages/FoodLog"`, `PAGES`에 `"/food-log": ({ user }) => <FoodLogPage user={user} />`, `resetScreens`에서 4b-2 `resetRecipeNutrition()` 바로 뒤에 `resetFoodLogView()`.
  - `More.tsx`: `우리 부엌` 위에 `h2.mo-group 기록` + `ul.list` 안 `Row icon={<Icon name="calendar" />} title="먹은 기록" sub={todayRowSub(today.data?.logs)} onClick={() => navigate("/food-log")}`(`today = useResource<FoodLogDay>(`/api/food-logs?date=${localToday()}`)`). `ExportSheet` 목록 `meals` 줄 뒤에 `먹은 기록` · `b {count(data?.food_logs)}`(기존 `count` 헬퍼, 단위 `개`).
  - `styles.css` `/* 먹은 기록 (4b-3) */`: `.fl-top`, `.fl-summary`, `.fl-stats`(3열, `b` 18px `tabular-nums`, `span` 12px `--text-3`), `.fl-split`(8px, 첫 `i` `--accent`, 둘째 `--chip-line`), `.fl-mnav`, `.fl-cal`(`--surface`, 20px 둥글게), `.fl-dow`·`.fl-wk`(7열 gap 4px), `.fl-cell`(높이 76px, 버튼 초기화, `.dim` `--chip-line` 글자, `.today .fl-d` 24px 초록 원, `.sel` `--accent-tint`, `:focus-visible` 기존 포커스 링), `.fl-th`(34px, 9px 둥글게, `object-fit: cover`), `.fl-dots`(높이 34px, `i` 6px 점 `--accent`), `.fl-kc`(10px `--text-3` `tabular-nums`), `.fl-legend`. 칸 버튼 터치 영역은 칸 전체(76px × 약 48px).

- [ ] **Step 0: 브랜치** — main(Task 6 병합)에서 `feature/foodlog-calendar-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-foodlog.mjs`(위 목록) → `node scripts/check-foodlog.mjs`가 `log.ts` 없음으로 실패하는지 확인. `package.json` `check` 끝에 `&& node scripts/check-foodlog.mjs`.
- [ ] **Step 2: `log.ts` 구현 → 검사 통과**
- [ ] **Step 3: 화면 구현** — `api.ts` 타입 → 경로·`App` → `FoodLog.tsx` → `More.tsx` → `styles.css`.
- [ ] **Step 4: 검사·빌드** — `cd frontend && npm run check && npm run build`.
- [ ] **Step 5: 브라우저 확인(데스크톱 크롬 384×832, Global Constraints의 `vite.wt.config.ts` 포트 5207 → 5181 프록시, 개발용 로그인)** — 음식 기록용 `food_code`는 실제 `GET /api/foods/dishes?q=제육덮밥` 한 번(이 태스크 실제 요청 2번 중 1)으로 받은 `items[0].food_code`를 쓴다(5181은 실제 키라 `SAMPLE-18`이 없을 수 있음). 기록이 없는 계정: 더보기 `기록` 묶음이 `우리 부엌` 위, `먹은 기록 · 먹은 것·사진을 달력에 남겨요` → 누르면 `#/food-log` 달력(요약 `0일 · — · —`, `집밥·외식을 고르면 비율을 보여줘요`, 오늘 초록 원, 미래 날짜는 눌리지 않음, `›` 막힘) → 개발자 도구 콘솔에서 `fetch("/api/food-logs", {method: "POST", headers: {"X-Requested-With": "fetch", "Content-Type": "application/json"}, body: JSON.stringify({eaten_on: "<어제>", meal: "lunch", title: "제육덮밥", place: "out"})})` 몇 개(오늘·어제, 집밥·외식, 위에서 받은 음식 코드로 `servings 0.5`) → 새로고침: 점·`약 N` kcal·요약 숫자·비율 막대 → 지난달로 갔다가 돌아오기·더보기 갔다 와도 달 유지 → 더보기 줄 `오늘 1끼 남겼어요` → 내보내기 시트 `먹은 기록 N개`. 다크 모드, 키보드 탭 순서(뒤로 → 지난달 → 다음 달 → 칸), 스크린리더 칸 이름(`cellLabel`). 스크린샷을 리뷰어에게 남긴다.
- [ ] **Step 6: 스펙** — 24절 `구현 세부`에 `화면:` 줄(요약 카드·달 이동·칸·범례·결정 20·22), 27절 표 `기록` 행 `먹은 기록(4b-3 완료)`.
- [ ] **Step 7: 커밋** — `feat: 먹은 기록 달력(월 요약·첫 사진·끼니 점·하루 kcal)과 더보기 기록 묶음`

---

### Task 8: 날짜 상세 시트

**Files:**
- Create: `frontend/src/components/FoodLogDaySheet.tsx`(`fillAttempted` Set 포함)
- Modify: `frontend/src/foodlog/log.ts`, `frontend/scripts/check-foodlog.mjs`, `frontend/src/pages/FoodLog.tsx`, `frontend/src/styles.css`, 스펙(24절 `구현 세부` `화면:` 줄, 21절 4b-2 Task 7 채우기 설명 한 줄)

**Interfaces:**
- Consumes: Task 7 타입·`FoodLog.tsx`(`selected` state·`pendingOpen`)·`PLACE_LABEL`, `format.ts` `withJosa`, `BodyProfileResponse`, Task 2 `GET /api/food-logs?date=`, Task 5 `POST /api/meal-slots/<id>/eaten`, 4b-2 `POST /api/nutrition/fill`·`dailyTarget`·`kcalNumber`·`meterPercent`·`sodiumDay`·`.nt-meter`·`.nt-dmeter`·`.nt-src`, `plan.ts` `MEALS`·`slotDateText`, `Sheet`, `Icon`, `useResource`·`forgetResources`, `useAsyncAction`
- Produces:
  - `log.ts` 추가(검사 같이):
    ```ts
    export interface DayTotals { kcal: number; approx: boolean; sugars_g: number; sodium_mg: number }
    /** kcal 있는 기록만 더한다(결정 11·15). 당류·나트륨은 값 있는 것만. kcal 있는 기록이 없으면 null.
     *  (이름 없는 사진 기록 수는 세지 않는다 — dayDescription이 logs.some으로 본다, 개정 1 D7) */
    export function dayTotals(logs: Pick<FoodLog, "nutrition" | "approx">[]): DayTotals | null {
      const counted = logs.filter((l) => l.nutrition);
      if (!counted.length) return null;
      const t: DayTotals = { kcal: 0, approx: false, sugars_g: 0, sodium_mg: 0 };
      for (const l of counted) {
        t.kcal += l.nutrition!.kcal;
        t.approx ||= l.approx;
        t.sugars_g += l.nutrition!.sugars_g ?? 0;
        t.sodium_mg += l.nutrition!.sodium_mg ?? 0;
      }
      return t;
    }
    /** 시트 설명(시안 DAY·PHOTO FIRST) */
    export function dayDescription(logs: Pick<FoodLog, "nutrition" | "approx" | "title">[], goal: number | null): string {
      if (!logs.length) return "아직 남긴 기록이 없어요";
      const t = dayTotals(logs);
      const hint = logs.some((l) => l.title === null) ? "이름을 넣으면 kcal을 계산해요" : "";
      if (!t) return hint || "kcal을 계산할 수 있는 기록이 없어요";
      return [
        `${t.approx ? "약 " : ""}${kcalNumber(t.kcal)}${goal ? ` / 목표 ${kcalNumber(goal)}` : ""}kcal`,
        t.sugars_g ? `당류 ${Math.round(t.sugars_g)}g` : "",
        t.sodium_mg ? `나트륨 ${kcalNumber(t.sodium_mg)}mg` : "",
        hint,
      ].filter(Boolean).join(" · ");
    }
    /** 끼니 머리 오른쪽 "310kcal" / "약 400kcal" / "" */
    export const mealKcalText = (logs: Pick<FoodLog, "nutrition" | "approx" | "title">[]) => {
      const t = dayTotals(logs);
      return t ? `${t.approx ? "약 " : ""}${kcalNumber(t.kcal)}kcal` : "";
    };
    /** 0.5 → "½인분", 1.5 → "1½인분", 2 → "2인분" */
    export const servingsText = (n: number) => `${Math.floor(n) || ""}${n % 1 ? "½" : ""}인분`;
    /** 서울 시각 "12:41" */
    export const timeText = (iso: string) => new Date(iso).toLocaleString("sv-SE", { timeZone: "Asia/Seoul" }).slice(11, 16);
    /** 기록 줄 보조 글자 "1인분 · 310kcal" / "2인분 중 1인분 · 약 480kcal" / "300g · 약 555kcal" / 사진 기록 "12:41 · 누르면 무엇을 먹었는지 채워요" */
    export function logSubText(log: Pick<FoodLog, "title" | "servings" | "grams" | "slot_servings" | "nutrition" | "approx" | "created_at">): string {
      if (log.title === null) return `${timeText(log.created_at)} · 누르면 무엇을 먹었는지 채워요`;
      const amount = log.grams !== null ? `${log.grams}g`
        : log.servings === null ? ""
        : log.slot_servings && log.slot_servings > log.servings ? `${log.slot_servings}인분 중 ${servingsText(log.servings)}` : servingsText(log.servings);
      const kcal = log.nutrition ? `${log.approx ? "약 " : ""}${kcalNumber(log.nutrition.kcal)}kcal` : "";
      return [amount, kcal].filter(Boolean).join(" · ");
    }
    /** 만족도 별 글자 "★★★★☆"(aria는 "만족도 4점") */
    export const starsText = (rating: number) => "★".repeat(rating) + "☆".repeat(5 - rating);
    ```
    검사: 시안 날짜 상세 기록 `[{토스트 310 exact}, {제육덮밥 400 approx, sodium 820}, {김치찌개 480 approx}]` → `dayTotals.kcal 1190`·`approx true`; `dayDescription(그 기록 + 당류 22·나트륨 2380, 1294) === "약 1,190 / 목표 1,294kcal · 당류 22g · 나트륨 2,380mg"`(당류·나트륨 값을 맞춰 넣음), 목표 없으면 `"약 1,190kcal · 당류 22g · 나트륨 2,380mg"`; 사진만 먼저 `[{토스트 310}, {title null, nutrition null}]` → `"310kcal · 이름을 넣으면 kcal을 계산해요"`; `[]` → `"아직 남긴 기록이 없어요"`; 제목만 있는 기록 `[{title "샐러드", nutrition null}]` → `"kcal을 계산할 수 있는 기록이 없어요"`; `mealKcalText([])` `""`; `servingsText(0.5) "½인분"`, `(1.5) "1½인분"`, `(2) "2인분"`; `timeText("2026-09-15T03:41:00+00:00") === "12:41"`; `logSubText` 시안 세 줄(`1인분 · 310kcal`, `1인분 · 약 400kcal`, `slot_servings 2, servings 1` → `2인분 중 1인분 · 약 480kcal`), `grams 300` → `300g · 약 555kcal`, 사진 기록 → `12:41 · 누르면 무엇을 먹었는지 채워요`, 직접 제목만 → `1인분`; `starsText(4) === "★★★★☆"`.
  - `FoodLogDaySheet`(`export default function FoodLogDaySheet(props: { date: string; today: string; user: User; onOpenLog: (log: FoodLog, day: FoodLogDay) => void; onAdd: (meal: MealKind, day: FoodLogDay) => void; onChanged: () => void; onClose: () => void })`), 프레임 2·4:
    - 같은 파일에서 `/** 먹은 기록 화면에서 채우기를 이미 부른 레시피 id(날짜 상세·추가 시트 공용, resetFoodLogView가 비움) */ export const fillAttempted = new Set<number>();`
    - `const day = useResource<FoodLogDay>(`/api/food-logs?date=${date}`)`, `const body = useResource<BodyProfileResponse>("/api/body-profile")`, `goal = body.data?.profile ? dailyTarget(body.data.profile, today).target : null`(결정 15).
    - **채우기(개정 1 S10 — 4b-2 리뷰 수정 `Meals.tsx attempted`·`RecipeNutrition filled`와 같은 방식):** `user.nutrition !== "off"`이면 `ids = day.data.nutrition_pending_recipe_ids.filter((id) => !fillAttempted.has(id)).slice(0, 31)`; 비어 있지 않으면 **요청 전에** `ids.forEach((id) => fillAttempted.add(id))` → `api("/api/nutrition/fill", { method: "POST", body: { recipe_ids: ids } })` → 끝나면(실패도 조용히) `day.reload()`·`onChanged()`. 날짜·조합 키(`${date}|${ids}`)로 기억하지 않는다(pending이 줄 때마다 새 조합으로 다시 부르던 4b-2 버그).
    - `Sheet` title `slotDateText(date, "")`(오늘도 `· 오늘` 없이, 시안), description `dayDescription(logs, goal)`. 받기 전 `p.muted role="status" 불러오는 중…`, 오류 `p.error role="alert"` + `button.btn.secondary 다시 불러오기`.
    - 목표와 합계가 있으면 설명 아래 `div.nt-meter.nt-dmeter`(`role="img"`, `aria-label="목표의 92%"`, 넘으면 `.warn`)에 `i style={{ width: `${meterPercent(t.kcal, goal)}%` }}`. `t = dayTotals(logs)`의 나트륨이 `sodiumDay(t.sodium_mg).warn`이면 그 아래 `p.fl-warn` `나트륨 {sodiumDay(t.sodium_mg).text}`(`나트륨 1일 기준치 넘었어요`, `--warn` 글자).
    - 끼니마다(`MEALS`) `section.fl-meal`(`aria-labelledby`): `div.fl-mealh` `h3 {아침}` + `span.fl-mk {mealKcalText}`. 그 끼니 기록마다 `button.fl-log`(`aria-haspopup="dialog"`, `aria-label="{점심} {제육덮밥 | 사진 기록} 고치기"`) → `onOpenLog(log, day.data)`: 왼쪽 첫 사진이 있으면 `img.fl-ph`(52px, `alt=""`) 아니면 `span.fl-noph`(`Icon bowl`), 가운데 `b {title ?? "사진 기록"}` + place가 있으면 `span.badge.info {집밥}` / `span.badge {외식}`, 사진 기록이면 `span.badge.old 이름 없음`, `small {logSubText}` + rating이 있으면 ` · ` + `span.fl-stars aria-label="만족도 {4}점" {starsText}`, memo가 있으면 둘째 `small {memo}`.
    - 그 끼니의 `plan_slots`마다 `div.fl-plan`: `Icon calendar` + `span 식단에 <b>{title}</b>{withJosa(title, "이", "가").slice(title.length)} 있었어요`(`요거트가 있었어요`) + `button.nt-link 먹었어요`(`aria-label="식단 {요거트} 먹었어요"`, 날짜가 오늘 뒤면 줄 자체를 그리지 않음) → `POST /api/meal-slots/<id>/eaten` → `forgetResources("/api/meal-plans")`·`forgetResources("/api/food-logs")` → `day.reload()`·`onChanged()`. 실패는 끼니 아래 `p.error role="alert"`.
    - 끼니 끝 `button.fl-addrow`(`aria-label="{점심} 먹은 것 추가"`, `aria-haspopup="dialog"`) `b +` `먹은 것` → `onAdd(meal, day.data)`. 날짜가 오늘 뒤면 숨김(달력에서 못 열지만 방어).
    - 맨 아래 `p.nt-src 의료 조언이 아니라 참고용이에요.`
  - `FoodLog.tsx`: 칸을 누르면 `selected`와 함께 시트 열림(`open` state), 닫으면 `selected`는 남겨 `.sel`. `onChanged`는 달 `reload()`와 `forgetResources("/api/food-logs?date=")`(더보기 줄). `pendingOpen`이 있으면 받자마자 시트를 연다. `onOpenLog`·`onAdd`는 Task 9가 시트를 붙일 때까지 `setEditing({ meal, log, day })` state만 둔다(Task 9에서 그 state로 시트를 그린다). `resetFoodLogView()`에 `fillAttempted.clear()`를 더한다(`import { fillAttempted } from "../components/FoodLogDaySheet"`).
  - `styles.css`: `--star` 토큰 세 곳(`#e0a100` / `#f5c542`), `.fl-meal`(위 선 `--line`, 8px 위 여백), `.fl-mealh`, `.fl-mk`(`--text-3` `tabular-nums`), `.fl-log`(52px + 1fr 격자, 버튼 초기화, 최소 높이 56px), `.fl-ph`·`.fl-noph`(52px, 12px 둥글게, `object-fit: cover`, `--field`), `.fl-stars`(`--star`, 12px), `.fl-plan`(`--field` 배경, 12px 둥글게, 링크 오른쪽), `.fl-addrow`(40px → 터치 44px, 안쪽 테두리 `--chip-line`, `b` `--accent-strong`), `.fl-warn`(13px `--warn` 글자).

- [ ] **Step 0: 브랜치** — main(Task 5·7 병합)에서 `feature/foodlog-day-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-foodlog.mjs`에 위 목록 → 실패 확인 → `log.ts` 추가 → 통과.
- [ ] **Step 2: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 3: 브라우저 확인(384×832, `vite.wt.config.ts` 포트 5208 → 5181 프록시; 실제 `fill`·식품 찾기는 2번까지, 나머지는 CDP 가짜 응답)** — 몸 정보 목표 저장(4b-2 카드) → 식단에 오늘·어제 칸 몇 개(레시피 칸 하나·직접 `요거트` 간식 칸) → 콘솔로 어제 기록(토스트 직접 아침 ★4, 실제 `GET /api/foods/dishes` 한 번으로 받은 음식 코드로 점심 외식 메모, 레시피 저녁) → 달력 어제 칸 → 시트 제목 `9월 14일 월요일`·설명 `약 N / 목표 N kcal · 당류 · 나트륨`·막대(넘으면 주황)·끼니별 줄(사진 없음 자리 아이콘·알약·별·메모 줄)·레시피 기록이 처음 `nutrition_pending`이면 채우기 한 번 뒤 kcal이 붙음(실제 `fill` 한 번) → 시트를 닫았다 다시 열어도 같은 레시피로 `fill`이 다시 나가지 않음(네트워크 탭, S10) → 간식 `식단에 요거트가 있었어요 · 먹었어요` 누르면 줄이 기록으로 바뀌고 달력 칸 점이 늘어남 → 오늘 칸에 사진 기록(콘솔로 `POST /api/food-logs/photo` FormData) → `사진 기록`·`이름 없음`·`12:41 · 누르면 무엇을 먹었는지 채워요`·설명 끝 `이름을 넣으면 kcal을 계산해요` → 목표를 지우면 막대가 사라짐 → 식단 칸 상세의 `먹었어요`로 들어온 경우(`openFoodLog`를 콘솔에서 부를 수 없으면 Task 11에서) 생략. 다크·키보드(시트 안 탭 순서: 기록 → 먹었어요 → 먹은 것 추가)·스크린리더 이름(`점심 제육덮밥 고치기`, `만족도 3점`, `목표의 92%`). 스크린샷.
- [ ] **Step 4: 스펙** — 24절 `구현 세부` `화면:`에 날짜 상세(결정 14·15, 채우기 흐름 = 레시피 id별 `fillAttempted`). 21절 `구현 세부 (2026-09-15, 4b-2, Task 7)` `주 보기` 줄의 `식단·레시피 조합마다 한 번만(모듈 Set filledOnce …)` 설명을 실제 코드(`Meals.tsx attempted`에 `${planId}|${recipeId}`를 요청 전에 넣음, `resetMealsView`가 비움)대로 고친다(개정 1 S10).
- [ ] **Step 5: 커밋** — `feat: 먹은 기록 날짜 상세(목표 대비 kcal·끼니별 기록·식단에 있던 칸 먹었어요)`

---

### Task 9: 먹은 것 추가·고치기 시트

**Files:**
- Create: `frontend/src/components/FoodLogSheet.tsx`
- Modify: `frontend/src/foodlog/log.ts`, `frontend/scripts/check-foodlog.mjs`, `frontend/src/pages/FoodLog.tsx`, `frontend/src/styles.css`, 스펙(24절 `구현 세부` `화면:` 줄)

**Interfaces:**
- Consumes: Task 7·8 타입·`log.ts`·`FoodLog.tsx` `editing` state·`FoodLogDaySheet` `onOpenLog`/`onAdd`·`fillAttempted`, 4b-2 Task 8 `FoodPickSheet` 모양(검색 칸 `div.input-suffix.nt-food-search`, 후보 `label.nt-cand`+`input.sr-only`+`span.nt-radio`, 아래 고정 `div.scan-foot` > `div.nt-pick-actions`, 틀린 입력 `p.hint.nt-invalid`, `focusTitle`), Task 1 `GET /api/foods/dishes?q=`, Task 2 `POST/PATCH/DELETE /api/food-logs`, 기존 `GET /api/recipes/choices?q=`(`RecipeChoice`), 4b-2 `GET /api/recipes/<id>/nutrition`(`RecipeNutrition.per_serving`·`approx`·`usable`·`pending`)·`POST /api/nutrition/fill`, `plan.ts` `MEALS`·`mealLabel`·`slotDateText`, `Sheet`, `Icon`, `useAsyncAction`, `forgetResources`
- Produces:
  - `log.ts` 추가(검사 같이). `DishItem`·`FoodLogNutrition`은 파일 중간에 새 import 블록을 두지 않고 **Task 7의 맨 위 `import type { … } from "../api"`에 합친다**(개정 1):
    ```ts
    export const MIN_SERVINGS = 0.5;
    export const MAX_SERVINGS = 20;
    /** −/+ 0.5씩, 0.5~20 */
    export const stepServings = (n: number, delta: 1 | -1) => Math.min(MAX_SERVINGS, Math.max(MIN_SERVINGS, n + delta * 0.5));
    /** 서버 scaled(_round0/_round1, .5 올림)와 같은 반올림(kcal·mg 정수, g 소수 첫째). 인자 타입은 FoodLogNutrition 한 벌(개정 1 D8·S3) */
    export function scaleNutrition(per: FoodLogNutrition, factor: number): FoodLogNutrition {
      const g = (v: number | null) => (v === null ? null : Math.round(v * factor * 10) / 10);
      return { kcal: Math.round(per.kcal * factor), carbs_g: g(per.carbs_g), protein_g: g(per.protein_g), fat_g: g(per.fat_g), sugars_g: g(per.sugars_g), sodium_mg: per.sodium_mg === null ? null : Math.round(per.sodium_mg * factor) };
    }
    /** 음식 먹은 g: g 입력이면 그대로, 인분이면 1인분 무게 × 인분(무게 없으면 null) */
    export const dishGrams = (item: Pick<DishItem, "serving_g">, amount: { servings: number } | { grams: number }) =>
      "grams" in amount ? amount.grams : item.serving_g === null ? null : item.serving_g * amount.servings;
    /** 미리보기 "약 370kcal · 당류 11g · 나트륨 820mg" */
    export function previewText(n: FoodLogNutrition | null, approx: boolean): string {
      if (!n) return "";
      return [`${approx ? "약 " : ""}${kcalNumber(n.kcal)}kcal`, n.sugars_g ? `당류 ${Math.round(n.sugars_g)}g` : "", n.sodium_mg ? `나트륨 ${kcalNumber(n.sodium_mg)}mg` : ""].filter(Boolean).join(" · ");
    }
    /** 음식 후보 설명 "음식 · 1인분(400g) 약 740kcal" / "음식 · 100g당 185kcal" */
    export const dishSub = (item: Pick<DishItem, "serving_g" | "kcal">) =>
      item.serving_g === null ? `음식 · 100g당 ${kcalNumber(item.kcal)}kcal` : `음식 · 1인분(${kcalNumber(item.serving_g)}g) 약 ${kcalNumber((item.kcal * item.serving_g) / 100)}kcal`;
    /** g 입력 → 1~3000 정수, 아니면 null */
    export function parseGrams(text: string): number | null {
      const n = Number(text.trim());
      return Number.isInteger(n) && n >= 1 && n <= 3000 ? n : null;
    }
    ```
    검사: `stepServings(0.5, -1) === 0.5`, `(1, -1) === 0.5`, `(20, 1) === 20`, `(1, 1) === 1.5`; 시안 `제육덮밥 {kcal 185, carbs_g 22, protein_g 8.5, fat_g 6.8, sugars_g 5.5, sodium_mg 410, serving_g 400}` → `dishGrams(item, {servings: 0.5}) === 200` → `scaleNutrition(item, 2)`가 `{kcal: 370, carbs_g: 44, protein_g: 17, fat_g: 13.6, sugars_g: 11, sodium_mg: 820}` → `previewText(…, true) === "약 370kcal · 당류 11g · 나트륨 820mg"`; `dishSub(item) === "음식 · 1인분(400g) 약 740kcal"`, `dishSub({serving_g: null, kcal: 185}) === "음식 · 100g당 185kcal"`; `dishGrams({serving_g: null}, {servings: 1}) === null`, `({serving_g: null}, {grams: 250}) === 250`; 레시피 `scaleNutrition({kcal: 134, carbs_g: 10.2, protein_g: null, fat_g: null, sugars_g: null, sodium_mg: 333}, 1.5)` → `kcal 201`·`carbs_g 15.3`·`protein_g null`·`sodium_mg 500`; `previewText(null, false) === ""`; `parseGrams("250") === 250`, `("0")`·`("3001")`·`("1.5")`·`("")`·`("abc")` null.
  - `FoodLogSheet`(`export default function FoodLogSheet(props: { date: string; meal: MealKind; day: FoodLogDay; log?: FoodLog; user: User; onSaved: (log: FoodLog) => void; onDeleted: () => void; onClose: () => void })`), 프레임 3:
    - `Sheet` title 새 기록 `{점심} · 먹은 것 추가`, 고치기 `{점심} · 먹은 것 고치기`, description `slotDateText(date, "")`, `focusTitle`.
    - **고치기의 끼니:** `log`가 있으면 맨 위 `div.field` `끼니` + `div.chips` 아침·점심·저녁·간식(`aria-pressed`) — 사진만 먼저로 시간 끼니가 틀렸을 때 옮긴다(결정 7).
    - **무엇(새 기록 또는 고치기에서 `바꾸기`를 눌렀을 때):** `div.segmented`(`role="group"`, `aria-label="무엇을 먹었나요"`) `식단에서 · 내 레시피 · 음식 찾기 · 직접` 버튼(`aria-pressed`). `user.nutrition === "off"`면 `음식 찾기`를 뺀다(결정 13). 처음 칸: 그 끼니 `plan_slots`가 있으면 `식단에서`, 없으면 `내 레시피`; 사진 기록 고치기면 `음식 찾기`(off면 `직접`).
      - 고치기이고 사진 기록이 아니면 먼저 `div.fl-picked` `b {title}` + `span.muted {식단에서 | 내 레시피 | 음식 | 직접}` + `button.nt-link 바꾸기` — 누르기 전에는 무엇·양 칸을 보내지 않는다(PATCH에 `title`·`recipe_id`·`food_code`·`meal_slot_id`를 넣지 않음). 양 스테퍼는 보이고 바꾸면 `servings`(또는 `grams`)만 보낸다.
      - `식단에서`: `day.plan_slots`(그 끼니 먼저, 나머지 끼니 순) `div role="radiogroup" aria-label="식단 칸"` 줄마다 `label.nt-cand`(FoodPickSheet 후보 줄과 같은 마크업: `input.sr-only type="radio"` + `span.nt-radio` + `span` > `b {title}` + `small {아침 · 2인분}`, 고르면 `.on`); 없으면 `p.muted 이 날 식단에 채운 칸이 없어요`. 고르면 place를 안 만졌을 때 `home`.
      - `내 레시피`: `input.input type="search"`(placeholder `내 레시피 찾기`, 16px) 300ms 뒤 `GET /api/recipes/choices?q=`(`AbortController`) → 라디오 목록 `b {title}` + `small {N인분 기준}`; 없으면 `p.muted 찾는 레시피가 없어요`. 고르면 place 안 만졌을 때 `home`. 영양 모드가 off가 아니면 `GET /api/recipes/<id>/nutrition` → `pending`이고 `!fillAttempted.has(id)`이면 **요청 전에** `fillAttempted.add(id)` → `fill { recipe_ids: [id] }` → 다시 받기(Task 8 `fillAttempted`를 함께 써서 시트를 열 때마다 같은 레시피를 다시 부르지 않음 — 4b-2 `RecipeNutrition` `filled`와 같은 방식, 개정 1 S10).
      - `음식 찾기`: 검색 칸은 FoodPickSheet와 같은 `div.input-suffix.nt-food-search` > `input.input type="search"`(placeholder `먹은 음식 이름`, `maxLength={30}`) + `span.suffix` `Icon search`. **`q.trim()`이 2글자 이상일 때만 입력이 멈추고 600ms 뒤, Enter는 글자 수와 상관없이 바로**(빈 칸이면 부르지 않음) `GET /api/foods/dishes?q=`(`AbortController`) — 검색어마다 서버가 식품 DB 요청을 끝까지 보내 체험 계정 하루 50번이 몇 번의 입력으로 닳지 않게(개정 1 P2). 1글자에서 멈추면 `p.muted 두 글자 이상 입력하거나 Enter를 눌러주세요`. → 라디오 목록 `label.nt-cand`(`b {name}` + `small {dishSub}`); 고른 줄은 `.nt-cand.on`(`--accent-tint`). 결과 없음: `searched`면 `p.muted 찾는 음식이 없어요. 이름만 남길 수 있어요` + `button.btn.secondary ‘{q}’ 이름으로 남기기`(→ `직접` 칸, 제목 = q), 아니면 `p.muted 지금은 음식을 찾지 못했어요. 잠시 후 다시 찾아주세요`. 찾는 중 `p.muted 찾는 중…`. 고르면 place 안 만졌을 때 `out`.
      - `직접`: `input.input`(`maxLength={60}`, placeholder `무엇을 먹었나요?`) + `p.hint kcal은 음식 찾기에서 고르면 계산해줘요`(off면 이 줄 없음).
    - **`얼마나 먹었어요?`(`div.field role="group"`):** 음식이고 `serving_g`가 있으면 위에 작은 `div.segmented.fl-unit` `인분 · g`. 인분: `div.stepper` `−`(`aria-label="인분 줄이기"`, 0.5면 disabled) · `output.input aria-live="polite" {servingsText}` · `+`. g: `input-suffix`(`inputMode="numeric"`, 시작 `String(dishGrams(item, {servings}) ?? 100)`, 뒤 `g`), 틀리면 `p.hint.nt-invalid 1~3000g 사이로 입력해주세요`. `serving_g`가 없는 음식은 g만. 아래 `span.muted {previewText}`(레시피 = `scaleNutrition(per_serving, servings)`·`approx || !usable`, 음식 = `scaleNutrition(item, grams / 100)`·`true`, **식단에서·직접은 비움** — 저장값은 `slot_nutrition`(칸 AI 추정 우선일 수 있음)이라 레시피 값과 다를 수 있어서, 저장 뒤 날짜 상세에서 보인다, 개정 1 P10).
    - **`어디서`:** `div.chips` `집밥`·`외식`(`aria-pressed`, 다시 누르면 해제, 만지면 `placeTouched`).
    - **`만족도 (선택)`:** `div.fl-bigstars role="radiogroup" aria-label="만족도"` 별 버튼 5개(`role="radio"`, `aria-checked`, `aria-label="{3}점"`, 44px, 켜진 별 `--star` 꺼진 별 `--chip-line`, 같은 점수를 다시 누르면 `null`).
    - **`메모 (선택)`:** `textarea.input`(`maxLength={200}`, 2줄) + 오른쪽 아래 `span.muted {n} / 200`.
    - (사진 칸은 Task 10.)
    - 버튼 줄은 FoodPickSheet처럼 시트 아래에 붙는 `div.scan-foot` > `div.nt-pick-actions`(1fr 1.6fr): `button.btn.secondary 취소` · `button.btn.primary {남기기 | 저장}`(저장 중 `남기는 중…`/`저장하는 중…`). 새 기록인데 무엇이 없으면 `aria-disabled` + 누르면 검색·제목 칸으로 포커스와 `p.error role="alert" 무엇을 먹었는지 골라주세요`. 서버 오류는 `scan-foot` 바로 위 `p.error role="alert"`. (`기록 지우기`는 스크롤 영역 맨 아래, `scan-foot` 앞에 둔다.)
      - 새 기록 body: 식단 `{meal_slot_id, servings, place, rating, memo}` / 레시피 `{eaten_on: date, meal, recipe_id, servings, …}` / 음식 `{eaten_on, meal, food_code, servings | grams, …}` / 직접 `{eaten_on, meal, title, servings, …}` → `POST /api/food-logs`.
      - 고치기: 바뀐 칸만 `PATCH /api/food-logs/<id>`(끼니·무엇·양·place·rating·memo; memo는 빈 글자면 `null`).
      - 성공하면 `forgetResources("/api/food-logs")`, 식단에서 골랐으면 `forgetResources("/api/meal-plans")` → `onSaved(log)` → 닫기.
    - 고치기이면 맨 아래 `button.btn.danger-text 기록 지우기` → `confirm("이 기록을 지울까요? 사진도 함께 지워져요.")` → `DELETE` → 캐시 지우기 → `onDeleted()` → 닫기.
  - `FoodLog.tsx`: `editing`이 있으면 `FoodLogSheet`를 그리고 `onSaved`/`onDeleted`는 날짜 시트 `reload`(시트에 `key`로 `reloadTick`)·달 `reload()`. `pendingOpen.logId`가 있으면 그날 데이터를 받은 뒤 그 기록으로 `editing`을 연다(Task 11이 쓴다).
  - `styles.css`: `.fl-picked`, `.fl-unit`(작은 segmented), `.fl-bigstars`(26px 별, 버튼 44px). 후보 줄·라디오·버튼 줄·틀린 입력 글자는 4b-2 Task 8의 `.nt-cand`·`.nt-radio`·`.scan-foot`·`.nt-pick-actions`·`.nt-invalid`를 그대로 쓰고 `.fl-cand`·`.fl-actions`·`.fl-invalid`는 만들지 않는다(개정 1).

- [ ] **Step 0: 브랜치** — main(Task 8 병합)에서 `feature/foodlog-add-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-foodlog.mjs`에 위 목록 → 실패 확인 → `log.ts` 추가 → 통과.
- [ ] **Step 2: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 3: 브라우저 확인(384×832, `vite.wt.config.ts` 포트 5209 → 5181 프록시; 실제 식품 찾기·`fill`은 합쳐 2번까지 — `제육덮밥` 찾기 1번 + 레시피 채우기 1번, 나머지 `/api/foods/dishes`는 CDP 가짜 응답 — 결과 있음은 첫 실제 응답을 그대로 복사(저장 때 `food_code`가 서버 캐시에 있어야 해서), 결과 없음은 `{items: [], searched: true}`)** — 어제 칸 → 날짜 상세 `점심 + 먹은 것` → 시트 `점심 · 먹은 것 추가` / `9월 14일 월요일` → `음식 찾기`에 `제`(1글자)만 치면 요청 없음·안내 → `제육덮밥`까지 치고 멈추면 600ms 뒤 요청 한 번(네트워크 탭, 중간 글자마다 요청 없음) → 후보 `음식 · 1인분(Ng) 약 Nkcal` 고르면 초록 줄·어디서 `외식` 자동 → `−`로 `½인분` → `약 N kcal · 당류 · 나트륨` 미리보기 → 별 3 → 메모 `회사 앞 · 조금 짰어요`(`12 / 200`) → `남기기` → 날짜 상세에 줄·달력 칸 kcal → 같은 줄 눌러 고치기(끼니 칩·`바꾸기`·지우기 버튼 연빨강 배경·테두리) → g 칸 `300` → 저장 → kcal이 300g 기준으로 바뀜(서버 캐시 값이라 가짜 응답 숫자와 다를 수 있음) → `없는음식` 검색 → `‘없는음식’ 이름으로 남기기` → `직접` 칸으로 → 남기기 → kcal 없음 → `내 레시피`에서 레시피 고르고 1½인분(미리보기, 계산하는 중이면 채우기 뒤 값; 시트를 닫고 같은 레시피를 다시 골라도 `fill`이 다시 안 나감) → `식단에서` 칸 고르기(미리보기 줄 없음, 저장 뒤 날짜 상세에 kcal) → 긴 목록에서도 `취소`·`남기기` 줄이 아래에 붙어 보임 → 식단 탭 그 칸에 `먹었어요`는 Task 11 → 기록 지우기(확인 창). 무엇 없이 `남기기` → 안내·포커스. 다크·키보드(세그먼트·라디오 화살표·별 라디오)·스크린리더(`만족도 3점`, `인분 줄이기`). 스크린샷.
- [ ] **Step 4: 스펙** — 24절 `구현 세부` `화면:`에 추가·고치기 시트(네 갈래 규칙·결정 3·4·12·13, 끼니 옮기기).
- [ ] **Step 5: 커밋** — `feat: 먹은 것 추가·고치기 시트(식단에서·내 레시피·음식 찾기·직접, 양·집밥/외식·만족도·메모)`

---

### Task 10: 시트 사진 4장·사진만 먼저

**Files:**
- Modify: `frontend/src/components/FoodLogSheet.tsx`, `frontend/src/pages/FoodLog.tsx`, `frontend/src/styles.css`, 스펙(24절 `구현 세부` `화면:` 줄)

**Interfaces:**
- Consumes: Task 3 `POST /api/food-logs/<id>/photos`·`DELETE …/photos/<photo_id>`·`POST /api/food-logs/photo`, Task 9 `FoodLogSheet`, Task 8 날짜 시트 열기, `image.ts` `resizeImage`, `api`(FormData), `Sheet`, `Icon`, `.sh-photos`·`.sh-photo`(+`.add`)
- Produces:
  - `FoodLogSheet.tsx`에서 export:
    ```ts
    export const MAX_LOG_PHOTOS = 4;
    /** 긴 변 1568px JPEG로 줄여 올린다(결정 9). url은 `/api/food-logs/<id>/photos` 또는 `/api/food-logs/photo` */
    export async function uploadFoodPhoto<T>(url: string, file: Blob): Promise<T> {
      const form = new FormData();
      form.append("image", await resizeImage(file), "photo.jpg");
      return api<T>(url, { method: "POST", body: form });
    }
    ```
  - **시트 사진 칸(`사진 (선택)`, 메모 위):** 안드로이드 사진 선택기에 카메라가 없어 입력을 둘로(메모 사진과 같은 사용자 결정 2026-09-14): `input type="file" accept="image/*" capture="environment" hidden`, `input type="file" accept="image/*" multiple hidden`. `div.sh-photos`: 이미 올린 사진(고치기) `div.sh-photo` 안 `img`(`alt="사진 {n}"`) + `button.fl-photo-x`(`aria-label="사진 {n} 빼기"`, `Icon close`, 누르면 바로 `DELETE` — 확인 없음, 실패는 사진 칸 아래 `p.error`) → 새로 고른 사진(아직 안 올림, `URL.createObjectURL` 미리보기, ✕로 빼기, 닫힐 때 `revokeObjectURL`) → 합계가 4장 미만이면 `button.sh-photo.add` `Icon camera` `찍기` · `button.sh-photo.add` `Icon file` `앨범`. 앨범에서 여러 장이면 남은 자리만큼만 넣고 `p.hint 사진은 4장까지 넣을 수 있어요`.
  - **저장 순서:** 기록 POST/PATCH 성공 → 새 사진을 하나씩 `uploadFoodPhoto(`/api/food-logs/${id}/photos`, file)` → 모두 되면 닫기. 하나라도 실패하면 시트를 닫지 않고 고치기 모드로 바꿔(`log` = 저장된 기록) `p.error role="alert" 사진 {N}장은 올리지 못했어요 · {서버 문구}`와 남은 사진을 그대로 둔다(다시 `저장`하면 남은 것만 올림).
  - **사진만 먼저(프레임 4):** `FoodLog.tsx` 머리 오른쪽 `button.icon-btn.fl-camera`(`aria-label="사진만 먼저 남기기"`, `aria-haspopup="dialog"`, `Icon camera`) → `Sheet` title `빠르게 사진만 남기기`, description `지금 시간의 끼니(아침 5–10시·점심 10–15시·저녁 15–21시·그 밖은 간식)에 사진 기록이 생겨요` → `div.actions.actions-even` `button.btn.secondary Icon file 앨범에서 고르기` · `button.btn.primary Icon camera 카메라로 찍기`(각각 숨긴 입력, 한 장). 고르면 시트를 닫고 `p.muted role="status" 사진을 남기는 중…` → `uploadFoodPhoto<FoodLog>("/api/food-logs/photo", file)` → `forgetResources("/api/food-logs")` → 그 기록 날짜의 달로 옮기고 날짜 상세를 연다. 실패는 머리 아래 `p.error role="alert"`(503 문구 그대로).
  - 사진 기록 줄을 누르면(Task 8 `onOpenLog`) Task 9 고치기 시트가 `음식 찾기`로 열린다 — 이름·양을 채워 저장하면 `사진 기록`이 이름으로 바뀐다(시안 `누르면 무엇을 먹었는지 채워요`).
  - `styles.css`: `.fl-camera`(머리 오른쪽 끝), `.fl-photo-x`(사진 오른쪽 위 28px 원, 터치 44px 영역은 `::before`로).

- [ ] **Step 0: 브랜치** — main(Task 9 병합)에서 `feature/foodlog-photo-ui`.
- [ ] **Step 1: 화면 구현 → `npm run check && npm run build`** (순수 로직이 없어 검사 추가 없음 — `resizeImage`는 기존)
- [ ] **Step 2: 브라우저 확인(384×832, `vite.wt.config.ts` 포트 5210 → 5181 프록시; 사진은 5181 개발 서버의 저장소에 쌓이므로 확인에 쓴 기록은 끝에 `기록 지우기`로 지운다; 실제 식품 찾기는 2번까지, 나머지는 CDP 가짜 응답(첫 실제 응답 복사))** — 달력 머리 카메라 → `빠르게 사진만 남기기` 시트 → `앨범에서 고르기`로 JPG 한 장 → 오늘 날짜 상세가 열리고 지금 시간 끼니에 `사진 기록 · 이름 없음`·시각 → 달력 오늘 칸에 사진 썸네일 → 그 줄 → 고치기 시트 `음식 찾기`로 `토스트` 골라 저장 → 이름·kcal → 다시 열어 사진 칸에 기존 사진 + `찍기`·`앨범` → 앨범에서 5장 고르면 3장만 들어가고 안내 → ✕로 한 장 빼기(바로 지워짐) → 새 기록 추가 시트에서 사진 2장 + 남기기 → 날짜 상세 첫 사진·달력 썸네일이 첫 사진 → 네트워크를 끄고 사진 올리기 실패 시 시트가 남고 안내 → PNG·WEBP도 확인, 텍스트 파일 이름을 `.jpg`로 바꿔 올리면 415 문구. 다크·키보드(사진 빼기 버튼 이름)·스크린리더. 폰 카메라 확인은 Task 12. 스크린샷.
- [ ] **Step 3: 스펙** — 24절 `구현 세부` `화면:`에 사진 칸·저장 순서·사진만 먼저 흐름(결정 8·9).
- [ ] **Step 4: 커밋** — `feat: 먹은 기록 사진 4장(찍기·앨범)과 사진만 먼저 남기기 카메라 버튼`

---

### Task 11: 식단 칸 상세 `먹었어요` 버튼

**Files:**
- Modify: `frontend/src/components/MealSlotSheet.tsx`, `frontend/src/pages/Meals.tsx`, `frontend/src/components/DayNutritionSheet.tsx`, `frontend/src/styles.css`(식단 묶음 끝 `.ml-eaten` 한 줄만, 개정 1), 스펙(20절 `화면`·24절 `구현 세부` `화면:` 줄)

**Interfaces:**
- Consumes: Task 5 `POST /api/meal-slots/<id>/eaten`·칸 `eaten_log_id`, Task 7 `MealSlot.eaten_log_id` 타입·`openFoodLog`, `navigate`, `useAsyncAction`, `forgetResources`, `Icon check`
- Produces:
  - `MealSlotSheet`(프레임 5): 재료 줄(`ml-detail-meta`) 바로 아래, 인분 칸 위에 — `slot.date <= today`일 때만:
    - `slot.eaten_log_id === null`: `button.btn.primary`(`Icon check`) `먹었어요 · 먹은 기록에 남기기` → `run(async () => { await queue.current; const log = await api<FoodLog>(`/api/meal-slots/${slot.id}/eaten`, { method: "POST" }); setSlot({ ...slot, eaten_log_id: log.id }); forgetResources("/api/food-logs"); onChanged(); })` — 인분 저장 줄이 끝난 뒤 보낸다. 성공하면 버튼 아래 `p.hint role="status" 먹은 기록에 남겼어요`. 실패는 버튼 아래 `p.error role="alert"`.
    - `slot.eaten_log_id !== null`: `button.btn.secondary`(`Icon check`) `먹었어요 · 기록 보기` → `openFoodLog({ date: slot.date, logId: slot.eaten_log_id })` → `onClose()` → `navigate("/food-log")`.
    - `칸 비우기`는 지금 자리·모양(`.btn.danger-text`, 맨 아래) 그대로. 다른 걸로 바꾸기 뒤 칸이 덮어써지면 서버가 연결을 끊으므로(Task 5) 다시 받은 칸은 `먹었어요 · 먹은 기록에 남기기`로 돌아간다.
    - `useAsyncAction`은 `칸 비우기`와 따로 하나 더(`eaten`) 둔다 — 두 버튼의 바쁨·오류가 섞이지 않게.
  - `Meals.tsx` 주 보기 칸 줄: `ml-sub` 끝에 `slot.eaten_log_id !== null`이면 ` · ` + `span.ml-eaten`(`Icon check size 14` + `먹었어요`), 줄 `aria-label` 끝에 `, 먹었어요`(결정 21). 스타일은 기존 `.ml-use` 옆에 `.ml-eaten { color: var(--accent-strong); }` 한 줄(4b-3 묶음이 아니라 식단 묶음 끝 — `styles.css`는 이 한 줄만).
  - `DayNutritionSheet.tsx`: 끝 문구의 `먹은 기록은 다음에 ‘먹은 기록’에서 남길 수 있어요.`를 `먹은 기록은 더보기 ‘먹은 기록’에서 남길 수 있어요.`로(결정 21).
  - **파일 겹침 주의:** `styles.css` 한 줄은 Task 8~10의 `/* 먹은 기록 (4b-3) */` 묶음과 다른 곳(식단 묶음)이라 병합 때 따로 붙는다. 병렬로 돌 때 `styles.css` 충돌이 나면 두 쪽 모두 남긴다.

- [ ] **Step 0: 브랜치** — main(Task 5·7 병합)에서 `feature/foodlog-meal-button-ui`.
- [ ] **Step 1: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 2: 브라우저 확인(384×832, `vite.wt.config.ts` 포트 5211 → 5181 프록시)** — 식단 주 보기 어제 저녁 레시피 칸(인분 2) → 칸 상세 맨 위 `먹었어요 · 먹은 기록에 남기기`(초록) → 누르면 `먹은 기록에 남겼어요`, 버튼이 `먹었어요 · 기록 보기`로 → 닫으면 주 보기 칸 줄 `2인분 · 먹었어요` → 다시 열어 `기록 보기` → `#/food-log`에서 그 달·날짜 상세가 열리고 그 기록 줄 `2인분 중 1인분`이 보임(그 기록 고치기 시트가 이어서 열리는 것은 Task 9가 만들어 병렬 시점엔 없을 수 있으므로 여기서 보지 않고 Task 12 Step 3에서 본다, 개정 1 P21) → 뒤로가기로 식단 탭 → 같은 칸 `다른 걸로 바꾸기`로 다른 레시피 → `먹었어요` 표시가 사라지고 먹은 기록은 남음 → 내일 칸에는 버튼 없음 → 인분 −/+를 빠르게 누른 뒤 곧바로 `먹었어요`(요청 순서 확인) → 하루 영양 시트 끝 문구. 다크·키보드·스크린리더(칸 줄 이름 끝 `먹었어요`). 스크린샷.
- [ ] **Step 3: 스펙** — 20절 `화면` 칸 상세 시트 줄에 `맨 위 먹었어요(24절)`, 24절 `구현 세부` `화면:`에 결정 21.
- [ ] **Step 4: 커밋** — `feat: 식단 칸 상세 먹었어요 버튼(먹은 기록에 남기기·기록 보기)과 주 보기 표시`

---

### Task 12: 전체 검사·체험 계정·폰 확인·배포 준비

**Files:**
- Modify: 필요할 때만(발견한 문제를 고친 파일), `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 2절 표(4b 행에 `4b-3 먹은 기록 달력 완료(2026-09-xx)`)

- [ ] **Step 1: 전체 검사** — 백엔드 SQLite·PostgreSQL(에이전트 전용 DB) 전체 실패·경고 0, `cd frontend && npm run check && npm run build`, 스크래치 DB에서 `flask db upgrade`·`flask db check` 차이 없음, head 하나(`g3f3l3p3h3o3`).
- [ ] **Step 2: 실제 키로 로컬 확인(사용자가 `./dev.sh`를 다시 켠 공용 개발 서버, 에이전트는 켜고 끄지 않음)** — `음식 찾기`로 `제육덮밥`·`김치찌개`·`짜장면` → 음식 행·`1인분(Ng)`이 나오는지(Task 1 Step 0 기록과 같은지), 개발 서버 로그에 주소·키가 없는지(`grep -c serviceKey` 0). 식품중량이 비는 음식은 g 입력만 나오는지.
- [ ] **Step 3: 체험 계정 확인** — `DEMO_LOGIN=1` 개발 서버에서 체험하기 → 더보기 `기록` → 달력 어제·오늘 점·요약(집밥 67%) → 어제 상세 김치찌개 kcal이 채우기 뒤 붙는지 → 사진만 먼저(체험 20MB 한도) → 식단 칸 `먹었어요` → `기록 보기` → `#/food-log` 날짜 상세에 이어 그 기록 고치기 시트까지 열리는지(Task 9·11 합친 흐름, 개정 1 P21) → 내보내기 zip `food_logs.csv` → `flask purge-demo-users`가 먹은 기록 사진 파일까지 지우는지(만료 시각을 바꾼 계정으로).
- [ ] **Step 4: 사용자 폰 확인(갤럭시 S22 Ultra, `http://<맥 IP>:5180`)** — 카메라 버튼 → `카메라로 찍기`가 바로 카메라를 여는지, `앨범에서 고르기`, 추가 시트 `찍기`·`앨범`, 큰 사진(1200만 화소)이 줄어 올라가는지, 달력 칸 썸네일·점·kcal 글자가 384px에서 넘치지 않는지(`약 2,120`), 날짜 상세 스크롤·키보드가 메모 칸을 가리지 않는지, 별 터치, 인분 −/+ 연타, 식단 칸 `먹었어요` → `기록 보기` 이동과 뒤로가기, 다크 모드. **사용자에게 확인 목록을 보여주고 결과를 받는다**(문제는 고친 뒤 다시 확인).
- [ ] **Step 5: 배포 여부 확인** — 사용자가 고르면 `git push origin main`(마이그레이션 세 개는 시작 명령의 `flask db upgrade`) → 운영 R2에서 사진 올리기·보기·지우기 → 체험 계정으로 운영 주소에서 한 바퀴. 심사 기간이면 사용자가 정한 때까지 미룬다.
- [ ] **Step 6: 메모리·스펙** — 2절 표 표시, 메모리 `recipe-ai-post-deploy-roadmap`의 다음 단계를 5단계(요리 일기)로, `recipe-ai-carryover`에 남은 것(회원 탈퇴 API에 `photos.user_photo_keys` 쓰기, 달력 `요` 표시).
- [ ] **Step 7: 커밋** — `docs: 4b-3 먹은 기록 달력 완료 표시`

---

## 자체 점검 (스펙 대조, 계획 작성 시)

| 스펙 요구 | 태스크 |
|---|---|
| 24절 위치 더보기 > 먹은 기록 `#/food-log`, 식단 탭과 분리 | 7 |
| 월 달력 좌우 이동·오늘 강조·첫 사진 또는 끼니 점·하루 kcal `약` | 4(데이터)·7(화면) |
| `요리함`/`요` 표시 | 5단계로 미룸(결정 19, 29절) |
| 날짜 상세: 끼니별 목록·`+ 먹은 것 추가`·항목(이름·양·kcal·당류·추정·사진·메모·만족도) | 2·8·9 |
| 사진만 먼저·`사진 기록`·시간 끼니 규칙 | 3·8·10 |
| `food_logs` 확장 칸(photo·memo ≤200·rating 1~5·place·source) | 2·3(photo_key는 사진 테이블, 결정 1) |
| 사진 저장·소유 확인·1568px·서명·10MB | 3·10 |
| 요리 기록 합치기·`먹은 기록에도 남기기` | 5단계(source `cook_log` 자리만, 결정 19) |
| 월 요약(기록한 날·하루 평균 kcal·집밥/외식 비율) | 4·7 |
| 개인정보(본인만·계정 삭제 시 함께·참고용 문구) | 2(소유 404·CASCADE)·3(사진 파일)·8(문구), 탈퇴 API는 범위 밖(결정 17) |
| 2026-09-15 결정: 네 갈래·인분(음식 g)·집밥/외식·별·메모·사진 | 1·2·9·10 |
| 결정 A 외식 kcal = 식품영양성분 DB 음식 행, 못 찾으면 비움, 사진 AI 없음 | 1·2·9 |
| 결정 B 식단 칸 `먹었어요`·표시·다시 누르면 열기·날짜 상세 제안 | 2(plan_slots)·5·8·11 |
| 결정 C 사진 4장·메모 사진과 같은 처리 | 3·10 |
| 결정 D 달력 칸 표시 | 4·7 |
| 날짜 상세 위 목표 대비 막대·당류·나트륨 | 8 |
| 더보기 `기록` 묶음 맨 위·오늘 끼니 수 | 7 |
| 21절 계산값 스냅숏·`estimated` | 2(결정 2·5) |
| 21절 식품 검색·내 레시피·식단 칸에서 `먹었어요` | 1·2·5·9·11 |
| 26절 페이지 방식 | 2 스펙 갱신(결정 10) |
| 27절 내보내기 먹은 기록 CSV | 6·7(시트 줄) |
| 27절 회원 탈퇴 사진 접두사 | 3(`user_photo_keys`, 스펙 줄) |
| 9절 체험 계정 예시 데이터·AI 없음 | 6·3(사진 한도) |
