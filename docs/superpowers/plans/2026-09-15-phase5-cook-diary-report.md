# 5단계(요리 일기 · 집밥 리포트) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 내 레시피 상세와 식단 레시피 칸에서 `요리했어요` 시트로 인분·쓴 재료(23절 D2 기본값)·날짜·사 먹으면 얼마·별점·사진·메모·`먹은 기록에도 남기기`를 받아 한 트랜잭션에 재고를 빼고 요리 일기를 남기며, 10초 `되돌리기`로 재고(지워진 재료 포함)를 복구한다. 일기마다 `사 먹으면 × 인분 − 재료비(구입 가격 × 쓴 비율)`로 아낀 돈을 계산해 요리 일기 목록(커서 무한 스크롤)·상세(계산표·고치기·지우기)·월간 집밥 리포트(아낀 돈 합계·요리 횟수·기록한 날·집밥 비율·버린 재료·지난달 대비·많이 아낀 요리 3개)로 보여주고, 먹은 기록 달력에 `요` 표시를 붙인다.

**Architecture:** 서버는 `app/cooklog.py`(순수 계산 `draft_rows`·`is_seasoning`·`item_cost`·`summarize` + 요리했어요 초안 GET + 일기 저장·되돌리기·목록·상세·고치기·지우기·사진)와 `app/cook_report.py`(월간 리포트 GET) 두 파일에 모은다. 저장 때 재고 행의 이름·양·단위·위치·날짜·가격·구입 수량을 `cook_log_items`에 **스냅숏**으로 남겨 계산표와 되돌리기가 같은 행을 쓰고, 아낀 돈 합계는 `cook_logs` 행에 정수로 넣어 리포트가 더하기만 한다. 사 먹으면 얼마는 `recipes.eat_out_price`에 두고 없을 때만 AI를 한 번 부른다(`recipe_ai.py`, AI 레시피 한도 묶음). 재료비 비율은 새 칸 `ingredients.price_quantity`(가격을 넣은 순간의 수량)로 구한다. 화면은 폼 시트 `CookSheet`, 앱 전체에 한 개인 `UndoToast`, 목록·상세 페이지 `CookDiary`, 리포트 페이지 `CookReport`이고, 표시 수식은 브라우저 API 없는 `src/cooklog/cook.ts`로 떼어 `scripts/check-cooklog.mjs`로 고정한다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, anthropic 1.5.0(`messages.parse` 구조화 출력, 기존 `ai._parse`), pydantic, boto3(기존 `storage.py`), pytest 9.1.1 / React 19 + TypeScript + Vite 8, Node 24(`.ts` 직접 실행 검사 스크립트). **새 의존성 없음.**

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` **29절(5단계 요리 일기 · 집밥 리포트 화면, 결정 A~D — 이 계획의 기준)**, 27절(집밥 리포트·아낀 돈·가격 수집·재료 지울 때 이유·데이터 내보내기), 23절 D2(차감 기본값), 6절 6~7번(요리했어요 폼·기록 탭), 7절(조리 기록 저장 트랜잭션·AI 일일 한도 묶음), 4절(`cook_logs` 원안, `ingredient_removals`), 24절(`food_logs.source = cook_log`, 달력 `요` 표시), 26절(목록 페이지 방식), 9절(보안·체험 계정), 5절(API 규칙), 8절(업로드 오류). **디자인: `docs/design/cooklog-5/index.html`(사용자 승인 2026-09-15, 결정 A~D 수락).** 화면 태스크는 프레임 문구·배치·버튼을 그대로 따른다(바꾼 곳은 아래 결정에 적었다).

시안 프레임: 1 `COOKED`(요리했어요 폼) · 2 `SAVED`(저장 후 알림·되돌리기) · 3 `DIARY`(요리 일기 목록) · 4 `DETAIL`(일기 상세 — 아낀 돈 계산) · 5 `REPORT`(집밥 리포트) · 6 `REMOVE REASON`(재료 지울 때 이유).

**4b-2·4b-3과의 관계:** 5단계는 4b-3 Task 12가 끝난 main에서 시작한다(4b-2 개정 1 포함, 둘 다 병합됐다고 본다). 두 계획이 만든 이름을 **그대로** 쓴다 —
- 4b-2: `nutrition.TRACE_WORDS`, `nutrition/body.ts kcalNumber`, `.nt-card`·`.nt-link`·`.nt-src`·`.nt-meter` 스타일.
- 4b-3 서버: `models.FoodLog`(`source` `manual|meal_plan|cook_log`, `meal_slot`·`recipe` 관계, `MealSlot.food_log` backref), `food_logs.FUTURE`·`BAD_REQUEST`·`eaten_date`·`check_caps`·`fill_snapshots`·`meal_for_time`·`log_json`·`month_start`·`month_json`, `GET /api/food-logs?date=`(`{date, logs, plan_slots, nutrition_pending_recipe_ids}`)·`GET /api/food-logs/month`(`{month, today, days, summary}`), `photos.read_image(max_bytes)`·`photos.user_photo_keys(user_ids)`, `demo.delete_demo_users`(사진 키는 `user_photo_keys`), `export.write_csv`·`safe`·`number`·`seoul_time`·`MEAL_LABELS`·`owned`·`BATCH`·`FOOD_LOG_SOURCE_LABELS`, `meals._owned_slot`·`meals.MEALS`.
- 4b-3 화면: `api.ts` `FoodLog`·`FoodLogDay`·`FoodLogMonthDay`·`FoodLogMonth`·`ExportSummary.food_logs`·`MealSlot.eaten_log_id`, `foodlog/log.ts` `monthOf`·`shiftMonth`·`monthLabel`·`cellLabel`·`starsText`·`summaryView`, `pages/FoodLog.tsx` `openFoodLog`·`resetFoodLogView`, `components/FoodLogDaySheet.tsx`, `components/FoodLogSheet.tsx` `uploadFoodPhoto`·`MAX_LOG_PHOTOS`, `MealSlotSheet`의 `먹었어요` 버튼(`eaten` `useAsyncAction`, `queue`), 더보기 `기록` 묶음(`Row`, `todayRowSub`), `--star` 토큰, `.fl-*` 스타일(`.fl-mnav`·`.fl-stats`·`.fl-split`·`.fl-bigstars`·`.fl-plan`·`.fl-cell`·`.fl-legend`·`.fl-actions`).
- 기존: `amounts.parse_amount`·`is_spoon`·`SPOON_UNITS`, `matching.prepare`·`match_prepared`·`names_match`·`normalize`·`title_key`, `recipe_parse.ingredient_key`, `recipes.ALWAYS_HAVE`·`recipe_json`·`inventory`·`get_recipe`, `ingredients.parse_fields`·`seasoning_names`·`status_of`·`user_rules`·`seoul_today`·`SEOUL`·`REMOVAL_REASONS`, `locations.default_location`, `scan.RECIPE_KINDS`·`check_ai_limits`·`start_ai_call`·`finish_ai_call`·`utcnow`, `ai.scan_mode`·`_parse`·`AiError`, `auth.ai_daily_limit`·`get_owned_or_404`·`login_required`, `validation.integer`·`iso_datetime`·`encode_cursor`·`decode_cursor`, `storage.mode`·`put`·`delete`·`UPLOAD_UNAVAILABLE`, 화면 `format.ts` `formatWon`·`formatQuantity`·`withJosa`, `meals/plan.ts` `slotDateText`·`mealLabel`·`MEALS`, `image.ts resizeImage`, `useInfiniteList`·`InfiniteSentinel`, `useResource`·`forgetResources`·`forgetRecipeCaches`, `useAsyncAction`, `Sheet`, `Icon`, `.r3-toggle`(스위치), `.cta-bar`, `.btn.danger-text`.

## Global Constraints

- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다. 태스크 작업은 태스크마다 git worktree에서 한다(메인 작업 폴더에서 직접 고치지 않는다).
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. SQLite와 PostgreSQL 둘 다 실패 0, 경고 0. **PostgreSQL DB는 에이전트(태스크)마다 따로 만든다**: `createdb recipe_ai_test_ck<N>` · `createdb recipe_ai_migrate_ck<N>` → `TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test_ck<N> TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate_ck<N>` → 끝나면 `dropdb` 두 개(병렬 태스크가 같은 DB를 지우지 않게).
- 프론트 태스크는 `cd frontend && npm run check && npm run build`가 오류 없이 끝나야 한다. Task 8에서 `check` 스크립트 끝에 `&& node scripts/check-cooklog.mjs`를 붙인다. **테스트 러너(vitest 등)를 새로 들이지 않는다.**
- **테스트는 절대 네트워크를 부르지 않는다.** 기존 `conftest.py` `block_network` 그대로. AI는 `monkeypatch.setattr("app.ai.estimate_eat_out", fake)` 또는 `fake_anthropic` 픽스처, 사진은 `conftest.make_app`의 임시 `UPLOAD_DIR`(로컬 저장소).
- API 키는 `backend/.env`에만 있다. **`.env`는 읽거나 커밋하지 않는다**(값을 출력하지 않는다). 이번 단계는 새 환경변수가 없다(`.env`·`.env.example`·`render.yaml`을 고치지 않는다). 예외는 로그에 `type(e).__name__`만, 사진 키·비밀값은 로그에 남기지 않는다.
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정하고 남의 것은 404. 상태 변경은 `X-Requested-With: fetch`(기존 전역 검사). DB int 범위 밖 id는 404(`get_owned_or_404`). 요리 일기·리포트·초안 GET 응답은 `Cache-Control: no-store`(식습관·지출 정보).
- 날짜·시각은 서울(`ingredients.SEOUL`, `seoul_today()`) 기준. 오늘보다 뒤 날짜는 남기지 않는다(`food_logs.eaten_date` 그대로).
- 모바일 384px 기준(갤럭시 S22 Ultra). 터치 영역 44px 이상, 입력 글자 16px 이상. 아이콘은 이모지 대신 `Icon`(`pan`·`camera`·`file`·`plus`·`minus`·`check`·`calendar`·`close`·`back`·`chevron`·`pencil`·`receipt`·`refresh`). 라이트·다크 모두 확인.
- **삭제 버튼은 연빨강 배경 + 테두리(`.btn.danger-text`)로 보이게 한다(`일기 지우기`, 재료 `지우기`). 승인된 기존 화면 조정(재료 삭제 시트의 `취소` 버튼, 수량 0 저장 = `다 먹었어요` 미리 고름, 칸 상세 `칸 비우기` 위치·모양, 4b-3 `먹었어요` 버튼 문구)은 그대로 둔다.**
- 화면 문구는 시안 그대로. 시안에 없는 새 문구는 보조 용언을 붙여 쓴다(`보여줘요`, `골라주세요`, `남겨요`, `계산해요`). 개발 용어(API, 캐시, 스냅숏, 토큰, 커서, 동기화, 매칭)는 화면에 쓰지 않는다. **돈 계산을 보여주는 곳(일기 상세 계산표, 집밥 리포트)에 `참고용이에요`를 둔다**(27절 `의료·재무 조언이 아닌 참고용 표시`). 먹은 기록 날짜 상세의 기존 `의료 조언이 아니라 참고용이에요.`는 그대로.
- 시안 `<style>`의 클래스는 `frontend/src/styles.css` 끝 `/* 요리 일기 (5) */` 묶음으로 `ck-` 접두사를 붙여 옮기되, 이미 있는 클래스(`btn`·`primary`·`secondary`·`outline`·`danger-text`, `chip`·`chips`, `stepper`·`icon-btn`, `field`·`field-label`·`input`·`input-suffix`, `badge`·`badge.info`·`badge.old`, `hint`, `error`, `list`·`mo-group`·`mo-row`, `sh-photos`·`sh-photo`, `r3-toggle`, `cta-bar`, 4b-2 `nt-card`·`nt-link`·`nt-src`·`nt-meter`, 4b-3 `fl-mnav`·`fl-stats`·`fl-split`·`fl-bigstars`·`fl-stars`·`fl-plan`·`fl-actions`)는 새로 만들지 않는다. 색은 CSS 변수만(새 토큰 없음 — `--star`는 4b-3). 병렬 태스크가 `styles.css`에서 충돌하면 두 쪽을 모두 남긴다(묶음 안 소제목 주석 `/* 5 · Task N */`로 나눈다).
- **포트:** 5173·5180·5181은 건드리지 않는다(공용 개발 서버는 끄거나 다시 켜지 않는다). 개발 DB(`backend/dev.sqlite3`)는 지우지 않는다. **서브에이전트는 `pkill`/`killall`을 쓰지 않는다. 직접 띄운 프로세스만 PID로 끈다.** 화면 확인은 worktree에서 `cd frontend && npm run build` → `cd backend && DEV_MODE=1 DATABASE_URL=sqlite:///<스크래치>/ck<N>.sqlite3 .venv/bin/flask --app app db upgrade && DEV_MODE=1 DATABASE_URL=… .venv/bin/flask --app app run --port 53<N 두 자리>`(Flask가 같은 worktree의 `frontend/dist`를 서빙, 예: Task 8은 5308)로 띄우고 `http://127.0.0.1:53NN`에서 개발용 로그인으로 본다(데스크톱 크롬 384×832).
- 마이그레이션 id·down_revision은 **구현 시점에 `ls backend/migrations/versions`와 `cd backend && .venv/bin/flask --app app db heads`로 다시 확인**한다. 계획 작성 시 main head는 `f2f2o2o2d2s2`이고 4b-3이 `g1s1e1r1v1n1`·`g2f2o2o2d2l2`·`g3f3l3p3h3o3`을 더해 5단계 시작 때 head `g3f3l3p3h3o3` 예정. head는 하나여야 한다. 다른 세션이 그사이 head를 옮겼으면 down_revision만 바꾸고 id는 그대로 둔다.
- 브랜치는 태스크마다 하나, 리뷰(백엔드: 코드·보안·테스트 설계 / 화면: 코드·UX·접근성) 통과 후 main에 `--no-ff` 병합. 배포(push)는 사용자 폰 확인(Task 14) 뒤 사용자가 고른 때에만 — 심사 기간(접수 9/18, 제출 9/20)에는 서비스 링크를 안정적으로 둔다.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음 한 줄만 붙인다:
  ```
  Claude-Session: https://claude.ai/code/session_01RfLBMnikALjpYKF3hjnepT
  ```

## 계획하며 정한 것 (스펙·시안에 없던 빈틈 — 사용자 확인 대상, 각 태스크 커밋 전에 스펙 29절 `구현 세부`에 적는다)

1. **이름·경로·테이블.** 목록 `#/cook-logs`(요리 일기), 리포트 `#/cook-report`(집밥 리포트). 테이블은 `cook_logs`(일기 한 건)와 `cook_log_items`(그 요리에 쓴 재료 한 줄 — 계산표·되돌리기 스냅숏). 4절 원안 `cook_logs` 칸(recipe_id SET NULL, title, cooked_on, rating, memo, photo_key, created_at)에 servings·사 먹으면 얼마·재료비·아낀 돈·제외 수·먹은 기록 연결·사진 크기·updated_at을 더한다.
2. **요리했어요 입구.** 내 레시피 상세(`cta-bar`)와 **레시피가 있는** 식단 칸 상세(오늘 이하 날짜)만. 공공 레시피 상세에는 두지 않는다 — 사 먹으면 얼마를 레시피에 저장해야 해서 `내 레시피로 저장` 뒤 내 레시피 상세에서 한다(6절 `레시피 상세(공통)`을 이렇게 좁힌다). 직접 쓴 칸(레시피 없음)은 쓴 재료가 없어 `먹었어요`만 쓴다.
3. **인분.** 정수 1~20(`recipes.servings`와 같게), 기본은 레시피 인분(식단 칸이면 칸 인분).
4. **쓴 양 기본값(23절 D2).** 서버 초안이 레시피 양을 **재고 단위 수량**으로 바꾼 `base_amount`(레시피 인분 기준)를 주고, 화면이 `base_amount × 요리 인분 ÷ 레시피 인분`(소수 셋째 자리)을 쓴다. 바꿀 수 없으면(단위 다름·못 읽음) `1`. 같은 단위는 `parse_amount`가 이미 쓰는 `kg↔g`·`L↔ml` 환산까지(`amounts.in_unit`). 재고 행 하나는 레시피 재료 하나에만 붙인다 — 재고는 `recipes.inventory`와 같은 순서(빨리 먹어야 할 것 먼저 → id)로 먼저 나온 재료에 붙고, 같은 재고에 또 맞는 뒤 재료는 `재고 없음`으로 둔다. 물(`ALWAYS_HAVE`)은 줄에 넣지 않는다. 폼의 양은 늘 재고 단위라 재료비 비율에서 단위가 어긋나는 일이 없다(27절 `단위가 달라 비율을 못 구하면`은 구입 수량이 없을 때만 생긴다).
5. **양념 판정(23절 D2 보강).** `조미료 분류 필수품(ingredients.seasoning_names)과 names_match` **또는** 레시피 양이 숟가락 단위(`SPOON_UNITS`에서 `컵` 뺀 것)·`nutrition.TRACE_WORDS`(약간·적당량…)면 양념. 필수품을 안 만든 사용자도 시안 `고춧가루 1큰술 · 양념 · 기본으로 안 빼요`가 나오게 하려는 것. 양념 줄은 체크 해제로 시작하고, 사용자가 켜서 빼도 **재료비에는 넣지 않는다**(27절 `양념 등 조금 쓰는 재료는 기본 제외`).
6. **차감.** `남은 양 = round(재고 − 쓴 양, 3)`, 0.001 미만이면 행을 지우고 같은 커밋에 `ingredient_removals(reason = eaten)`를 남긴다(29절 D `요리 차감으로 0이 되어 지워진 재료는 다 먹었어요`). 쓴 양이 재고보다 크면 재고만큼 뺀 것으로 기록한다(`used = min(쓴 양, 재고)`). 화면은 쓴 양 ≥ 재고면 `마저 써요` 알약.
7. **되돌리기 설계(결정 B).** 따로 토큰을 만들지 않는다 — `POST /api/cook-logs/<id>/undo`가 로그인 사용자 소유 + **서버 시각으로 저장 뒤 120초 안**(`UNDO_SECONDS`)인지만 본다. 화면 알림은 10초(포커스·손가락이 알림 위에 있으면 멈춤, WCAG 2.2.1)이고 120초는 네트워크·멈춤 여유다. 되돌리면 일기 행을 지우므로 두 번째 요청은 404 — 한 번만. 넘으면 400 `되돌릴 수 있는 시간이 지났어요. 재고는 직접 고쳐주세요.`
8. **되돌리기 중 재고가 바뀌었을 때.** 남아 있는 재료는 저장된 수량으로 덮지 않고 **뺀 양만큼 더한다**(그사이 고친 수량 위에 더함). 차감으로 지워진 재료는 스냅숏(이름·수량·단위·위치·구입일·유통기한·가격·구입 수량)으로 새로 만든다 — 위치가 그사이 지워졌으면 기본 위치, 재료 2000개 상한은 보지 않는다(되돌리기라서). 단위를 바꾼 재료와 사용자가 직접 지운 재료는 건너뛰고 이름을 알려준다(`재고를 되돌렸어요 · 대파는 그사이 바뀌어 그대로 뒀어요`). 함께 만든 먹은 기록·일기 사진·차감이 남긴 `다 먹었어요` 기록을 지운다. 폼에서 바꾼 레시피의 사 먹으면 얼마는 되돌리지 않는다. `ponytail:` 같은 이름 재료를 그사이 새로 넣었으면 되살린 행과 두 줄이 된다.
9. **동시성.** 저장·되돌리기는 사용자 잠금(PostgreSQL `pg_advisory_xact_lock(crc32("cook_logs"), user_id)`) → 쓴 재료 행 `FOR UPDATE`(id 순). 쓴 재료 id가 없거나 남의 것이면 400 `재고가 방금 바뀌었어요. 다시 불러와주세요.`(남의 id와 지워진 id를 같은 문구로 — 존재를 드러내지 않고, 초안 뒤 다른 탭에서 지운 흔한 경우를 404보다 알기 쉽게). `ponytail:` 재고 고치기(PATCH)는 잠그지 않는다 — 옛 수량이 열린 고치기 폼으로 저장하면 차감을 덮을 수 있다(기존 마지막 쓰기 우선). SQLite(개발)는 잠그지 않는다.
10. **구입 수량 `ingredients.price_quantity`.** 가격이 생기거나 바뀌거나 **단위가 바뀐 순간의 수량**(만들 때 가격이 있으면 그 수량, PATCH에 `price` 또는 `unit`이 있으면 고친 뒤 수량, 가격이 없으면 NULL). 요리 차감·수량만 고치기는 바꾸지 않는다. 기존 행은 마이그레이션이 `price IS NOT NULL`인 행에 `quantity`로 채운다. 재료비 = `가격 × min(쓴 양 ÷ 구입 수량, 1)`.
11. **사 먹으면 얼마(결정 A).** 1인분 원 정수 0~1,000,000. `recipes.eat_out_price`·`eat_out_source`(`user`|`ai`|`sample`). AI 추정은 `POST /api/recipes/<id>/eat-out-estimate` — 레시피에 값이 있으면 AI 없이 그 값, 없으면 AI 한 번(kind `eat_out`을 `scan.RECIPE_KINDS`에 더해 **AI 레시피 하루 한도 묶음**, 화면 `AI 레시피 N번 남음`에도 센다 — 29절 그대로), 결과가 1,000~100,000원 밖이면 버리고 502. 저장은 `eat_out_price IS NULL`일 때만(AI가 도는 사이 사용자가 넣은 값을 덮지 않음). 예시 모드는 9,000원(`sample`). 폼을 열 때 값이 없고 `scan`이 off가 아니면 레시피마다 한 번 자동으로 부르고, 실패·한도는 조용히 빈 칸. 폼·고치기에서 값을 넣어 바꾸면 레시피도 `user`로 바꾸고, 비워 저장해도 레시피 값은 지우지 않는다. 일기에는 그때 값과 출처를 스냅숏.
12. **KAMIS·참가격은 이번 범위 밖.** 두 API 모두 이용 조건 확인 전(27·29절 `구현 시 확인`)이라 재료 가격은 사용자 입력·영수증/주문 스캔 가격만, 외식 가격은 사용자 → AI 추정만 쓴다. 스펙 27절 두 줄에 `(5단계에서는 미룸, 29절 구현 세부 결정 12)`를 붙인다. 붙일 때는 `item_cost`의 가격 없음 분기와 결정 11의 ① 뒤에 끼운다.
13. **돈 반올림.** 재료 줄 재료비 = 10원 단위 반올림(0.5는 올림, `round_won`), 재료비 합 = 줄 합, 아낀 돈 = `사 먹으면 × 인분 − 재료비 합`(정수, 서버 저장). 화면의 `약 N원`은 100원 단위 반올림(시안 18,000 − 7,180 = 10,820 → `약 10,800원`, 대파 2,500 × ⅓ = 833 → `830원`). 계산표 줄 값은 저장값 그대로.
14. **계산한 일기.** 사 먹으면 얼마가 있고 **가격 있는 재료가 1개 이상**이면 `saved`를 넣고, 아니면 `saved = NULL`(재료비 0으로 사 먹는 값 전체를 아낀 돈으로 보이지 않게). `excluded_count` = 가격 모름 재료 수(재고에 없거나 가격·구입 수량이 없는 재료, 양념 제외). 리포트 `요리 N번 중 M번 계산 · 재료 K개 가격 제외`의 K는 계산한 일기들의 합.
15. **음수 아낀 돈(27절).** 그대로 저장·합산. 화면: 상세 `약 1,200원 더 들었어요`, 목록 `약 1,200원 더 듦`, 리포트 합계가 음수면 `약 N원` 아래 `더 들었어요`. 많이 아낀 요리 3개는 양수 합만.
16. **먹은 기록에도 남기기(24절).** 1인분(4b-3 결정 6과 같은 이유), `place home`, `source cook_log`, 제목·레시피는 일기와 같게, 영양은 `fill_snapshots`. 끼니: 식단 칸에서 열면 칸 끼니, 아니면 날짜가 오늘이면 **기기 시각의 서울 시(時)**로 4b-3 결정 8 규칙(`cookMeal`), 지난 날이면 `저녁`. 폼에는 끼니 고르기를 두지 않고(시안) 설명 줄 `9월 15일 저녁 · 집밥`만, 고치기는 먹은 기록에서. 식단 칸에서 열었고 칸이 아직 안 먹었으면 그 칸에 연결(`먹었어요` 표시), 이미 먹었으면 스위치를 끈 채 막고 `이미 먹은 기록이 있어요`. 먹은 기록 하루 20개에 걸리면 저장 전체가 400(문구 그대로, 스위치를 끄면 저장된다).
17. **일기 지우기.** 일기·사진 파일만 지운다. 재고는 되돌리지 않고(29절), 함께 만든 먹은 기록도 남긴다(먹은 것은 사실이라서 — `food_logs.source`는 `cook_log` 그대로). 상세 아래 `일기를 지워도 재고는 되돌리지 않아요.`
18. **고치기.** 날짜·사 먹으면 얼마(1인분)·별점·메모·사진만. 인분·쓴 재료는 재고와 어긋나서 고치지 않는다(시트 안내 `인분과 쓴 재료는 고칠 수 없어요`). 사 먹으면 얼마를 고치면 아낀 돈을 다시 계산한다. 날짜를 바꿔도 먹은 기록 날짜는 그대로.
19. **사진·메모·별점.** 사진은 일기당 1장(4절 `photo_key` 그대로, 시안 한 장), 줄인 뒤 3MB, 사용자 일기 사진 합계 200MB(체험 20MB, 메모·먹은 기록 사진과 따로), 키 `cooklog/<user_id>/<uuid4 hex>.<jpg|png|webp>`. 저장 요청 한 번에 함께(7절 `사진 업로드 실패 시 전체 롤백`: 저장소 오류면 아무것도 바꾸지 않고 503, 커밋이 실패하면 올린 파일을 지운다). 먹은 기록 사진으로 복사하지 않고 달력 칸이 그날 먹은 기록 사진이 없을 때 요리 일기 사진을 쓴다. 메모는 500자(일기라 먹은 기록 200자보다 길게), 별점 1~5 선택(다시 누르면 지움).
20. **목록·상한.** `cooked_on`·id 내림차순 커서 페이지(26절 `조리 기록` 줄), 기본 20개(1~50). 커서는 기존 `encode_cursor`에 날짜를 UTC 자정 시각으로 넣는다(`ponytail:` 날짜 전용 커서를 따로 두지 않음). 사용자당 5,000개 `요리 일기는 5000개까지 남길 수 있어요.` `ponytail:` 상한 확인은 사용자 잠금 안에서 한다.
21. **리포트 달 경계.** 서울 달. `cooked_on`·`eaten_on`은 날짜로 비교, 버린 재료(`ingredient_removals.created_at`, UTC 저장)는 서울 1일 00:00 ~ 다음 달 1일 00:00을 UTC로 바꿔 센다. `기록한 날` = 먹은 기록 있는 날 ∪ 요리 일기 있는 날(먹은 기록 달력 요약도 같은 규칙으로 바꾼다). 집밥 비율은 24절 그대로 먹은 기록 `place`. 미래 달은 빈 결과(화면이 `›`를 막는다).
22. **지난달 대비 줄.** 지난달 요리 0번·버린 재료 0개면 숨긴다. 요리: `지난달보다 요리 4번 더` / `지난달보다 요리 2번 덜` / `지난달과 요리 횟수가 같아요`, 버린 재료: `버린 재료 2개 줄었어요` / `버린 재료 1개 늘었어요` / `버린 재료는 그대로예요`, ` · `로 잇는다.
23. **많이 아낀 요리·버린 재료 이름.** 같은 제목(`title_key`)끼리 계산한 일기의 아낀 돈을 더해 양수만 큰 순 3개(같으면 최근 요리), 막대는 1등 대비 %(최소 4%). 버린 재료 이름은 최근 순 중복 없이 20개, 더 있으면 칩 끝 `외 N개`.
24. **버린 재료 카드 문구.** 시안 `식단에 넣으면 먼저 쓰도록 알려드려요`는 아직 없는 기능이라 사실인 `빨리 먹어야 할 재료는 추천에서 먼저 보여줘요`(추천 임박 가산점, 4절)로 바꾼다 — **사용자 확인 대상**.
25. **재료 지울 때 이유 저장(결정 D).** 이미 있는 삭제 기록 테이블 `ingredient_removals`(4·27절, `DELETE /api/ingredients/<id>?reason=`)를 그대로 쓴다. 재고 행을 남기는 soft delete는 하지 않는다 — 재고 목록·2000개 상한·매칭·추천 순위 캐시·내보내기 쿼리를 모두 고쳐야 해서. 서버는 바꾸지 않고 화면만 시안 6으로: 제목 `{이름} 지우기`, 설명 `구입 9일째 · 냉장`(구입일 모름이면 `냉장`만), 세 줄 라디오 `다 먹었어요 · 버렸어요(집밥 리포트에 세요) · 그냥 지우기`(기본 그냥 지우기), 버튼 `취소`(기존 유지) + `.btn.danger-text` `지우기`. 수량 0으로 저장해 열린 경우는 `다 먹었어요`가 골라진 채(기존).
26. **레시피 상세 요리 표시(시안 2).** `GET /api/recipes/<id>`에만 `cooked: {count, last_on, last_rating} | null`을 붙이고 머리 아래 `요리 3번` 알약 + `마지막 9월 15일 · ★★★★☆`(별점 없으면 날짜만). 다른 레시피 응답(`recipe_json`)은 바꾸지 않는다.
27. **먹은 기록 달력 `요`(24절).** 한 달 API `days` 칸에 `cooked: bool`, 요리 일기만 있는 날도 `days`에 들어간다(`meals 0`, `count 0`). 칸 오른쪽 위 작은 `요`(시안 `.cook`), 범례 `요 = 요리 일기 있음`, 칸 이름 끝 `요리 일기 있음`. 날짜 상세 GET에 `cook_logs: [{id, title, photo_url}]`을 붙이고 시트 맨 위에 `요리 일기 김치찌개 · 보기` 줄(누르면 일기 상세). 24절 `요리함` 표시는 `요`로 부른다.
28. **식단 칸 `요리했어요` 자리(결정 C).** 4b-3 `먹었어요 · 먹은 기록에 남기기` 버튼 **바로 아래** 한 줄 `btn.outline` `요리했어요` — 시안 `먹었어요 옆`이지만 384px에서 긴 4b-3 문구와 한 줄에 넣으면 넘친다. 누르면 칸 상세를 닫지 않고 그 위에 요리했어요 시트를 연다(칸 인분 저장 줄이 끝난 뒤).
29. **내보내기 `cook_logs.csv`(27절).** 칸: 날짜, 요리, 인분, 별점, 메모, 사 먹으면(1인분·원), 사 먹으면 출처(`직접`/`추정`/빈 칸), 재료비(원), 아낀 돈(원, 계산 못 하면 빈 칸), 가격 제외 재료 수, 쓴 재료(`김치 0.3kg; 두부 1모`, 재고에 없던 재료는 레시피 양), 사진 파일 이름, 남긴 시각(서울). 날짜 → id 순. 요약 응답에 `cook_logs`. 쓴 재료 행 CSV는 따로 두지 않는다.
30. **체험 계정.** 예시 재고 네 줄에 가격(`두부 2,480원`, `대파 2,500원`, `김치 12,900원`, `돼지고기 앞다리살 9,800원`, `price_quantity` = 수량)을 넣고, 예시 레시피에 사 먹으면 얼마(김치찌개 9,000원 `ai`, 된장찌개 8,000원 `user`), 요리 일기 3개(2일 전 김치찌개 2인분 ★4 메모 `두부 마저 썼어요`, 5일 전 된장찌개 2인분 ★5, 35일 전 김치찌개 1인분 — 지난달 대비 줄용)와 스냅숏 줄·계산값, 버린 재료 기록 2개(1일 전 `애호박`, 36일 전 `콩나물`)를 만든다. 재고는 빼지 않는다(예시). 사진·먹은 기록 연결은 없다.
31. **마이그레이션 id:** Task 1 `h1p1r1i1c1e1`(down `g3f3l3p3h3o3`), Task 4 `h2c2o2o2k2l2`(down `h1p1r1i1c1e1`) — **구현 시 head 확인.**

## 브랜치

| 브랜치 | 태스크 | 시작 시점 | 병렬 |
|---|---|---|---|
| `feature/cooklog-price-basis` | 1 (재료 구입 수량·레시피 사 먹으면 얼마 칸·`amounts.in_unit`) | 4b-3 Task 12 끝난 main | 12와 병렬 가능 |
| `feature/cooklog-draft` | 2 (`cooklog.py` 순수 계산·요리했어요 초안 API) | 1 병합 뒤 | 3·12와 병렬 가능(파일: `cooklog.py`·`__init__.py`·`test_cooklog_calc.py`; 스펙은 29절 `구현 세부` 줄만 — 겹치면 두 줄 모두 남김) |
| `feature/cooklog-eat-out-ai` | 3 (사 먹으면 얼마 AI 추정 API) | 1 병합 뒤 | 2·4·12와 병렬 가능(파일: `ai.py`·`scan.py`·`recipe_ai.py`·`test_eat_out.py`·`test_demo.py` 한 테스트) |
| `feature/cooklog-save-undo` | 4 (요리 일기 테이블·저장(차감·스냅숏·사진·먹은 기록)·되돌리기) | 2 병합 뒤(마이그레이션 차례) | 3·12와 병렬 가능 |
| `feature/cooklog-diary-api` | 5 (목록·상세·고치기·지우기·사진 바꾸기·레시피 상세 `cooked`) | 4 병합 뒤 | 6·12와 병렬 가능(파일: `cooklog.py`·`recipes.py`·`test_cooklog_diary.py`) |
| `feature/cooklog-report-api` | 6 (집밥 리포트 API·먹은 기록 달력 `cooked`·날짜 상세 `cook_logs`) | 4 병합 뒤 | 5·12와 병렬 가능(파일: `cook_report.py`·`food_logs.py`·`__init__.py`·`test_cook_report.py`·`test_food_log_month.py`) |
| `feature/cooklog-export-demo` | 7 (내보내기 `cook_logs.csv`·체험 계정 예시) | 5·6 병합 뒤 | 12와 병렬 가능 |
| `feature/cooklog-cook-ui` | 8 (`cook.ts`+검사, 요리했어요 시트·되돌리기 알림·레시피 상세 버튼과 요리 표시) | 3·5 병합 뒤(백엔드 7과 겹쳐도 됨) | 12와 병렬 가능 |
| `feature/cooklog-slot-ui` | 9 (식단 칸 상세 `요리했어요`) | 8 병합 뒤 | 10·12와 병렬 가능(파일: `MealSlotSheet.tsx`만) |
| `feature/cooklog-diary-ui` | 10 (요리 일기 목록·상세·고치기·지우기, 더보기 줄·경로·내보내기 줄) | 7·8 병합 뒤 | 9·12와 병렬 가능 |
| `feature/cooklog-report-ui` | 11 (집밥 리포트 화면·더보기 줄·경로) | 10 병합 뒤(`More.tsx`·`App.tsx`·`useHashRoute.ts` 겹침) | 12·13과 병렬 가능 |
| `feature/cooklog-remove-reason-ui` | 12 (재료 지울 때 이유 시트 시안 6) | 4b-3 Task 12 끝난 main(백엔드 필요 없음) | 모든 태스크와 병렬 가능(파일: `IngredientForm.tsx`·`styles.css` 한 묶음) |
| `feature/cooklog-calendar-ui` | 13 (먹은 기록 달력 `요`·범례·날짜 상세 요리 일기 줄) | 6·10 병합 뒤 | 11·12와 병렬 가능(파일: `foodlog/log.ts`·`check-foodlog.mjs`·`FoodLog.tsx`·`FoodLogDaySheet.tsx`·`styles.css` 4b-3 묶음) |
| — | 14 (전체 검사·실제 키 AI 추정·체험 계정·폰 확인·배포 준비) | 9·11·12·13 병합 뒤 | — |

## 파일 구조

```
backend/
  app/models.py                                            (수정, T1·T4) Ingredient.price_quantity, Recipe.eat_out_price/eat_out_source, CookLog, CookLogItem
  migrations/versions/h1p1r1i1c1e1_price_basis.py          (신규, T1) 칸 3개 + price_quantity 채우기
  migrations/versions/h2c2o2o2k2l2_cook_logs.py            (신규, T4) cook_logs, cook_log_items
  app/amounts.py                                           (수정, T1) in_unit
  app/ingredients.py                                       (수정, T1) price_quantity 규칙
  app/recipes.py                                           (수정, T1·T5) recipe_json eat_out 칸, get_recipe cooked
  app/cooklog.py                                           (신규, T2·T4·T5) 순수 계산, 초안, 저장·되돌리기, 목록·상세·고치기·지우기·사진
  app/cook_report.py                                       (신규, T6) GET /api/cook-report
  app/ai.py                                                (수정, T3) EatOutGuess, EAT_OUT_PROMPT, estimate_eat_out, SAMPLE_EAT_OUT_PRICE
  app/scan.py                                              (수정, T3) RECIPE_KINDS에 eat_out
  app/recipe_ai.py                                         (수정, T3) POST /api/recipes/<id>/eat-out-estimate
  app/photos.py                                            (수정, T4) cooklog/ 소유 확인, user_photo_keys에 일기 사진
  app/food_logs.py                                         (수정, T6) month_json cooked·기록한 날·요리 사진, 하루 cook_logs
  app/export.py                                            (수정, T7) cook_logs.csv, summary cook_logs
  app/demo.py                                              (수정, T7) 가격·사 먹으면 얼마·요리 일기·버린 재료 예시
  app/__init__.py                                          (수정, T2·T6) 블루프린트 cooklog·cook_report
  tests/test_price_basis.py (T1), test_cooklog_calc.py (T2), test_eat_out.py (T3), test_cooklog_save.py (T4),
  test_cooklog_diary.py (T5), test_cook_report.py (T6)
  tests/test_migrations.py·test_amounts.py·test_ingredients.py·test_food_log_month.py·test_export.py·test_demo.py (수정)
docs/superpowers/specs/2026-09-13-recipe-ai-design.md      (수정, T1~T14) 2·4·5·6·7·9·23·24·26·27·29절
frontend/
  package.json                                             (수정, T8) check에 check-cooklog.mjs
  scripts/check-cooklog.mjs                                (신규, T8·T10·T11)
  scripts/check-foodlog.mjs                                (수정, T13)
  src/cooklog/cook.ts                                      (신규, T8·T10·T11) 표시·기본값 순수 함수
  src/api.ts                                               (수정, T8) 요리 일기 타입, MyRecipe eat_out·cooked, FoodLogMonthDay.cooked, FoodLogDay.cook_logs, ExportSummary.cook_logs
  src/components/UndoToast.tsx                             (신규, T8) showUndoToast, hideUndoToast, useUndoToastVisible
  src/components/CookSheet.tsx                             (신규, T8) 요리했어요 시트 + DateChips, StarPicker, PhotoPicker, WonField export
  src/pages/RecipeDetail.tsx                               (수정, T8) 요리했어요 버튼·요리 표시·알림
  src/App.tsx, src/useHashRoute.ts                         (수정, T8·T10·T11) UndoToast, /cook-logs, /cook-report, reset
  src/components/MealSlotSheet.tsx                         (수정, T9)
  src/pages/CookDiary.tsx                                  (신규, T10) 목록, openCookLog, resetCookDiaryView
  src/components/CookLogSheet.tsx                          (신규, T10) 상세·계산표·지우기
  src/components/CookEditSheet.tsx                         (신규, T10) 고치기
  src/pages/CookReport.tsx                                 (신규, T11)
  src/pages/More.tsx                                       (수정, T10·T11) 기록 묶음 줄, 내보내기 줄
  src/components/IngredientForm.tsx                        (수정, T12) 지우는 이유 시트
  src/foodlog/log.ts, src/pages/FoodLog.tsx, src/components/FoodLogDaySheet.tsx (수정, T13)
  src/styles.css                                           (수정, T8~T13) /* 요리 일기 (5) */, T13은 /* 먹은 기록 (4b-3) */ 묶음 끝
```

---

### Task 1: 재료 구입 수량·레시피 사 먹으면 얼마 칸·재고 단위 환산

**Files:**
- Create: `backend/migrations/versions/h1p1r1i1c1e1_price_basis.py`, `backend/tests/test_price_basis.py`
- Modify: `backend/app/models.py`, `backend/app/amounts.py`, `backend/app/ingredients.py`, `backend/app/recipes.py`, `backend/tests/test_migrations.py`, `backend/tests/test_amounts.py`, 스펙(4·27·29절)

**Interfaces:**
- Consumes: `amounts.parse_amount`, `ingredients.parse_fields`·`create_ingredient`·`create_ingredients_bulk`·`update_ingredient`, `recipes.recipe_json`, 4b-3 head `g3f3l3p3h3o3`
- Produces:
  - 모델:
    ```python
    # Ingredient
    price_quantity = db.Column(db.Float)  # 가격을 넣거나 바꾸거나 단위를 바꾼 순간의 수량(재료비 비율 분모, 29절 결정 10). 가격 없으면 NULL
    # Recipe
    eat_out_price = db.Column(db.Integer)  # 사 먹으면 얼마(1인분, 원, 29절 결정 11)
    eat_out_source = db.Column(db.String(10))  # user | ai | sample
    ```
  - Alembic `h1p1r1i1c1e1`(down `g3f3l3p3h3o3`): `batch_alter_table("ingredients")`에 `price_quantity` Float nullable, `batch_alter_table("recipes")`에 `eat_out_price` Integer·`eat_out_source` String(10) nullable → `op.execute(sa.text("UPDATE ingredients SET price_quantity = quantity WHERE price IS NOT NULL"))`. downgrade는 세 칸을 뺀다.
  - `amounts.py`:
    ```python
    def in_unit(amount_text, unit):
        """레시피 양 글자를 재고 단위 수량으로(23절 D2). '300g'·'kg' → 0.3, '1/2모'·'모' → 0.5, '1L'·'ml' → 1000.0.
        단위가 다르거나(대소문자 무시) 못 읽거나 재고 단위에 숫자가 들었으면(30구) None."""
        if not unit or any(ch.isdigit() for ch in unit):
            return None
        parsed, target = parse_amount(amount_text), parse_amount(f"1{unit}")
        if parsed is None or target is None or parsed[1].lower() != target[1].lower():
            return None
        return parsed[0] / target[0]
    ```
  - `ingredients.py`:
    ```python
    def sync_price_quantity(item, fields):
        """29절 결정 10: 만들 때 또는 fields에 price·unit이 있으면 지금 수량을 구입 수량으로. 가격이 없으면 None."""
        if item.id is None or "price" in fields or "unit" in fields:
            item.price_quantity = item.quantity if item.price is not None else None
    ```
    `create_ingredient`·`create_ingredients_bulk`는 `Ingredient(...)`를 만든 뒤 `sync_price_quantity(item, fields)`, `update_ingredient`는 setattr 뒤 `sync_price_quantity(item, fields)`. 장보기 재고에 넣기(`shopping.py`)는 가격을 받지 않으므로 그대로(NULL). 응답 `to_json`은 바꾸지 않는다.
  - `recipes.recipe_json`에 `"eat_out_price": recipe.eat_out_price, "eat_out_source": recipe.eat_out_source`. `PUT /api/recipes/<id>`(`parse_recipe`)는 이 칸을 받지 않는다(폼에서만 바꾼다, Task 4·5).

- [ ] **Step 0: 브랜치·head** — worktree에서 main(4b-3 Task 12 병합) 기준 `feature/cooklog-price-basis`. `ls backend/migrations/versions`, `cd backend && .venv/bin/flask --app app db heads`(하나, `g3f3l3p3h3o3` 예정).
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_price_basis_migration` — `upgrade(revision="g3f3l3p3h3o3")` 뒤 사용자·위치·재료 두 행(`price 4980, quantity 300` / `price NULL, quantity 2`) 직접 넣기 → `upgrade(revision="h1p1r1i1c1e1")` → 첫 행 `price_quantity 300.0`, 둘째 `None`, `recipes` 컬럼에 `eat_out_price`·`eat_out_source` → `downgrade(revision="g3f3l3p3h3o3")` 뒤 세 칸 없음(기존 `test_ingredient_removals_migration_adds_and_removes_table` 모양).
  - `test_amounts.py`: `test_in_unit` parametrize — `("300g", "g") 300.0` · `("300g", "kg") 0.3` · `("1.5kg", "g") 1500.0` · `("1/2모", "모") 0.5` · `("1L", "ml") 1000.0` · `("200ml", "L") 0.2` · `("2", "개") 2.0` · `("1대", "단") None` · `("약간", "g") None` · `("300g", "") None` · `("10개", "30구") None` · `("1큰술", "큰술") 1.0` · `("300g", "G") 300.0`(대소문자 무시) · `("1KG", "g") 1000.0`.
  - `test_price_basis.py`(`client`·`login`):
    - `test_create_sets_price_quantity` — `POST /api/ingredients {name 깐마늘, quantity 300, unit g, price 4980}` → 앱 컨텍스트에서 행 `price_quantity 300.0`; 가격 없는 재료 → `None`; `POST /api/ingredients/bulk` 두 줄(가격 있음·없음) → `300.0`·`None`.
    - `test_patch_rules` — 가격 있는 300g 재료 → PATCH `{quantity: 100}` → `price_quantity 300.0`(수량만은 안 바뀜) → PATCH `{price: 5000}` → `100.0` → PATCH `{unit: "kg", quantity: 0.1}` → `0.1` → PATCH `{price: null}` → `None` → PATCH `{price: 3000}` → `0.1`.
    - `test_recipe_json_has_eat_out_fields` — `POST /api/recipes` 응답·`GET /api/recipes/<id>`에 `eat_out_price None`·`eat_out_source None`; 앱 컨텍스트에서 `9000`·`"ai"`로 바꾸면 GET에 그대로; `PUT`에 `eat_out_price 1`을 보내도 바뀌지 않음.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 스크래치 DB에서 `flask db upgrade`·`flask db check` 차이 없음. 기존 `test_ingredients.py`·`test_scan.py`·`test_shopping.py`·`test_recipes.py` 그대로 통과.
- [ ] **Step 3: 스펙** — 29절 끝에 `**구현 세부 (2026-09-xx, 5단계):**`를 만들고 결정 10·11(칸 부분)·31, `in_unit` 규칙. 4절 `ingredients` 줄에 `price_quantity`(29절), `recipes` 줄에 `eat_out_price`·`eat_out_source`. 27절 `집밥 재료비` 줄 `사용량 ÷ 구입 수량` 뒤에 `(구입 수량 = ingredients.price_quantity, 29절)`.
- [ ] **Step 4: 커밋** — `git add backend docs && git commit -m "feat: 재료 구입 수량과 레시피 사 먹으면 얼마 칸, 레시피 양을 재고 단위로 바꾸기" -m "Claude-Session: https://claude.ai/code/session_01RfLBMnikALjpYKF3hjnepT"`

---

### Task 2: 요리했어요 순수 계산·초안 API

**Files:**
- Create: `backend/app/cooklog.py`, `backend/tests/test_cooklog_calc.py`
- Modify: `backend/app/__init__.py`, 스펙(29절 `구현 세부`, 23절 D2, 5절 표)

**Interfaces:**
- Consumes: Task 1 `amounts.in_unit`·`Recipe.eat_out_price/eat_out_source`, `amounts.parse_amount`·`SPOON_UNITS`, `nutrition.TRACE_WORDS`(4b-2), `matching.prepare`·`match_prepared`·`names_match`·`normalize`, `recipe_parse.ingredient_key`, `recipes.ALWAYS_HAVE`, `ingredients.seasoning_names`·`status_of`·`user_rules`·`seoul_today`, `auth.login_required`·`get_owned_or_404`
- Produces (`app/cooklog.py`, blueprint `cooklog`, `url_prefix="/api"`):
  ```python
  """요리 일기(스펙 29절). 요리했어요 초안·저장·되돌리기·목록·상세. 쓴 재료는 저장할 때 스냅숏(결정 1·7·8)."""

  SEASONING_SPOONS = SPOON_UNITS - {"컵"}  # 결정 5: 컵은 밀가루·쌀처럼 많이 쓰는 양이라 양념으로 보지 않는다


  def is_seasoning(key, amount, staples):
      """결정 5. key는 ingredient_key(재료 이름), staples는 seasoning_names(user_id)."""
      if any(names_match(key, s) for s in staples):
          return True
      text = (amount or "").strip()
      if text in TRACE_WORDS:
          return True
      parsed = parse_amount(text)
      return parsed is not None and parsed[1].lower() in SEASONING_SPOONS


  def round_won(value, step=10):
      """0.5는 올린다(파이썬 round의 짝수 반올림을 쓰지 않는다). 음수는 쓰지 않는다."""
      return int(math.floor(value / step + 0.5)) * step


  def item_cost(used, price, price_quantity):
      """결정 10·13. 구입 가격 × min(쓴 양 ÷ 구입 수량, 1), 10원 단위. 가격·구입 수량이 없으면 None."""
      if price is None or not price_quantity:
          return None
      return round_won(price * min(used / price_quantity, 1))


  def summarize(eat_out_price, servings, items):
      """items: excluded·cost 속성(또는 키)을 가진 줄. 결정 13·14.
      → {"ingredient_cost": 가격 있는 줄 cost 합, "saved": 사 먹으면 × 인분 − 재료비 | None, "excluded_count": excluded == 'no_price' 수}"""


  def draft_rows(recipe, user_id):
      """결정 4·5. 레시피 재료 → [{name, amount, ingredient_id, stock_name, stock_quantity, stock_unit, base_amount, seasoning}].
      재고는 id 순으로 읽고 빨리 먹어야 할 것(status_of가 urgent·danger)을 앞에 둔다(recipes.inventory와 같은 순서).
      물(normalize(key) in ALWAYS_HAVE)은 뺀다. 재고 한 행은 먼저 맞은 재료 하나에만."""
  ```
  - `summarize`는 dict 줄과 모델 줄을 모두 받도록 `getattr(item, "cost", None) if not isinstance(item, dict) else item.get("cost")`로 읽는 작은 `_get(item, key)`를 쓴다.
  - `GET /api/recipes/<int:recipe_id>/cook-draft`(로그인) → 200 `{recipe_id, title, servings, eat_out_price, eat_out_source, rows}`, `Cache-Control: no-store`. 남의 레시피·없는 id 404.
  - `app/__init__.py`에 `from .cooklog import bp as cooklog_bp` 등록.

- [ ] **Step 0: 브랜치** — main(Task 1 병합)에서 `feature/cooklog-draft`.
- [ ] **Step 1: 실패하는 테스트 작성** (`test_cooklog_calc.py`; 재료는 `tests.test_meals.add_ingredient`·레시피는 `add_recipe`)
  - `test_round_won_and_item_cost` — `round_won(3870) 3870`, `round_won(833.33) 830`, `round_won(835) 840`, `round_won(10820, 100) 10800`; `item_cost(0.3, 12900, 1) 3870`, `item_cost(1, 2500, 3) 830`, `item_cost(1, 2480, 1) 2480`, `item_cost(2, 2480, 1) 2480`(비율 1로 자름), `item_cost(30, 4980, 300) 500`(498 → 500), `item_cost(1, None, 1) None`, `item_cost(1, 1000, None) None`, `item_cost(1, 1000, 0) None`.
  - `test_summarize` — 시안 계산: `summarize(9000, 2, [{cost 3870, excluded None}, {cost 2480, excluded None}, {cost 830, excluded None}, {cost None, excluded "no_price"}, {cost None, excluded "seasoning"}])` == `{"ingredient_cost": 7180, "saved": 10820, "excluded_count": 1}`; 사 먹으면 없음 → `saved None`·`ingredient_cost 7180`; 가격 있는 줄 없음 `[{None, "no_price"}]` → `saved None`·`excluded_count 1`; 음수 `summarize(3000, 1, [{cost 4200, None}])` → `saved -1200`; `eat_out 0` → `saved -4200`(0원도 값).
  - `test_is_seasoning` parametrize(staples `["간장"]`) — `("고춧가루", "1큰술") True` · `("다진 마늘", "1작은술") True` · `("소금", "약간") True` · `("진간장", "2") True`(필수품 names_match) · `("밀가루", "1컵") False` · `("김치", "300g") False` · `("두부", "1/2모") False` · `("후추", "") False`.
  - `test_draft_rows_defaults` — 재고 `김치 1 kg`, `두부 1 모`, `대파 3 대`, `고춧가루 100 g`, 레시피(2인분) `[김치 300g, 두부 1모, 대파 1대, 고춧가루 1큰술, 돼지고기 200g, 물 400ml]` → `GET /api/recipes/<id>/cook-draft` 200, `Cache-Control no-store`, `servings 2`, 줄 이름 `["김치", "두부", "대파", "고춧가루", "돼지고기"]`(물 없음); 김치 `{base_amount 0.3, stock_unit "kg", stock_quantity 1.0, seasoning False, ingredient_id 김치 id}`; 대파 `base_amount 1.0`; 고춧가루 `seasoning True`·`base_amount None`(큰술 ≠ g); 돼지고기 `ingredient_id None`·`stock_name None`·`base_amount None`.
  - `test_draft_unit_mismatch_and_one_stock_per_row` — 재고 `대파 1 단`, 레시피 `[대파 1대, 쪽파 2대, 파 1대]` → 대파 `base_amount None`(단 ≠ 대), 재고 대파는 첫 줄에만, 나머지 줄 중 `대파` 재고에 맞는 줄은 `ingredient_id None`.
  - `test_draft_prefers_urgent_stock` — 재고 `두부`(유통기한 30일 뒤, id 작음)·`두부`(유통기한 내일) → 첫 줄 `ingredient_id`가 내일 것.
  - `test_draft_eat_out_and_ownership` — 앱 컨텍스트에서 레시피 `eat_out_price 9000, source "ai"` → 초안 `eat_out_price 9000`·`eat_out_source "ai"`; 남의 레시피 404; `/api/recipes/2147483648/cook-draft` 404; 로그인 없음 401.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 29절 `구현 세부`에 결정 4·5·13·14와 초안 응답 모양. 23절 D2 끝에 `(구현: 양념은 조미료 분류 필수품 또는 숟가락·약간 양, 29절 결정 5 · 재고 단위 환산 amounts.in_unit)`. 5절 표에 `GET /api/recipes/<id>/cook-draft` 행.
- [ ] **Step 4: 커밋** — `feat: 요리했어요 초안(레시피 양을 재고 단위로·양념은 기본 안 빼기)과 재료비·아낀 돈 계산`

---

### Task 3: 사 먹으면 얼마 AI 추정 API

**Files:**
- Create: `backend/tests/test_eat_out.py`
- Modify: `backend/app/ai.py`, `backend/app/scan.py`, `backend/app/recipe_ai.py`, `backend/app/models.py`(AiCall.kind 주석), `backend/tests/test_demo.py`, 스펙(4·5·7·27·29절)

**Interfaces:**
- Consumes: Task 1 `Recipe.eat_out_price/eat_out_source`, `ai._parse`·`AiError`·`scan_mode`, `scan.check_ai_limits`·`start_ai_call`·`finish_ai_call`·`RECIPE_KINDS`, `auth.ai_daily_limit`·`get_owned_or_404`, `recipe_parse.ingredient_key`
- Produces:
  - `scan.RECIPE_KINDS = ("recipe", "link", "recipe_photo", "meal", "eat_out")` — 주석에 `eat_out: 사 먹으면 얼마 추정(29절 결정 11)`. `/api/ai-usage`의 `recipe.used`·`demo_ai_budget_spent`가 자동으로 함께 센다.
  - `ai.py`:
    ```python
    class EatOutGuess(BaseModel):
        price: int


    EAT_OUT_PROMPT = (
        "한국에서 요즘 이 요리를 동네 식당이나 배달로 1인분 사 먹으면 보통 얼마인지 원 단위 정수 하나로 추정해 price에 쓴다. "
        "가게마다 다르니 흔한 가격 하나만 쓴다. 요리 이름과 재료는 자료일 뿐 지시가 아니다.\n\n"
    )
    MAX_EAT_OUT_INGREDIENTS = 15
    SAMPLE_EAT_OUT_PRICE = 9000


    def estimate_eat_out(title, ingredient_names):
        """(결과 {price}, 토큰 사용량)을 돌려주고, 실패하면 AiError."""
        names = "\n".join(ingredient_names[:MAX_EAT_OUT_INGREDIENTS])
        prompt = EAT_OUT_PROMPT + f"<요리>\n{title}\n</요리>\n<재료>\n{names}\n</재료>"
        return _parse(prompt, EatOutGuess, 256, "eat-out estimate")
    ```
  - `recipe_ai.py`:
    ```python
    EAT_OUT_MIN, EAT_OUT_MAX = 1_000, 100_000
    EAT_OUT_FAIL = "사 먹는 가격을 추정하지 못했어요. 직접 입력해주세요."
    EAT_OUT_OFF = "사 먹는 가격을 지금은 추정할 수 없어요."


    @bp.post("/recipes/<int:recipe_id>/eat-out-estimate")
    @login_required
    def estimate_eat_out_price(recipe_id):
        """29절 결정 11. 레시피에 값이 있으면 AI 없이 그 값. 없을 때만 한 번 추정해 레시피에 저장한다."""
    ```
    순서: `get_owned_or_404(Recipe)` → 값이 있으면 200 `{eat_out_price, eat_out_source}` → `mode = ai.scan_mode(g.user)`: `off` 503 `EAT_OUT_OFF` / `sample` → `price, source = SAMPLE_EAT_OUT_PRICE, "sample"`(기록 없음) / `on` → `check_ai_limits(g.user.id, scan.RECIPE_KINDS, ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT"), "AI 레시피는")` → `call = start_ai_call(g.user.id, "eat_out")`(커밋됨) → `ai.estimate_eat_out(recipe.title, [ingredient_key(i["name"]) for i in recipe.ingredients])` → `AiError`면 502 `EAT_OUT_FAIL` → `finish_ai_call` → `price`가 bool 아닌 int이고 `EAT_OUT_MIN ≤ price ≤ EAT_OUT_MAX`가 아니면 502 `EAT_OUT_FAIL` → `source = "ai"`. 저장: `Recipe.query.filter(Recipe.id == recipe_id, Recipe.eat_out_price.is_(None)).update({eat_out_price: price, eat_out_source: source}, synchronize_session=False)` → 커밋 → 레시피를 다시 읽어(`db.session.refresh`) 200 `{eat_out_price, eat_out_source}`(그사이 사용자가 넣었으면 사용자 값).
  - `update()` dict에 `Recipe.updated_at: Recipe.updated_at`를 함께 넣어 `onupdate`가 돌지 않게 한다 — 추정 때문에 내 레시피 목록 순서(`updated_at` 내림차순)가 바뀌지 않게(테스트로 고정). Task 4·5에서 폼 값으로 레시피를 바꿀 때도 같은 방법을 쓴다.

- [ ] **Step 0: 브랜치** — main(Task 1 병합)에서 `feature/cooklog-eat-out-ai`.
- [ ] **Step 1: 실패하는 테스트 작성** (`test_eat_out.py`, `from tests.test_scan import USAGE, fail_if_called, ai_calls`, 레시피는 `add_recipe`)
  - `test_sample_mode_stores_once_without_record` — 키 없음·개발 앱, 레시피 → POST 200 `{eat_out_price: 9000, eat_out_source: "sample"}`, `AiCall` 0행 → `GET /api/recipes/<id>` 같은 값 → 다시 POST 200 같은 값.
  - `test_on_mode_calls_ai_once_and_counts_recipe_group` — `ANTHROPIC_API_KEY="k"` 앱, `monkeypatch.setattr("app.ai.estimate_eat_out", fake)`(받은 `(title, names)` 기록, `({"price": 12000}, USAGE)`) → 200 `{12000, "ai"}`, fake가 `("부대찌개", ["햄", "김치"])` 받음, `ai_calls == [(uid, "eat_out")]`·토큰 기록 → 두 번째 POST는 fake 안 부름(`fail_if_called`로 교체) → `GET /api/ai-usage` `recipe.used == 1`.
  - `test_limits_and_failures` — ① `recipe` kind 오늘 10행 → 429 `오늘 AI 레시피는 10번까지 쓸 수 있어요. 내일 다시 써주세요.`, 레시피 값 None ② fake가 `ai.AiError("x")` → 502 `사 먹는 가격을 추정하지 못했어요. 직접 입력해주세요.`, `AiCall` 1행(토큰 None), 값 None ③ fake price `500`·`150000`·`True` → 502, 값 None ④ `DEV_MODE=False`·키 없음 → 503 `사 먹는 가격을 지금은 추정할 수 없어요.`
  - `test_user_value_wins_race` — fake 안에서 앱 컨텍스트로 레시피 `eat_out_price 7000, source "user"`를 먼저 커밋 → 응답 `{7000, "user"}`.
  - `test_keeps_recipe_list_order` — 레시피 A(먼저)·B(나중) → A 추정 → `GET /api/recipes` 첫 항목이 여전히 B.
  - `test_ownership` — 남의 레시피 404, `2**31` 404, `raw_client` 400, 로그인 없음 401.
  - `test_demo.py`: `test_demo_budget_counts_eat_out_calls` — `DEMO_AI_GLOBAL_DAILY=1`, 체험 사용자 `eat_out` 1행이면 `ai.scan_mode(demo_user) == "sample"`.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — `test_recipe_ai.py`(AI 사용량)·`test_meal_ai.py` 그대로 통과.
- [ ] **Step 3: 스펙** — 29절 `구현 세부`에 결정 11·12, 4절 `ai_calls.kind`에 `eat_out`, 7절 AI 일일 한도 recipe 그룹 괄호에 `eat_out(29절 사 먹으면 얼마 추정)`, 5절 표 `POST /api/recipes/<id>/eat-out-estimate`, 27절 `사 먹으면 얼마` ②·`집밥 재료비` KAMIS 줄 끝에 `(5단계에서는 미룸, 29절 구현 세부 결정 12)`.
- [ ] **Step 4: 커밋** — `feat: 사 먹으면 얼마 AI 추정(레시피에 한 번만 저장, AI 레시피 한도 묶음)`

---

### Task 4: 요리 일기 저장(재고 차감·스냅숏·사진·먹은 기록)·되돌리기

**Files:**
- Create: `backend/migrations/versions/h2c2o2o2k2l2_cook_logs.py`, `backend/tests/test_cooklog_save.py`
- Modify: `backend/app/models.py`, `backend/app/cooklog.py`, `backend/app/photos.py`, `backend/tests/test_migrations.py`, 스펙(4·5·7·24·29절)

**Interfaces:**
- Consumes: Task 2 `draft_rows`·`item_cost`·`summarize`, Task 1 `Ingredient.price_quantity`·`Recipe.eat_out_*`, 4b-3 `FoodLog`·`food_logs.eaten_date`·`check_caps`·`fill_snapshots`·`BAD_REQUEST`, `photos.read_image`·`user_photo_keys`, `meals._owned_slot`·`MEALS`, `models.IngredientRemoval`·`StorageLocation`·`utcnow`, `locations.default_location`, `storage.mode`·`put`·`delete`·`UPLOAD_UNAVAILABLE`, `validation.integer`·`iso_datetime`, `auth.get_owned_or_404`
- Produces:
  - 모델(마이그레이션 `h2c2o2o2k2l2`, down `h1p1r1i1c1e1`):
    ```python
    class CookLog(db.Model):
        """요리 일기 한 건(스펙 4·29절). 돈 칸은 저장할 때 계산한 값 — 레시피·재고를 고쳐도 지난 일기는 그대로(결정 13·14)."""

        __tablename__ = "cook_logs"
        __table_args__ = (db.Index("ix_cook_logs_user_id_cooked_on", "user_id", "cooked_on"),)

        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
        recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="SET NULL"), index=True)
        food_log_id = db.Column(db.Integer, db.ForeignKey("food_logs.id", ondelete="SET NULL"))
        title = db.Column(db.String(60), nullable=False)
        cooked_on = db.Column(db.Date, nullable=False)
        servings = db.Column(db.Integer, nullable=False)
        rating = db.Column(db.Integer)
        memo = db.Column(db.String(500))
        photo_key = db.Column(db.String(200), unique=True)
        photo_size = db.Column(db.Integer)
        eat_out_price = db.Column(db.Integer)  # 1인분(원)
        eat_out_source = db.Column(db.String(10))  # user | ai | sample
        ingredient_cost = db.Column(db.Integer, nullable=False, default=0)
        saved = db.Column(db.Integer)  # None = 계산 못 함(결정 14)
        excluded_count = db.Column(db.Integer, nullable=False, default=0)
        created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
        updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

        recipe = db.relationship("Recipe")
        food_log = db.relationship("FoodLog")
        items = db.relationship("CookLogItem", order_by="CookLogItem.id", cascade="all, delete-orphan", passive_deletes=True)


    class CookLogItem(db.Model):
        """요리에 쓴 재료 한 줄. 재고에서 뺀 줄은 되돌리기용 스냅숏(결정 7·8), 재고에 없던 레시피 재료는 이름·양만(가격 모름)."""

        __tablename__ = "cook_log_items"

        id = db.Column(db.Integer, primary_key=True)
        cook_log_id = db.Column(db.Integer, db.ForeignKey("cook_logs.id", ondelete="CASCADE"), nullable=False, index=True)
        ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id", ondelete="SET NULL"), index=True)  # 남은 재료만(지운 재료는 처음부터 NULL)
        removal_id = db.Column(db.Integer, db.ForeignKey("ingredient_removals.id", ondelete="SET NULL"))
        name = db.Column(db.String(50), nullable=False)
        amount_text = db.Column(db.String(30))  # 재고에 없던 재료의 레시피 양
        used = db.Column(db.Float)  # 뺀 양(재고 단위)
        unit = db.Column(db.String(10))
        quantity_before = db.Column(db.Float)
        removed = db.Column(db.Boolean, nullable=False, default=False)
        location_id = db.Column(db.Integer)  # 스냅숏(FK 아님 — 위치가 지워져도 되돌리기가 기본 위치로)
        purchased_on = db.Column(db.Date)
        expires_on = db.Column(db.Date)
        price = db.Column(db.Integer)
        price_quantity = db.Column(db.Float)
        cost = db.Column(db.Integer)
        excluded = db.Column(db.String(10))  # seasoning | no_price | None

        ingredient = db.relationship("Ingredient")
        removal = db.relationship("IngredientRemoval")
    ```
    제약 이름은 `NAMING_CONVENTION` 그대로(`fk_cook_logs_food_log_id_food_logs`, `uq_cook_logs_photo_key`, `ix_cook_logs_recipe_id`, `ix_cook_logs_user_id_cooked_on`, `ix_cook_log_items_cook_log_id`, `ix_cook_log_items_ingredient_id`, `fk_cook_log_items_removal_id_ingredient_removals` …).
  - `cooklog.py` 추가:
    ```python
    MAX_COOK_LOGS = 5000
    MAX_USAGES = 50
    MAX_MEMO = 500
    MAX_EAT_OUT = 1_000_000
    MAX_AMOUNT = 100_000
    UNDO_SECONDS = 120
    MAX_PHOTO_BYTES = 3 * 1024 * 1024
    MAX_USER_PHOTO_BYTES = 200 * 1024 * 1024
    MAX_DEMO_PHOTO_BYTES = 20 * 1024 * 1024
    LOCK_KEY = zlib.crc32(b"cook_logs") & 0x7FFFFFFF
    STOCK_CHANGED = "재고가 방금 바뀌었어요. 다시 불러와주세요."
    UNDO_EXPIRED = "되돌릴 수 있는 시간이 지났어요. 재고는 직접 고쳐주세요."
    PHOTO_FULL = "사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요."
    EAT_OUT_ERROR = "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."
    AMOUNT_ERROR = "쓴 양은 0보다 커야 해요."


    def lock_user(user_id):
        """PostgreSQL 사용자 잠금(결정 9). SQLite는 잠그지 않는다."""


    def photo_url(log):
        return f"/api/photos/{log.photo_key}" if log.photo_key else None


    def list_json(log):
        return {"id": log.id, "recipe_id": log.recipe_id, "title": log.title, "cooked_on": log.cooked_on.isoformat(),
                "servings": log.servings, "rating": log.rating, "memo": log.memo, "photo_url": photo_url(log),
                "eat_out_price": log.eat_out_price, "eat_out_source": log.eat_out_source,
                "ingredient_cost": log.ingredient_cost, "saved": log.saved, "excluded_count": log.excluded_count,
                "created_at": iso_datetime(log.created_at)}


    def item_json(item):
        return {"name": item.name, "amount_text": item.amount_text, "used": item.used, "unit": item.unit, "removed": item.removed,
                "price": item.price, "price_quantity": item.price_quantity, "cost": item.cost, "excluded": item.excluded}


    def detail_json(log):
        created = log.created_at if log.created_at.tzinfo else log.created_at.replace(tzinfo=timezone.utc)
        return {**list_json(log), "items": [item_json(i) for i in log.items], "food_log_id": log.food_log_id,
                "undo_until": iso_datetime(created + timedelta(seconds=UNDO_SECONDS))}


    def parse_common(data, log, creating):
        """고치기(Task 5)와 같이 쓰는 칸. 보낸 칸만(creating이면 cooked_on 필수):
        cooked_on: food_logs.eaten_date / rating: None 또는 integer(rating, "별점은", 1, 5) /
        memo: None 또는 문자열(아니면 BAD_REQUEST), NUL 글자 BAD_REQUEST, strip 뒤 비면 None, 500자 넘으면 400 '메모는 500자까지 입력해주세요.' /
        eat_out_price: None 또는 bool 아닌 int 0~MAX_EAT_OUT(아니면 EAT_OUT_ERROR) → apply_eat_out(log, value)."""


    def apply_eat_out(log, value):
        """결정 11. value가 None이면 일기 칸만 비우고 레시피는 그대로. 레시피 값과 같으면 출처도 레시피 출처,
        다르면 'user'로 일기·레시피를 함께 바꾼다(레시피는 updated_at을 그대로 넣어 목록 순서를 지킨다)."""


    def check_photo_room(user, size, excluding=None):
        """사용자 일기 사진 합계(excluding 일기의 사진은 빼고) + size가 한도(체험 20MB)를 넘으면 400 PHOTO_FULL."""


    def new_photo_key(user_id, ext):
        return f"cooklog/{user_id}/{uuid.uuid4().hex}.{ext}"
    ```
  - `POST /api/cook-logs`(로그인) multipart: `data`(JSON 문자열) + 선택 `image` → 201 `{log: detail_json, deducted_names: [뺀 재료 이름, 요청 순서]}`. `data`: `{recipe_id, servings, cooked_on, rating?, memo?, eat_out_price?, usages: [{ingredient_id, amount}] 0~50, food_log?: bool(기본 true), meal?, meal_slot_id?}`. 순서:
    1. `data`가 없거나 JSON dict가 아니면 400 `BAD_REQUEST`. `recipe = get_owned_or_404(Recipe, recipe_id)`(bool·문자열이면 400 `BAD_REQUEST`). `servings = integer(..., "인분은", 1, 20)`.
    2. `log = CookLog(user_id, recipe=recipe, title=recipe.title, servings)` → `parse_common(data, log, creating=True)`.
    3. `usages`: 리스트 0~50개가 아니거나 줄이 dict가 아니거나 `ingredient_id`가 bool 아닌 1~2**31-1 int가 아니거나 겹치면 400 `BAD_REQUEST`; `amount`가 bool 아닌 유한수 0 < x ≤ MAX_AMOUNT가 아니면 400 `AMOUNT_ERROR`.
    4. `food_log` bool 아니면 `BAD_REQUEST`. `meal_slot_id`가 있으면 `slot = meals._owned_slot(id)`(404), `slot.recipe_id != recipe.id`면 400 `BAD_REQUEST`. `food_log`이고 slot이 없으면 `meal`이 `MEALS` 안이어야 한다(아니면 400 `끼니를 골라주세요.`).
    5. 사진: `"image" in request.files`이면 `storage.mode() == "off"` → 503 `UPLOAD_UNAVAILABLE`, `data_bytes, media_type, ext = photos.read_image(MAX_PHOTO_BYTES)`.
    6. `lock_user(g.user.id)` → `CookLog` 수 ≥ MAX_COOK_LOGS면 400 `f"요리 일기는 {MAX_COOK_LOGS}개까지 남길 수 있어요."` → 사진이 있으면 `check_photo_room(g.user, len(data_bytes))`.
    7. `rows = draft_rows(recipe, g.user.id)`(차감 전) → 쓴 재료 행을 `Ingredient.query.filter(Ingredient.id.in_(ids), Ingredient.user_id == g.user.id).order_by(Ingredient.id).with_for_update().all()` → 개수가 다르면 400 `STOCK_CHANGED`.
    8. 요청 순서로 줄마다: `before = item.quantity`, `used = min(amount, before)`, `left = round(before - amount, 3)`. `row = 초안에서 ingredient_id가 같은 줄`(없으면 `is_seasoning(ingredient_key(item.name), "", staples)`로 판정). `excluded = "seasoning" if seasoning else ("no_price" if item.price is None or not item.price_quantity else None)`, `cost = item_cost(used, item.price, item.price_quantity) if excluded is None else None`. `CookLogItem(name=item.name, used, unit=item.unit, quantity_before=before, location_id, purchased_on, expires_on, price, price_quantity, cost, excluded)`. `left < 0.001`이면 `removal = IngredientRemoval(user_id, name=item.name, reason="eaten")`, 줄에 `removed=True, removal=removal`, `db.session.delete(item)`; 아니면 `item.quantity = left`, 줄에 `ingredient=item`.
    9. 초안에서 `ingredient_id is None and not seasoning`인 줄마다 `CookLogItem(name=row["name"][:50], amount_text=row["amount"][:30], excluded="no_price")`.
    10. `for k, v in summarize(log.eat_out_price, servings, log.items).items(): setattr(log, k, v)`.
    11. `food_log`이면: slot이 있고 `slot.food_log`가 있으면 만들지 않음(결정 16), 아니면 `check_caps(g.user.id, log.cooked_on)` → `FoodLog(user_id, eaten_on=log.cooked_on, meal=slot.meal if slot else meal, source="cook_log", title=log.title, recipe=recipe, meal_slot=slot, servings=1.0, place="home")` 추가 → `fill_snapshots([food])` → `log.food_log = food`.
    12. 사진이 있으면 `key = new_photo_key(...)` → `storage.put(key, data_bytes, media_type)`(저장소 오류는 storage가 503 — 아직 커밋 전이라 모두 되돌려짐) → `log.photo_key, log.photo_size = key, len(data_bytes)`.
    13. 커밋. 실패하면 rollback → 올린 파일 `storage.delete([key])` → `IntegrityError`면 400 `STOCK_CHANGED`, 그 밖은 다시 올린다.
    - `ponytail:` R2에 올리는 동안(최대 수 초) 사용자 잠금·재료 행 잠금을 잡고 있다 — 같은 사용자 요청만 기다린다.
  - `POST /api/cook-logs/<int:log_id>/undo`(로그인) → 200 `{restored: [이름], skipped: [이름]}`. 순서: `get_owned_or_404(CookLog)` → `utcnow() > created_at + UNDO_SECONDS`면 400 `UNDO_EXPIRED` → `lock_user` → 줄마다(id 순):
    - `removed`: 위치 = `db.session.get(StorageLocation, item.location_id)`가 내 것이면 그것, 아니면 `default_location(g.user.id)` → `Ingredient(user_id, name, quantity=quantity_before, unit, location_id, purchased_on, expires_on, price, price_quantity)` 추가 → restored. `item.removal`이 있으면 삭제.
    - `used is not None and not removed`: `ing = Ingredient.query.filter_by(id=item.ingredient_id, user_id=g.user.id).with_for_update().first()` if `item.ingredient_id` else None → 없거나 `ing.unit != item.unit`이면 skipped, 아니면 `ing.quantity = round(ing.quantity + item.used, 3)` → restored.
    - 가격 모름 줄(`used is None`)은 건너뜀(목록에 넣지 않음).
    → `keys = [log.photo_key] if log.photo_key else []` → `log.food_log`가 있으면 삭제 → `db.session.delete(log)` → 커밋 → `storage.delete(keys)`(실패는 로그만) → 200.
  - `photos.py`: `photo(key)` 소유 확인에 `key.startswith(f"cooklog/{g.user.id}/") and CookLog.query.filter_by(photo_key=key, user_id=g.user.id).first()`. `user_photo_keys(user_ids)`에 `CookLog.photo_key`(NULL 제외)를 더한다.

- [ ] **Step 0: 브랜치·head** — main(Task 2 병합)에서 `feature/cooklog-save-undo`, head `h1p1r1i1c1e1`.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_cook_logs_migration_adds_and_removes_tables` — `upgrade(revision="h2c2o2o2k2l2")` 뒤 두 테이블 컬럼 집합(모델 칸 전부), FK `cook_logs {users: CASCADE, recipes: SET NULL, food_logs: SET NULL}`, `cook_log_items {cook_logs: CASCADE, ingredients: SET NULL, ingredient_removals: SET NULL}`, UNIQUE `("photo_key",)`, 인덱스 네 개 → `downgrade(revision="h1p1r1i1c1e1")` 뒤 두 테이블 없음.
  - `test_cooklog_save.py` 헬퍼: `stock(client, name, quantity, unit, price=None)` → 재료 id; `cook(client, recipe_id, usages, image=None, **data)` → `client.post("/api/cook-logs", data={"data": json.dumps({"recipe_id": recipe_id, "servings": 2, "cooked_on": "2026-09-15", "usages": usages, "food_log": False, **data}), **({"image": (io.BytesIO(image), "a.jpg")} if image else {})}, content_type="multipart/form-data")`; 오늘 고정 픽스처(`app.food_logs.seoul_today`·`app.cooklog.seoul_today`·`app.ingredients.seoul_today` 9/15); `from tests.test_shopping_notes import JPEG, photo_path`.
    - `test_save_deducts_and_snapshots_money` — 시안: 재고 `김치 1 kg 12900`, `두부 1 모 2480`, `대파 3 대 2500`, `고춧가루 100 g 3000`; 레시피 2인분 `[김치 300g, 두부 1모, 대파 1대, 고춧가루 1큰술, 돼지고기 200g, 물 400ml]`; `eat_out_price 9000`; usages `김치 0.3, 두부 1, 대파 1, 고춧가루 5` → 201; `deducted_names ["김치", "두부", "대파", "고춧가루"]`; `log.ingredient_cost 7180`·`saved 10820`·`excluded_count 1`·`eat_out_source "user"`; items 이름·excluded `[(김치, None, 3870), (두부, None, 2480), (대파, None, 830), (고춧가루, "seasoning", None), (돼지고기, "no_price", None)]`(돼지고기 `amount_text "200g"`·`used None`); 두부 `removed True`; 재고 GET: 김치 `0.7`, 대파 `2.0`, 고춧가루 `95.0`, 두부 없음; 앱 컨텍스트 `IngredientRemoval` 한 행 `(두부, eaten)`; 레시피 GET `eat_out_price 9000`·`eat_out_source "user"`; `undo_until`이 `created_at + 120초`.
    - `test_overuse_and_tiny_left` — 재고 `우유 1 L 3000`(price_quantity 1) usages `amount 2` → 줄 `used 1.0`·`cost 3000`·`removed True`; 재고 `소금 1.0004 kg` `amount 1` → 남은 양 `round(0.0004, 3) == 0.0`이라 삭제·`removed True`; 재고 `설탕 1.002 kg` `amount 1` → `0.002` 남음.
    - `test_counted_rules` — 사 먹으면 없음 → `saved None`, 가격 있는 재료 없음(`eat_out 9000`, 재고 가격 없음) → `saved None`·`excluded_count 1`; `eat_out 3000` 비싼 재료 → `saved` 음수.
    - `test_eat_out_keeps_recipe_source_and_blank_does_not_clear` — 앱 컨텍스트로 레시피 `9000 ai` → `eat_out_price 9000`으로 저장 → 일기 `source "ai"`, 레시피 그대로 → `eat_out_price null`로 저장 → 일기 `None`, 레시피 `9000 ai` 그대로 → `8000` → 레시피 `8000 user`.
    - `test_food_log_created_and_slot_link` — `food_log true, meal "dinner"` → 먹은 기록 GET 9/15 `logs` 한 줄 `{source "cook_log", place "home", servings 1.0, meal "dinner", title 레시피 제목, recipe_id}`·`log.food_log_id` 그 id; 식단(`make_plan`) 칸 9/15 저녁 같은 레시피 → `meal_slot_id`로 저장 → 칸 `eaten_log_id` = 새 먹은 기록 id; 이미 먹은 칸(`POST /api/meal-slots/<id>/eaten` 뒤) → 저장 201·`food_log_id None`·그날 먹은 기록 수 그대로; 다른 레시피의 칸 id → 400 `잘못된 요청이에요.`; `food_log true`·`meal` 없음·칸 없음 → 400 `끼니를 골라주세요.`; `monkeypatch.setattr("app.food_logs.MAX_PER_DAY", 0)` → 400 `하루에 0개까지 남길 수 있어요.`·재고 그대로.
    - `test_photo_saved_and_owner_only` — `image=JPEG` → `photo_url`이 `/api/photos/cooklog/{uid}/`로 시작 → 파일 바이트 == JPEG → `GET photo_url` 200 → 다른 사용자 404 → `photos.user_photo_keys([uid])`에 키.
    - `test_photo_failure_rolls_back_everything` — `DEV_MODE=False`·R2 없는 앱 `image` 있음 → 503 `사진을 지금은 올릴 수 없어요.`, 재고·일기·먹은 기록 그대로; `monkeypatch.setattr("app.storage.put", boom)`(503 abort) → 같음; `b"hello"` → 415, 아무것도 안 바뀜; `monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", 1)` → 400 `사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요.`
    - `test_validation` parametrize(모두 재고·행 그대로) — `data` 없음·`"[]"`·`"x"` `잘못된 요청이에요.` · `servings 0`·`21`·`"2"` `인분은 1~20 사이 정수로 입력해주세요.` · `cooked_on "2026-09-16"` `아직 오지 않은 날은 남길 수 없어요.` · `cooked_on` 없음 `날짜를 골라주세요.` · `rating 6` `별점은 1~5 사이 정수로 입력해주세요.` · `memo` 501자 `메모는 500자까지 입력해주세요.` · `memo "a\x00"` `잘못된 요청이에요.` · `eat_out_price -1`·`1000001`·`True`·`"9000"` `사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요.` · usages 51개·`[{ingredient_id: 1}, {ingredient_id: 1}]`·`[{ingredient_id: True, amount: 1}]` `잘못된 요청이에요.` · `amount 0`·`-1`·`"1"`·`100001` `쓴 양은 0보다 커야 해요.` · `food_log "yes"` `잘못된 요청이에요.`
    - `test_stock_changed_and_ownership` — 지운 재료 id·남의 재료 id → 400 `재고가 방금 바뀌었어요. 다시 불러와주세요.`(다른 재료도 안 빠짐); 남의 레시피 404; `raw_client` 400; 로그인 없음 401; `monkeypatch.setattr("app.cooklog.MAX_COOK_LOGS", 1)` 두 번째 400 `요리 일기는 1개까지 남길 수 있어요.`
    - `test_undo_restores_quantities_and_deleted_rows` — 첫 테스트 저장(두부 삭제 + 먹은 기록 + 사진) → undo 200 `{restored: ["김치", "두부", "대파", "고춧가루"], skipped: []}` → 재고: 김치 `1.0`, 대파 `3.0`, 고춧가루 `100.0`, 두부 새 행 `1 모 2480`·같은 위치·구입일·`price_quantity 1.0` → 일기 0행·먹은 기록 0행·`IngredientRemoval` 0행·사진 파일 없음 → 다시 undo 404.
    - `test_undo_adds_on_top_of_edits_and_skips_changed` — 저장 뒤 PATCH 김치 `{quantity: 0.5}` → 대파 PATCH `{unit: "단"}` → 고춧가루 DELETE(이유 없이) → undo → 김치 `0.8`(0.5 + 0.3), `skipped ["대파", "고춧가루"]`, 대파 `2 단` 그대로, 고춧가루 없음.
    - `test_undo_deleted_location_uses_default` — 두부만 쓴 저장(삭제됨) → 그 보관 위치 행을 앱 컨텍스트에서 지움 → undo → 두부가 `default_location` 위치로 생김.
    - `test_undo_window` — `monkeypatch.setattr("app.cooklog.utcnow", lambda: 저장 시각 + 121초)` → 400 `되돌릴 수 있는 시간이 지났어요. 재고는 직접 고쳐주세요.`, 재고·일기 그대로; 남의 일기 undo 404.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — `test_food_logs.py`·`test_meal_food_log.py`·`test_food_log_photos.py`·`test_shopping_notes.py`·`test_demo.py` 그대로 통과.
- [ ] **Step 3: 스펙** — 29절 `구현 세부`에 테이블·저장 순서·되돌리기·결정 6~9·16·19. 4절 `cook_logs` 줄을 구현 칸으로 바꾸고 `cook_log_items` 줄 추가. 5절 표 `GET/POST /api/cook-logs` 줄의 생성 설명을 `multipart data(JSON) + image`로, `POST /api/cook-logs/<id>/undo` 행, `GET /api/photos/<key>`에 `cooklog/`. 7절 `조리 기록 저장` 줄 끝에 `(구현: 29절 — 사용자 잠금·행 잠금, 0 이하면 삭제 + 다 먹었어요 기록, 사진 저장 실패·커밋 실패 시 되돌림)`. 24절 `요리 기록 자동 표시` 줄에 `(구현 29절 결정 16)`. 27절 회원 탈퇴 줄 접두사에 `·cooklog/<user_id>/`.
- [ ] **Step 4: 커밋** — `feat: 요리 일기 저장(재고 차감·쓴 재료 스냅숏·사진·먹은 기록)과 2분 안 되돌리기`

---

### Task 5: 요리 일기 목록·상세·고치기·지우기·사진 바꾸기·레시피 상세 요리 표시

**Files:**
- Create: `backend/tests/test_cooklog_diary.py`
- Modify: `backend/app/cooklog.py`, `backend/app/recipes.py`, 스펙(5·26·29절)

**Interfaces:**
- Consumes: Task 4 `CookLog`·`list_json`·`detail_json`·`parse_common`·`apply_eat_out`·`check_photo_room`·`new_photo_key`·`summarize`·`MAX_PHOTO_BYTES`, `validation.encode_cursor`·`decode_cursor`, `photos.read_image`, `storage.put`·`delete`·`mode`
- Produces:
  ```python
  LIST_PAGE = 20


  def day_cursor(day, row_id):
      """결정 20: 날짜를 UTC 자정 시각으로 기존 커서에 넣는다."""
      return encode_cursor(datetime.combine(day, time.min, tzinfo=timezone.utc), row_id)


  def recipe_cooked(recipe_id, user_id):
      """레시피 상세 요리 표시(결정 26). 없으면 None, 있으면 {count, last_on, last_rating} — 마지막은 cooked_on·id가 가장 큰 일기."""
  ```
  - `GET /api/cook-logs?limit=1~50(기본 20)&cursor=` → 200 `{items: [list_json], next_cursor}`, `Cache-Control: no-store`. `cooked_on`·id 내림차순, 커서 조건 `or_(cooked_on < d, and_(cooked_on == d, id < i))`(`d = decode_cursor(c)[0].date()`). 잘못된 커서 400(기존 `decode_cursor`).
  - `GET /api/cook-logs/<int:log_id>` → 200 `detail_json`, `Cache-Control: no-store`. 남의 것 404.
  - `PATCH /api/cook-logs/<int:log_id>` JSON `{cooked_on?, rating?, memo?, eat_out_price?}`(결정 18) → 200 `detail_json`. body dict 아님 400 `BAD_REQUEST`, 그 밖 키(`servings`·`usages`)는 400 `BAD_REQUEST`(`인분과 쓴 재료는 고칠 수 없어요` 화면 안내가 따로 있음). `parse_common(data, log, creating=False)` → `eat_out_price`를 보냈으면 `summarize(log.eat_out_price, log.servings, log.items)`로 세 칸 다시 → 커밋.
  - `DELETE /api/cook-logs/<int:log_id>` → 204. 키를 모아 일기만 삭제(재고·먹은 기록 그대로, 결정 17) → 커밋 → `storage.delete(keys)`.
  - `PUT /api/cook-logs/<int:log_id>/photo` multipart `image` → 200 `detail_json`. 순서: 저장소 off 503 → `get_owned_or_404` → `read_image(MAX_PHOTO_BYTES)` → `lock_user` → `check_photo_room(g.user, size, excluding=log)` → 새 키로 `storage.put` → `old = log.photo_key` → 칸 바꾸고 커밋(실패하면 새 파일 삭제) → `storage.delete([old])`.
  - `DELETE /api/cook-logs/<int:log_id>/photo` → 204(사진이 없어도 204), 커밋 뒤 파일 삭제.
  - `recipes.get_recipe` 응답에 `"cooked": recipe_cooked(recipe.id, g.user.id)`(함수 안에서 `from .cooklog import recipe_cooked` — cooklog가 recipes를 import하므로).

- [ ] **Step 0: 브랜치** — main(Task 4 병합)에서 `feature/cooklog-diary-api`.
- [ ] **Step 1: 실패하는 테스트 작성** (`test_cooklog_diary.py`, 일기는 앱 컨텍스트에서 `CookLog`·`CookLogItem` 행을 직접 넣는 헬퍼 `diary(app, user_id, title, cooked_on, **cols)`, 사진 테스트만 `test_cooklog_save.cook` 사용)
  - `test_list_order_and_cursor` — 9/10·9/15(id 작음)·9/15(id 큼)·9/12 일기 + 남의 일기 → `?limit=2` 제목 순서 `[9/15 큰 id, 9/15 작은 id]`·`next_cursor` 있음 → 다음 쪽 `[9/12, 9/10]`·`next_cursor None`; 키 집합 == `list_json` 칸; `Cache-Control no-store`; `?cursor=abc` 400 `잘못된 요청이에요.`; `?limit=0`은 1개, `?limit=99`는 50개까지.
  - `test_detail_shape` — Task 4 저장 일기 GET → `items` 5줄·`undo_until`·`food_log_id`; 남의 일기 404; `2**31` 404.
  - `test_patch_recomputes_saved_and_updates_recipe` — 저장 일기(`eat_out 9000`, 재료비 7180, `saved 10820`) → PATCH `{eat_out_price: 12000}` → `saved 16820`, 레시피 `12000 user` → PATCH `{eat_out_price: null}` → `saved None`·`ingredient_cost 7180` 그대로, 레시피 `12000` 그대로 → PATCH `{rating: null, memo: "  ", cooked_on: "2026-09-14"}` → `rating None`·`memo None`·`cooked_on "2026-09-14"`, 연결된 먹은 기록 날짜 `2026-09-15` 그대로 → PATCH `{servings: 3}`·`{usages: []}`·`[]` 400 `잘못된 요청이에요.` → `{cooked_on: "2026-09-16"}` 400 `아직 오지 않은 날은 남길 수 없어요.`
  - `test_delete_keeps_stock_and_food_log` — 저장(두부 삭제·먹은 기록·사진) → DELETE 204 → 재고 그대로(두부 없음)·먹은 기록 남음(`source "cook_log"`)·사진 파일 없음·`undo` 404.
  - `test_photo_replace_and_remove` — 사진 없는 일기 PUT JPEG → `photo_url` 있음·파일 있음 → PUT PNG → 새 `.png` url, 옛 파일 없음 → DELETE photo 204 → `photo_url None`·파일 없음 → 다시 DELETE 204; 저장소 off 503; `b"hello"` 415; `monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", len(JPEG))`에서 사진이 있는 일기의 사진을 JPEG로 바꾸면 200(자기 사진은 합계에서 뺌), 사진 없는 다른 일기에 올리면 400 `사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요.`
  - `test_recipe_detail_cooked` — 일기 없음 `cooked None`; 9/10 ★3, 9/15 ★4(id 작음), 9/15 별점 없음(id 큼) → `{count: 3, last_on: "2026-09-15", last_rating: None}`; 남의 일기는 세지 않음; 레시피 목록·`POST /api/recipes` 응답에는 `cooked` 키 없음.
  - `test_auth` — 로그인 없음 401 네 API, `raw_client` PATCH·DELETE 400.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 29절 `구현 세부`에 목록·상세·고치기·지우기·사진 API와 결정 17·18·20·26. 5절 표: `GET/POST /api/cook-logs` 목록 설명 `cooked_on·id 내림차순 커서 20개`, `GET/PATCH/DELETE /api/cook-logs/<id>`(원래 `DELETE`만 있던 줄을 바꿈), `PUT/DELETE /api/cook-logs/<id>/photo`, `GET /api/recipes/<id>` 설명에 `cooked`. 26절 표 `앞으로(… 조리 기록)` 줄(4b-3이 나눈 `조리 기록` 줄)을 `요리 일기 | 5,000 | 서버 커서 페이지 + 무한 스크롤, 20개씩(29절)`로.
- [ ] **Step 4: 커밋** — `feat: 요리 일기 목록·상세·고치기(아낀 돈 다시 계산)·지우기·사진 바꾸기와 레시피 상세 요리 횟수`

---

### Task 6: 집밥 리포트 API·먹은 기록 달력 요리 표시

**Files:**
- Create: `backend/app/cook_report.py`, `backend/tests/test_cook_report.py`
- Modify: `backend/app/food_logs.py`, `backend/app/__init__.py`, `backend/tests/test_food_log_month.py`, `backend/tests/test_food_logs.py`, 스펙(5·24·27·29절)

**Interfaces:**
- Consumes: Task 4 `CookLog`·`photo_url`, 4b-3 `food_logs.month_start`·`month_json`·`BAD_REQUEST`, `FoodLog`, `IngredientRemoval`, `matching.title_key`, `ingredients.SEOUL`·`seoul_today`
- Produces:
  - `app/cook_report.py`(blueprint `cook_report`, `url_prefix="/api"`):
    ```python
    """집밥 리포트(스펙 27·29절). 한 달 요리 일기·먹은 기록·버린 재료를 모은다(결정 21~23)."""

    MAX_DISCARDED_NAMES = 20
    TOP_SAVED = 3


    def next_month(first):
        return date(first.year + (first.month == 12), first.month % 12 + 1, 1)


    def seoul_bounds(first):
        """서울 달 [1일 00:00, 다음 달 1일 00:00)을 UTC 시각 두 개로(결정 21)."""
        start = datetime.combine(first, time.min, tzinfo=SEOUL).astimezone(timezone.utc)
        return start, datetime.combine(next_month(first), time.min, tzinfo=SEOUL).astimezone(timezone.utc)


    def month_counts(user_id, first):
        """(요리 수, 버린 재료 수) — 지난달 대비 줄용."""


    def top_saved(logs):
        """결정 23. saved가 있는 일기를 title_key로 묶어 합, 양수만, (합 내림차순, 가장 늦은 cooked_on·id 내림차순) 3개 → [{title(가장 최근 제목), saved}]."""


    def report_json(user_id, first):
        """→ {month, today, cooked, counted, saved_total, excluded_ingredients, logged_days, home, out, home_percent,
        discarded, discarded_names, discarded_more, top_saved, previous: {cooked, discarded}}"""
    ```
    - `cooked` = 그 달 일기 수, `counted` = `saved is not None` 수, `saved_total` = 그 합(없으면 0), `excluded_ingredients` = 계산한 일기들의 `excluded_count` 합.
    - `logged_days` = `{FoodLog.eaten_on 그 달} ∪ {CookLog.cooked_on 그 달}` 수. `home`/`out` = 그 달 먹은 기록 `place`별 수, `home_percent` = `round(home * 100 / (home + out))`(둘 다 0이면 None) — 4b-3 결정 11과 같은 식.
    - `discarded` = `IngredientRemoval.reason == "discarded"`이고 `seoul_bounds` 안인 행 수, `discarded_names` = 그 행을 `created_at`·id 내림차순으로 이름 중복 없이 앞 20개, `discarded_more` = 중복 없는 이름 수 − 20(0 이상).
    - `previous` = `month_counts(user_id, 지난달 1일)`.
  - `GET /api/cook-report?month=YYYY-MM`(로그인) → 200 `report_json`, `Cache-Control: no-store`. `month_start`의 400 문구 그대로.
  - `food_logs.month_json` 바꿈(결정 21·27): 그 달 내 `CookLog`(cooked_on·id 순)를 함께 읽어 날짜마다 `cooked = True`, 먹은 기록이 없는 날은 `{date, meals: 0, count: 0, kcal: None, approx: False, photo_url: None, cooked: True}`로 `days`에 넣는다(날짜 순 유지). 모든 날 칸에 `cooked`(기본 False). 그날 먹은 기록 사진이 없으면 `photo_url` = 사진이 있는 첫 일기 `photo_url`. `summary.logged_days` = 두 날짜 집합의 합집합 수. `avg_kcal`·집밥 비율은 그대로(먹은 기록만).
  - `GET /api/food-logs?date=` 응답에 `cook_logs: [{id, title, photo_url}]`(그날 내 일기, id 순).
  - `app/__init__.py`에 `cook_report` 블루프린트 등록.
  - `ponytail:` 한 달 일기·먹은 기록을 파이썬에서 묶는다(요리 일기는 한 달 보통 수십 개) — 느리면 `GROUP BY` 쿼리로.

- [ ] **Step 0: 브랜치** — main(Task 4 병합)에서 `feature/cooklog-report-api`.
- [ ] **Step 1: 실패하는 테스트 작성** (`test_cook_report.py`, 일기·먹은 기록·지운 기록은 앱 컨텍스트에서 행 직접)
  - `test_report_totals` — 9월: 일기 `부대찌개 9/13 saved 23100 excluded 0`, `제육볶음 9/7 saved 12400 excluded 2`, `된장찌개 9/10 saved 9800 excluded 1`, `김치찌개 9/15 saved 10820 excluded 1`, `김치찌개 9/2 saved -800 excluded 0`, `계란말이 9/12 saved None excluded 2`; 8/31·10/1 일기(빠짐); 먹은 기록 9/1 home·9/1 out·9/13 home(9/13은 일기와 같은 날)·9/20 place None; 지운 기록 `discarded` 애호박(9/14 10:00 서울)·콩나물(9/3)·애호박(9/2)·`eaten` 두부(빠짐)·`discarded` 우유(`2026-08-31T15:30Z` = 서울 9/1 00:30 → 들어감)·`discarded` 양파(`2026-08-31T14:59Z` = 서울 8/31 23:59 → 빠짐) → `?month=2026-09` == `{cooked: 6, counted: 5, saved_total: 55320, excluded_ingredients: 4, logged_days: 8, home: 2, out: 1, home_percent: 67, discarded: 4, discarded_names: ["애호박", "콩나물", "우유"], discarded_more: 0, top_saved: [{title: "부대찌개", saved: 23100}, {title: "제육볶음", saved: 12400}, {title: "김치찌개", saved: 10020}]}` + `month`·`today`, `previous == {cooked: 1, discarded: 1}`(8/31 일기·양파). (날짜 집합: 일기 9/2·9/7·9/10·9/12·9/13·9/15 + 먹은 기록 9/1·9/20 → 8일.) `Cache-Control no-store`.
  - `test_top_saved_positive_and_ties` — `A 5000`(9/1), `B 5000`(9/3), `C -100`, `D 0` → `[B, A]`(같은 합이면 최근), 음수·0 없음; 같은 제목 `계란 말이`/`달걀말이` 합쳐 최근 제목.
  - `test_discarded_names_cap` — 서로 다른 이름 23개 → 20개 + `discarded_more 3`.
  - `test_empty_and_other_users` — 남의 데이터만 → `{cooked 0, counted 0, saved_total 0, excluded_ingredients 0, logged_days 0, home 0, out 0, home_percent None, discarded 0, discarded_names [], discarded_more 0, top_saved [], previous {0, 0}}`.
  - `test_month_validation` parametrize — `month` 없음·`"2026-9"`·`"2026-13"` 400 `잘못된 요청이에요.`, `"1999-12"` 400 `날짜를 다시 확인해주세요.`, 로그인 없음 401; `?month=2026-01`의 `previous`는 2025-12.
  - `test_food_log_month.py`: `test_month_marks_cook_days` — 9/2 먹은 기록(사진 없음) + 같은 날 일기(사진 `cooklog/<uid>/k.jpg`), 9/5 일기만 → `days` 날짜 `["2026-09-02", "2026-09-05"]`, 9/2 `cooked True`·`photo_url "/api/photos/cooklog/<uid>/k.jpg"`·`meals 1`, 9/5 `{meals: 0, count: 0, kcal: None, approx: False, cooked: True}`, `summary.logged_days 2`; 먹은 기록 사진이 있는 날은 그 사진이 먼저. 기존 테스트의 `days` 칸 비교에 `cooked: False`를 더한다.
  - `test_food_logs.py`: `test_day_includes_cook_logs` — 9/14 일기 둘(하나는 사진) + 남의 일기 → `GET /api/food-logs?date=2026-09-14` `cook_logs == [{id, title, photo_url: None}, {id, title, photo_url: "/api/photos/…"}]`; 다른 날 `[]`.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 29절 `구현 세부`에 리포트 응답·결정 14·15·21~23·27. 5절 표 `GET /api/cook-report`, `GET /api/food-logs/month` 설명에 `cooked`, `GET /api/food-logs` 설명에 `cook_logs`. 24절 `월 요약` 줄의 기록한 날에 `(요리 일기 날 포함, 29절)`, `요리 기록이 있는 날은 작은 요리함 표시` → `요` 표시(29절). 27절 집밥 리포트 줄에 `(구현 29절)`.
- [ ] **Step 4: 커밋** — `feat: 집밥 리포트 API(아낀 돈·요리·기록한 날·집밥 비율·버린 재료·지난달)와 먹은 기록 달력의 요리한 날`

---

### Task 7: 내보내기 `cook_logs.csv`·체험 계정 예시

**Files:**
- Modify: `backend/app/export.py`, `backend/app/demo.py`, `backend/tests/test_export.py`, `backend/tests/test_demo.py`, 스펙(5·9·27·29절)

**Interfaces:**
- Consumes: Task 4·5 `CookLog`·`CookLogItem`, `export.write_csv`·`number`·`seoul_time`·`owned`·`BATCH`, `demo.seed_demo_data`의 `recipe_rows`·`today`·`INGREDIENTS`, `models.IngredientRemoval`
- Produces:
  - `export.py`:
    ```python
    EAT_OUT_SOURCE_LABELS = {"user": "직접", "ai": "추정", "sample": "추정"}
    COOK_LOG_HEADER = ["날짜", "요리", "인분", "별점", "메모", "사 먹으면(1인분·원)", "사 먹으면 출처", "재료비(원)", "아낀 돈(원)",
                       "가격 제외 재료 수", "쓴 재료", "사진 파일 이름", "남긴 시각"]


    def used_text(item):
        """'김치 0.3kg' · 재고에 없던 재료는 '돼지고기 200g' · 양이 없으면 이름만."""
        if item.used is not None:
            return f"{item.name} {number(item.used)}{item.unit or ''}"
        return f"{item.name} {item.amount_text}".strip()
    ```
    한 줄: `[log.cooked_on, log.title, log.servings, "" if log.rating is None else log.rating, log.memo or "", "" if log.eat_out_price is None else log.eat_out_price, EAT_OUT_SOURCE_LABELS.get(log.eat_out_source, ""), log.ingredient_cost, "" if log.saved is None else log.saved, log.excluded_count, "; ".join(used_text(i) for i in log.items), os.path.basename(log.photo_key) if log.photo_key else "", seoul_time(log.created_at)]`. `food_logs.csv` 뒤에 `owned(CookLog).options(selectinload(CookLog.items)).order_by(CookLog.cooked_on, CookLog.id).yield_per(BATCH)`. `summary`에 `cook_logs=owned(CookLog).count()`.
  - `demo.py`(결정 30):
    ```python
    INGREDIENT_PRICES = {"두부": 2480, "대파": 2500, "김치": 12900, "돼지고기 앞다리살": 9800}  # price_quantity = 예시 수량
    EAT_OUT_PRICES = {"김치찌개": (9000, "ai"), "된장찌개": (8000, "user")}
    # (며칠 전, 레시피 제목, 인분, 별점, 메모, [(재료, 쓴 양, 단위, 구입 가격, 구입 수량, 제외)], 재고에 없던 재료 [(이름, 레시피 양)])
    COOK_LOGS = [
        (2, "김치찌개", 2, 4, "두부 마저 썼어요", [("김치", 0.3, "kg", 12900, 1, None), ("두부", 1, "모", 2480, 1, None), ("대파", 0.5, "단", 2500, 1, None)], [("고춧가루", "1큰술")]),
        (5, "된장찌개", 2, 5, None, [("두부", 0.5, "모", 2480, 1, None), ("애호박", 0.33, "개", None, None, "no_price"), ("감자", 1, "개", None, None, "no_price")], []),
        (35, "김치찌개", 1, 3, None, [("김치", 0.15, "kg", 12900, 1, None)], []),
    ]
    DISCARDED = [(1, "애호박"), (36, "콩나물")]  # (며칠 전, 이름)
    ```
    `seed_demo_data`: 재료를 만들 때 이름이 `INGREDIENT_PRICES`에 있으면 `price`와 `price_quantity = quantity`. 식단 뒤에: 레시피 행에 `EAT_OUT_PRICES`, `COOK_LOGS`마다 `CookLog(recipe=제목이 같은 recipe_rows, title, cooked_on=today - n, servings, rating, memo, eat_out_price·source = 레시피 값)` + 줄마다 `CookLogItem(name, used, unit, price, price_quantity, cost=cooklog.item_cost(...) if 제외 없음 else None, excluded)` + 재고에 없던 재료는 `is_seasoning`이면 `excluded "seasoning"`·`amount_text`, 아니면 `no_price` → `summarize`로 세 칸. `DISCARDED`마다 `IngredientRemoval(reason="discarded", created_at=utcnow() - timedelta(days=n))`. 재고는 빼지 않는다. (김치찌개 2일 전: 3870 + 2480 + 1250 = 7600, 18000 − 7600 = `saved 10400`; 된장찌개: 1240, 16000 − 1240 = `saved 14760`·`excluded 2`; 35일 전: 1940, 9000 − 1940 = `7060`.)

- [ ] **Step 0: 브랜치** — main(Task 5·6 병합)에서 `feature/cooklog-export-demo`.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_export.py`: `test_export_includes_cook_logs_csv` — 내 일기 둘(9/14 `김치찌개` 2인분 ★4 memo `=맛있음` eat_out 9000 ai, 재료비 7180, saved 10820, excluded 1, 줄 `김치 0.3 kg`·`두부 1 모`·`돼지고기 amount_text 200g`, 사진 키 `cooklog/<uid>/a.jpg` / 9/13 `계란말이` saved None eat_out None) + 남의 일기 → zip `cook_logs.csv` 머리글 == `COOK_LOG_HEADER`, 줄 순서 9/13 → 9/14, 9/14 줄 `사 먹으면(1인분·원) "9000"`·`사 먹으면 출처 "추정"`·`재료비(원) "7180"`·`아낀 돈(원) "10820"`·`가격 제외 재료 수 "1"`·`쓴 재료 "김치 0.3kg; 두부 1모; 돼지고기 200g"`·`메모 "'=맛있음"`·`사진 파일 이름 "a.jpg"`, 9/13 줄 `아낀 돈(원) ""`·`사 먹으면 출처 ""`.
  - `test_summary_counts_only_my_data`(기존) — 기대 dict에 `cook_logs`.
  - `test_demo.py`: `test_demo_login_seeds_cook_diary` — 체험하기 → `GET /api/cook-logs` 제목 `["김치찌개", "된장찌개", "김치찌개"]`, 첫 줄 `saved 10400`·`rating 4`·`memo "두부 마저 썼어요"`, 둘째 `excluded_count 2`·`saved 14760` → `GET /api/cook-report?month=<이번 달>`의 `discarded_names`에 `애호박` → 재고 GET 두부 `price 2480`·앱 컨텍스트 `price_quantity 1.0` → 레시피 김치찌개 `eat_out_price 9000`·`eat_out_source "ai"`. 다른 체험 계정과 섞이지 않음. (이번 달이 1~5일이면 된장찌개가 지난달일 수 있어 월 합계 숫자는 확인하지 않는다.)
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 27절 내보내기 목록에 `cook_logs.csv` 칸(결정 29), `요리 기록은 5단계에서 추가한다` 문장을 지운다. 5절 표 `GET /api/export/summary`에 `cook_logs`, `GET /api/export` 파일 목록에 `cook_logs.csv`. 9절 체험 계정 줄에 `요리 일기 예시 3개·버린 재료 2개·예시 재료 가격`. 29절 `구현 세부`에 결정 29·30.
- [ ] **Step 4: 커밋** — `feat: 요리 일기 내보내기(cook_logs.csv)와 체험 계정 예시 일기·가격·버린 재료`

---

### Task 8: 요리했어요 시트·되돌리기 알림·레시피 상세 (시안 1·2)

**Files:**
- Create: `frontend/src/cooklog/cook.ts`, `frontend/scripts/check-cooklog.mjs`, `frontend/src/components/UndoToast.tsx`, `frontend/src/components/CookSheet.tsx`
- Modify: `frontend/package.json`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/pages/RecipeDetail.tsx`, `frontend/src/styles.css`, 스펙(6·29절 `구현 세부` `화면:`)

**Interfaces:**
- Consumes: Task 2 `GET /api/recipes/<id>/cook-draft`, Task 3 `POST /api/recipes/<id>/eat-out-estimate`, Task 4 `POST /api/cook-logs`·`POST /api/cook-logs/<id>/undo`, Task 5 `GET /api/recipes/<id>` `cooked`, `format.ts` `formatWon`·`formatQuantity`·`withJosa`, `meals/plan.ts` `mealLabel`·`slotDateText`, `foodlog/log.ts` `starsText`, `image.ts resizeImage`, `api`·`ApiError`·`localToday`, `useResource`·`forgetResources`·`forgetRecipeCaches`, `useAsyncAction`, `Sheet`, `Icon`, `.r3-toggle`, `.fl-bigstars`, `.sh-photos`·`.sh-photo`, `.cta-bar`
- Produces:
  - `api.ts`(Task 9~13이 이 타입을 그대로 쓴다 — 뒤 태스크는 `api.ts`를 고치지 않는다):
    ```ts
    // ---- 요리 일기·집밥 리포트(스펙 29절, 5단계) ----
    export type EatOutSource = "user" | "ai" | "sample";
    export interface CookDraftRow {
      name: string; amount: string; ingredient_id: number | null; stock_name: string | null;
      stock_quantity: number | null; stock_unit: string | null;
      /** 레시피 인분 기준 재고 단위 양. 단위가 다르면 null(기본 1) */
      base_amount: number | null; seasoning: boolean;
    }
    export interface CookDraft { recipe_id: number; title: string; servings: number; eat_out_price: number | null; eat_out_source: EatOutSource | null; rows: CookDraftRow[] }
    export interface EatOutEstimate { eat_out_price: number; eat_out_source: EatOutSource }
    export interface CookLogItem {
      name: string; amount_text: string | null; used: number | null; unit: string | null; removed: boolean;
      price: number | null; price_quantity: number | null; cost: number | null; excluded: "seasoning" | "no_price" | null;
    }
    export interface CookLogListItem {
      id: number; recipe_id: number | null; title: string; cooked_on: string; servings: number; rating: number | null; memo: string | null;
      photo_url: string | null; eat_out_price: number | null; eat_out_source: EatOutSource | null;
      ingredient_cost: number; saved: number | null; excluded_count: number; created_at: string;
    }
    export interface CookLogDetail extends CookLogListItem { items: CookLogItem[]; food_log_id: number | null; undo_until: string }
    export interface CookLogPage { items: CookLogListItem[]; next_cursor: string | null }
    export interface CookSaveResult { log: CookLogDetail; deducted_names: string[] }
    export interface CookUndoResult { restored: string[]; skipped: string[] }
    export interface RecipeCooked { count: number; last_on: string; last_rating: number | null }
    export interface CookReport {
      month: string; today: string; cooked: number; counted: number; saved_total: number; excluded_ingredients: number;
      logged_days: number; home: number; out: number; home_percent: number | null;
      discarded: number; discarded_names: string[]; discarded_more: number;
      top_saved: { title: string; saved: number }[]; previous: { cooked: number; discarded: number };
    }
    export interface FoodLogCookLog { id: number; title: string; photo_url: string | null }
    ```
    `MyRecipe`에 `eat_out_price: number | null; eat_out_source: EatOutSource | null; /** 상세 GET에만 */ cooked?: RecipeCooked | null;`, `FoodLogMonthDay`에 `cooked: boolean;`, `FoodLogDay`에 `cook_logs: FoodLogCookLog[];`, `ExportSummary`에 `cook_logs: number;`.
  - `src/cooklog/cook.ts`(브라우저 API 없음, 오늘·시각은 인자):
    ```ts
    import type { CookDraftRow, MealKind } from "../api";
    import { formatQuantity, formatWon, withJosa } from "../format.ts";
    import { mealLabel } from "../meals/plan.ts";

    export const MAX_COOK_SERVINGS = 20;
    export const MAX_EAT_OUT = 1_000_000;
    /** 23절 D2: 레시피 양 × 인분 배율(재고 단위, 소수 셋째), 모르면 1 */
    export const defaultAmount = (row: Pick<CookDraftRow, "base_amount">, servings: number, recipeServings: number) =>
      row.base_amount === null ? 1 : Math.round(((row.base_amount * servings) / Math.max(recipeServings, 1)) * 1000) / 1000;
    /** 처음 체크: 재고에 있고 양념이 아니면 */
    export const defaultChecked = (row: Pick<CookDraftRow, "ingredient_id" | "seasoning">) => row.ingredient_id !== null && !row.seasoning;
    /** 결정 6: 쓴 양이 재고 이상이면 `마저 써요` */
    export const usesUp = (amount: number, stock: number) => amount >= stock - 0.0005;
    /** 쓴 양 입력 "1.5"·"0,3" → 0 < n ≤ 100000, 아니면 null */
    export function parseAmountInput(text: string): number | null {
      const n = Number(text.trim().replace(",", "."));
      return text.trim() !== "" && Number.isFinite(n) && n > 0 && n <= 100000 ? n : null;
    }
    /** 사 먹으면 얼마 입력 "9,000원" → 9000, "" → null, 틀리면 undefined */
    export function parseWon(text: string): number | null | undefined {
      const digits = text.replace(/[,\s원]/g, "");
      if (digits === "") return null;
      if (!/^\d+$/.test(digits)) return undefined;
      const n = Number(digits);
      return n <= MAX_EAT_OUT ? n : undefined;
    }
    /** 입력 칸 표시 9000 → "9,000" */
    export const wonFieldText = (n: number | null) => (n === null ? "" : n.toLocaleString("ko-KR"));
    /** 결정 13: 100원 단위 반올림 "약 10,800원"(부호는 호출 측) */
    export const aboutWon = (n: number) => `약 ${formatWon(Math.round(Math.abs(n) / 100) * 100)}`;
    /** 결정 15 */
    export const savedText = (saved: number) => (saved >= 0 ? `${aboutWon(saved)} 아꼈어요` : `${aboutWon(saved)} 더 들었어요`);
    /** 결정 16: 식단 칸 끼니 → 오늘이면 시각(5–9 아침·10–14 점심·15–20 저녁·그 밖 간식) → 지난 날은 저녁 */
    export function cookMeal(date: string, today: string, hour: number, slotMeal?: MealKind): MealKind {
      if (slotMeal) return slotMeal;
      if (date < today) return "dinner";
      return hour >= 5 && hour < 10 ? "breakfast" : hour >= 10 && hour < 15 ? "lunch" : hour >= 15 && hour < 21 ? "dinner" : "snack";
    }
    /** 서울 시(時) — 화면이 new Date()를 넘긴다 */
    export const seoulHour = (d: Date) => Number(d.toLocaleString("en-US", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }));
    /** 먹은 기록 스위치 설명 "9월 15일 저녁 · 집밥" */
    export const foodLogLine = (date: string, meal: MealKind) => `${Number(date.slice(5, 7))}월 ${Number(date.slice(8, 10))}일 ${mealLabel(meal)} · 집밥`;
    /** 언제 칩 */
    export function dateChip(date: string, today: string, yesterday: string): "today" | "yesterday" | "pick" {
      return date === today ? "today" : date === yesterday ? "yesterday" : "pick";
    }
    /** 저장 후 알림 첫 줄(시안 2) */
    export function deductedText(names: string[]): string {
      if (!names.length) return "요리 일기에 남겼어요";
      const shown = names.length <= 3 ? names.join("·") : `${names.slice(0, 3).join("·")} 외 ${names.length - 3}개`;
      return `재고에서 ${withJosa(shown, "을", "를")} 뺐어요`; // withJosa는 낱말 + 조사를 돌려준다
    }
    /** 되돌린 뒤 알림 */
    export const undoneText = (r: { skipped: string[] }) =>
      r.skipped.length ? `재고를 되돌렸어요 · ${withJosa(r.skipped.join("·"), "은", "는")} 그사이 바뀌어 그대로 뒀어요` : "재고를 되돌렸어요";
    /** 쓴 양 칸 옆 "재고 600g" */
    export const stockText = (row: Pick<CookDraftRow, "stock_quantity" | "stock_unit">) =>
      row.stock_quantity === null ? "재고에 없어요" : `재고 ${formatQuantity(row.stock_quantity)}${row.stock_unit ?? ""}`;
    /** 레시피 상세 "마지막 9월 15일 · ★★★★☆" */
    export function cookedLine(c: { last_on: string; last_rating: number | null }, stars: (n: number) => string): string {
      const day = `마지막 ${Number(c.last_on.slice(5, 7))}월 ${Number(c.last_on.slice(8, 10))}일`;
      return c.last_rating === null ? day : `${day} · ${stars(c.last_rating)}`;
    }
    ```
  - `check-cooklog.mjs`(`node:assert/strict`, Task 10·11이 이어 붙인다): `defaultAmount({base_amount: 0.3}, 2, 2) === 0.3`, `({base_amount: 0.3}, 3, 2) === 0.45`, `({base_amount: 1}, 1, 3) === 0.333`, `({base_amount: null}, 4, 2) === 1`, `({base_amount: 1}, 2, 0) === 2`; `defaultChecked({ingredient_id: 1, seasoning: false}) === true`, `({1, true}) false`, `({null, false}) false`; `usesUp(1, 1) true`, `usesUp(0.9995, 1) true`, `usesUp(0.99, 1) false`; `parseAmountInput("1.5") 1.5`, `("0,3") 0.3`, `("0") null`, `("") null`, `("abc") null`, `("100001") null`; `parseWon("9,000원") 9000`, `("") null`, `(" ") null`, `("9천") undefined`, `("1000001") undefined`, `("0") 0`; `wonFieldText(9000) "9,000"`, `(null) ""`; `aboutWon(10820) "약 10,800원"`, `aboutWon(10850) "약 10,900원"`, `aboutWon(-1250) "약 1,300원"`; `savedText(10820) "약 10,800원 아꼈어요"`, `savedText(-1200) "약 1,200원 더 들었어요"`, `savedText(0) "약 0원 아꼈어요"`; `cookMeal("2026-09-15", "2026-09-15", 12) "lunch"`, `(…, 4) "snack"`, `(…, 5) "breakfast"`, `(…, 20) "dinner"`, `(…, 21) "snack"`, `("2026-09-14", "2026-09-15", 8) "dinner"`, `("2026-09-14", "2026-09-15", 8, "breakfast") "breakfast"`; `seoulHour(new Date("2026-09-15T03:41:00Z")) === 12`, `(new Date("2026-09-14T15:00:00Z")) === 0`; `foodLogLine("2026-09-15", "dinner") "9월 15일 저녁 · 집밥"`; `dateChip` 세 경우; `deductedText(["김치", "두부", "대파"]) "재고에서 김치·두부·대파를 뺐어요"`, `(["두부", "김치", "대파", "양파", "감자"]) "재고에서 두부·김치·대파 외 2개를 뺐어요"`, `(["김치찌개용 돼지고기"]) "재고에서 김치찌개용 돼지고기를 뺐어요"`, `(["떡"]) "재고에서 떡을 뺐어요"`, `([]) "요리 일기에 남겼어요"`; `undoneText({skipped: []}) "재고를 되돌렸어요"`, `({skipped: ["대파"]}) "재고를 되돌렸어요 · 대파는 그사이 바뀌어 그대로 뒀어요"`, `({skipped: ["대파", "김"]}) "… · 대파·김은 …"`; `stockText({stock_quantity: 600, stock_unit: "g"}) "재고 600g"`, `({0.5, "모"}) "재고 0.5모"`, `({null, null}) "재고에 없어요"`; `cookedLine({last_on: "2026-09-15", last_rating: 4}, (n) => "★".repeat(n)) "마지막 9월 15일 · ★★★★"`, 별점 없음 `"마지막 9월 15일"`.
  - `components/UndoToast.tsx`:
    ```ts
    export interface UndoToastInput {
      message: string;
      /** 둘째 줄 굵은 초록 글자(시안 `약 10,800원 아꼈어요`) */
      strong?: string;
      /** 되돌리기. 끝나면 보여줄 글자를 돌려준다(실패는 throw → 오류 글자) */
      onUndo: () => Promise<string>;
    }
    export const UNDO_TOAST_MS = 10_000;
    export function showUndoToast(input: UndoToastInput): void;
    export function hideUndoToast(): void;
    /** 알림이 떠 있는지(레시피 상세 cta-bar를 올릴 때) */
    export function useUndoToastVisible(): boolean;
    export default function UndoToast(): JSX.Element | null;
    ```
    - 모듈 상태 + 구독(`Set<() => void>`). 새 알림이 오면 앞 알림을 바꾼다(되돌리기는 마지막 저장만).
    - `div.ck-toast role="status" aria-live="polite"` 안에 `span` `{message}` + `strong`이 있으면 `br` + `b.ck-toast-strong` + `button.ck-toast-undo` `되돌리기`(44px, `aria-label="방금 한 요리 되돌리기"`). 10초 뒤 사라지고, `onPointerEnter`/`onFocus`면 멈췄다가 `onPointerLeave`/`onBlur`면 남은 시간부터 다시(결정 7). 누르면 버튼 `되돌리는 중…`(disabled) → 성공 글자로 바꾸고 버튼 없이 3초 → 실패하면 `p` 오류 글자(`ApiError` 문구) 5초.
    - `App.tsx`: 로그인 화면 밖 레이아웃 끝에 `<UndoToast />`, `resetScreens`에 `hideUndoToast()`.
  - `components/CookSheet.tsx`(프레임 1):
    ```ts
    export interface CookStart { servings: number; date: string; meal: MealKind; slotId: number; slotEaten: boolean }
    interface Props {
      recipeId: number;
      user: User;
      /** 식단 칸에서 열 때(결정 16·28) */
      start?: CookStart;
      onSaved: (result: CookSaveResult) => void;
      onClose: () => void;
    }
    export default function CookSheet(props: Props): JSX.Element;
    /** 고치기 시트(Task 10)도 쓰는 조각 */
    export function DateChips(props: { value: string; today: string; onChange: (date: string) => void }): JSX.Element;
    export function StarPicker(props: { value: number | null; label?: string; onChange: (n: number | null) => void }): JSX.Element;
    export function WonField(props: { value: string; source: EatOutSource | null; estimating: boolean; onChange: (text: string) => void }): JSX.Element;
    export function PhotoPicker(props: { file: Blob | null; currentUrl: string | null; onPick: (file: Blob | null) => void; onRemoveCurrent?: () => void }): JSX.Element;
    /** 요리 일기 저장·되돌리기 요청과 알림(RecipeDetail·MealSlotSheet 공통) */
    export async function undoCook(logId: number): Promise<string>;
    /** onUndone: 되돌린 뒤 화면을 새로 받을 곳(레시피 상세 reload, 식단 onChanged) */
    export function toastSaved(result: CookSaveResult, onUndone?: () => void): void;
    ```
    - 데이터: `useResource<CookDraft>(`/api/recipes/${recipeId}/cook-draft`)`. 받기 전 `p.muted role="status" 불러오는 중…`, 오류는 `p.error` + `다시 불러오기`.
    - `Sheet` title `` `${draft.title} 요리했어요` ``(시안 `김치찌개 요리했어요`), description `쓴 재료는 재고에서 빼요`.
    - **인분:** `div.ck-row` `span.field-label 인분` + `div.stepper`(−/`output.input aria-live="polite" {n}인분`/+, `aria-label="인분 줄이기"`·`"인분 늘리기"`, 1·20에서 disabled). 바꾸면 **사용자가 손대지 않은 줄**의 양만 `defaultAmount`로 다시(`touched` Set).
    - **쓴 재료(`div.field role="group" aria-labelledby`, 라벨 `쓴 재료`):** 재고에 있는 줄(`ingredient_id !== null`)마다 `div.ck-use`: `input type="checkbox"`(22px 모양 `.ck-box`, `aria-label="{김치} 재고에서 빼기"`) · 가운데 `span {row.stock_name ?? row.name}` + 양이 재고 이상이면 `span.badge.old 마저 써요` + `small {seasoning ? "양념 · 기본으로 안 빼요" : stockText(row)}` · 오른쪽 `span.input-suffix.ck-qty`(`input inputMode="decimal"` 16px 폭 64px, `aria-label="{김치} 쓴 양"`, 뒤 `{stock_unit}`, 체크 해제면 `disabled`). 틀린 양이면 줄 아래 `p.hint.ck-invalid 쓴 양은 0보다 커야 해요`. 재고에 없는 줄은 목록 아래 `p.muted 재고에 없는 재료: {돼지고기 · 참기름}`(없으면 줄 없음).
    - **언제:** `DateChips` — `div.chips role="group" aria-label="언제"` `오늘`·`어제`·`날짜 고르기`(`aria-pressed`), `날짜 고르기`를 누르면 옆에 `input.input type="date" max={today}`(값이 오늘·어제가 아니면 칩 `날짜 고르기` 켜짐). 기본 `start?.date ?? localToday()`.
    - **사 먹으면 얼마 (1인분):** `WonField` — `span.input-suffix` `input inputMode="numeric"`(placeholder `예: 9,000`, 입력마다 `wonFieldText(parseWon(text))`로 쉼표) + 뒤 `원` + 오른쪽 `em.ck-est`: `estimating`이면 `추정하는 중…`, 출처가 `ai`·`sample`이고 사용자가 안 고쳤으면 `추정 · 고칠 수 있어요`. 틀리면 `p.hint.ck-invalid 0~1,000,000원 사이로 입력해주세요`. 시작값 `draft.eat_out_price`. 값이 없고 `user.scan !== "off"`이고 모듈 `Set` `estimatedOnce`에 레시피 id가 없으면 넣고 `POST eat-out-estimate` → 사용자가 칸을 안 만졌으면 채우고 출처 반영(실패 조용히).
    - **별점:** `div.ck-row` `b 별점` + `StarPicker`(4b-3 `.fl-bigstars` 모양, `role="radiogroup" aria-label="별점"`, 별 버튼 `role="radio" aria-checked aria-label="{n}점"`, 같은 점수 다시 누르면 null).
    - **사진·메모:** `div.ck-row` — `PhotoPicker`(`button.btn.secondary` `Icon camera` `사진`: 숨긴 `input type="file" accept="image/*"` 한 개(폰이 카메라·앨범을 고르게, 4b-3과 달리 한 장이라 입력 하나), 고르면 버튼 자리에 52px 미리보기 `img`(`URL.createObjectURL`, 닫힐 때 `revokeObjectURL`) + `button.icon-btn aria-label="사진 빼기"` `Icon close`) + `button.btn.secondary.ck-memo-btn` `메모 (선택)` → 누르면 그 자리에 `textarea.input`(maxLength 500, 3줄, 포커스) + `span.muted {n} / 500`.
    - **먹은 기록에도 남기기:** `div.ck-row` `span` `b 먹은 기록에도 남기기` + `br` + `span.muted {start?.slotEaten ? "이미 먹은 기록이 있어요" : foodLogLine(date, meal)}` + `button role="switch" className="r3-toggle" aria-checked aria-label="먹은 기록에도 남기기"`(기본 켜짐, `slotEaten`이면 꺼짐·disabled). `meal = cookMeal(date, today, seoulHour(new Date()), start?.meal)`.
    - **버튼:** `button.btn.primary` `저장하고 재고에서 빼기`(저장 중 `저장하는 중…`, 틀린 칸이 있으면 `aria-disabled` + 첫 틀린 칸으로 포커스). 오류는 버튼 위 `p.error role="alert"`.
    - **저장:** `FormData` `data` = `JSON.stringify({recipe_id, servings, cooked_on: date, rating, memo: memo.trim() || null, eat_out_price: parseWon(text) ?? null, usages: 체크된 줄 {ingredient_id, amount}, food_log: on && !slotEaten, meal, meal_slot_id: start?.slotId})`, 사진이 있으면 `form.append("image", await resizeImage(file), "photo.jpg")` → `api<CookSaveResult>("/api/cook-logs", { method: "POST", body: form })` → `forgetRecipeCaches()`·`forgetResources("/api/recipes")`·`forgetResources("/api/food-logs")`·`forgetResources("/api/meal-plans")`·`forgetResources("/api/cook-")` → `onSaved(result)` → 닫기.
    - `toastSaved(result, onUndone)` = `showUndoToast({ message: deductedText(result.deducted_names), strong: result.log.saved === null ? undefined : savedText(result.log.saved), onUndo: async () => { const text = await undoCook(result.log.id); onUndone?.(); return text; } })`; `undoCook` = `POST …/undo` → 같은 캐시 지우기 → `undoneText(r)`.
  - `RecipeDetail.tsx`(프레임 2):
    - `RecipeDetail` props에 `user: User`(4b-2 Task 8이 이미 넘김 — 없으면 `App.tsx` 두 경로에 `user` 전달).
    - 머리 `header.rc-head` 아래 `recipe.kind === "mine" && recipe.cooked`이면 `p.ck-cooked` `span.badge.info 요리 {count}번` + `span.muted {cookedLine(cooked, starsText)}`(별 글자는 `aria-hidden`, 옆 `span.sr-only 별점 {n}점`).
    - 내 레시피: `div.cta-bar`(`useUndoToastVisible()`이면 `.ck-lift`) 안 `button.btn.primary` `Icon pan` `요리했어요` → `setCooking(true)`. `CookSheet`의 `onSaved`는 `toastSaved(result, reload)` + `reload()`(재고 표시·요리 표시 새로, 되돌린 뒤에도 `reload`). 페이지를 떠난 뒤 되돌리면 `reload`는 사라진 화면의 상태를 바꾸지 않도록 `mounted` ref로 막는다.
    - 기존 `rc-actions`(수정·삭제)는 자리·모양 그대로(`cta-bar` 높이만큼 아래 여백은 기존 공공 레시피 상세와 같은 방식).
  - `styles.css` `/* 요리 일기 (5) */` `/* 5 · Task 8 */`: `.ck-toast`(fixed, 좌우 16px, `bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom) + 12px)`, `--text` 배경 `--bg` 글자, 16px 둥글게, z-index 시트 아래), `.ck-toast-strong`(`--accent`), `.ck-toast-undo`(`--accent` 글자, 44px), `.cta-bar.ck-lift`(아래 여백 +84px), `.ck-row`(flex), `.ck-use`(22px 1fr auto 격자, 최소 48px, 위 선 `--line`), `.ck-box`, `.ck-qty`(폭 108px), `.ck-invalid`(`--danger`), `.ck-est`(`--text-3` 13px), `.ck-memo-btn`, `.ck-cooked`.

- [ ] **Step 0: 브랜치** — main(Task 3·5 병합)에서 `feature/cooklog-cook-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-cooklog.mjs`(위 목록) → `node scripts/check-cooklog.mjs`가 `cook.ts` 없음으로 실패하는지 확인. `package.json` `check` 끝에 `&& node scripts/check-cooklog.mjs`.
- [ ] **Step 2: `cook.ts` 구현 → 검사 통과**
- [ ] **Step 3: 화면 구현** — `api.ts` 타입 → `UndoToast`·`App` → `CookSheet` → `RecipeDetail` → `styles.css`.
- [ ] **Step 4: 검사·빌드** — `cd frontend && npm run check && npm run build`.
- [ ] **Step 5: 브라우저 확인(384×832, 자기 포트 5308, 키 없는 개발 모드)** — 재고 `김치 1kg 12,900원`·`두부 1모 2,480원`·`대파 3대 2,500원`·`고춧가루 100g`, 내 레시피 `김치찌개`(2인분, 김치 300g·두부 1모·대파 1대·고춧가루 1큰술·돼지고기 200g·물) → 상세 아래 `요리했어요`(초록) → 시트 `김치찌개 요리했어요` / `쓴 재료는 재고에서 빼요` → 줄: 김치 `재고 1kg`·`0.3 kg`, 두부 `마저 써요`, 고춧가루 체크 해제·`양념 · 기본으로 안 빼요`, `재고에 없는 재료: 돼지고기` → 사 먹으면 얼마가 `추정하는 중…` → `9,000` `추정 · 고칠 수 있어요`(예시 모드) → 인분 `+` 3인분이면 김치 `0.45`, 직접 고친 줄은 그대로 → 2인분으로 → 언제 `어제` → 스위치 설명 `9월 14일 저녁 · 집밥` → 별 4 → 사진 한 장·메모 → `저장하고 재고에서 빼기` → 시트 닫힘·아래 알림 `재고에서 김치·두부·대파를 뺐어요` / `약 10,800원 아꼈어요` / `되돌리기`, 버튼 `요리했어요`가 알림에 가리지 않음 → 머리 `요리 1번 · 마지막 9월 14일 · ★★★★☆` → 재고 탭: 두부 없음·김치 0.7kg → 다시 저장 뒤 알림 위에 손가락(마우스)을 올려 10초 넘게 멈춤 확인 → `되돌리기` → `재고를 되돌렸어요` → 재고 원래대로(두부 다시 있음) → 먹은 기록 어제 날짜에 `김치찌개` 없음. 틀린 양 `0` → 안내·저장 막힘·포커스. 다크 모드, 키보드(체크 → 양 → 언제 칩 → 별 라디오 화살표 → 스위치 → 저장), 스크린리더 이름(`김치 재고에서 빼기`, `별점 4점`, 알림 읽힘). 스크린샷을 리뷰어에게 남긴다.
- [ ] **Step 6: 스펙** — 29절 `구현 세부`에 `화면:` 줄(요리했어요 시트·알림·레시피 상세 요리 표시, 결정 2·3·16·26). 6절 6번 `요리했어요 폼`에 `(구현 29절)`.
- [ ] **Step 7: 커밋** — `feat: 요리했어요 시트(쓴 재료 기본 양·사 먹으면 얼마 추정·먹은 기록)와 10초 되돌리기 알림`

---

### Task 9: 식단 칸 상세 `요리했어요` (결정 C)

**Files:**
- Modify: `frontend/src/components/MealSlotSheet.tsx`, `frontend/src/styles.css`(한 줄), 스펙(20절 `화면`, 29절 `구현 세부` `화면:`)

**Interfaces:**
- Consumes: Task 8 `CookSheet`·`CookStart`·`toastSaved`, 4b-3 Task 11 `MealSlotSheet`의 `먹었어요` 버튼·`queue`·`slot.eaten_log_id`, `User`
- Produces:
  - `MealSlotSheet` props에 `user: User`(`Meals.tsx`가 넘긴다 — 이 파일은 prop 한 줄만 고친다).
  - 4b-3 `먹었어요` 버튼 바로 아래, `slot.recipe_id !== null && slot.date <= today`일 때 `button.btn.outline` `Icon pan` `요리했어요`(`aria-haspopup="dialog"`) → `await queue.current`(인분 저장이 끝난 뒤) → `setCooking(true)`.
  - `cooking`이면 `<CookSheet recipeId={slot.recipe_id} user={user} start={{ servings, date: slot.date, meal: slot.meal, slotId: slot.id, slotEaten: slot.eaten_log_id !== null }} onSaved={(r) => { if (r.log.food_log_id !== null) setSlot({ ...slot, eaten_log_id: r.log.food_log_id }); toastSaved(r, onChanged); onChanged(); }} onClose={() => setCooking(false)} />` — 시트는 칸 상세 `Sheet` **옆**(안이 아니라, `IngredientForm` 삭제 시트와 같은 이유)에 둔다. 저장 뒤 칸 상세는 열린 채로(먹었어요 표시가 바뀜).
  - `styles.css`: 식단 묶음 끝에 `.ml-cook { margin-top: 8px; }` 한 줄(버튼에 `className="btn outline ml-cook"`).
  - 서버가 칸 연결을 만들어도(`meal_slot_id`) 되돌리면 먹은 기록이 지워져 `eaten_log_id`가 끊긴다 — `onChanged`로 식단을 다시 받으면 맞춰진다.

- [ ] **Step 0: 브랜치** — main(Task 8 병합)에서 `feature/cooklog-slot-ui`.
- [ ] **Step 1: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 2: 브라우저 확인(384×832, 자기 포트 5309)** — 식단 주 보기 오늘 저녁 `김치찌개` 칸(인분 3) → 칸 상세 `먹었어요 · 먹은 기록에 남기기` 아래 `요리했어요` → 시트 인분 `3인분`·언제 `오늘`·스위치 설명 `9월 15일 저녁 · 집밥` → 인분을 −로 바꾼 직후 `요리했어요`를 눌러도 시트가 2인분으로 열림 → 저장 → 칸 상세 버튼이 `먹었어요 · 기록 보기`로, 알림 표시 → 되돌리기 → 식단 다시 받으면 `먹었어요 · 먹은 기록에 남기기`로 돌아옴 → 이미 먹었어요 누른 칸에서 `요리했어요` → 스위치 꺼짐·막힘·`이미 먹은 기록이 있어요` → 직접 쓴 칸·내일 칸에는 버튼 없음 → 칸 상세의 `칸 비우기` 위치·연빨강 모양 그대로. 다크·키보드(칸 상세 → 요리했어요 시트 → 닫으면 포커스가 `요리했어요` 버튼으로)·스크린리더. 스크린샷.
- [ ] **Step 3: 스펙** — 20절 칸 상세 시트 줄에 `먹었어요 아래 요리했어요(29절 결정 28)`, 29절 `구현 세부` `화면:`에 결정 16·28.
- [ ] **Step 4: 커밋** — `feat: 식단 칸 상세에서 요리했어요(칸 인분·날짜·끼니로 열고 먹었어요와 연결)`

---

### Task 10: 요리 일기 목록·상세·고치기·지우기 (시안 3·4)

**Files:**
- Create: `frontend/src/pages/CookDiary.tsx`, `frontend/src/components/CookLogSheet.tsx`, `frontend/src/components/CookEditSheet.tsx`
- Modify: `frontend/src/cooklog/cook.ts`, `frontend/scripts/check-cooklog.mjs`, `frontend/src/useHashRoute.ts`, `frontend/src/App.tsx`, `frontend/src/pages/More.tsx`, `frontend/src/styles.css`, 스펙(27·29절)

**Interfaces:**
- Consumes: Task 5 `GET /api/cook-logs`·`GET/PATCH/DELETE /api/cook-logs/<id>`·`PUT/DELETE …/photo`, Task 6 `GET /api/cook-report`, Task 7 `summary.cook_logs`, Task 8 타입·`cook.ts`·`DateChips`·`StarPicker`·`WonField`·`PhotoPicker`, 4b-3 `foodlog/log.ts` `starsText`·`monthOf`, `meals/plan.ts` `slotDateText`, `useInfiniteList`·`InfiniteSentinel`, `useResource`·`forgetResources`, `navigate`·`goBack`, `Row`(More), `resizeImage`
- Produces:
  - `cook.ts` 추가(검사 같이):
    ```ts
    import type { CookLogItem, CookLogListItem, CookReport } from "../api";

    /** 목록 행 아낀 돈 조각(결정 14·15). good이면 초록 글자 */
    export function savedRowText(log: Pick<CookLogListItem, "saved" | "eat_out_price" | "excluded_count">): { text: string; good: boolean } {
      if (log.saved !== null) return log.saved >= 0 ? { text: `${aboutWon(log.saved)} 아낌`, good: true } : { text: `${aboutWon(log.saved)} 더 듦`, good: false };
      if (log.eat_out_price === null) return { text: "사 먹으면 얼마 모름", good: false };
      return { text: log.excluded_count ? `재료 ${log.excluded_count}개 가격 모름` : "재료 가격 모름", good: false };
    }
    /** "9월 15일 · 2인분" */
    export const diaryDateText = (log: Pick<CookLogListItem, "cooked_on" | "servings">) =>
      `${Number(log.cooked_on.slice(5, 7))}월 ${Number(log.cooked_on.slice(8, 10))}일 · ${log.servings}인분`;
    /** 메모 첫 줄 */
    export const firstLine = (memo: string | null) => (memo ?? "").split("\n")[0].trim();
    /** 목록 위 카드 "9월 요리 12번 · 약 86,000원 아꼈어요" */
    export function diaryHeader(r: Pick<CookReport, "month" | "cooked" | "counted" | "saved_total">): string {
      const head = `${Number(r.month.slice(5, 7))}월 요리 ${r.cooked}번`;
      return r.counted ? `${head} · ${savedText(r.saved_total)}` : head;
    }
    /** 계산표 사 먹으면 줄 "사 먹으면 9,000원 × 2인분" */
    export const eatOutLine = (price: number, servings: number) => `사 먹으면 ${formatWon(price)} × ${servings}인분`;
    /** 계산표 재료 줄 "김치 0.3kg / 1kg 12,900원" (가격 있는 줄만) */
    export const costLine = (i: Pick<CookLogItem, "name" | "used" | "unit" | "price" | "price_quantity">) =>
      `${i.name} ${formatQuantity(i.used ?? 0)}${i.unit ?? ""} / ${formatQuantity(i.price_quantity ?? 0)}${i.unit ?? ""} ${formatWon(i.price ?? 0)}`;
    /** 계산표 아래 안내(시안 4) */
    export function excludedNote(items: Pick<CookLogItem, "name" | "used" | "unit" | "amount_text" | "excluded">[]): string {
      const unknown = items.filter((i) => i.excluded === "no_price");
      const label = (i: (typeof unknown)[number]) => `${i.name} ${i.used !== null ? `${formatQuantity(i.used)}${i.unit ?? ""}` : (i.amount_text ?? "")}`.trim();
      const parts = [];
      if (unknown.length === 1) parts.push(`${withJosa(label(unknown[0]), "은", "는")} 가격 모름이라 뺐어요`);
      if (unknown.length > 1) parts.push(`${label(unknown[0])} 외 ${unknown.length - 1}개는 가격 모름이라 뺐어요`);
      if (items.some((i) => i.excluded === "seasoning")) parts.push("양념은 계산에 넣지 않아요");
      parts.push("참고용이에요");
      return parts.join(" · ");
    }
    ```
    검사: `savedRowText({saved: 10820, …})` `{text: "약 10,800원 아낌", good: true}`, `({saved: -1200})` `"약 1,200원 더 듦"`·false, `({saved: null, eat_out_price: null})` `"사 먹으면 얼마 모름"`, `({null, 9000, excluded_count: 2})` `"재료 2개 가격 모름"`, `({null, 9000, 0})` `"재료 가격 모름"`; `diaryDateText({cooked_on: "2026-09-15", servings: 2}) "9월 15일 · 2인분"`; `firstLine("두부 마저 썼어요\n김치가 시어서") "두부 마저 썼어요"`, `(null) ""`; `diaryHeader({month: "2026-09", cooked: 12, counted: 10, saved_total: 86000}) "9월 요리 12번 · 약 86,000원 아꼈어요"`, `counted 0` → `"9월 요리 12번"`, 음수 합 `"9월 요리 3번 · 약 2,000원 더 들었어요"`; `eatOutLine(9000, 2) "사 먹으면 9,000원 × 2인분"`; `costLine({name: "김치", used: 0.3, unit: "kg", price: 12900, price_quantity: 1}) "김치 0.3kg / 1kg 12,900원"`, `({두부, 1, 모, 2480, 1}) "두부 1모 / 1모 2,480원"`; `excludedNote([{돼지고기 used null amount_text "200g" no_price}, {고춧가루 seasoning}]) "돼지고기 200g은 가격 모름이라 뺐어요 · 양념은 계산에 넣지 않아요 · 참고용이에요"`, 둘 `"애호박 0.33개 외 1개는 가격 모름이라 뺐어요 · 참고용이에요"`, `[]` `"참고용이에요"`.
  - `pages/CookDiary.tsx`:
    ```ts
    /** 다른 화면(먹은 기록 날짜 상세)에서 올 때 열 일기. 화면이 읽고 비운다 */
    export function openCookLog(id: number): void;
    /** 로그아웃: 열 대상을 비운다 */
    export function resetCookDiaryView(): void;
    export default function CookDiary({ user }: { user: User }): JSX.Element;
    ```
    - `header.topbar`: `button.icon-btn aria-label="더보기로 돌아가기"`(`goBack("/more")`) + `h1 요리 일기`.
    - 이번 달 카드(프레임 3): `useResource<CookReport>(`/api/cook-report?month=${monthOf(localToday())}`)` → `div.nt-card.ck-month`(`--accent-tint` 배경) 안 `b {diaryHeader}`. 받기 전에는 카드를 그리지 않는다. (누르면 리포트로 가는 버튼·`집밥 리포트 보기`·`›`는 경로가 생기는 Task 11이 붙인다.)
    - 목록 `useInfiniteList<CookLogListItem>((cursor) => api<CookLogPage>(`/api/cook-logs?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`).then((p) => ({ items: p.items, next: p.next_cursor })), ["cook-logs"])`. `ul.nt-card.ck-list` 행마다 `li > button.ck-diary`(`aria-haspopup="dialog"`, `aria-label="{김치찌개} {9월 15일} 일기 보기"`): 사진 있으면 `img.ck-ph`(64px, `alt=""`, `loading="lazy"`) 아니면 `span.ck-noph`(`Icon pan`) · `b {title}` + 별점 있으면 `span.fl-stars aria-hidden {starsText}` + `span.sr-only 별점 {n}점` · `small {diaryDateText} · <span className={good ? "ck-save" : ""}>{savedRowText.text}</span>` · 메모가 있으면 `small {firstLine(memo)}`. 끝에 `InfiniteSentinel`.
    - 빈 목록: `p.muted.center 아직 요리 일기가 없어요` + `p.hint.center 레시피 상세의 요리했어요로 남겨요`.
    - 일기를 누르거나 `openCookLog` 대상이 있으면 `CookLogSheet`. 지우기·고치기 뒤 목록 `reload()`와 카드 `reload()`.
  - `components/CookLogSheet.tsx`(프레임 4, `export default function CookLogSheet(props: { id: number; today: string; user: User; onChanged: () => void; onClose: () => void })`):
    - `useResource<CookLogDetail>(`/api/cook-logs/${id}`)`, 404면 `p.muted 지운 일기예요`.
    - `Sheet` title `{title}`, description `{slotDateText(cooked_on, "")} · {servings}인분`(+ 별점 있으면 ` · ` 뒤 별 글자는 시트 안 첫 줄 `p.ck-sd`에 `span.fl-stars`로 — Sheet description은 글자만이라). 사진 `img.ck-hero`(150px, `object-fit: cover`, `alt="{title} 사진"`), 메모 `p.ck-memo`(줄바꿈 유지).
    - 계산 카드 `section.nt-card.ck-calc`(`aria-labelledby`, `--field` 배경): 머리 `span.muted 아낀 돈` + `span.ck-big` — `saved === null`이면 `계산하지 못했어요`(글자 `--text-2`), 아니면 `aboutWon(saved)`(음수면 `--warn` 글자와 아래 `span 더 들었어요`). `dl.ck-table`(2열): ① `eat_out_price`가 있으면 `dt {eatOutLine(price, servings)}`(+ 출처 `ai`·`sample`이면 `span.badge 추정`) · `dd {formatWon(price × servings)}` ② `cost !== null`인 줄마다 `dt {costLine(item)}` · `dd − {formatWon(cost)}` ③ 합계 줄 `.ck-tot`: `dt 재료비 {aboutWon(ingredient_cost)}` · `dd {saved === null ? "사 먹으면 얼마를 넣으면 계산해요" : `아낀 돈 ${aboutWon(saved)}`}`. 아래 `p.nt-src {excludedNote(items)}`.
    - 버튼 `div.ck-two`(1fr 1fr): `button.btn.secondary Icon pencil 고치기` → `CookEditSheet` · `button.btn.danger-text 일기 지우기` → `confirm("이 일기를 지울까요? 재고는 되돌리지 않아요.")` → `DELETE` → `forgetResources("/api/cook-")`·`forgetResources("list:")`·`forgetRecipeCaches()` → `onChanged()` → 닫기. 아래 `p.nt-src 일기를 지워도 재고는 되돌리지 않아요.`
  - `components/CookEditSheet.tsx`(`export default function CookEditSheet(props: { log: CookLogDetail; today: string; onSaved: (log: CookLogDetail) => void; onClose: () => void })`):
    - `Sheet` title `{title} 고치기`, description `인분과 쓴 재료는 고칠 수 없어요`, `focusTitle`.
    - 칸: `언제`(`DateChips`), `사 먹으면 얼마 (1인분)`(`WonField`, 추정 표시는 출처가 ai·sample이고 안 고쳤을 때), `별점`(`StarPicker`), `사진`(`PhotoPicker` — 기존 사진이 있으면 미리보기 + `사진 빼기`), `메모 (선택)`(`textarea` 500자, 카운터).
    - `저장`: 바뀐 칸만 `PATCH`(`eat_out_price`는 `parseWon` 값, 빈 칸이면 null) → 새 사진을 골랐으면 `PUT …/photo`(resizeImage) → 사진을 뺐으면 `DELETE …/photo` → 마지막 응답(또는 `GET`)으로 `onSaved`. 사진 단계만 실패하면 시트를 닫지 않고 `p.error 사진은 올리지 못했어요 · {문구}`(글 칸은 저장됨). 버튼 `div.fl-actions` `취소` · `저장`(`저장하는 중…`).
  - 경로: `useHashRoute.ts` `ROUTES`에 `"/cook-logs"`, `App.tsx` `PAGES`에 `"/cook-logs": ({ user }) => <CookDiary user={user} />`, `resetScreens`에 `resetCookDiaryView()`.
  - `More.tsx` `기록` 묶음 `먹은 기록` 줄 아래 `Row icon={<Icon name="pan" />} title="요리 일기" sub={report.data ? (report.data.cooked ? `이번 달 요리 ${report.data.cooked}번` : "요리했어요로 남긴 기록을 모아 봐요") : ""} onClick={() => navigate("/cook-logs")}`(`report = useResource<CookReport>(…이번 달…)`). `ExportSheet` 목록 `먹은 기록` 줄 뒤 `요리 일기` · `b {count(data?.cook_logs)}`.
  - `styles.css` `/* 5 · Task 10 */`: `.ck-month`, `.ck-list`, `.ck-diary`(64px 1fr 격자, 위 선, 버튼 초기화, 최소 84px), `.ck-ph`·`.ck-noph`(64px, 14px 둥글게), `.ck-save`(`--accent-strong` 600), `.ck-hero`, `.ck-sd`, `.ck-memo`(15px/23px, `white-space: pre-line`), `.ck-calc`, `.ck-big`(28px/34px 700 `tabular-nums` `--accent-strong`), `.ck-table`(2열 grid, 짝수 오른쪽 정렬, `tabular-nums`, `dt`·`dd` 여백 0), `.ck-tot`(700, 위 선), `.ck-two`(1fr 1fr).

- [ ] **Step 0: 브랜치** — main(Task 7·8 병합)에서 `feature/cooklog-diary-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-cooklog.mjs`에 위 목록 → 실패 확인 → `cook.ts` 추가 → 통과.
- [ ] **Step 2: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 3: 브라우저 확인(384×832, 자기 포트 5310, `DEMO_LOGIN=1`로 체험하기 — 예시 일기 3개)** — 더보기 `기록` 묶음 `먹은 기록` 아래 `요리 일기 · 이번 달 요리 N번` → `#/cook-logs`: 위 카드 `9월 요리 2번 · 약 25,200원 아꼈어요`(오늘 날짜에 따라 다름), 행 `김치찌개 ★★★★☆ / 9월 13일 · 2인분 · 약 10,400원 아낌 / 두부 마저 썼어요`, `된장찌개 … 약 14,800원 아낌`, 사진 없는 행 아이콘 → Task 8 흐름으로 사진 있는 일기와 재료 30개 넘게(콘솔 `POST` 반복) 만들어 무한 스크롤·`다 봤어요` → `김치찌개` → 시트 계산표 `사 먹으면 9,000원 × 2인분 [추정] 18,000원`·`김치 0.3kg / 1kg 12,900원 − 3,870원`·`재료비 약 7,600원`·`아낀 돈 약 10,400원`·안내 `양념은 계산에 넣지 않아요 · 참고용이에요` → `고치기`: 사 먹으면 `12,000`·별 5·메모·사진 → 저장 → 계산표·목록 행이 새 값 → 사진 빼기 → `일기 지우기`(연빨강 배경·테두리, 확인 창) → 목록에서 사라짐·재고 그대로 → 사 먹으면 얼마 없는 일기 행 `사 먹으면 얼마 모름`, 상세 `계산하지 못했어요`. 내보내기 시트 `요리 일기 N개`. 다크·키보드(행 → 시트 → 고치기 → 지우기)·스크린리더(`김치찌개 9월 13일 일기 보기`, `별점 4점`). 스크린샷.
- [ ] **Step 4: 스펙** — 29절 `구현 세부` `화면:`에 목록·상세·고치기(결정 17·18·20). 27절 표 `기록` 행 `요리 기록(5)`을 `요리 일기(5단계 완료)`로.
- [ ] **Step 5: 커밋** — `feat: 요리 일기 목록(이번 달 카드·무한 스크롤)·상세 아낀 돈 계산표·고치기·지우기`

---

### Task 11: 집밥 리포트 화면 (시안 5)

**Files:**
- Create: `frontend/src/pages/CookReport.tsx`
- Modify: `frontend/src/cooklog/cook.ts`, `frontend/scripts/check-cooklog.mjs`, `frontend/src/pages/CookDiary.tsx`(카드를 버튼으로), `frontend/src/useHashRoute.ts`, `frontend/src/App.tsx`, `frontend/src/pages/More.tsx`, `frontend/src/styles.css`, 스펙(27·29절)

**Interfaces:**
- Consumes: Task 6 `GET /api/cook-report`, Task 8·10 `cook.ts`(`aboutWon`·`savedText`)·`CookReport` 타입, 4b-3 `foodlog/log.ts` `monthOf`·`shiftMonth`·`monthLabel`, `.fl-mnav`·`.fl-stats`·`.fl-split`·`.nt-card`·`.nt-meter`·`.nt-src`, `useResource`, `goBack`·`navigate`, `localToday`
- Produces:
  - `cook.ts` 추가(검사 같이):
    ```ts
    /** 리포트 머리 "2026년 9월 집밥 리포트" */
    export const reportTitle = (month: string) => `${monthLabel(month)} 집밥 리포트`;
    /** 큰 숫자 위 글자: 이번 달이면 "이번 달 집밥으로", 아니면 "9월 집밥으로" */
    export const reportLead = (month: string, today: string) => (month === today.slice(0, 7) ? "이번 달 집밥으로" : `${Number(month.slice(5, 7))}월 집밥으로`);
    /** 합계 아래 "요리 12번 중 10번 계산 · 재료 5개 가격 제외" */
    export function reportNote(r: Pick<CookReport, "cooked" | "counted" | "excluded_ingredients">): string {
      const head = `요리 ${r.cooked}번 중 ${r.counted}번 계산`;
      return [head, r.excluded_ingredients ? `재료 ${r.excluded_ingredients}개 가격 제외` : "", "참고용이에요"].filter(Boolean).join(" · ");
    }
    /** 결정 22. 지난달 기록이 없으면 null */
    export function compareLine(r: Pick<CookReport, "cooked" | "discarded" | "previous">): string | null {
      const { cooked, discarded } = r.previous;
      if (!cooked && !discarded) return null;
      const dc = r.cooked - cooked, dd = r.discarded - discarded;
      const cook = dc > 0 ? `지난달보다 요리 ${dc}번 더` : dc < 0 ? `지난달보다 요리 ${-dc}번 덜` : "지난달과 요리 횟수가 같아요";
      const waste = dd < 0 ? `버린 재료 ${-dd}개 줄었어요` : dd > 0 ? `버린 재료 ${dd}개 늘었어요` : "버린 재료는 그대로예요";
      return `${cook} · ${waste}`;
    }
    /** 막대 폭 %(1등 대비, 최소 4) */
    export const barWidths = (rows: { saved: number }[]) => rows.map((r) => Math.max(4, Math.round((r.saved * 100) / Math.max(rows[0]?.saved ?? 1, 1))));
    ```
    `monthLabel`은 `../foodlog/log.ts`에서 import. 검사: `reportTitle("2026-09") "2026년 9월 집밥 리포트"`; `reportLead("2026-09", "2026-09-15") "이번 달 집밥으로"`, `("2026-08", "2026-09-15") "8월 집밥으로"`; `reportNote({cooked: 12, counted: 10, excluded_ingredients: 5}) "요리 12번 중 10번 계산 · 재료 5개 가격 제외 · 참고용이에요"`, 제외 0 → `"요리 3번 중 3번 계산 · 참고용이에요"`; `compareLine({cooked: 12, discarded: 3, previous: {cooked: 8, discarded: 5}}) "지난달보다 요리 4번 더 · 버린 재료 2개 줄었어요"`, `({2, 1, {4, 0}}) "지난달보다 요리 2번 덜 · 버린 재료 1개 늘었어요"`, `({3, 2, {3, 2}}) "지난달과 요리 횟수가 같아요 · 버린 재료는 그대로예요"`, `({5, 0, {0, 0}}) null`; `barWidths([{saved: 23100}, {saved: 12400}, {saved: 9800}])` `[100, 54, 42]`, `([{saved: 23100}, {saved: 500}])` `[100, 4]`, `([])` `[]`.
  - `pages/CookReport.tsx`(`export default function CookReport(): JSX.Element`, 모듈 `let viewMonth: string | null`, `export function resetCookReportView(): void`):
    - `header.topbar`: 뒤로(`aria-label="더보기로 돌아가기"`, `goBack("/more")`). 달 이동 `div.fl-mnav`: `button.icon-btn aria-label="지난달"` · `h1 aria-live="polite" {reportTitle(month)}` · `button.icon-btn aria-label="다음 달"`(이번 달이면 disabled).
    - `useResource<CookReport>(`/api/cook-report?month=${month}`)`. 받기 전 `p.muted 불러오는 중…`, 오류 `p.error` + `다시 불러오기`.
    - 카드 1 `section.nt-card.ck-hero-card`(`aria-labelledby`): `cooked === 0`이면 `span.muted {reportLead}` + `b.ck-hero-empty 요리 일기가 없어요` + `p.nt-src 요리했어요로 남기면 아낀 돈을 계산해요`. 아니면 `span.muted {reportLead}` + `span.ck-hero-big {aboutWon(saved_total)}`(음수 `--warn`) + `span.ck-hero-sub {saved_total >= 0 ? "아꼈어요" : "더 들었어요"}` + `p.nt-src {reportNote}`. `counted === 0`이면 큰 숫자 대신 `b 계산한 요리가 없어요` + `p.nt-src 사 먹으면 얼마와 재료 가격을 넣으면 계산해요`.
    - 카드 2 `section.nt-card`: `div.fl-stats.ck-stats4`(4열) `b {cooked}번`/`span 요리` · `b {logged_days}일`/`span 기록한 날` · `b {home_percent ?? "—"}{%}`/`span 집밥` · `b.ck-warn? {discarded}개`/`span 버린 재료`(0보다 크면 `--warn`). `home_percent`가 있으면 `div.fl-split role="img" aria-label="집밥 72%, 외식 28%"`. `compareLine`이 있으면 `p.muted {…}`.
    - 카드 3(있을 때만) `section.nt-card` `b 많이 아낀 요리` + `ul.ck-bars` 줄마다 `li.ck-bar`: `span {title}` · `div.nt-meter role="img" aria-label="{부대찌개} {23,100원}"` 안 `i style={{ width: `${w}%` }}` · `span {formatWon(saved)}`.
    - 카드 4(`discarded > 0`일 때만) `section.nt-card` `b 버린 재료` + `ul.ck-chips` `li.badge.old {이름}` + `discarded_more`면 `li.badge 외 {n}개` + `p.muted 빨리 먹어야 할 재료는 추천에서 먼저 보여줘요`(결정 24).
  - `CookDiary.tsx` 이번 달 카드를 `button.nt-card.ck-month`로 바꾸고 `span.muted 집밥 리포트 보기` + `Icon chevron`, 누르면 `navigate("/cook-report")`(시안 3).
  - 경로: `ROUTES`에 `"/cook-report"`, `PAGES`에 `"/cook-report": () => <CookReport />`, `resetScreens`에 `resetCookReportView()`.
  - `More.tsx` `요리 일기` 줄 아래 `Row icon={<Icon name="receipt" />} title="집밥 리포트" sub={report.data ? (report.data.counted ? `이번 달 ${savedText(report.data.saved_total)}` : "아낀 돈·버린 재료를 한 달씩 보여줘요") : ""} onClick={() => navigate("/cook-report")}`(Task 10의 같은 `report` 리소스).
  - `styles.css` `/* 5 · Task 11 */`: `.ck-hero-card`, `.ck-hero-big`(34px/42px 700 `tabular-nums` `--accent-strong`), `.ck-hero-sub`(15px 600), `.ck-hero-empty`, `.ck-stats4`(4열), `.ck-warn`(`--warn`), `.ck-bars`(목록 초기화, gap 8px), `.ck-bar`(76px 1fr 64px 격자, 13px `tabular-nums`, 마지막 오른쪽 정렬), `.ck-chips`(flex wrap gap 6px).

- [ ] **Step 0: 브랜치** — main(Task 10 병합)에서 `feature/cooklog-report-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-cooklog.mjs`에 위 목록 → 실패 확인 → `cook.ts` 추가 → 통과.
- [ ] **Step 2: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 3: 브라우저 확인(384×832, 자기 포트 5311, 체험하기)** — 더보기 `집밥 리포트 · 이번 달 약 N원 아꼈어요` → `#/cook-report` 머리 `2026년 9월 집밥 리포트`·`›` 막힘 → 큰 숫자·`요리 2번 중 2번 계산 · 재료 2개 가격 제외 · 참고용이에요` → 네 칸(버린 재료 주황)·먹은 기록 집밥 비율 막대(체험 먹은 기록 집밥 2·외식 1 → 67%)·`지난달보다 요리 1번 더 · 버린 재료는 그대로예요`(체험 35일 전 일기·36일 전 콩나물 기준, 날짜에 따라 다름) → 많이 아낀 요리 막대 → 버린 재료 `애호박` 칩·새 안내 문구 → `‹` 지난달 → 요리 1번 → 더 이전 달 `요리 일기가 없어요` → 돌아와도 보던 달 유지 → 요리 일기 목록 카드 `집밥 리포트 보기`로 이동. 음수 합계는 콘솔로 사 먹으면 1,000원 일기를 만들어 `더 들었어요`·주황 확인. 다크·키보드(지난달 → 다음 달)·스크린리더(`집밥 72%, 외식 28%`, 막대 이름). 스크린샷.
- [ ] **Step 4: 스펙** — 29절 `구현 세부` `화면:`에 리포트(결정 15·21~24), 27절 표 `기록` 행 `집밥 리포트는 5단계 뒤` → `집밥 리포트(5단계 완료)`.
- [ ] **Step 5: 커밋** — `feat: 집밥 리포트 화면(아낀 돈 합계·요리·기록한 날·집밥 비율·버린 재료·지난달 대비·많이 아낀 요리)`

---

### Task 12: 재료 지울 때 이유 시트 (시안 6, 결정 D)

**Files:**
- Modify: `frontend/src/components/IngredientForm.tsx`, `frontend/src/styles.css`, 스펙(27·29절)

**Interfaces:**
- Consumes: 기존 `IngredientForm` `deleting` state·`confirmDelete`·`onDelete(reason)`·`usedUp`, `DeleteReason`, `KIND_LABEL`(`format.ts`), `Ingredient.days_since_purchase`·`location_kind`, `Sheet`, 서버 `DELETE /api/ingredients/<id>?reason=`(바꾸지 않음)
- Produces:
  - `DELETE_REASONS`를 세 줄로: `[{value: "eaten", label: "다 먹었어요"}, {value: "discarded", label: "버렸어요", note: "집밥 리포트에 세요"}, {value: null, label: "그냥 지우기"}]`(타입 `{ value: DeleteReason | null; label: string; note?: string }[]`).
  - 삭제 시트: title `` `${initial.name} 지우기` ``, description `[initial.days_since_purchase !== null && `구입 ${initial.days_since_purchase}일째`, KIND_LABEL[initial.location_kind]].filter(Boolean).join(" · ")`(시안 `구입 9일째 · 냉장` — 재고 목록 `Fridge.tsx`의 `구입 N일째`와 같은 값).
  - 본문 `div.ck-reason role="radiogroup" aria-label="지우는 이유"`: 줄마다 `button.ck-reason-opt role="radio" aria-checked={deleting.reason === value}`(52px, 켜짐 `--accent-tint` 배경 + `--accent` 테두리) 안 `span {label}` + note가 있으면 `small {note}`. 누르면 그 값으로(다시 눌러도 해제하지 않는다 — `그냥 지우기`가 해제). 화살표 키로 옮기기(`onKeyDown` ↑↓, 로빙 tabindex).
  - 시작값: `이 재료 삭제` 버튼 → `{reason: null}`(그냥 지우기), 수량 0 저장 → `{reason: "eaten"}`(기존).
  - 버튼 `div.actions`: `button.btn.outline 취소`(기존 유지) · `button.btn.danger-text {busy ? "지우는 중…" : "지우기"}`(기존 `danger-fill` → 규칙에 맞게 연빨강 배경·테두리).
  - 설명 줄 `왜 지우는지 고르면 이번 달 집밥 리포트에 반영해요. 안 골라도 괜찮아요.`는 시안에 없어 뺀다(`버렸어요` 줄의 `집밥 리포트에 세요`가 대신).
  - `styles.css` `/* 5 · Task 12 */`: `.ck-reason`(grid gap 8px), `.ck-reason-opt`(flex, 최소 52px, 14px 둥글게, `--field`, 16px 600, `[aria-checked="true"]` 켜짐, `small` 오른쪽 12px `--text-3`), 포커스 링은 기존 `:focus-visible`.

- [ ] **Step 0: 브랜치** — 4b-3 Task 12 끝난 main에서 `feature/cooklog-remove-reason-ui`(백엔드 태스크와 무관).
- [ ] **Step 1: 화면 구현 → `npm run check && npm run build`** (순수 로직 없음 — 검사 추가 없음)
- [ ] **Step 2: 브라우저 확인(384×832, 자기 포트 5312)** — 재고 `애호박`(구입 9일 전, 냉장) → 고치기 → `이 재료 삭제` → 시트 `애호박 지우기` / `구입 9일째 · 냉장`(목록의 `구입 N일째`와 같은 숫자) → `그냥 지우기` 켜짐 → `버렸어요`(초록 테두리·`집밥 리포트에 세요`) → `지우기`(연빨강 배경·테두리) → 목록에서 사라짐 → Task 6이 병합된 main이면 리포트 `버린 재료`에 `애호박`(아니면 개발 서버 SQLite에서 `ingredient_removals` 행 `discarded` 확인) → 구입일 모름 재료는 설명 `냉장`만 → 수량 0으로 저장 → 시트가 `다 먹었어요` 켜진 채 → `취소`는 지우지 않음. 다크·키보드(↑↓로 이유 옮기기, Tab이 한 번에 라디오 묶음을 지나감)·스크린리더(`지우는 이유`, `버렸어요, 선택됨`). 스크린샷.
- [ ] **Step 3: 스펙** — 27절 `정리 작업 결정` `재료 삭제 이유` 줄을 `다 먹었어요 · 버렸어요 · 그냥 지우기(기본)`로, 29절 `구현 세부` `화면:`에 결정 25.
- [ ] **Step 4: 커밋** — `feat: 재료 지울 때 이유 시트(다 먹었어요·버렸어요·그냥 지우기, 기본 그냥 지우기)`

---

### Task 13: 먹은 기록 달력 `요` 표시·날짜 상세 요리 일기 줄

**Files:**
- Modify: `frontend/src/foodlog/log.ts`, `frontend/scripts/check-foodlog.mjs`, `frontend/src/pages/FoodLog.tsx`, `frontend/src/components/FoodLogDaySheet.tsx`, `frontend/src/styles.css`(4b-3 묶음 끝), 스펙(24·29절)

**Interfaces:**
- Consumes: Task 6 한 달 `days[].cooked`·날짜 `cook_logs`, Task 8 타입(`FoodLogMonthDay.cooked`·`FoodLogDay.cook_logs`), Task 10 `openCookLog`, 4b-3 `cellLabel`·`FoodLog.tsx` 칸 그리기·`FoodLogDaySheet`·`.fl-plan`·`.nt-link`, `navigate`
- Produces:
  - `log.ts` `cellLabel`: 기록 있는 날 목록 끝에 `day.cooked && "요리 일기 있음"`(요리 일기만 있는 날은 `끼니 0개`를 빼고 `…, 요리 일기 있음`). 바뀐 식:
    ```ts
    export function cellLabel(date: string, day: FoodLogMonthDay | undefined, today: string): string {
      const base = slotDateText(date, today);
      if (!day) return `${base}, 기록 없음`;
      return [base, day.meals > 0 && `끼니 ${day.meals}개`, day.kcal != null && `${cellKcalText(day)}kcal`, day.photo_url && "사진 있음", day.cooked && "요리 일기 있음"].filter(Boolean).join(", ");
    }
    ```
    검사 추가: 4b-3 기존 `cellLabel` 기대값은 칸에 `cooked: false`를 넣어 그대로; `cellLabel("2026-09-14", {…meals 2…, cooked: true}, "2026-09-15")` 끝 `, 요리 일기 있음`; `{meals: 0, count: 0, kcal: null, approx: false, photo_url: null, cooked: true}` → `"9월 14일 월요일, 요리 일기 있음"`. `summaryView` note의 `기록한 날 기준이에요`는 그대로.
  - `FoodLog.tsx` 칸: `day?.cooked`이면 칸 안 오른쪽 위 `span.fl-cook aria-hidden="true"` `요`. 요리만 있는 날(`meals 0`, 사진 없음)은 점 자리를 비운다(`span.fl-dots` 안 `i` 0개). 범례 `p.fl-legend`를 `● 끼니 기록 · 사진 = 첫 사진 · 요 = 요리 일기 있음`으로.
  - `FoodLogDaySheet`: 시트 설명 아래·끼니 목록 위에 `day.data.cook_logs`마다 `div.fl-plan.fl-cookrow`: `Icon pan` + `span 요리 일기 <b>{title}</b>` + `button.nt-link 보기`(`aria-label="요리 일기 {김치찌개} 보기"`) → `openCookLog(id)` → `onClose()` → `navigate("/cook-logs")`.
  - `styles.css` 4b-3 묶음 끝 `/* 5 · Task 13 */`: `.fl-cook`(absolute 위 2px 오른쪽 3px, 14px 원, `--warn-tint` 배경 `--warn` 글자 9px 700 — 시안 `.cook`), `.fl-cell { position: relative; }`가 없으면 더한다, `.fl-cookrow`(아래 여백 8px).

- [ ] **Step 0: 브랜치** — main(Task 6·10 병합)에서 `feature/cooklog-calendar-ui`.
- [ ] **Step 1: 실패하는 검사** — `check-foodlog.mjs`에 위 기대값 → 실패 확인 → `log.ts` 바꿈 → 통과(4b-3 기존 기대값 그대로 통과).
- [ ] **Step 2: 화면 구현 → `npm run check && npm run build`**
- [ ] **Step 3: 브라우저 확인(384×832, 자기 포트 5313)** — 요리 일기(사진 있음)만 남긴 어제, 먹은 기록 + 요리 일기가 있는 그제, 먹은 기록만 있는 날 → 달력: 어제 칸 요리 사진 썸네일 + `요`, 그제 칸 점·kcal + `요`(먹은 기록 사진이 있으면 그 사진), 먹은 기록만 있는 날 `요` 없음 → 범례 → 요약 `기록한 날`이 요리만 있는 날까지 셈 → 어제 칸 → 날짜 상세 맨 위 `요리 일기 김치찌개 · 보기` → 누르면 `#/cook-logs`에서 그 일기 상세가 열림 → 뒤로가기로 먹은 기록 달력(보던 달 그대로). 384px에서 `요`가 날짜 원·썸네일과 겹치지 않는지, 다크 모드, 스크린리더 칸 이름 끝 `요리 일기 있음`. 스크린샷.
- [ ] **Step 4: 스펙** — 24절 `요리 기록 자동 표시`·`2026-09-15 화면·결정`에 `요 표시·날짜 상세 요리 일기 줄(29절 결정 27)`, 29절 `구현 세부` `화면:`에 결정 27.
- [ ] **Step 5: 커밋** — `feat: 먹은 기록 달력에 요리한 날 요 표시와 날짜 상세 요리 일기 줄`

---

### Task 14: 전체 검사·실제 키 추정·체험 계정·폰 확인·배포 준비

**Files:**
- Modify: 필요할 때만(발견한 문제를 고친 파일), `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 2절 표(5단계 행에 `요리 일기·집밥 리포트 완료(2026-09-xx)`)

- [ ] **Step 1: 전체 검사** — 백엔드 SQLite·PostgreSQL(에이전트 전용 DB) 전체 실패·경고 0, `cd frontend && npm run check && npm run build`, 스크래치 DB에서 `flask db upgrade`·`flask db check` 차이 없음, head 하나(`h2c2o2o2k2l2`). 바뀐 파일에 `TODO`·`test.skip`·`.only`·빈 분기가 없는지 `git diff main~N --stat`과 `grep -rn "TODO\|\.only(\|skip(" backend/app backend/tests frontend/src frontend/scripts`로 확인.
- [ ] **Step 2: 실제 키로 로컬 확인(사용자가 `./dev.sh`를 다시 켠 공용 개발 서버, 에이전트는 켜고 끄지 않음)** — 레시피 세 개(`김치찌개`·`부대찌개`·`까르보나라`)에서 요리했어요 → 사 먹으면 얼마 추정이 1,000~100,000원 안의 그럴듯한 값인지, 두 번째 열 때 AI를 다시 부르지 않는지(`ai_calls` `eat_out` 한 줄씩), 더보기 AI 사용량 `AI 레시피`가 늘었는지. 서버 로그에 키·사진 키가 없는지. 값이 이상하면 프롬프트를 사용자에게 보여주고 고친다.
- [ ] **Step 3: 체험 계정 확인** — `DEMO_LOGIN=1` 개발 서버에서 체험하기 → 요리 일기 3개·계산표 → 집밥 리포트(버린 재료 `애호박`) → 레시피 `김치찌개` 요리했어요(예시 재고 가격으로 계산) → 되돌리기 → 사진 올리기(체험 20MB) → 내보내기 zip `cook_logs.csv` → `flask purge-demo-users`가 일기 사진 파일까지 지우는지(만료 시각을 바꾼 계정으로).
- [ ] **Step 4: 사용자 폰 확인(갤럭시 S22 Ultra, `http://<맥 IP>:5180`)** — 요리했어요 시트 스크롤·숫자 키패드(쓴 양 decimal, 사 먹으면 numeric)·키보드가 저장 버튼·메모를 가리지 않는지, 사진 버튼이 카메라·앨범을 고르게 하는지·큰 사진이 줄어 올라가는지, 알림 10초·되돌리기 터치·알림이 탭 바·`요리했어요`를 가리지 않는지, 식단 칸 `요리했어요`, 요리 일기 무한 스크롤, 계산표 줄 넘침(`돼지고기 앞다리살 0.15kg / 0.6kg 9,800원`), 리포트 네 칸 숫자 넘침(`123번`·`31일`), 달력 `요`, 재료 지우기 이유 라디오 터치, 다크 모드. **사용자에게 확인 목록을 보여주고 결과를 받는다**(문제는 고친 뒤 다시 확인). 결정 24(버린 재료 문구)·결정 28(요리했어요 자리)·결정 12(KAMIS·참가격 미룸)도 이때 확인받는다.
- [ ] **Step 5: 배포 여부 확인** — 사용자가 고르면 `git push origin main`(마이그레이션 두 개는 시작 명령의 `flask db upgrade`) → 운영 R2에서 일기 사진 올리기·보기·지우기 → 체험 계정으로 운영 주소에서 한 바퀴. 심사 기간이면 사용자가 정한 때까지 미룬다.
- [ ] **Step 6: 메모리·스펙** — 2절 표 표시, 메모리 `recipe-ai-post-deploy-roadmap`의 다음 단계를 `리포트`(해커톤 제출 리포트)로, `recipe-ai-carryover`에 남은 것(KAMIS·참가격 조건 확인, 회원 탈퇴 API에 `cooklog/` 접두사, 되돌리기 뒤 같은 이름 재료 두 줄 가능성, 재고 고치기 잠금 없음).
- [ ] **Step 7: 커밋** — `docs: 5단계 요리 일기·집밥 리포트 완료 표시`

---

## 자체 점검 (스펙 대조, 계획 작성 시)

| 스펙 요구 | 태스크 |
|---|---|
| 29절 요리했어요 시트: 레시피 상세·식단 칸 상세(`먹었어요` 옆)에서 열기, 식단 칸이면 요리·인분·날짜 | 8·9(자리는 결정 28, 공공 레시피는 결정 2) |
| 29절 인분 −/+ → 23절 D2 기본 양(배율, 단위 다르면 1, 양념 필수품 체크 해제), 행마다 체크·양 수정, 재고 양 보조 줄 | 1(`in_unit`)·2(`draft_rows`·`is_seasoning`)·8 |
| 29절 언제 칩 `오늘 · 어제 · 날짜 고르기`, 사 먹으면 얼마(1인분), 별점, 사진, 메모, `먹은 기록에도 남기기`(기본 켜짐, source cook_log·place home) | 4(서버)·8(화면), 결정 16·19 |
| 29절 `저장하고 재고에서 빼기` = 7절 트랜잭션(소유 확인·차감·0 이하 삭제·사진 실패 롤백) | 4, 결정 6·9·19 |
| 결정 A 사 먹으면 얼마: 사용자 값 → AI 추정 한 번(레시피에 저장, recipe 한도 묶음, `추정`), 폼에서 고치면 레시피에 저장, 참가격은 조건 확인 뒤 | 1·3·4·8, 결정 11·12 |
| 결정 B 저장 후 알림 `재고에서 …를 뺐어요 · 약 N원 아꼈어요` + 10초 되돌리기(재고 수량·삭제된 재료 복구 + 일기·먹은 기록 삭제), 그 뒤 지우기는 재고 안 되돌림 + 안내 | 4(undo)·8(알림)·5·10(지우기·안내), 결정 7·8·17 |
| 29절 요리 일기 목록: 더보기 > 기록 > 요리 일기, 날짜 역순 커서 무한 스크롤, 위 `9월 요리 N번 · 약 N원 아꼈어요`(누르면 리포트), 행 사진·제목·별점·날짜·인분·아낀 돈 또는 `재료 N개 가격 모름`·메모 첫 줄 | 5·6(카드 값)·10·11(카드 버튼), 결정 20 |
| 29절 일기 상세: 사진·별점·메모, 계산표(사 먹으면 × 인분, 재료별 `쓴 양 / 구입 양 구입 가격`, 합계), 가격 모름·양념 뺐다고 적기, `고치기`·`일기 지우기`(삭제 버튼 규칙) | 4(스냅숏)·5·10, 결정 13·18 |
| 29절 집밥 리포트: 좌우 달 이동, 합계(`요리 N번 중 M번 계산 · 재료 K개 가격 제외`), 요리 횟수·기록한 날·집밥 비율·버린 재료 수, 지난달 대비, 많이 아낀 요리 3개 막대, 버린 재료 칩 | 6·11, 결정 14·21~24 |
| 결정 D 재고 삭제 시트 `다 먹었어요 · 버렸어요 · 그냥 지우기`(기본 그냥), 리포트는 버렸어요만, 요리 차감으로 0 → 다 먹었어요 | 12(화면)·4(차감 기록)·6(세기), 결정 25 |
| 29절·24절 먹은 기록 달력 요리한 날 `요`, 요리 기록 합쳐 보이기 | 6·13, 결정 27 |
| 27절 아낀 돈 계산: 재료비 = 구입 가격 × 사용량 비율, 가격 없으면 제외 + `재료 N개 가격 제외`, 양념 기본 제외, KAMIS 추정 | 1(`price_quantity`)·2·4, KAMIS는 결정 12(미룸) |
| 27절 아낀 돈 0 이하도 그대로·합계에 음수 반영·참고용 표시 | 2·6·10·11, 결정 15, Global Constraints 참고용 문구 |
| 27절 가격 수집(영수증·주문 스캔 가격, 폼 가격 칸) | 이미 있음 — 1이 구입 수량만 더함 |
| 27절 데이터 내보내기에 요리 기록 CSV | 7·10(시트 줄), 결정 29 |
| 4절 `cook_logs` 모델 | 4(칸 확장, 결정 1) |
| 5절 API 표 `GET/POST /api/cook-logs`·`DELETE /api/cook-logs/<id>`(재고 복원 안 함) | 4·5 |
| 6절 6·7번 요리했어요 폼·기록 탭(날짜 역순, 썸네일·제목·별점·메모) | 8·10 |
| 7절 AI 일일 한도 kind 묶음 | 3(`eat_out` → recipe) |
| 9절 체험 계정 예시 데이터·AI 한도·사진 정리 | 3(예산)·4(`user_photo_keys`)·7(예시) |
| 23절 D2 차감 결과 0 이하면 삭제 | 4, 결정 6 |
| 26절 앞으로(조리 기록) 서버 커서 페이지 + 무한 스크롤·접근성 대안 | 5·10(`InfiniteSentinel`) |
| 27절 회원 탈퇴 사진 접두사 | 4(스펙 줄·`user_photo_keys`), 탈퇴 API는 범위 밖(4b-3 결정 17과 같음) |

빈틈으로 남긴 것(사용자 확인): 결정 12(KAMIS·참가격 미룸), 24(버린 재료 카드 문구 바꿈), 28(요리했어요 버튼 자리), 2(공공 레시피 상세에는 요리했어요 없음), 17(일기를 지워도 먹은 기록은 남김).
