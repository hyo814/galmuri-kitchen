# 4단계(장보기 · 오프라인 매장 장보기) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `장보기` 탭에서 살 것을 `오늘 · 이번 주 · 날짜 미정`으로 묶어 보고, 레시피의 없는 재료·떨어진 필수품·빨리 먹어야 할 재료를 한 번에 담는다. 항목마다 쇼핑몰 검색 결과(`낮은 가격순 · 많이 산 순 · 새 상품순`)로 바로 간다. 마트 지하처럼 인터넷이 없어도 목록·메모·사진을 열어 체크하고, 연결되면 알아서 저장된다. 메모 사진은 AI가 살 것 목록으로 바꿔 준다. 체크한 것은 `체크한 N개를 재고에 넣을까요?` → `재고에 넣기` 한 화면에서 산 날·보관 위치를 정해 재고로 옮기고, 옮긴 것은 목록 맨 아래 `산 것 N개`에 접혀 남는다.

**Architecture:** 서버는 장보기 한 묶음(`/api/shopping*`, 새 파일 `shopping.py`)으로 두고, 오프라인을 위해 **목록·산 것·메모 전체를 한 번에 주는 스냅숏 GET**과 **다시 보내도 두 번 생기지 않는 쓰기**(`client_id` UNIQUE, 체크는 `done_changed_at` 마지막 변경 우선, 메모는 `edited_at` 비교 후 409)를 제공한다. 재고에 넣기는 기존 `ingredients.parse_fields`·2000개 상한을 그대로 써서 재료 생성과 장보기 항목 `stocked_at` 기록을 한 트랜잭션에 한다(산 것은 7일 보이고 스냅숏 요청 때 지운다). 사진은 새 `storage.py`(R2 환경변수가 있으면 R2, 없으면 `backend/uploads/`, 스펙 3절)와 `/api/photos/<key>`(소유자 확인). 메모 사진 인식은 `scan.py`에 `memo` kind만 더한다(한도 묶음·`ai_calls.kind`는 이미 `memo` 포함). 화면 쪽 오프라인은 **순수 로직 모듈**(`shopping/sync.ts`: 대기열 합치기, 스냅숏 위에 대기 변경 얹기, 날짜 묶음, 응답 분류, 수량 글자 해석)을 node 검사 스크립트로 먼저 고정하고, 그 위에 IndexedDB 얇은 래퍼·`useShopping` 훅·서비스 워커 정적 파일 캐시를 얹는다. 동기화는 Background Sync가 아니라 **화면 안에서**(`online` 이벤트·앱 열 때·변경 직후) 순서대로 보낸다. 쇼핑몰 링크는 서버를 거치지 않고 화면 모듈 `storeLinks.ts` 한 곳에서 만든다(표 하나, 제휴 ID는 `/api/me`로 받음, 마지막으로 연 쇼핑몰은 localStorage).

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, anthropic 1.5.0, boto3(신규, 스펙 3절에 이미 적힌 R2 클라이언트), pytest 9.1.1 / React 19 + TypeScript + Vite 8, Node 24(`.ts` 직접 실행 검사 스크립트), IndexedDB·Service Worker(브라우저 기본 기능, 라이브러리 없음), `@fontsource/ibm-plex-sans-kr`(신규, 글꼴 파일 자체 호스팅 — Task 7 근거)

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 2절(4단계), 3절(사진 저장·운영 R2 없으면 503), 4절(`ai_calls.kind` memo), 5절(`/api/scan`, `/api/photos`), 7절(AI 일일 한도 scan 묶음), 8절(업로드 10MB·파일 서명), 12절(PWA는 HTTPS), 13절(주문·장바구니 API 없음), **16절(장보기 — 2026-09-14 시안 승인 결정 포함)**, **19절(오프라인 매장 장보기 — 같음)**, **23절 D3(체크와 재고 등록 분리)**, 25절(제휴 링크·`광고` 표시·순서는 수수료와 무관), 26절(장보기는 페이지 없이 300개 상한 — 예외), 27절(회원 탈퇴 때 사진 파일 삭제). **디자인: `docs/design/shopping-4/*.dc.html` + `canvas.json`(사용자 승인 2026-09-14).** 화면 태스크는 프레임 문구·배치·버튼을 그대로 따른다.

시안 프레임(`canvas.json` 순서): 1 `ShoppingList` · 1-오프라인 `ShoppingOffline` · 1-다크 `ShoppingDark` · 2 `AddSheet` · 3 `StoreSheet` · 4 `RecipeEntry` · 5 `MemoPage` · 6 `StockIn`.

## Global Constraints

- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다. 태스크 작업은 git worktree에서 한다(다른 세션 `recipe-ai-ce`가 같은 저장소를 쓴다).
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. SQLite와 PostgreSQL(`TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate`, 이미 설정됨) 둘 다 실패 0, 경고 0.
- 프론트 태스크는 `cd frontend && npm run check && npm run build`가 오류 없이 끝나야 한다. `npm run check`는 `frontend/scripts/check-*.mjs`를 모두 돌린다(Task 5에서 `"check": "node scripts/check-seasoning.mjs && node scripts/check-store-links.mjs"`, Task 6에서 `&& node scripts/check-shopping-sync.mjs`를 붙인다). **테스트 러너(vitest 등)를 새로 들이지 않는다** — 오프라인 로직은 브라우저 API 없이 돌도록 순수 모듈로 떼어 node 스크립트로 검사하고, IndexedDB·서비스 워커 연결부는 얇게 두어 폰·데스크톱 크롬 오프라인 수동 확인으로 본다(`fake-indexeddb` 같은 의존성을 넣을 만큼 로직이 없게 만든다).
- **테스트는 절대 네트워크를 부르지 않는다.** 기존 `conftest.py` 차단 픽스처 그대로. `app.ai.extract`와 R2 클라이언트(`app.storage._r2_client`)는 `monkeypatch`로 바꾼다. 쇼핑몰 URL은 테스트에서 열지 않는다.
- API 키·R2 비밀값은 `backend/.env`에만 둔다. **`.env`는 읽거나 커밋하지 않는다.** 예외는 로그에 `type(e).__name__`만.
- `DEV_MODE=1`이고 `ANTHROPIC_API_KEY`가 없으면 `kind=memo` 스캔은 예시 결과(`sample: true`, 한도·기록 없음). R2가 없으면 개발에서는 `backend/uploads/`(gitignore에 `uploads/` 있음), **운영(`RENDER`)에서 R2가 없으면 사진 올리기는 503**(Render 디스크는 배포 때 지워진다).
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정하고 남의 것은 404. 상태 변경은 `X-Requested-With: fetch`(기존 전역 검사).
- 모바일 384px 기준(갤럭시 S22 Ultra). 터치 영역 44px 이상, 입력 글자 16px 이상. 아이콘은 이모지 대신 `Icon`. 라이트·다크 모두 확인(`ShoppingDark`).
- **삭제 버튼은 연빨강 배경 + 테두리(`.btn.danger-text`)로 보이게, 다른 버튼 아래에 둔다(`MemoPage`의 `메모 삭제`).** 시안을 고칠 때도 이미 승인된 이 규칙을 지킨다.
- 화면 문구는 시안 그대로, 시안에 없는 새 문구는 보조 용언을 붙여 쓴다(`보여줘요`, `저장돼요`, `입력해주세요`). 개발 용어(동기화, 대기열, 캐시, 스냅숏, IndexedDB, 서비스 워커, 409, 제휴)는 화면에 쓰지 않는다.
- 시안의 `sh-*`·`mo-*` 클래스 스타일은 `docs/design/shopping-4/*.dc.html`의 `<style>`에서 `frontend/src/styles.css`로 옮기되, 이미 있는 토큰·클래스(`rc-sec`, `btn`, `icon-btn`, `field`, `actions`, `cta-bar`, `back-link`)는 새로 만들지 않는다.
- 앱 안에 가격을 보여주지 않는다(네이버 쇼핑 검색 API 2026-07-31 종료, 공식 대체 없음). **가격·상품 스크래핑 금지.** 네이버 키를 추가하지 않는다.
- 제휴 ID는 환경변수(`COUPANG_PARTNERS_ID` 등)로만, 제휴가 붙은 쇼핑몰 이름 옆에만 `광고` 표시, 쇼핑몰 순서는 제휴 여부와 무관(마지막으로 연 쇼핑몰만 맨 위, 나머지는 고정 순서).
- 개발 서버는 Vite 5180, Flask 5181. 5173은 건드리지 않는다. 개발 DB는 지우지 않는다. **서브에이전트는 `pkill`/`killall`을 쓰지 않고 공용 개발 서버를 끄거나 다시 켜지 않는다. 직접 띄운 프로세스만 PID로 끈다.**
- 서비스 워커·앱 모드는 HTTPS(또는 `localhost`)에서만 동작한다. 폰 확인은 USB 디버깅 + `adb reverse tcp:5180 tcp:5180` 후 폰에서 `http://localhost:5180`(보안 컨텍스트)로 하거나 Render 배포 뒤에 한다. LAN IP로는 서비스 워커가 등록되지 않는다.
- 마이그레이션 id·down_revision은 **구현 시점에 `ls backend/migrations/versions`와 `flask db heads`로 다시 확인**한다(지금 head `b3b3c3d3e3f3`). 다른 세션이 붙인 게 있으면 그 뒤로 붙이고 id가 겹치지 않게 바꾼다. head는 하나여야 한다.
- 브랜치는 태스크마다 하나, 리뷰(백엔드: 코드·보안·테스트 / 화면: 코드·UX·접근성 / 오프라인: 테스트 설계) 통과 후 main에 `--no-ff` 병합.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음 한 줄만 붙인다:
  ```
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치

| 브랜치 | 태스크 | 시작 시점 | 시안 |
|---|---|---|---|
| `feature/shopping-items-backend` | 1 (장보기 항목 테이블·스냅숏·추가·일괄 담기·체크·고치기·삭제, 산 것 7일) | main에서 바로 | **UI 시안 승인 전 진행 가능** |
| `feature/shopping-stock-backend` | 2 (재고에 넣기 초안·일괄 등록, 영수증 결과로 산 항목 찾기·산 것으로 옮기기) | 1 병합 뒤 | **UI 시안 승인 전 진행 가능** |
| `feature/shopping-notes-backend` | 3 (사진 저장소 `storage.py`, 메모·사진 테이블·API, `/api/photos`) | 1 병합 뒤(2와 병렬 가능) | **UI 시안 승인 전 진행 가능** |
| `feature/scan-memo` | 4 (`/api/scan?kind=memo`) | main에서 바로(1~3과 파일 안 겹침) | **UI 시안 승인 전 진행 가능** |
| `feature/store-links` | 5 (쇼핑몰 링크 표·만드는 함수·검사 스크립트, `/api/me` 제휴 ID) | main에서 바로 | **UI 시안 승인 전 진행 가능** |
| `feature/shopping-sync-core` | 6 (오프라인 순수 로직 + 검사 스크립트) | main에서 바로 | **UI 시안 승인 전 진행 가능** |
| `feature/shopping-offline-shell` | 7 (서비스 워커 정적 파일 캐시, 글꼴 자체 호스팅, IndexedDB 래퍼, `useShopping`, 오프라인으로 앱 열기) | 1·3·6 병합 뒤 | **UI 시안 승인 전 진행 가능**(화면 문구 없는 부분만) |
| `feature/shopping-list-ui` | 8 (장보기 탭 목록·제자리 체크·재고에 넣기 막대·살 것 추가/고치기 시트·오프라인 띠·산 것 접기) | 7 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |
| `feature/shopping-links-ui` | 9 (쇼핑몰에서 찾기 시트 + **사용자 폰 URL 검증**) | 5·8 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |
| `feature/shopping-notes-ui` | 10 (메모 카드·장보기 메모 화면·사진) | 8 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |
| `feature/shopping-memo-scan-ui` | 11 (사진에서 살 것 뽑기 → 확인 → 담기) | 4·10 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |
| `feature/shopping-stock-ui` | 12 (재고에 넣기 화면, 영수증 스캔 뒤 장보기에서 빼기 제안) | 2·8 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |
| `feature/shopping-entry-points` | 13 (레시피 없는 재료·떨어진 필수품·재료 고치기에서 담기) | 8 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |

## 파일 구조

```
backend/
  requirements.txt                                   (수정, T3) boto3
  app/__init__.py                                    (수정, T1·T3·T5) 블루프린트, UPLOAD_DIR·R2_*·COUPANG_PARTNERS_ID
  app/models.py                                      (수정, T1·T3) ShoppingItem, ShoppingNote, ShoppingNotePhoto
  migrations/versions/b4b4c4d4e4f4_shopping_items.py (신규, T1) down_revision b3b3c3d3e3f3
  migrations/versions/b5b5c5d5e5f5_shopping_notes.py (신규, T3) down_revision b4b4c4d4e4f4
  app/shopping.py                                    (신규, T1·T2·T3) /api/shopping*, 메모·사진
  app/storage.py                                     (신규, T3) put/delete/photo_response (R2 | 로컬 uploads)
  app/photos.py                                      (신규, T3) GET /api/photos/<path:key>
  app/scan.py, app/ai.py                             (수정, T4) memo kind·프롬프트·예시
  app/auth.py                                        (수정, T5) user_json에 shop_affiliates
  tests/test_shopping.py                             (신규, T1·T2), tests/test_shopping_notes.py (신규, T3)
  tests/test_storage.py                              (신규, T3), tests/test_scan.py·test_auth.py·test_migrations.py·test_locations.py (수정)
docs/superpowers/specs/2026-09-13-recipe-ai-design.md (수정, T1~T5) §28 장보기 구현 세부, 5절 API 표
docs/deploy.md                                       (수정, T3·T7) R2 CORS·버킷, adb reverse 폰 확인
frontend/
  package.json                                       (수정, T5·T6·T7) check 스크립트, @fontsource/ibm-plex-sans-kr
  index.html                                         (수정, T7) Google Fonts 링크 제거
  public/sw.js                                       (수정, T7) /assets 캐시
  scripts/check-store-links.mjs                      (신규, T5), scripts/check-shopping-sync.mjs (신규, T6)
  src/storeLinks.ts                                  (신규, T5) 쇼핑몰 URL 표 + storeLinks()
  src/shopping/sync.ts                               (신규, T6) 순수 로직
  src/shopping/idb.ts                                (신규, T7) IndexedDB 래퍼(kv·blobs)
  src/shopping/useShopping.ts                        (신규, T7) 스냅숏·대기열·보내기, addMany(T13)
  src/main.tsx, src/App.tsx                          (수정, T7) 글꼴 import, 오프라인으로 앱 열기, 로그아웃 시 기기 데이터 지우기
  src/api.ts                                         (수정, T1~T7) ShoppingItem, ShoppingNote, ScanKind memo, User.shop_affiliates
  src/pages/Shopping.tsx                             (신규, T8) 장보기 탭
  src/components/ShoppingItemSheet.tsx               (신규, T8) 살 것 추가·고치기
  src/components/StoreLinksSheet.tsx                 (신규, T9)
  src/pages/ShoppingMemo.tsx                         (신규, T10) #/shopping/memo, #/shopping/memos
  src/components/MemoScanReview.tsx                  (신규, T11) (ScanSheet 촬영·축소·오류 처리 재사용)
  src/pages/ShoppingStock.tsx                        (신규, T12) #/shopping/stock
  src/pages/RecipeDetail.tsx, pages/RecipeAi.tsx, components/StaplesSheet.tsx, components/IngredientForm.tsx,
  components/ScanSheet.tsx, components/ScanReview.tsx, pages/ComingSoon.tsx, useHashRoute.ts, styles.css, components/Icon.tsx (수정, T8~T13)
```

---

### Task 1: 장보기 항목 백엔드 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `backend/app/shopping.py`, `backend/migrations/versions/b4b4c4d4e4f4_shopping_items.py`, `backend/tests/test_shopping.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`, `backend/tests/test_migrations.py`, `backend/tests/test_locations.py`, 스펙(§28 신설 + 5절 표)

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`(auth), `text`, `iso_date`, `iso_datetime`(validation), `owned_location`/`user_locations`(locations), `names_match`(matching), `utcnow`
- Produces:
  - `app.models.ShoppingItem`(`shopping_items`, 스펙 16절): id, user_id FK users CASCADE NOT NULL index, client_id String(36) NULL, name String(50), quantity Float NOT NULL default 1, unit String(10) NOT NULL default `개`, planned_on Date NULL, **location_id FK storage_locations `ondelete="SET NULL"` NULL index**, source String(10) NOT NULL default `manual`(`manual|recipe|staple|urgent|meal_plan|memo`), source_label String(60) NULL(레시피 이름 — 시안 태그 `레시피 · 두부조림`), done_at DateTime(tz) NULL, done_changed_at DateTime(tz) NULL, stocked_at DateTime(tz) NULL, created_at. UNIQUE(user_id, client_id)(NULL은 서로 겹치지 않음 — SQLite·PostgreSQL 같음). **`store` 칸은 두지 않는다**(시안에 항목별 쇼핑몰이 없고, 마지막으로 연 쇼핑몰은 기기에 기억 — 스펙 16절).
  - Alembic `b4b4c4d4e4f4`, down_revision `b3b3c3d3e3f3`(구현 시 재확인).
  - 상수: `MAX_SHOPPING_ITEMS = 300`(사용자당, **산 것(stocked_at 있음) 제외**), `BULK_MAX = 50`, `SOURCES`, `STOCKED_KEEP_DAYS = 7`.
  - `item_json(item)` → `{id, client_id, name, quantity, unit, planned_on, location_id, location_name, source, source_label, done_at, done_changed_at, stocked_at, created_at}`.
  - API(로그인):
    - `GET /api/shopping` → `{items:[...], stocked:[...], notes:[], today}` — **페이지 없음**(오프라인 스냅숏 한 번에, 26절 예외). 먼저 이 사용자의 `stocked_at`이 7일 지난 행을 지운다(`ponytail:` 요청 때 지움, 크론 없음). `items`는 stocked_at NULL, created_at·id 오름차순(묶음은 화면 순수 함수). `stocked`는 최근 7일, stocked_at 내림차순(`산 것 N개`). `notes`는 Task 3에서 채운다.
    - `POST /api/shopping/items` `{name, quantity?, unit?, planned_on?, location_id?, source?, source_label?, client_id?}` → 201. 같은 `client_id`가 이미 있으면 **그 항목을 200**으로(다시 보내도 하나). 검증 문구: 이름 `이름은 1~50자로 입력해주세요.`(기존 `text`), 수량 `수량은 0보다 커야 해요.`, 단위 10자, 날짜 `날짜 형식이 올바르지 않아요.`, source 목록 밖 `잘못된 요청이에요.`, source_label 60자, 남의/없는 위치 기존 문구, client_id는 1~36자 `[A-Za-z0-9-]`만. 300개 → 400 `장보기 목록은 300개까지 담을 수 있어요. 필요 없는 항목을 빼주세요.`
    - `POST /api/shopping/items/bulk` `{source, source_label?, items:[{name, quantity?, unit?, planned_on?, location_id?}] 1~50}` → 201 `{created:[...], skipped:["대파"]}`. **목록에 있는(stocked_at NULL) 항목과 `names_match`되는 이름, 요청 안에서 겹치는 이름은 건너뛴다**(시안 `RecipeEntry` 한 번에 담기). 하나라도 틀리면 아무것도 만들지 않고 400 `{error: "N번째 재료: …", errors}`(재고 bulk와 같은 모양). 상한은 만들 개수로 센다.
    - `PATCH /api/shopping/items/<id>` — 두 가지 모양:
      - 고치기 `{name?, quantity?, unit?, planned_on?, location_id?}`(planned_on·location_id는 null로 비우기 가능) → 200. 도착 순서대로 덮어쓴다.
      - 체크 `{done: bool, changed_at: ISO datetime}` → `changed_at < done_changed_at`이면 **바꾸지 않고** 현재 항목 200(늦게 도착한 옛 체크). 아니면 `done_at = done ? changed_at : null`, `done_changed_at = changed_at`. changed_at이 서버 시각보다 10분 넘게 미래면 서버 시각으로 자른다. `ponytail:` 기기 시계 차이만큼 틀릴 수 있음(한 사용자·기기 몇 대라 허용) — 문제되면 서버 수신 순서로 바꾼다.
      - 두 모양을 섞으면 400 `잘못된 요청이에요.`
    - `DELETE /api/shopping/items/<id>` → 204, 남의 것·없는 것 404.
  - 보관 위치 삭제: `locations.delete_location`은 그대로(재료만 막음), 장보기 항목의 `location_id`는 DB가 NULL로 바꾼다.

- [ ] **Step 0: 브랜치·head 확인** — worktree에서 main 기준 `feature/shopping-items-backend`. `ls backend/migrations/versions`, `flask db heads`.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_shopping_items_migration_adds_and_removes_table`(컬럼·UNIQUE(user_id, client_id)·location FK ondelete SET NULL 확인 후 downgrade).
  - `test_shopping.py`
    - `test_requires_login_and_csrf`(GET 401, POST 헤더 없음 400).
    - `test_snapshot_splits_items_and_recent_stocked_and_purges_old` — 목록 항목 created 순, 3일 전 산 것은 `stocked`, 8일 전 산 것은 응답에 없고 행도 지워짐. 남의 항목 안 보임.
    - `test_create_defaults_and_validation` parametrize(이름 없음/51자, 수량 0·`True`·`"1"`, source `ai`, source_label 61자, 날짜 `2026/09/14`, 남의 location_id, client_id 37자·공백).
    - `test_create_same_client_id_returns_existing_200`(두 번째도 1개, 다른 사용자의 같은 client_id는 따로 생김).
    - `test_cap_300_excludes_stocked`(목록 299개 + 산 것 5개 `add_all` → API 1개 201, 다음 400; bulk 2개 → 400 아무것도 안 생김).
    - `test_bulk_skips_listed_duplicates_and_in_request_duplicates`(`대파` 목록에 있음(체크했어도) → skipped, 산 것 `두부`는 다시 담김, 요청 안 `양파`·`양파` → 하나, source_label 저장).
    - `test_bulk_all_or_nothing_with_index_errors`.
    - `test_check_last_change_wins` — `changed_at` T2로 체크 → T1(더 이른) 해제 요청은 무시(done_at 그대로) → T3 해제는 반영. 미래 1시간 → 서버 시각으로 잘림.
    - `test_patch_edit_and_clear_nullable_fields`, `test_patch_mixed_shapes_400`.
    - `test_delete_and_other_users_item_404`(PATCH·DELETE).
    - `test_user_delete_cascades`.
  - `test_locations.py`: `test_deleting_location_nulls_shopping_item_location`(재료 없는 위치 삭제 204 → 항목 location_id NULL).
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 개발 DB `flask db upgrade` 후 `flask db check` 차이 없음.
- [ ] **Step 3: 스펙** — §28 `4단계 구현 세부`에 API·상한·체크 규칙. 5절 표에 `/api/shopping*` 행.
- [ ] **Step 4: 커밋** — `git add backend docs && git commit -m "feat: 장보기 항목 API(한 번에 받기·담기·일괄 담기 중복 건너뛰기·체크 마지막 변경 우선·산 것 7일, 사용자당 300개)" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

### Task 2: 재고에 넣기 백엔드 (UI 시안 승인 전 진행 가능)

**Files:**
- Modify: `backend/app/shopping.py`, `backend/app/ingredients.py`(재사용할 부분만 공개 이름으로, 동작 그대로), `backend/tests/test_shopping.py`, 스펙 §28

**Interfaces:**
- Consumes: `ingredients.parse_fields(data, creating=True, locations=...)`, `ingredients._check_ingredient_cap`(→ `check_ingredient_cap`으로 이름만 바꾸고 기존 호출부 수정), `locations.default_location`, `matching.normalize`·`names_match`
- Produces:
  - `GET /api/shopping/stock-draft` → `{purchased_on: 오늘(서울), items:[{id, name, quantity, unit, location_id, location_reason}]}` — **체크했고(done_at 있음) 아직 안 넣은(stocked_at NULL) 항목만**, 목록 순서. 위치 프리필(23절 D3): 항목의 `location_id`(`item`) → 같은 이름(`normalize` 같음)의 가장 최근 `created_at` 재료의 위치(`same_name`, 시안 `같은 이름 재료가 있던 곳`) → `default_location`(`default`).
  - `POST /api/shopping/items/stock` `{purchased_on, items:[{id, name, quantity, unit, location_id}] 1~50}` → 201 `{created: N}`. 시안 `StockIn`에 유통기한·가격 칸이 없어 받지 않는다(`유통기한은 재고에서 고칠 수 있어요`). 한 트랜잭션에서:
    1. 각 `id`가 내 항목이고 done_at 있음·stocked_at NULL인지 — 아니면 400 `목록이 방금 바뀌었어요. 다시 불러와주세요.`(아무것도 안 만듦).
    2. 각 줄을 `purchased_on`을 넣어 `parse_fields`로 검증 — 틀리면 400 `{error: "N번째 재료: …", errors}`.
    3. `check_ingredient_cap(user, N)` — 2000개 문구 그대로.
    4. `Ingredient` 생성 + 해당 항목 `stocked_at = now` → 커밋. 위치가 커밋 중 사라지면 재고 bulk와 같은 400.
  - `POST /api/shopping/items/match` `{names:[1~50 문자열]}` → `{items:[{id, name}]}` — 목록에 있는(stocked_at NULL) 항목 중 이름이 `names_match`되는 것(영수증·주문 스캔으로 재고에 넣은 뒤 제안용, 스펙 16절).
  - `POST /api/shopping/items/mark-stocked` `{ids:[1~300]}` → 204 — 내 항목만 `stocked_at = now`(재고는 이미 스캔으로 넣었으므로 재료를 만들지 않음), 없는 id는 조용히 넘긴다.
  - `ponytail:` 산 것 기록은 `stocked_at` 칸 하나로 7일만 둔다(따로 기록 테이블 없음). 월간 리포트 등에서 구매 기록이 필요해지면 그때 보관 기간을 늘린다.

- [ ] **Step 0: 브랜치** — main(Task 1 병합)에서 `feature/shopping-stock-backend`.
- [ ] **Step 1: 실패하는 테스트**
  - `test_stock_draft_only_checked_unstocked_with_location_reason`(항목 위치 있음 → `item` / 없음 + 같은 이름 재료 둘 → 최근 것 위치 `same_name` / 없음 → 냉장실 `default`).
  - `test_stock_creates_ingredients_and_marks_items_stocked_atomically`(재고 2개 생김·항목 stocked_at 있음·스냅숏 `stocked`에 보임·안 체크한 항목은 그대로).
  - `test_stock_rejects_unchecked_already_stocked_or_missing_without_creating`.
  - `test_stock_index_errors_all_or_nothing`, `test_stock_respects_2000_cap`, `test_stock_other_users_item_400`.
  - `test_match_returns_listed_items_only`, `test_mark_stocked_ignores_missing_and_others`.
  - 기존 `test_ingredients.py` 전부 그대로 통과(이름만 바꾼 함수).
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — §28에 재고에 넣기·위치 프리필 이유·산 것 기록.
- [ ] **Step 4: 커밋** — `feat: 체크한 장보기 항목 재고에 넣기 API(산 날 하나·위치 프리필·산 것으로 옮기기), 영수증 결과로 산 항목 찾기`

---

### Task 3: 장보기 메모·사진 백엔드 + 사진 저장소 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `backend/app/storage.py`, `backend/app/photos.py`, `backend/migrations/versions/b5b5c5d5e5f5_shopping_notes.py`, `backend/tests/test_shopping_notes.py`, `backend/tests/test_storage.py`
- Modify: `backend/requirements.txt`(boto3 버전 고정), `backend/app/models.py`, `backend/app/shopping.py`, `backend/app/__init__.py`, `backend/tests/test_migrations.py`, `backend/tests/conftest.py`(`UPLOAD_DIR`을 tmp_path로, R2 값 None), 스펙 §28·5절, `docs/deploy.md`

**Interfaces:**
- Consumes: `scan.sniff_image_type`, `MAX_CONTENT_LENGTH`(10MB → 413), `iso_datetime`, `text`
- Produces:
  - `app.storage`(모듈 함수, 클래스 없음):
    - `mode() -> "r2" | "local" | "off"` — `R2_ACCOUNT_ID`·`R2_ACCESS_KEY_ID`·`R2_SECRET_ACCESS_KEY`·`R2_BUCKET`이 모두 있으면 r2, 없고 `RENDER` 환경변수가 있으면 off, 아니면 local.
    - `put(key, data, content_type)`, `delete(keys)`(없는 키·실패는 로그만), `photo_response(key)` — local은 `send_from_directory(UPLOAD_DIR, key)` + `Cache-Control: private, max-age=86400` + nosniff, r2는 만료 5분 presigned URL로 302(스펙 3·9절).
    - `_r2_client()` — boto3 S3 클라이언트(`endpoint_url=https://<account>.r2.cloudflarestorage.com`). 테스트는 이 함수를 가짜로 바꾼다.
    - `UPLOAD_DIR` 기본 `backend/uploads`(절대 경로). 키에 `..`·앞 `/` 금지(`safe_join`).
  - `ShoppingNote`(`shopping_notes`, 스펙 19절): id, user_id CASCADE index, client_id String(36) NULL, place String(30) NULL(시안 `어디서`), body Text(≤2000자, 빈 문자열 허용, 시안 `메모`), created_at, updated_at. UNIQUE(user_id, client_id). **`planned_on` 칸은 두지 않는다**(시안 `MemoPage`에 없음 — 스펙 19절).
  - `ShoppingNotePhoto`(`shopping_note_photos`): id, note_id FK CASCADE index, client_id String(36) NULL, photo_key String(200) UNIQUE, created_at. UNIQUE(note_id, client_id).
  - Alembic `b5b5c5d5e5f5`, down_revision `b4b4c4d4e4f4`(Task 2는 마이그레이션이 없어 병렬이어도 충돌 없음).
  - 상수: `MAX_NOTES = 20`(사용자당), `MAX_PHOTOS = 10`(메모당, 시안 `2 / 10`), `MAX_BODY = 2000`, `MAX_PLACE = 30`.
  - `note_json(note)` → `{id, client_id, place, body, updated_at, photos:[{id, client_id, url: "/api/photos/<key>"}]}`. `GET /api/shopping`의 `notes`를 `updated_at` 내림차순으로 채운다.
  - API(로그인):
    - `POST /api/shopping/notes` `{place?, body, client_id?}` → 201(같은 client_id면 200 기존). 20개 → 400 `메모는 20개까지 둘 수 있어요.` 본문 2001자 → 400 `메모는 2000자까지 쓸 수 있어요.`, place 31자 → 400 `장소는 30자까지 입력해주세요.`
    - `PUT /api/shopping/notes/<id>` `{place, body, edited_at}` → **`note.updated_at > edited_at`이면 409 `{error: "다른 기기에서 먼저 고친 메모가 있어요.", note: 서버 메모}`**(바꾸지 않음). 아니면 저장하고 `updated_at = edited_at`(같은 요청을 다시 보내도 409가 나지 않게, 10분 넘게 미래면 서버 시각). `ponytail:` 기기 시계 비교 — Task 1 체크와 같은 한계.
    - `DELETE /api/shopping/notes/<id>` → 204. 커밋 뒤 사진 파일 `storage.delete`.
    - `POST /api/shopping/notes/<id>/photos` multipart `image`, `client_id?` → 201 사진 JSON(같은 client_id면 200). 순서: 모드 off → 503 `사진을 지금은 올릴 수 없어요.` / 사진 없음 400 `사진을 올려주세요.` / 서명이 JPG·PNG·WEBP 아님 415(스캔 문구) / 10장 → 400 `사진은 메모 하나에 10장까지 넣을 수 있어요.` / 키 `shopping/<user_id>/<uuid4 hex>.<ext>` → `storage.put` → 행 커밋(커밋 실패하면 방금 올린 파일 지움).
    - `DELETE /api/shopping/notes/<id>/photos/<photo_id>` → 204, 커밋 뒤 파일 삭제.
    - `GET /api/photos/<path:key>`(`photos.py`) → 키가 `shopping/<g.user.id>/`로 시작하고 `ShoppingNotePhoto` 행이 있어야 `storage.photo_response`, 아니면 404(남의 키·지운 사진). 5단계 조리 기록·4b 먹은 기록 사진도 같은 경로에 접두사를 늘려 쓴다.
  - 회원 탈퇴(27절, 아직 없음) 때 `shopping/<user_id>/` 파일도 지워야 한다 — 스펙 27절에 적어 두었고 탈퇴 태스크에서 처리.

- [ ] **Step 0: 브랜치** — main(Task 1 병합)에서 `feature/shopping-notes-backend`. boto3 최신 안정 버전을 `pip index versions boto3`로 확인해 고정(네트워크 필요 — 없으면 멈추고 보고).
- [ ] **Step 1: 실패하는 테스트**
  - `test_storage.py`: local put→`photo_response` 200 본문·헤더, `../x` 키 거부, delete 없는 키 조용함, `RENDER=1`+R2 없음 → off, R2 값 모두 있음 → 가짜 `_r2_client`로 `put_object`·`delete_objects` 호출 인자 확인, `photo_response` 302 `Location`이 가짜 presign 주소.
  - `test_migrations.py`: `test_shopping_notes_migration_adds_and_removes_tables`.
  - `test_shopping_notes.py`: 생성·client_id 재전송 200·상한 20·본문/장소 길이 / PUT 최신 저장 우선(서버 T2, 기기 T1 → 409 + note, 기기 T3 → 200 updated_at=T3, 같은 T3 다시 → 200) / 스냅숏에 notes·photos 포함 / 사진 올리기(가짜 JPEG 서명 바이트) 201·client_id 재전송 200·11번째 400·PDF 415·10MB+1 413·off 503 / 사진 삭제 후 `/api/photos` 404·파일 없음 / 메모 삭제 시 사진 파일 삭제 / 남의 메모·사진·키 404 / 사용자 삭제 CASCADE.
- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 개발 DB `flask db upgrade`·`flask db check`.
- [ ] **Step 3: 문서** — 스펙 §28 메모·사진 API, 5절 `/api/photos` 설명 갱신. `docs/deploy.md`: R2 버킷(비공개), 환경변수 4개, **오프라인 사진 보관을 위해 R2 CORS에 앱 주소 GET 허용**, `RENDER`에서 R2 없으면 사진 기능 503.
- [ ] **Step 4: 커밋** — `feat: 장보기 메모·사진 API(다른 기기와 겹치면 알려주기, 메모당 사진 10장), 사진 저장소(R2 또는 로컬 uploads), 소유자 확인 사진 보기`

---

### Task 4: 메모 사진 인식 `kind=memo` (UI 시안 승인 전 진행 가능)

**Files:**
- Modify: `backend/app/ai.py`(PROMPTS·SAMPLES), `backend/app/scan.py`(`UPLOAD_KINDS`, `clean_result`), `backend/tests/test_scan.py`, 스펙 5절

**Interfaces:**
- Consumes: 기존 스캔 흐름 전부(`check_ai_limits(SCAN_KINDS)` — `memo`는 이미 scan 묶음, `start_ai_call`, `ai.extract`)
- Produces:
  - `UPLOAD_KINDS = ("fridge", "receipt", "order", "memo")`.
  - `PROMPTS["memo"]`: "장을 보려고 손으로 쓴 메모, 마트 전단지, 상품 사진이다. 사야 할 식품 이름을 뽑아라. 메모에 수량이 있으면 quantity·unit으로, 없으면 1과 '개'. 전단지는 가격·할인·광고 문구를 빼고 상품 이름만. 지워진 줄(두 줄 긋기)은 뺀다. purchased_on은 항상 null, price는 항상 null. " + `_COMMON`.
  - `SAMPLES["memo"]`: `대파 1단 fridge`, `두부 1모 fridge`, `계란 1판 fridge`, `참기름 1병 room`, `양파 3개 room`.
  - `clean_result("memo", …)`: price·purchased_on 항상 None. 응답 모양은 그대로(`location_kind`는 장보기 항목 `location_id` 프리필에 쓴다).
- [ ] **Step 0: 브랜치** — main에서 `feature/scan-memo`.
- [ ] **Step 1: 실패하는 테스트** — `test_scan_memo_sample_mode`(sample true, 가격·날짜 null), `test_scan_memo_calls_ai_and_counts_in_scan_group`(가짜 `ai.extract`가 price 3000·purchased_on을 줘도 null, `ai_calls.kind == "memo"`, 오늘 fridge 9회 + memo 1회 → 다음 memo 429), `test_scan_unknown_kind_still_400`.
- [ ] **Step 2: 구현 → 전체 테스트(SQLite·PostgreSQL)**
- [ ] **Step 3: 스펙** — 5절 `/api/scan?kind=fridge|receipt|order|memo`.
- [ ] **Step 4: 커밋** — `feat: 장보기 메모 사진에서 살 것 인식(kind=memo, 사진 인식 한도에 함께 셈)`

---

### Task 5: 쇼핑몰 링크 모듈 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `frontend/src/storeLinks.ts`, `frontend/scripts/check-store-links.mjs`
- Modify: `frontend/package.json`(check), `frontend/src/api.ts`(`User.shop_affiliates`), `backend/app/__init__.py`(`COUPANG_PARTNERS_ID`), `backend/app/auth.py`(`user_json`), `backend/tests/test_auth.py`, 스펙 16절

**Interfaces:**
- Produces:
  ```ts
  export type StoreId = "coupang" | "naver" | "kurly" | "emart" | "homeplus" | "lottemart" | "gmarket";
  export type SortId = "price_asc" | "popular" | "newest";
  export const SORTS: { id: SortId; label: string }[];   // 시안 StoreSheet 순서: 낮은 가격순 · 많이 산 순 · 새 상품순

  /** ⚠ 이 표의 주소는 네트워크 없이 적은 후보다. Task 9에서 사용자가 폰으로 하나씩 열어 확인하기 전에는 화면에 내보내지 않는다.
   *  확인된 칸만 남기고, 안 되는 정렬은 칸을 지운다(칩이 숨겨진다). verified에 확인 날짜를 적는다. */
  export const STORES: readonly {
    id: StoreId; name: string;             // 순서 = 기본 화면 순서(제휴와 무관). 이름은 시안: 쿠팡 · 네이버 쇼핑 · 컬리 · 이마트몰 · 홈플러스 · 롯데마트 · G마켓
    host: string;                          // 검사용: 만든 주소의 호스트가 이것과 같아야 한다
    search: string;                        // "{q}" 자리에 encodeURIComponent(검색어) — 정렬이 하나도 확인 안 된 쇼핑몰의 `검색 결과` 칩
    sorts: Partial<Record<SortId, string>>;
    verified: string | null;               // "2026-09-xx 사용자 폰 확인" | null
  }[];

  /** 제휴 링크 모양. 파트너스 가입 후 형식을 확인하고 채운다(그 전엔 빈 객체 → 광고 표시 없음) */
  export const AFFILIATE_FORMATS: Partial<Record<StoreId, (url: string, id: string) => string>>;

  export function searchQuery(name: string): string;   // 앞뒤 공백·괄호 내용 제거, 50자
  export interface StoreLink { sort: SortId | null; label: string; url: string }
  /** 쇼핑몰마다 링크(확인된 정렬만, 하나도 없으면 [검색 결과]). 순서: lastUsed가 있으면 그 쇼핑몰 맨 위, 나머지는 STORES 순서.
   *  ad는 쇼핑몰 단위(시안: 이름 옆 `광고`). 검색어가 비면 []. onlyVerified면 verified 없는 쇼핑몰 제외 */
  export function storeLinks(
    name: string,
    affiliates: Partial<Record<StoreId, string>>,
    options?: { lastUsed?: StoreId | null; onlyVerified?: boolean; formats?: typeof AFFILIATE_FORMATS },
  ): { store: StoreId; name: string; ad: boolean; links: StoreLink[] }[];
  export const LAST_STORE_KEY = "shopping-last-store";   // localStorage, 링크를 누를 때 저장(Task 9)
  ```
- **후보 주소 표(검증 전 — 기억에 기댄 값, 틀릴 수 있음):**

  | 쇼핑몰 | 검색 | 낮은 가격순 | 많이 산 순 | 새 상품순 |
  |---|---|---|---|---|
  | 쿠팡 | `https://www.coupang.com/np/search?q={q}` | `&sorter=salePriceAsc` | `&sorter=saleCountDesc` | `&sorter=latestAsc` |
  | 네이버 쇼핑 | `https://search.shopping.naver.com/search/all?query={q}` | `&sort=price_asc` | (리뷰 많은순 `&sort=review`만 후보 — 판매량 아님, 확인 후 결정) | `&sort=date` |
  | 컬리 | `https://www.kurly.com/search?sword={q}` | 후보 없음 | 후보 없음 | 후보 없음 |
  | 이마트몰(SSG) | `https://emart.ssg.com/search.ssg?query={q}` | `&sort=prcasc` | `&sort=sale` | `&sort=regdt` |
  | 홈플러스 | `https://front.homeplus.co.kr/search?entry=direct&keyword={q}` | 후보 없음 | 후보 없음 | 후보 없음 |
  | 롯데마트(롯데온) | `https://www.lotteon.com/search/search/search.ecn?render=search&platform=pc&q={q}&mallId=4` | 후보 없음 | 후보 없음 | 후보 없음 |
  | G마켓 | `https://www.gmarket.co.kr/n/search?keyword={q}` | `&s=1` | `&s=8` | `&s=3` |

  "후보 없음"은 Task 9 검증 때 폰에서 해당 쇼핑몰 검색 결과의 정렬을 직접 바꿔 주소창 값을 받아 적거나, 안 바뀌면(앱 전환·POST 정렬) 칸을 비워 둔다.
- 백엔드: `COUPANG_PARTNERS_ID=os.environ.get(...) or None`, `user_json`에 `shop_affiliates: {"coupang": id}`(값 있는 것만, 없으면 `{}`). 다른 쇼핑몰 ID는 가입할 때 같은 방식으로 추가(YAGNI).
- [ ] **Step 0: 브랜치** — main에서 `feature/store-links`.
- [ ] **Step 1: 검사 스크립트 먼저** — `check-store-links.mjs`(`import ... from "../src/storeLinks.ts"`):
  - `storeLinks("", {})` → `[]`; `searchQuery(" 대파(국산) ")` → `"대파"`.
  - `storeLinks("대파", {})`: 쇼핑몰 순서가 `STORES` 순서와 같음, 모든 url이 `https://` + 해당 `host`, 검색어가 `encodeURIComponent("대파")`로 들어감(`&`·`#`·`%` 섞인 이름도 `new URL(url)`의 검색 파라미터 값이 원래 이름), 모든 `ad === false`, `sorts`에 없는 정렬 링크는 없음, 정렬이 없는 쇼핑몰은 `[{sort: null, label: "검색 결과"}]` 하나.
  - `lastUsed: "kurly"` → 컬리가 맨 앞, 나머지는 STORES 순서 그대로. 없는 id → 순서 그대로.
  - 가짜 `formats: { gmarket: (u, id) => u + "&aff=" + id }` + `affiliates: { gmarket: "X" }` → gmarket만 `ad === true`·모든 링크에 `aff=X`, **순서 그대로**. affiliates에 ID가 있어도 formats에 없으면 ad false.
  - `onlyVerified: true` → verified 없는 쇼핑몰 빠짐.
  - `STORES` id 7개·중복 없음, `SORTS` 라벨이 시안과 같음.
  - 출력 `store links ok`.
- [ ] **Step 2: 구현** — 위 표를 `STORES`에 넣고 `verified: null`, 파일 맨 위에 "⚠ 검증 전" 주석. `AFFILIATE_FORMATS = {}`.
- [ ] **Step 3: 백엔드** — `test_auth.py`: `/api/me`에 `shop_affiliates` `{}`, 환경값 있으면 `{"coupang": "…"}`. 전체 pytest.
- [ ] **Step 4: 확인** — `npm run check && npm run build`. `node scripts/check-store-links.mjs --print`로 `대파` 링크 목록을 출력하는 옵션을 두어 Task 9 검증 때 쓴다.
- [ ] **Step 5: 스펙** — 16절에 "주소 표는 `frontend/src/storeLinks.ts` 한 곳, 사용자 폰 검증 전에는 화면에 안 보임, 제휴 ID는 `/api/me`의 `shop_affiliates`".
- [ ] **Step 6: 커밋** — `feat: 쇼핑몰 검색·정렬 링크 만드는 모듈(검증 전 후보 주소, 제휴 쇼핑몰에만 광고 표시, 마지막으로 연 쇼핑몰 맨 위)`

---

### Task 6: 오프라인 장보기 순수 로직 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `frontend/src/shopping/sync.ts`, `frontend/scripts/check-shopping-sync.mjs`
- Modify: `frontend/package.json`(check), `frontend/src/api.ts`(`ShoppingItem`, `ShoppingNote`, `ShoppingSnapshot` 타입 — Task 1·3 JSON과 같게), 스펙 §28

**Interfaces:**
- Consumes: `addDays`·`formatAmountNumber`(format.ts), `parseAmountInput`(seasoning.ts, `½`·`1/2` 해석)
- Produces (브라우저 API·`Date.now()`를 직접 부르지 않는다 — 시각·id는 인자로 받는다):
  ```ts
  export type Ref = { id: number } | { client_id: string };   // 서버에 아직 없는 항목은 client_id로 가리킨다
  export type Op =
    | { op: "add"; client_id: string; fields: ItemFields; at: string }
    | { op: "edit"; ref: Ref; fields: Partial<ItemFields>; at: string }
    | { op: "check"; ref: Ref; done: boolean; at: string }
    | { op: "delete"; ref: Ref; at: string }
    | { op: "note_add"; client_id: string; fields: NoteFields; at: string }
    | { op: "note_save"; ref: Ref; fields: NoteFields; edited_at: string }
    | { op: "note_delete"; ref: Ref; at: string }
    | { op: "photo_add"; note: Ref; client_id: string; blob_key: string; at: string }
    | { op: "photo_delete"; note: Ref; photo: Ref; at: string };

  /** 새 변경을 대기열에 넣으며 합친다. dropBlobs: 더 이상 보낼 필요 없는 사진 blob 키(호출 측이 IndexedDB에서 지움) */
  export function enqueue(queue: Op[], next: Op): { queue: Op[]; dropBlobs: string[] };
  /** 서버 스냅숏 위에 대기 변경을 얹은 화면용 목록. 아직 안 보낸 항목·메모·사진은 pending: true */
  export function applyQueue(snapshot: ShoppingSnapshot, queue: Op[]): ShoppingView;
  /** add·note_add·photo_add 성공 후 뒤 변경들의 client_id 참조를 서버 id로 바꾼다 */
  export function remapRef(queue: Op[], client_id: string, id: number): Op[];
  /** 보낸 결과 분류: ok(빼고 다음) · retry(멈추고 나중에: 네트워크 0·5xx·408·429) · auth(멈춤: 401) ·
   *  drop(빼고 실패 목록에: 400·413·415, photo_add의 503(사진 저장소 꺼짐), 삭제/체크의 404는 ok로) · conflict(409 note_save) */
  export function classify(op: Op, status: number): "ok" | "retry" | "auth" | "drop" | "conflict";
  /** 시안 ShoppingList 날짜 묶음(Asia/Seoul 날짜 문자열로만 계산). 체크한 항목도 제자리(묶음·순서 그대로). 빈 묶음은 뺀다 */
  export function groupItems<T extends { planned_on: string | null; created_at: string }>(
    items: T[], today: string,
  ): { key: "today" | "week" | "later" | "undated"; title: string; items: T[] }[];
  /** 시안 AddSheet `언제 살까요?` 칩 → planned_on */
  export function plannedOnFor(choice: "today" | "week" | "undated", today: string): string | null;
  /** 시안 AddSheet 수량 칸 한 줄: "1모"·"30구"·"1L"·"½봉"·"2"·"모"·"" → {quantity, unit}, 틀리면 null */
  export function parseQuantityText(text: string): { quantity: number; unit: string } | null;
  export function quantityText(quantity: number, unit: string): string;   // 1,"모" → "1모", 0.5,"봉" → "½봉"
  /** 시안 태그: recipe → {text: "레시피 · 두부조림", tone: "info"}, urgent → {"곧 떨어져요", "warn"}, staple → {"필수품", ""}, memo → {"메모 사진", ""}, manual → null */
  export function sourceTag(item: { source: string; source_label: string | null }): { text: string; tone: "" | "info" | "warn" } | null;
  ```
- **합치기 규칙(`enqueue`):**
  1. 같은 대상 `check` 뒤 `check` → 마지막 것만.
  2. 아직 안 보낸 `add` 뒤 같은 client_id `edit` → add의 fields에 합침, `check` → 그대로 둠(add 다음에 보냄).
  3. 아직 안 보낸 `add` 뒤 `delete` → 그 add와 그 대상의 모든 변경을 지우고 delete도 넣지 않음. 메모도 같음(`note_add`+`note_delete` → 메모의 `photo_add` blob 키를 `dropBlobs`로).
  4. 서버에 있는 대상의 `delete` → 앞의 같은 대상 `edit`·`check`를 지움. 서버 메모 `note_delete` → 앞의 `note_save`·그 메모 `photo_add`(blob 키 `dropBlobs`)를 지움.
  5. 같은 메모 `note_save` 뒤 `note_save` → 마지막 fields·edited_at으로 하나(메모 화면이 자동 저장이라 여러 번 들어온다). 아직 안 보낸 `note_add`면 그 fields에 합침.
  6. 아직 안 보낸 `photo_add` 뒤 같은 client_id `photo_delete` → 둘 다 없앰 + `dropBlobs`.
  7. 순서는 들어온 순서 유지(합쳐진 항목은 처음 자리).
- **묶음 규칙(`groupItems`, 사용자 결정 2026-09-14):** planned_on ≤ today(지난 날짜 포함) → `today`(`오늘`) / ≤ today+6 → `week`(`이번 주`) / 그 뒤 → `later`(`나중에`) / 없음 → `undated`(`날짜 미정`). 묶음 안은 planned_on·created_at 오름차순. **체크(done_at)는 묶음·순서에 영향이 없다**(제자리에서 줄 긋기). 산 것(stocked)은 스냅숏의 `stocked`로 따로 온다. `plannedOnFor("week")` = today+6(이 날까지 사면 된다는 뜻, `이번 주` 묶음에 들어감).
- **메모 충돌(19절 "덮어쓰기 전 기기 쪽 사본 보관"):** `classify`가 conflict면 호출 측(Task 7)이 기기에서 쓴 fields를 `backups`에 저장하고 서버 메모를 받아들인다. 기기 쪽 edited_at이 더 늦으면 서버가 받아들이므로 충돌이 아니다(그때도 호출 측이 보내기 직전 스냅숏 본문을 `backups`에 한 번 남긴다 — 덮어쓴 서버 쪽 사본).

- [ ] **Step 0: 브랜치** — main에서 `feature/shopping-sync-core`.
- [ ] **Step 1: 검사 스크립트 먼저 쓰고 실패 확인** — `check-shopping-sync.mjs`, 합치기 규칙 1~7 각각 최소 한 줄, 그리고:
  - `applyQueue`: 서버 항목 체크 대기 → 그 항목 done_at = op.at·pending; 대기 add → 목록 끝에 pending 항목(id 없음, client_id); 대기 delete → 안 보임; note_save → 본문 바뀜; photo_add → 사진 목록에 `{client_id, blob_key, pending}`; `stocked`는 그대로.
  - `remapRef`: add 성공 후 `{client_id}` edit·check·delete가 `{id}`로, 다른 client_id는 그대로. photo_add·photo_delete의 `note` 참조도.
  - `classify`: (check, 404) ok, (delete, 404) ok, (edit, 404) drop, (add, 400) drop, (any, 0) retry, (edit, 503) retry, (photo_add, 503) drop, (any, 429) retry, (any, 401) auth, (note_save, 409) conflict, (photo_add, 413) drop.
  - `groupItems`: today `2026-09-14`에 planned_on `2026-09-10`(지남)→오늘, `2026-09-20`(+6)→이번 주, `2026-09-21`→나중에, null→날짜 미정. done_at 있는 항목이 같은 묶음 같은 자리. 빈 묶음 없음. `plannedOnFor("week", "2026-12-29")` → `"2027-01-04"`.
  - `parseQuantityText`: `"1모"`→{1,"모"}, `"30구"`→{30,"구"}, `"1L"`→{1,"L"}, `"½봉"`→{0.5,"봉"}, `"1/2대"`→{0.5,"대"}, `"2"`→{2,"개"}, `"모"`→{1,"모"}, `""`→{1,"개"}, `"0개"`·`"-1개"`·단위 11자 → null. `quantityText(0.5, "봉")` → `"½봉"`.
  - `sourceTag` 네 종류 + manual null.
  - 대기열 200개에 고정 시드 무작위 op를 넣고 `applyQueue`가 같은 id를 두 번 내지 않는지(간단한 속성 검사).
  - 출력 `shopping sync ok`.
- [ ] **Step 2: 구현** — 위 규칙대로. `ponytail:` 대기열은 배열 통째 저장(수백 개 이하), 느려지면 op별 키로.
- [ ] **Step 3: 확인** — `npm run check && npm run build`.
- [ ] **Step 4: 스펙** — §28에 합치기·충돌 처리 요약.
- [ ] **Step 5: 커밋** — `feat: 오프라인 장보기 변경 합치기·화면용 목록·날짜 묶음·수량 글자 해석 순수 로직과 검사`

---

### Task 7: 서비스 워커·글꼴·기기 저장소·오프라인으로 앱 열기 (UI 시안 승인 전 진행 가능 — 화면 문구가 없는 부분만)

**Files:**
- Create: `frontend/src/shopping/idb.ts`, `frontend/src/shopping/useShopping.ts`
- Modify: `frontend/public/sw.js`, `frontend/index.html`, `frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `docs/deploy.md`

**Interfaces:**
- Consumes: Task 6 `sync.ts`, Task 1·3 API, `api()`의 `ApiError(0)`(네트워크 없음), `onUnauthorized`
- Produces:
  - **`sw.js`(CACHE `galmuri-shell-v2`, 스펙 19절):**
    - install: `/`를 받아 캐시하고, 받은 HTML에서 `/assets/…`(js·css) 주소를 정규식으로 뽑아 함께 캐시, `/manifest.webmanifest`·아이콘도.
    - fetch: 화면 이동은 지금처럼 네트워크 우선 → 실패 시 캐시 `/`. **같은 오리진 GET `/assets/*`는 캐시 우선 → 없으면 네트워크 후 캐시에 넣기**(파일 이름에 해시가 있어 바뀌지 않음, 글꼴 조각 포함). `/api`·`/auth`·POST·다른 오리진은 그대로 통과(데이터는 IndexedDB가 맡는다).
    - activate: `galmuri-shell-`로 시작하는 옛 캐시 삭제.
    - `ponytail:` 배포마다 옛 해시 파일이 캐시에 쌓인다(배포당 수백 KB). 커지면 activate에서 지금 `/`와 CSS가 가리키지 않는 항목을 지운다.
    - 지금 `sw.js`는 `/`만 캐시해서 **오프라인으로 열면 JS·CSS가 없어 빈 화면**이다 — 이 태스크가 고친다.
  - **글꼴 자체 호스팅:** `index.html`의 Google Fonts `preconnect`·`stylesheet` 3줄 삭제, `main.tsx`에서 `@fontsource/ibm-plex-sans-kr`의 쓰는 굵기 CSS만 import(Vite가 woff2를 `/assets`로 내보내고 unicode-range로 필요한 조각만 받는다 → 서비스 워커가 쓴 조각을 캐시). 근거: 직접 woff2를 받아 조각내는 것보다 짧고, 외부 글꼴 요청(개인정보·오프라인)이 없어진다. 패키지가 없거나 한글 조각이 없으면 IBM Plex 공식 배포(OFL)에서 400·700 두 굵기만 `public/fonts/`에 넣고 `@font-face`를 styles.css에 쓴다(대체안 — 사용자에게 알리고 진행). 굵기는 `grep -n "font-weight" frontend/src/styles.css`로 실제 쓰는 것만(지금 400·500·600·700). 시안 파일의 Google Fonts 링크는 시안 보기용이라 그대로 둔다.
  - **`idb.ts`(라이브러리 없음, 40줄 안팎):** DB `galmuri` v1, 저장소 `kv`(키: `me`, `snapshot`, `queue`, `failed`, `backups`)·`blobs`(사진 Blob). `get(store, key)`, `set(store, key, value)`, `del(store, key)`, `clearAll()`. IndexedDB를 못 열면(사생활 모드 등) 메모리 Map으로 대신하고 오프라인 보관은 안 된다(`ponytail:`).
  - **`useShopping.ts`(install.ts처럼 모듈 상태 + 구독):**
    ```ts
    export function useShopping(): {
      view: ShoppingView | null;          // applyQueue(snapshot, queue) — items, stocked, notes
      offline: boolean;                   // 마지막 요청이 네트워크 0이었거나 navigator.onLine false
      pending: number;                    // queue.length (시안 `기다리는 중 3건`)
      failed: { op: Op; error: string }[];// drop된 변경
      backups: { note_ref: Ref; fields: NoteFields; saved_at: string }[];
      act(op: Op): void;                  // enqueue → 저장 → 화면 갱신 → 온라인이면 flush
      addPhoto(note: Ref, blob: Blob): void; // blobs에 저장 후 photo_add
      photoBlob(photo: { id?: number; client_id?: string; url?: string; blob_key?: string }): Promise<Blob | null>; // 기기 blob → 없으면 fetch(url) 후 저장
      refresh(): Promise<void>;           // GET /api/shopping → snapshot 저장(대기열이 비었을 때만 덮어씀, 아니면 flush 뒤)
      dismissFailed(): void; dismissBackup(i: number): void;
    };
    /** 다른 화면에서 한 번에 담기(T11·T13). 온라인 전용 bulk → refresh. */
    export function addMany(source: string, items: { name: string; quantity?: number; unit?: string; planned_on?: string | null; location_id?: number }[], sourceLabel?: string): Promise<{ created: number; skipped: string[] }>;
    export function clearShoppingDevice(): Promise<void>;  // 로그아웃·401에서 호출
    ```
    - flush: 한 번에 하나만 돈다(모듈 플래그). 대기열 앞에서부터 보내고 `classify`대로 처리, add 계열 성공 시 `remapRef`, retry·auth면 멈춤. 다 보내면 `refresh()`. 트리거: 앱 시작, `online` 이벤트, `visibilitychange`(보이게 될 때), `act` 직후.
    - 체크 op의 `at`·메모 `edited_at`은 `new Date().toISOString()`, client_id는 `crypto.randomUUID()`(보안 컨텍스트에서만 있음 — 없으면 `Math.random` 기반 대체).
    - 사진: 올리기 성공 시 blob을 지우지 않고 `photo:<server id>` 키로 남겨 오프라인에서도 보이게(메모 20개 × 10장 상한 안에서 전부). 서버 사진은 처음 보일 때 `photoBlob`이 받아 저장. 메모·사진 삭제 시 blob도 삭제.
  - **`App.tsx` 오프라인으로 열기:** `/api/me` 성공 시 `idb.set("kv", "me", user)`. `ApiError(0)`이고 저장된 `me`가 있으면 **그 사용자로 앱을 열고** 오프라인 표시(지금의 `서버에 연결할 수 없어요.` 화면은 저장된 사용자가 없을 때만). 로그아웃·401(`signOut`)에서 `clearShoppingDevice()` — 같은 폰을 다른 사람이 쓸 때 목록이 남지 않게.
- **구현 때 바뀐 것(2026-09-14, 리드 결정):** 글꼴 자체 호스팅(`@fontsource` 설치·woff2 내려받기)은 하지 않는다 — 새 의존성·네트워크 내려받기 없이 `sw.js`가 Google Fonts 응답을 캐시한다(CSS stale-while-revalidate, gstatic 캐시 우선, opaque 허용, 200개 상한, `index.html` 링크에 `crossorigin`). `ponytail:` 첫 온라인 방문 뒤부터 오프라인 글꼴, 그 전엔 시스템 글꼴. 외부 글꼴 요청(개인정보)이 문제되면 그때 자체 호스팅. 미리 받을 목록은 HTML 정규식 대신 빌드 끝 플러그인이 `dist` 전체 목록·해시로 넣는다(캐시 이름이 해시라 옛 파일이 쌓이지 않음). 브랜치는 `feature/offline-shell`. 스펙 §19·§28.
- [ ] **Step 0: 브랜치** — main(1·3·6 병합)에서 `feature/shopping-offline-shell`. `npm view @fontsource/ibm-plex-sans-kr version`(네트워크 필요)으로 확인 후 `npm install`로 고정.
- [ ] **Step 1: 확인 가능한 것 먼저** — `npm run check && npm run build`. `dist/index.html`에 `fonts.googleapis.com`이 없고 `dist/assets`에 woff2가 있는지 `grep`/`ls`로.
- [ ] **Step 2: 데스크톱 크롬 확인(`localhost`는 보안 컨텍스트)** — 공용 개발 서버는 끄거나 새로 띄우지 않는다. **자기 포트(예: 5191)로 `vite preview`를 따로 띄워** 셸만 확인하고 자기 PID만 끈다: DevTools Application에 `galmuri-shell-v2`와 `/assets/*` → Network `Offline` → 새로고침해도 화면이 뜬다. `useShopping` 동작은 Task 8 화면에서 확인한다.
- [ ] **Step 3: 문서** — `docs/deploy.md` "폰에서 오프라인 확인": USB 디버깅 → `adb reverse tcp:5180 tcp:5180` → 폰 크롬 `http://localhost:5180` → 목록 받기 → 비행기 모드 → 앱 다시 열기. 또는 Render 배포 후 https.
- [ ] **Step 4: 커밋** — `feat: 오프라인으로 앱 열기(화면 파일·글꼴 기기 보관, 마지막 사용자 기억), 장보기 기기 저장소와 연결되면 순서대로 보내기, IBM Plex Sans KR 자체 호스팅`

---

### Task 8: 장보기 탭 목록 (시안 승인 후)

**시안(그대로 따른다):** `docs/design/shopping-4/ShoppingList.dc.html`, `ShoppingOffline.dc.html`, `ShoppingDark.dc.html`, `AddSheet.dc.html`

**Files:**
- Create: `frontend/src/pages/Shopping.tsx`, `frontend/src/components/ShoppingItemSheet.tsx`
- Modify: `frontend/src/App.tsx`(`/shopping` → `Shopping`), `frontend/src/pages/ComingSoon.tsx`(장보기 문구 제거), `frontend/src/useHashRoute.ts`(`/shopping/stock`·`/shopping/memo`·`/shopping/memos` 자리), `frontend/src/styles.css`, `frontend/src/components/Icon.tsx`

**Interfaces:**
- Consumes: `useShopping`, `groupItems`·`plannedOnFor`·`parseQuantityText`·`quantityText`·`sourceTag`, `Sheet`, `setLeaveGuard`(시트 작성 중)
- Produces:
  - **`ShoppingList` — `Shopping.tsx`:** 머리 `장보기` + 오른쪽 `icon-btn` `aria-label="항목 추가"`(더하기 아이콘 → 추가 시트). 요약 `살 것 N개 · 체크한 M개`(`sh-summary`, 체크 0이면 `살 것 N개`).
    - 오프라인(`ShoppingOffline`): 요약 아래 `sh-offline` 띠 — 아이콘 + `오프라인 · 연결되면 저장돼요` + 대기 있으면 굵게 `기다리는 중 N건`(`role="status"`). 온라인에서 대기가 0이 되면 사라진다. 저장 실패(`failed`)가 있으면 같은 띠 모양으로 `저장하지 못한 변경 N건` → 탭하면 시트(내용·이유·`지우기`) — 시안에 없는 상태.
    - 메모 카드 자리(`sh-memo`, Task 10).
    - **체크한 항목이 있을 때만** 초록 막대 `sh-stock`: `체크한 M개를 재고에 넣을까요?` + `btn primary` `재고에 넣기` → `#/shopping/stock`(오프라인이면 누르면 `인터넷이 연결되면 넣을 수 있어요` 안내).
    - 묶음 제목(`sh-group`: `오늘` · `이번 주` · `나중에` · `날짜 미정`) + 흰 `list` 카드. 행 `sh-row`: 왼쪽 체크 칸(`sh-check`, 44px, `role="checkbox"` `aria-checked`, `aria-label="{이름} 샀어요"`) · 가운데 이름 + 수량(`sh-name` 안 작은 글씨 `1모`) · 아래 태그(`sh-tag` — `sourceTag`, 없으면 줄 없음) · 오른쪽 쇼핑몰 아이콘 버튼(`icon-btn`, `aria-label="{이름} 쇼핑몰에서 찾기"`, Task 9). **체크하면 제자리에서 `done`(체크 칸 초록·이름 줄 긋기·회색), 다시 누르면 해제. 다시 열어도 자리 그대로.** 행 가운데를 누르면 고치기 시트. 대기 중(pending) 항목은 태그 줄 끝에 작은 회색 `저장 전`.
    - 맨 아래 `sh-fold` `산 것 N개` + 아래 화살표(`aria-expanded`) — 최근 7일 재고에 넣은 항목. 펼치면 같은 `list` 카드에 이름·수량 · 보조 `9월 14일 재고에 넣었어요` · 오른쪽 작은 `btn outline` `다시 담기`(같은 이름·수량 add op, source manual). 산 것이 0이면 접기 줄을 숨긴다.
    - 빈 목록(목록·산 것 모두 0): 기존 `empty` 카드 + 다람이 + `살 것을 담아두면 마트에서 체크만 하면 돼요`(시안에 없는 상태, 추천 기본값).
  - **`AddSheet` — `ShoppingItemSheet.tsx`:** 시트 제목 `살 것 추가`. 한 줄 두 칸(`sh-two`): `이름`(16px) · `수량`(글자 한 칸, 자리 표시 `1개`, `parseQuantityText` — 틀리면 칸 빨간 테두리 `수량을 1모, 30구처럼 입력해주세요`). `언제 살까요?` 칩(`sh-when`, 선택 `on`): `오늘` · `이번 주` · `날짜 미정` · 달력 아이콘 `날짜 고르기`(`<input type="date">`를 열고 고른 날짜를 칩 글자로 `9월 20일`). 기본 선택 `오늘`. 하단 `actions`: `btn outline` `계속 추가`(저장 후 이름·수량만 비우고 이름 칸에 포커스, 언제 선택은 유지) · `btn primary` `추가`(저장 후 닫기). 이름이 비면 두 버튼 비활성. 저장은 `act({op: "add"})`라 오프라인에서도 된다.
  - **고치기(시안 `AddSheet` 모양 재사용):** 제목 `살 것 고치기`, 같은 칸, 하단 `btn primary` `저장`, 그 아래 `.btn.danger-text` `목록에서 빼기`(확인창 `목록에서 뺄까요?` → delete op). 넣을 곳(`location_id`)은 여기서 고치지 않는다(메모 인식이 채우고, 재고에 넣기 화면에서 고친다).
- [ ] **Step 0: 브랜치·시안** — main(7 병합)에서 `feature/shopping-list-ui`. 시안 네 프레임을 열어 두고 `sh-*`·`mo-note` 스타일을 styles.css로(다크 토큰은 기존 것).
- [ ] **Step 1: 경로** — `/shopping/stock`·`/shopping/memo`·`/shopping/memos`를 `ROUTES`에 넣고 3c와 같은 `node --input-type=module -e` 한 줄 검사로 새 경로·기존 경로 그대로 → `matchRoute ok`.
- [ ] **Step 2: 목록·체크·시트 구현** — `npm run check && npm run build`.
- [ ] **Step 3: 폰 확인(adb reverse, 개발용 로그인)** — `+` → `두부`·`1모`·오늘 → `계속 추가` → `계란`·`30구`·이번 주 → `추가` → 묶음이 시안과 같음. 체크 → 제자리 줄 긋기·초록 막대 `체크한 1개를 재고에 넣을까요?` → 앱 다시 열어도 자리 그대로 → 해제 → 막대 사라짐. 비행기 모드 → 앱 닫고 다시 열기 → 목록이 열리고 `오프라인 · 연결되면 저장돼요` → 체크 2개·추가 1개 → `기다리는 중 3건` → 비행기 모드 해제 → 띠 사라짐 → 데스크톱에서 같은 계정으로 새로고침해 반영 확인. 같은 항목을 폰(오프라인)에서 체크하고 데스크톱에서 나중에 해제 → 폰 연결 후 해제 상태(마지막 변경 우선). `ShoppingDark` 대조, 384px, 입력 시 화면 확대 없음(16px), 고치기 시트의 `목록에서 빼기`가 `저장` 아래 연빨강.
- [ ] **Step 4: 커밋** — `feat: 장보기 탭(날짜 묶음·제자리 체크·재고에 넣기 막대·살 것 추가 시트·산 것 접기·인터넷 없이 체크하고 연결되면 저장)`

---

### Task 9: 쇼핑몰에서 찾기 시트 + 주소 검증 (시안 승인 후)

**시안(그대로 따른다):** `docs/design/shopping-4/StoreSheet.dc.html`

**Files:**
- Create: `frontend/src/components/StoreLinksSheet.tsx`
- Modify: `frontend/src/pages/Shopping.tsx`, `frontend/src/storeLinks.ts`(검증 결과 반영), `frontend/scripts/check-store-links.mjs`, `frontend/src/styles.css`, 스펙 16절

**Interfaces:**
- Consumes: `storeLinks(searchQuery(name), user.shop_affiliates, { lastUsed: localStorage[LAST_STORE_KEY], onlyVerified: true })`(localStorage는 try/catch)
- Produces: 행 오른쪽 쇼핑몰 아이콘 → 시트 제목 `{이름} 찾기` / 설명 `누르면 쇼핑몰 검색 결과로 이동해요. 결제는 쇼핑몰에서 해요.` 쇼핑몰마다 `sh-store`: 머리 이름(`쿠팡`) + 제휴면 옆 `sh-ad` `광고` · 아래 칩 줄 `sh-sorts` `낮은 가격순`(첫 칩 `first` 초록 톤) · `많이 산 순` · `새 상품순`(확인된 것만, 없으면 `검색 결과` 하나). 칩은 `<a href target="_blank" rel="noopener noreferrer">`(앱이 깔려 있으면 폰이 앱으로 연다), 누르면 `LAST_STORE_KEY`에 그 쇼핑몰 저장 → 다음에 맨 위. 시트 아래 `mo-note` 아이콘 + `‘광고’가 붙은 링크로 사면 갈무리부엌이 수수료를 받을 수 있어요. 순서와는 상관없어요.`(제휴 쇼핑몰이 하나도 없으면 이 줄은 숨김). 오프라인이면 설명 대신 `인터넷이 연결되면 열려요`.
- [ ] **Step 0: 브랜치** — main(5·8 병합)에서 `feature/shopping-links-ui`.
- [ ] **Step 1: 시트 구현** — 검증 전이라 `onlyVerified`로 비어 있으면 시트에 `쇼핑몰 링크를 준비하고 있어요`. `npm run check && npm run build`.
- [ ] **Step 2: ⚠ 사용자 폰 검증(병합 전 필수, 에이전트가 대신할 수 없음)** — 사용자가 갤럭시 S22 Ultra(크롬·삼성 인터넷 둘 다)에서 `node scripts/check-store-links.mjs --print`로 뽑은 `대파`·`두부 한 모`(띄어쓰기)·`참기름` 링크를 하나씩 연다. 쇼핑몰×정렬마다 기록: ① 검색 결과가 그 검색어로 뜨는가 ② 정렬이 실제로 적용됐는가 ③ 앱으로 넘어가면 앱에서도 검색어가 유지되는가. "후보 없음" 칸은 사용자가 쇼핑몰에서 정렬을 바꾼 뒤 주소창 주소를 붙여 주면 반영한다. 결과를 PR 설명에 표로 남기고, **통과한 칸만 `STORES`에 남기고 나머지 정렬 칸은 지우며** 검색까지 안 되는 쇼핑몰은 `verified: null`로 둬 숨긴다. 통과한 쇼핑몰에 `verified: "2026-09-xx 사용자 폰 확인"`.
- [ ] **Step 3: 검사 갱신** — `check-store-links.mjs`에 검증된 쇼핑몰 수가 1개 이상임을 확인하는 줄. `npm run check && npm run build`.
- [ ] **Step 4: 폰 확인** — `두부` 쇼핑몰 아이콘 → 시트가 시안과 같음 → `컬리 · 낮은 가격순` 누름 → 돌아와 다른 항목 시트 → 컬리가 맨 위, 나머지 순서 그대로. 제휴 ID 없는 개발 환경에서 `광고`·아래 안내 줄 없음. 다크.
- [ ] **Step 5: 스펙** — 16절 URL 형식 확인 결과(날짜, 숨긴 정렬).
- [ ] **Step 6: 커밋** — `feat: 장보기 쇼핑몰에서 찾기 시트(쇼핑몰별 낮은 가격순·많이 산 순·새 상품순, 마지막으로 연 쇼핑몰 맨 위, 폰에서 확인한 주소만)`

---

### Task 10: 메모 카드·장보기 메모 화면 (시안 승인 후)

**시안(그대로 따른다):** `docs/design/shopping-4/MemoPage.dc.html`, 메모 카드는 `ShoppingList.dc.html`의 `sh-memo`

**Files:**
- Create: `frontend/src/pages/ShoppingMemo.tsx`
- Modify: `frontend/src/pages/Shopping.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/components/Icon.tsx`

**Interfaces:**
- Consumes: `useShopping`(`note_add`·`note_save`·`note_delete`·`addPhoto`·`photo_delete`·`photoBlob`·`backups`), `resizeImage`(image.ts, 긴 변 1568px), `goBack`
- Produces:
  - **메모 카드(`sh-memo`):** 아이콘 · 제목 `메모 · {어디서}`(어디서가 비면 `메모`) · 본문 첫 줄(`sh-memo-text`, 한 줄 말줄임) · 사진 썸네일(`sh-thumbs`, 최대 4개) · 오른쪽 화살표 → 가장 최근 메모의 장보기 메모 화면. 메모가 2개 이상이면 카드 아래 작은 링크 `메모 N개 더 보기` → `#/shopping/memos`(행: `어디서` 또는 `메모` · 본문 첫 줄 · 사진 수, 아래 `새 메모`). 메모가 없으면 같은 자리에 점선 카드 `메모 쓰기`(note_add 후 화면으로).
  - **경로:** `#/shopping/memo`(열 메모는 `sessionStorage`의 `shopping-memo-ref`에 `{id}` 또는 `{client_id}` — 오프라인에서 만든 메모도 열리고 새로고침에도 남음), `#/shopping/memos`.
  - **`MemoPage` — `ShoppingMemo.tsx`:** 뒤로 `장보기`, 제목 `장보기 메모`. `rc-sec` 안 `어디서`(input, 30자, 자리 표시 `이마트 성수점`) · `메모`(textarea `rc-area`, 16px, 2000자). **저장 버튼 없음 — 입력이 멈추고 1초 뒤와 화면을 나갈 때 `note_save`**(대기열이 합쳐 준다). 둘 다 비어 있고 사진도 없는 채로 나가면 메모를 지운다(빈 메모가 쌓이지 않게).
    - `rc-sec` `사진` 머리 + 오른쪽 `N / 10`(`hint`). `sh-photos` 칸: 썸네일들 + 마지막 칸 `사진 추가`(누르면 작은 시트 `사진 찍기`(`<input type="file" accept="image/*" capture="environment">`) · `앨범에서 고르기`(capture 없음)). 10장이면 `사진 추가` 칸을 숨긴다. 오프라인에서 찍은 사진은 기기 blob으로 바로 보이고 썸네일 모서리에 작은 `저장 전`.
    - 사진 아래 `btn secondary` 아이콘 + `사진에서 살 것 뽑기`(Task 11) — 사진이 0장이면 숨김.
    - 썸네일 누르면 전체 화면(`<dialog>`) 사진 보기: `이전 사진`·`다음 사진` 버튼(44px), 아래 `.btn.danger-text` `사진 삭제`(확인창).
    - 맨 아래 `rc-actions` `.btn.danger-text` `메모 삭제`(확인창 `메모와 사진을 삭제할까요?` → note_delete → `goBack("/shopping")`).
    - 겹친 메모(`backups`): 제목 아래 `mo-note` 모양 한 줄 `다른 기기에서 고친 메모가 있어서 이 기기에서 쓴 내용을 따로 보관했어요` + `보기`(보관 본문 시트, `이걸로 바꾸기` → note_save 새 edited_at / `지우기`).
    - 사진 올리기 503(저장소 꺼짐)은 실패 목록으로 가고 목록 띠에 보인다.
- [ ] **Step 0: 브랜치** — main(8 병합)에서 `feature/shopping-notes-ui`. 시안 `MemoPage` 열어 두기.
- [ ] **Step 1: 구현** — `npm run check && npm run build`.
- [ ] **Step 2: 폰 확인(adb reverse)** — 카드 `메모 쓰기` → `이마트 성수점`·본문 두 줄·사진 2장(온라인) → 뒤로 → 카드 `메모 · 이마트 성수점`·썸네일 2개 → 비행기 모드 → 앱 다시 열어 메모·사진이 보임 → 오프라인에서 본문 고치고 사진 1장 더(`3 / 10`) → 연결 → `backend/uploads/shopping/<id>/`에 파일 3개. 데스크톱에서 같은 메모를 먼저 고친 뒤 폰(오프라인에서 더 이른 시각에 고친 것)을 연결 → 보관 알림과 `이걸로 바꾸기`. 빈 메모로 들어갔다 나오면 카드가 다시 `메모 쓰기`. `메모 삭제` 연빨강이 맨 아래. 다크.
- [ ] **Step 3: 커밋** — `feat: 장보기 메모(어디서·메모·사진 10장, 자동 저장, 인터넷 없이 쓰고 찍기, 다른 기기와 겹치면 따로 보관)`

---

### Task 11: 사진에서 살 것 뽑기 (시안 승인 후)

**시안:** 입구는 `MemoPage.dc.html`의 `사진에서 살 것 뽑기`. 확인 화면 프레임은 없으므로 이미 승인된 스캔 확인 화면(`docs/design/scan-2/`, `ScanReview`)을 구입일·가격 칸 없이 따른다.

**Files:**
- Create: `frontend/src/components/MemoScanReview.tsx`
- Modify: `frontend/src/components/ScanSheet.tsx`(업로드·만드는 중·오류·한도 부분을 kind 인자로 재사용할 수 있게 — 재고 쪽 동작 그대로), `frontend/src/api.ts`(`ScanKind`에 `memo`), `frontend/src/pages/ShoppingMemo.tsx`

**Interfaces:**
- Consumes: Task 4 `/api/scan?kind=memo`, `useShopping.addMany`(source `memo`), `/api/ai-usage`(`오늘 N번 남음`), `photoBlob`
- Produces:
  - `사진에서 살 것 뽑기`: 사진이 1장이면 그 사진, 여러 장이면 작은 시트 `어느 사진에서 뽑을까요?`(썸네일 고르기). 기기 blob을 FormData로 보낸다(`ponytail:` 서버에 있는 사진도 다시 올리는 셈 — 서버 사진 키로 스캔하는 API는 필요해지면). `user.scan === "off"`면 버튼 숨김, 오프라인이면 누르면 `인터넷이 연결되면 할 수 있어요`. 버튼 아래 작은 회색 `오늘 N번 남음`.
  - 확인 화면 `찾은 재료 N개`: 행마다 체크(기본 모두 켬, **15개 넘으면 모두 끈 채로 시작 + `모두 선택`**) · 이름·수량(`quantityText`) 펼쳐 고치기. 넣을 곳은 `location_kind`로 첫 위치를 조용히 채운다(화면에 안 보임). 공통 `언제 살까요?` 칩 한 줄(AddSheet와 같은 칩). 하단 `N개 장보기에 담기` → `addMany("memo", …)` → `장보기에 N개 담았어요` + skipped 있으면 `이미 목록에 있는 대파는 뺐어요` → 장보기로.
  - 예시 모드(`sample`)는 기존 스캔과 같은 `예시 결과예요` 표시.
- [ ] **Step 0: 브랜치** — main(4·10 병합)에서 `feature/shopping-memo-scan-ui`.
- [ ] **Step 1: ScanSheet 재사용 정리** — 재고 화면 스캔(냉장고·영수증·주문) 흐름이 그대로인지 먼저 개발 서버에서 확인.
- [ ] **Step 2: 구현** — `npm run check && npm run build`.
- [ ] **Step 3: 폰 확인(키 없는 개발 모드)** — 메모 사진 2장 → `사진에서 살 것 뽑기` → 사진 고르기 → 예시 5개 → 하나 끄고 `두부` 수량 `2모` → 담기 → 목록 묶음에 4개(태그 `메모 사진`), 이미 있던 `대파`는 빠졌다는 문구. 재고 탭 스캔 3종류 그대로.
- [ ] **Step 4: 커밋** — `feat: 장보기 메모 사진에서 살 것 뽑기(확인하고 담기, 이미 있는 재료 건너뛰기)`

---

### Task 12: 재고에 넣기 화면 (시안 승인 후)

**시안(그대로 따른다):** `docs/design/shopping-4/StockIn.dc.html`

**Files:**
- Create: `frontend/src/pages/ShoppingStock.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/ScanReview.tsx`(영수증·주문 재고 등록 성공 뒤 제안), `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 2 `stock-draft`·`stock`·`match`·`mark-stocked`, `/api/locations`, `forgetResources`·`forgetRecipeCaches`(재고가 바뀌면 추천 캐시도), `useShopping.refresh`, `setLeaveGuard`
- Produces:
  - **`StockIn` — `#/shopping/stock`:** 뒤로 `장보기`, 제목 `재고에 넣기`, 요약 `체크한 N개를 재고로 옮겨요`. `rc-sec` `산 날`(date 입력, 표시 `오늘 · 9월 14일`, 오늘이 아니면 `9월 12일`). `rc-sec` 행 `sh-in-row`: 이름 + 수량 · 보조 줄 = 프리필 이유(`item` → `장보기에 적어 둔 곳`, `same_name` → `같은 이름 재료가 있던 곳`(시안), `default` → `기본 위치`) · 오른쪽 위치 select(`input` 모양 + 아래 화살표, 위치 이름). 안내 `mo-note` `재고에 넣으면 장보기 목록에서 빠져요. 유통기한은 재고에서 고칠 수 있어요.` 하단 `cta-bar` `actions`: `btn outline` `취소`(`goBack("/shopping")`) · `btn primary` `N개 넣기` → 성공 시 장보기로 `replace`, `refresh()`(넣은 것은 `산 것 N개`로), 재고·추천 캐시 비우기. 400 `목록이 방금 바뀌었어요…`면 초안을 다시 받는다. `N번째 재료` 오류는 그 행 빨간 테두리. 위치를 바꾸면 작성 중으로 보고 나가기 확인. 오프라인이면 화면 대신 `인터넷이 연결되면 넣을 수 있어요` + `장보기로`.
  - **영수증·주문 스캔 뒤(스펙 16절):** 재고 `ScanReview`에서 등록 성공 뒤 `match`로 찾은 게 있으면 시트 `장보기 목록에 있던 우유·양파도 샀나요?` / `재고에 넣은 걸로 장보기에서 뺄게요` + `btn primary` `장보기에서 빼기`(mark-stocked → `산 것`으로) · `btn outline` `그대로 두기`.
- [ ] **Step 0: 브랜치** — main(2·8 병합)에서 `feature/shopping-stock-ui`. 시안 `StockIn` 열어 두기.
- [ ] **Step 1: 구현** — `npm run check && npm run build`.
- [ ] **Step 2: 폰 확인** — 체크 2개 → 초록 막대 `재고에 넣기` → 시안과 같은 화면, 위치 프리필 이유(같은 이름 재료가 있는 `대파`는 `같은 이름 재료가 있던 곳`) → `2개 넣기` → 재고 탭에 2개, 장보기 막대 사라짐·`산 것 2개` 접기에 보임 → 펼쳐 `다시 담기`. 영수증 예시 스캔 → 재고 등록 → `우유`가 목록에 있으면 제안 → 빼기 → `산 것`으로. 다크.
- [ ] **Step 3: 커밋** — `feat: 체크한 장보기 항목 재고에 넣기 화면(산 날 하나·위치 프리필 이유), 영수증 등록 뒤 장보기에서 빼기 제안`

---

### Task 13: 다른 화면에서 장보기에 담기 (시안 승인 후)

**시안(그대로 따른다):** `docs/design/shopping-4/RecipeEntry.dc.html`

**Files:**
- Modify: `frontend/src/pages/RecipeDetail.tsx`(`RecipeBody`에 선택 prop `onAddMissing`), `frontend/src/pages/RecipeAi.tsx`(같은 prop), `frontend/src/components/StaplesSheet.tsx`, `frontend/src/components/IngredientForm.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `useShopping.addMany`(Task 7, source `recipe`·`staple`·`urgent`·`manual`), 레시피 상세 `ingredients[].have`
- Produces:
  - **`RecipeEntry`:** 레시피 상세(내 레시피·공공·AI 자세히)의 `재료` 섹션 목록 바로 아래, 없는 재료가 있을 때만 `btn outline sh-missing-cta` 장바구니 아이콘 + `없는 재료 N개 장보기에 담기`. **누르면 고르기 없이 한 번에 담는다**(`addMany("recipe", 없는 재료 이름들, 레시피 제목)`, 수량은 담지 않음 → `1개`, 개별로 빼는 건 장보기에서). 담는 중 버튼 비활성 `담는 중…`, 끝나면 버튼이 체크 아이콘 + `장보기에 담았어요`(비활성)로 바뀌고 아래 `role="status"` 한 줄 `장보기에 N개 담았어요`(+ skipped 있으면 ` · 이미 있는 대파는 뺐어요`). 오프라인·실패는 같은 줄에 오류 문구. `ponytail:` 레시피 양(`1작은술`)은 단위가 달라 담지 않는다 — 23절 D4 합산은 4b.
  - **필수품 시트**(재고 배너 `필수품 N개가 떨어졌어요` → 떨어진 것만 보기): 떨어진 게 있으면 목록 아래 같은 모양 `떨어진 필수품 N개 장보기에 담기` → `addMany("staple", …)`, 결과 표시도 같음(태그 `필수품`).
  - **재료 고치기 시트**(`IngredientForm` 수정 모드): 삭제 버튼보다 위에 `btn outline` `장보기에 담기` → `addMany(상태가 urgent·danger면 "urgent" 아니면 "manual", [{name, quantity, unit}])` → 버튼이 `장보기에 담았어요`로(태그 `곧 떨어져요`). 삭제 이유 `다 먹었어요` 뒤 제안은 넣지 않는다.
- [ ] **Step 0: 브랜치** — main(8 병합)에서 `feature/shopping-entry-points`.
- [ ] **Step 1: 구현** — `npm run check && npm run build`.
- [ ] **Step 2: 폰 확인** — 두부조림 상세(없음 2개) → 시안과 같은 버튼 → 누름 → `장보기에 담았어요` → 장보기 `날짜 미정`에 `다진 마늘`·`청양고추`, 태그 `레시피 · 두부조림` → 같은 레시피를 다시 열어 누름 → `이미 있는 …뺐어요`. 재고 배너 → 필수품 시트 → 담기(태그 `필수품`). 임박 재료 고치기 시트 → `장보기에 담기`(태그 `곧 떨어져요`). 삭제 버튼이 여전히 맨 아래 연빨강.
- [ ] **Step 3: 커밋** — `feat: 레시피 없는 재료·떨어진 필수품·재료 고치기에서 장보기에 한 번에 담기`

---

## 4단계 완료 기준

- 백엔드: SQLite·PostgreSQL 테스트 실패 0, 경고 0, 네트워크 차단 픽스처 켠 채. `flask db heads` 하나, 개발 DB `flask db check` 차이 없음.
- 프론트엔드: `npm run check`(`seasoning ok`·`store links ok`·`shopping sync ok`) + `matchRoute ok` + `npm run build` 성공. `dist/index.html`에 외부 글꼴 주소 없음.
- 13개 브랜치가 순서대로 main에 `--no-ff` 병합됨.
- 화면이 시안 8개 프레임(`ShoppingDark` 포함)과 문구·배치가 같다.
- 폰(adb reverse 또는 https 배포)에서: 비행기 모드로 앱을 새로 열어 장보기 목록·메모·사진이 보이고, 체크·추가·메모 수정·사진 찍기 후 연결하면 모두 서버에 반영되며 `기다리는 중 N건`이 사라진다.
- 쇼핑몰 링크 표가 사용자 폰 검증을 거쳤고(스펙 16절에 날짜), 검증 안 된 정렬 칩은 보이지 않는다. 제휴 ID가 없으면 `광고` 표시가 하나도 없다.
- 운영 설정(DEV_MODE 끔, 키·R2 없음)에서 `사진에서 살 것 뽑기`가 숨고 사진 올리기가 503 문구로 끝난다.

## 시안 승인 결정 (2026-09-14, 스펙 16·19·26·27절에 반영함)

1. 체크한 항목은 제자리에서 줄 긋기(다시 누르면 해제), 다시 열어도 내려가지 않는다. 재고에 넣은 항목은 목록에서 빠지고 맨 아래 접힌 `산 것 N개`(최근 7일)에 남는다 — `stocked_at` 칸 하나, 7일 지나면 스냅숏 요청 때 지움(30일 보관은 보여줄 곳이 없어 7일로 줄임).
2. 쇼핑몰에서 찾기 시트: 쇼핑몰 × 칩(`낮은 가격순 · 많이 산 순 · 새 상품순`), 마지막으로 연 쇼핑몰 맨 위(localStorage), 나머지 고정 순서, 제휴 쇼핑몰 이름 옆 `광고`, 아래 수수료 안내 한 줄. 항목별 `store` 칸은 두지 않는다.
3. 체크한 항목이 있을 때만 목록 위 초록 막대 `체크한 N개를 재고에 넣을까요?` + `재고에 넣기`.
4. 레시피 상세 버튼 하나 `없는 재료 N개 장보기에 담기`로 한 번에 담고(중복 건너뛰기), 빼기는 장보기에서.
5. 살 것 추가 시트: 이름 + 수량 한 줄, `언제 살까요?` 칩 `오늘 · 이번 주 · 날짜 미정 · 날짜 고르기`, 버튼 `계속 추가` / `추가`. 넣을 곳·쇼핑몰 칸 없음(`더 적기`도 두지 않음).
6. 행 오른쪽 쇼핑몰 아이콘 버튼, `aria-label="{이름} 쇼핑몰에서 찾기"`.
7. 장보기 메모는 별도 화면 `장보기 메모`(어디서·메모·사진 N/10·`사진에서 살 것 뽑기`·아래 연빨강 `메모 삭제`), 저장 버튼 없이 자동 저장. 메모는 여러 개(최대 20), 카드는 최근 1개 + `메모 N개 더 보기`. 메모 `planned_on` 칸은 두지 않는다.
8. 나머지 추천 기본값 수락: `이번 주` = 오늘부터 7일(칩은 오늘+6일로 저장), 그 뒤 날짜는 `나중에` 묶음, 지난 날짜는 `오늘`; 오프라인 띠는 장보기 탭(다른 탭은 기존 오류 처리); 전단지 결과 15개 넘으면 모두 끈 채로; 재고에 넣기는 별도 화면; 레시피 재료는 이름만; 임박 재료 입구는 재료 고치기 시트 버튼만; 오프라인 사진은 상한 안에서 전부 기기 보관.

## 남은 결정 (시안 승인 뒤에도 열려 있는 것)

- 쇼핑몰 URL 표 — **사용자 폰 검증 필요**(Task 9 Step 2). 검증 전에는 시트가 `쇼핑몰 링크를 준비하고 있어요`.
- 제휴 링크 형식 — 쿠팡 파트너스 등 가입 후 형식 확인(Render 배포 후, 25절). 그 전에는 `AFFILIATE_FORMATS` 비움 → `광고` 없음. 쿠팡 등은 ID만으로 링크를 만드는 공개 형식이 없을 수 있다(링크 생성 API가 필요하면 그때 설계).
- `@fontsource/ibm-plex-sans-kr` — 구현 때 패키지·한글 조각을 확인하고, 없으면 공식 배포 400·700만 자체 호스팅(사용자에게 알림).
- 빈 장보기 화면·저장 실패 띠·사진 보기 화면·메모 목록·메모 인식 확인 화면 — 시안 프레임이 없어 위 태스크의 기존 모양 재사용안으로 만든다. 따로 시안이 필요하면 Task 8 전에 알려준다.
