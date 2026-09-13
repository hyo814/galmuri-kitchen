# 냉장고 레시피

냉장고 속 재료를 기록해 두면, 상하기 전에 알려 주고 떨어진 필수품을 챙겨 주는 모바일 우선 웹 서비스.

재료를 넣은 날짜와 보관 위치만 적어 두면 곧 먹어야 할 재료가 위로 올라오고, 늘 있어야 하는 필수품이 떨어지면 첫 화면에 표시됩니다.
두부·요거트·햄처럼 날짜가 헷갈리는 품목은 식약처 소비기한 참고값을 바탕으로 경고합니다.
네이티브 앱 없이 휴대폰 브라우저에서 바로 쓰도록 만들고 있으며, 사진 스캔·레시피 추천·장보기·식단은 순서대로 준비 중입니다.

## 주요 기능

### 구현됨 (1단계 · 1b · 1c)

- **로그인**: 카카오·구글 소셜 로그인 준비 완료(키를 넣으면 버튼이 나타남). 로컬에서는 개발용 로그인.
- **재고 관리**: 재료 이름·수량·단위·구입일·유통기한(선택) 등록, 수정, 삭제.
- **보관 위치**: 기본 `냉장실`·`냉동실`·`실온`에 더해 사용자가 직접 위치를 만들고(예: 김치냉장고, 찬장) 위치별로 걸러 보기.
- **임박·오래됨 배지**: `D-2`, `구입 9일째`, `섭취 주의` 같은 배지로 곧 먹어야 할 재료를 위로.
- **필수품**: 대파·참기름처럼 늘 있어야 하는 재료를 등록해 두면, 재고에 없을 때 상단 배너로 알림.
- **품목별 경고 규칙**: 식약처 「식품유형별 소비기한 설정 보고서」 참고값(두부 23일, 발효유 32일, 과채주스 35일, 빵류 31일, 어묵 42일, 소시지 56일, 햄 57일)을 기본 제공.
  참고값은 제조일 기준이라 구입일 기준으로는 80%(내림)에서 빨강, 그 3일 전부터 노랑으로 판정합니다.
  달걀·계란은 사용자 결정에 따라 구입 30일. 우유는 소비기한 표시제가 2031년부터라 규칙을 두지 않고, 포장의 날짜 입력을 안내합니다.
  모든 규칙은 사용자가 수정·삭제할 수 있습니다.
- **판정 우선순위**: 직접 입력한 유통기한이 규칙보다 우선, 냉동실 재료는 품목 규칙을 쓰지 않음.
- **주방 도구**: 도구 목록과 주기 점검. 코팅 프라이팬은 6개월 점검을 제안(식약처는 코팅이 30% 이상 벗겨지면 교체를 권고).
- **하단 탭 + 해시 라우팅**: `#/`, `#/more`, `#/tools`. 휴대폰 뒤로가기 버튼이 그대로 동작.
- **디자인**: 라이트·다크 테마, 텍스트 대비 WCAG AA(4.5:1) 기준으로 조정, 터치 영역 44px 이상.

### 준비 중

순서대로 진행합니다. 아직 동작하지 않습니다.

0. **1d단계 사용성 개선**(계획 작성됨): 페르소나 사용성 점검에서 고른 항목. 재료 연속 추가, 재고 검색, 짧은 이름 매칭 오탐 차단, 필수품 시트 정리.
1. **AI 스캔**: 냉장고 사진·영수증·온라인 주문 완료 화면 → Claude 비전 → 확인 후 일괄 등록. API 키가 없으면 샘플 데이터로 동작.
2. **레시피**: 내 레시피, 식약처 공공 레시피 DB, AI 추천, 유튜브·인스타그램 링크 가져오기, 숟가락 단위 양념 비율 계산기.
3. **장보기**: 쇼핑몰 7곳 검색·정렬 링크, 네이버 최저가, 매장 장보기(메모·사진·동기화).
4. **식단·영양**: 1주·1달 식단, 다이어트 AI 초안, 기초대사량(Mifflin–St Jeor), 식약처 식품영양성분 DB 기반 칼로리·당류 합산, 먹은 것 기록.
5. **조리 기록**
6. **Render 배포**

## 화면

- 개발자 포트폴리오(케이스 스터디): [`docs/site/portfolio.html`](docs/site/portfolio.html)
- 제품 소개 페이지: [`docs/site/product.html`](docs/site/product.html)

두 페이지 모두 외부 이미지 없이 앱의 실제 디자인 토큰으로 화면을 그린 정적 HTML입니다. 브라우저에서 파일을 바로 열면 됩니다.
실제 앱 스크린샷은 배포 이후 추가할 예정입니다. 배포 주소도 아직 없습니다.

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 프론트엔드 | React 19, TypeScript, Vite 8, 순수 CSS(모바일 우선) |
| 백엔드 | Python 3.14, Flask 3.1, Flask-SQLAlchemy, Flask-Migrate(Alembic), Authlib |
| 데이터베이스 | PostgreSQL 17(운영·검증), SQLite(로컬·테스트) |
| 테스트 | pytest |
| 실행·배포 | Docker(멀티 스테이지, 비루트 사용자), gunicorn, Render(예정) |

Flask 한 앱이 `/api/*`와 React 빌드 결과를 같은 오리진에서 서빙합니다(CORS 없음).

## 폴더 구조

```
.
├── backend/
│   ├── app/                 Flask 앱 (재료, 보관 위치, 필수품, 품목 규칙, 주방 도구, 인증)
│   ├── migrations/          Alembic 마이그레이션 (기존 사용자 기본값 시드 포함)
│   ├── tests/               pytest
│   ├── requirements.txt     운영 의존성
│   ├── requirements-dev.txt 개발·테스트 의존성
│   └── .env.example         환경 변수 예시
├── frontend/
│   ├── src/
│   │   ├── pages/           재고, 더보기, 주방 도구, 로그인
│   │   ├── components/      시트, 폼, 하단 탭, 아이콘
│   │   └── styles.css       디자인 토큰(라이트·다크)
│   ├── public/              PWA manifest, 아이콘
│   └── vite.config.ts       개발 서버 5180, /api·/auth → 5181 프록시
├── docs/
│   ├── superpowers/specs/   설계 문서
│   ├── superpowers/plans/   단계별 구현 계획
│   ├── design/fridge-1b/    승인된 화면 시안
│   ├── site/                포트폴리오·제품 소개 페이지
│   └── deploy.md            배포 가이드와 배포 전 로컬 검증
├── dev.sh                   로컬 개발 서버 실행
└── Dockerfile
```

## 로컬 실행

macOS 기준이며, 각 명령은 저장소 루트에서 시작합니다. 저장소 경로에 공백이 있으면 따옴표로 감싸 주세요.

1. 백엔드 가상환경과 의존성
   ```
   cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
   ```
   테스트 없이 앱만 돌릴 때는 `requirements.txt`만 설치해도 됩니다.
2. 프론트엔드 의존성
   ```
   cd frontend && npm install
   ```
3. 환경 변수 파일
   ```
   cp backend/.env.example backend/.env
   ```
   예시 파일에는 `DEV_MODE=1`이 켜져 있어 개발용 로그인을 쓸 수 있습니다. 소셜 로그인 키는 비워 두면 해당 버튼이 숨겨집니다.
4. 개발 서버
   ```
   ./dev.sh
   ```
   - 마이그레이션(`flask db upgrade`) 후 Flask를 `127.0.0.1:5181`, Vite를 `0.0.0.0:5180`에서 띄웁니다.
   - 휴대폰은 같은 와이파이에서 `http://<맥 IP>:5180`으로 접속합니다. 스크립트가 시작할 때 주소를 출력합니다.
   - 로그인 화면의 **개발용 로그인** 버튼으로 들어갑니다. OAuth 리다이렉트 URI에 사설 IP를 등록할 수 없어서 `DEV_MODE=1`일 때만 열리는 기능이며, 운영에서는 `DEV_MODE`를 넣지 않습니다.
   - 포트가 이미 쓰이고 있으면 다른 번호로 옮기지 않고 실패합니다(strictPort).

## 테스트

[`docs/deploy.md`](docs/deploy.md)의 배포 전 로컬 검증과 같은 명령입니다. 저장소 루트에서 실행합니다.

SQLite:
```
backend/.venv/bin/pytest -q -W error::DeprecationWarning
```

PostgreSQL (`brew install postgresql@17` 필요):
```
brew services start postgresql@17
createdb recipe_ai_test
createdb recipe_ai_migrate
TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test \
TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate \
backend/.venv/bin/pytest -q -W error::DeprecationWarning
```

현재 백엔드 테스트 138개가 SQLite와 PostgreSQL 모두에서 경고 없이 통과합니다.
프론트엔드는 `cd frontend && npm run build`(`tsc --noEmit` + `vite build`)로 확인합니다.

## 배포

Render(Docker + PostgreSQL) 배포 절차, 환경 변수 표, 배포 전 체크리스트, 마이그레이션 점검과 Docker 스모크 테스트는 [`docs/deploy.md`](docs/deploy.md)에 있습니다.
아직 배포하지 않았습니다.

## 개발 방식

1. **설계 문서**: 요구사항과 결정을 먼저 [설계 문서](docs/superpowers/specs/2026-09-13-recipe-ai-design.md)에 적습니다. 중간에 요구사항이 늘면 코드보다 문서를 먼저 고칩니다.
2. **구현 계획**: 단계마다 태스크 단위 계획을 씁니다.
   - [1단계: 기반](docs/superpowers/plans/2026-09-13-phase1-foundation.md)
   - [1b단계: 보관 위치·필수품·품목별 경고](docs/superpowers/plans/2026-09-13-phase1b-locations-staples-rules.md)
   - [1c단계: 하단 탭·주방 도구](docs/superpowers/plans/2026-09-13-phase1c-tabs-kitchen-tools.md)
   - [1d단계: 사용성 개선](docs/superpowers/plans/2026-09-13-phase1d-usability.md) (계획만 작성, 구현 전)
3. **기능 브랜치**: `feature/*`, `fix/*`, `docs/*`, `chore/*` 브랜치에서 작업하고 `main`에 `--no-ff`로 병합합니다(`git log --oneline --graph`).
4. **리뷰**: 태스크마다 독립 코드 리뷰, 단계 끝에 브랜치 전체 리뷰. 리뷰 지적은 `fix/*` 브랜치로 반영합니다.
5. **휴대폰 확인**: 단계마다 실제 휴대폰에서 주요 흐름을 확인하는 체크포인트를 둡니다.

## 로드맵

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 로그인, 재료 등록, 임박 표시 | 완료 |
| 1b | 보관 위치, 필수품, 품목별 경고, 새 디자인 | 완료 |
| 1c | 하단 탭, 주방 도구 | 완료 |
| 1d | 사용성 개선(연속 추가, 재고 검색, 매칭 오탐, 필수품 시트) | 계획 작성됨 |
| 2 | AI 사진·영수증·주문 캡처 스캔 | 준비 중 |
| 3 | 레시피(내 레시피, 공공 DB, AI, 링크 가져오기, 양념 비율 계산기) | 준비 중 |
| 4 | 장보기(쇼핑몰 링크, 네이버 최저가, 매장 장보기) | 준비 중 |
| 4b | 식단·영양(식단 달력, 기초대사량, 칼로리·당류, 먹은 것 기록) | 준비 중 |
| 5 | 조리 기록 | 준비 중 |
| - | Render 배포 | 준비 중 |

## 작성자

- 이름: [이름]
- 이메일: [이메일]
- GitHub: [GitHub]
