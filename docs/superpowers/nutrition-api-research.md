# 4b-2 영양 계산 — 식약처 영양성분 API 조사 (2026-09-15)

스펙 §20(다이어트 AI 초안 kcal 추정 → "정확한 영양성분은 범위 밖, 필요해지면 추가"), §21(영양 계산기),
§23 D4(식단→장보기 수량 비교), §24(먹은 기록 달력)를 전제로 조사. 코드 변경 없음, 조사 전용.

## 1. 기존 FOODSAFETY_API_KEY로 I2790/I0750 호출 가능한가 — **불가 (실측 확인)**

`.env`에 `FOODSAFETY_API_KEY`(길이 20, COOKRCP01에 쓰는 그 키)가 설정돼 있다.
`backend/.venv/bin/python`으로 `dotenv_values()`만 써서 키를 변수에만 로드하고(출력·기록 없음),
`https://openapi.foodsafetykorea.go.kr/api/{key}/{서비스}/json/1/5` 패턴으로 실제 호출했다(키는 URL에서 항상 REDACTED로만 출력).

| 서비스 | HTTP | RESULT | 비고 |
|---|---|---|---|
| `I2790` | 200 | `ERROR-310` — "해당하는 서비스를 찾을 수 없습니다. 요청인자 중 SERVICE를 확인하십시오." | 같은 키로 실패 |
| `I0750` | 200 | `ERROR-310` — 위와 동일 | 같은 키로 실패 |
| `COOKRCP01` (대조군) | 200 | `INFO-000` 정상처리, `total_count: 1156` | **같은 키가 COOKRCP01은 정상 동작** → 키 자체는 유효, 문제는 서비스별 등록/가용성 |

**결론: 현재 키로는 안 된다.** 키 자체는 살아있고(COOKRCP01 정상), I2790·I0750만 `ERROR-310`(서비스를 찾을 수 없음)을 반환한다.
`.env.example`의 "인증키 하나로 식품안전나라 여러 API를 함께 써요"라는 안내와 달리, 최소한 이 두 서비스는 별도 신청이 필요하거나(식품안전나라는 서비스마다 개별 승인이 필요한 경우가 있음) — 더 근본적으로는 **`I2790` 서비스 자체가 폐지·이전됐을 가능성이 크다**(아래 3절). 새 키를 발급해도 같은 엔드포인트로는 안 될 수 있다는 뜻이므로, 재신청보다 먼저 3절의 후속 서비스 경로를 확인하는 게 순서.

참고: `.env`에는 `FOOD_NUTRITION_API_KEY`도 이미 값이 들어 있다(길이 102 — 공공데이터포털 일반인증키(Decoding) 형식과 일치. `.env.example`은 "아직 만들지 않았어요, 지금은 비워 둬요"라고 안내했는데 이미 채워져 있음). 이번 조사 지시에 따라 **이 키로는 라이브 호출을 하지 않았다**(3번 질문은 문서 조사만 하라고 명시됨) — 4b-2 구현 시 이 키를 공공데이터포털 쪽(3절)으로 테스트해볼 것.

스크래치 스크립트: `/private/tmp/claude-501/-Users-limhyojin-PycharmProjects--recipe-ai/8f858f72-ed2d-44e7-90a3-2de729b7e8d2/scratchpad/nutrition/test_nutrition_api.py` (프로젝트 밖, 커밋 대상 아님).

## 2. 필드 정의 (I2790 식품영양성분DB 기준, 문서·예제 기반)

URL 패턴은 COOKRCP01과 동일 계열:
`http://openapi.foodsafetykorea.go.kr/api/{key}/I2790/{json|xml}/{start}/{end}` (뒤에 조건을 경로 세그먼트로 이어 붙임, 예: `.../1/5/DESC_KOR=하리보`).

| 필드 | 의미 |
|---|---|
| `DESC_KOR` | 식품명(국문) — **이름 검색은 이 필드를 URL 경로에 조건으로 붙여서 한다** (COOKRCP01의 `RCP_NM=` 방식과 동일 관례) |
| `FOOD_CD` | 식품코드(고유 식별자) — 로컬 캐시 테이블의 UNIQUE 키로 쓸 것 |
| `GROUP_NAME` | 식품 분류(카테고리) |
| `NUTR_CONT1` | 에너지 (kcal) |
| `NUTR_CONT2` | 탄수화물 (g) |
| `NUTR_CONT3` | 단백질 (g) |
| `NUTR_CONT4` | 지방 (g) |
| `NUTR_CONT5` | **당류 (g)** |
| `NUTR_CONT6` | **나트륨 (mg)** |
| `NUTR_CONT7` | 콜레스테롤 (mg) |
| `NUTR_CONT8` | 포화지방 (g) |
| `NUTR_CONT9` | 트랜스지방 (g) |
| `SERVING_SIZE` | 영양성분 함량 기준량 — 보통 100g 기준(값 확인 필요, "1회섭취참고량"과 별도 필드가 있을 수 있음) |
| `NUM`, `RESEARCH_YEAR`, `MAKER_NAME`, `SUB_REF_NAME`, 샘플링 지역/월 필드 | 메타데이터 |

페이징: 식약처(openapi.foodsafetykorea.go.kr) 계열은 요청당 최대 1,000행, 요청 한도는 서비스마다 다름(문서상 개발 단계 1만 콜, 운영은 사용 사례 등록 후 확장). COOKRCP01 예로는 `total_count`를 그대로 믿지 않고 상한을 두는 게 이 저장소 관행(`public_recipes.py`의 `MAX_TOTAL_ROWS`) — I2790도 같은 방어가 필요.

**주의**: 이 필드 목록은 GitHub 예제·검색 요약에서 재구성한 것이라 실측이 아니다(키가 통과하지 않아 실제 응답을 못 봤다). 새 키/새 서비스로 뚫리면 필드명·타입을 다시 실측 확인할 것.

## 3. I2790는 사실상 구식(~2023) 서비스일 가능성 — 후속: K-FIND

식품안전나라 API 설명 페이지 제목 자체가 **"식품영양성분DB(~2023)"**다
(https://www.foodsafetykorea.go.kr/api/openApiInfo.do?menu_grp=MENU_GRP31&menu_no=661&show_cnt=10&start_idx=1&svc_no=I2790).
검색 결과 종합: 기존 I2790 서비스는 **K-FIND 식품영양성분 데이터베이스**(https://various.foodsafetykorea.go.kr/nutrient/)로 통합·이전된 것으로 보인다.
K-FIND 쪽 Open API 안내 페이지(`/nutrient/industry/openApi/info.do`)는 JS 렌더링이라 WebFetch로 서비스ID·엔드포인트를 못 읽었다 — **직접 로그인해서 신청 화면까지 들어가 확인이 필요**.
즉 오늘 실측한 `ERROR-310`은 "이 키에 이 서비스가 승인 안 됨"과 "이 서비스 자체가 이 엔드포인트에서 더는 안 됨" 두 원인이 겹쳐 있을 수 있다.

## 4. 공공데이터포털(data.go.kr) 대안 — 문서 조사만 (키 미사용)

- 데이터셋: **식품의약품안전처_식품영양성분DB정보** — https://www.data.go.kr/data/15127578/openapi.do
- 별도 신청 필요: data.go.kr 회원가입 → 데이터셋 페이지에서 **활용신청** → 승인 후 마이페이지에서 **일반 인증키(Decoding)** 발급(Encoding 키 아님). `.env.example` 203~212행에 이미 이 안내가 적혀 있다.
- 인증 방식: `serviceKey` 파라미터(공공데이터포털 표준 REST), 식품안전나라 키(`FOODSAFETY_API_KEY`)와는 **별개 키 체계** — 즉 지금 있는 COOKRCP01용 키로는 안 되고, 이 API는 이 전용 키가 있어야 한다.
- 트래픽: 개발단계 1만 콜/일 수준, 운영 전환 시 활용사례 등록해 확장.
- 필드: I2790과 사실상 같은 원천 데이터(식품명·분류·식품코드·영양성분 함량 기준량·에너지·탄수화물·단백질·지방 등·출처·1회섭취참고량·식품중량 등).
- 참고: 식의약 데이터포털(data.mfds.go.kr)에서도 같은 데이터셋에 접근하는 경로가 있다(`data.mfds.go.kr/OPCAA01F01`) — data.go.kr과 이곳 중 어느 쪽이 최신·권장 경로인지는 실제 신청 화면에서 재확인 필요.
- **`.env`의 `FOOD_NUTRITION_API_KEY`(길이 102)가 이미 이 계열(데이터활용포털 Decoding 키) 형식과 맞아떨어진다** — 구현 시 이 키로 먼저 시도해볼 가치가 있다(단, 이번 조사 지시상 라이브 테스트는 하지 않았음).

## 5. 화면에 표시할 공인 기준값

- **당류 1일 기준치 100g / 나트륨 1일 기준치 2,000mg**: 식품등의 표시·광고에 관한 법률 시행규칙 [별표5] "1일 영양성분기준치"(하루 2,000kcal 섭취 기준). 근거 법령: https://www.law.go.kr/LSW/flDownload.do?gubun=&flSeq=156389317&bylClsCd=110201 (2022. 11. 28 개정 별표5), 최초 당류 100g 기준 도입은 2020. 9. 9 개정. 참고 보도: https://www.chungbuk.go.kr/sobi/selectBbsNttView.do?key=1575&bbsNo=218&nttNo=24165
- **WHO 유리당(free sugars) 권고**: 성인·아동 모두 총 에너지 섭취의 10% 미만(강한 권고), 5% 미만이면 추가 건강 이득(조건부 권고). 5%는 평균 성인 기준 하루 약 25g(약 6티스푼)에 해당.
  출처: WHO Guideline: Sugars intake for adults and children — https://www.who.int/publications/i/item/WHO-NMH-NHD-15.3 , NCBI Bookshelf 요약 https://www.ncbi.nlm.nih.gov/books/NBK285525/
- **Mifflin–St Jeor 공식**:
  - 남성 BMR = 10×체중(kg) + 6.25×키(cm) − 5×나이 + 5
  - 여성 BMR = 10×체중(kg) + 6.25×키(cm) − 5×나이 − 161
  - 활동계수(널리 쓰이는 5단계, 스펙의 "거의 없음·가벼움·보통·많음·매우 많음"과 그대로 대응): 거의 없음(좌식) ×1.2, 가벼움(주 1-3회 가벼운 운동) ×1.375, 보통(주 3-5회) ×1.55, 많음(주 6-7회) ×1.725, 매우 많음(매일 강도 높은 운동·육체노동) ×1.9.
  - 출처: Mifflin MD et al. 1990 원 논문 기반 요약 — Medscape 계산기 https://reference.medscape.com/calculator/846/mifflin-st-jeor-equation-calculator , 미국영양및식이요법학회(AND) 성인 체중관리 가이드라인 https://www.andeal.org/vault/pq130.pdf
- **다이어트 목표 kcal 하한**: 2020 한국인 영양소 섭취기준(KDRIs, 보건복지부·한국영양학회, 2020-12-22 발표 — https://www.mohw.go.kr/board.es?mid=a10411010100&bid=0019&tag=&act=view&list_no=370012 , 원문 https://www.kns.or.kr/FileRoom/FileRoom_view.asp?idx=108&BoardID=Kdr)에는 "다이어트 최소 kcal" 같은 직접적인 하한 수치가 검색으로는 확인되지 않았다. **원문 PDF(에너지·다량영양소 편)를 직접 열어 확인이 필요** — 지금은 KDRIs에서 확답을 못 찾았다.
  실무에서 흔히 쓰이는 하한(여성 1,200kcal / 남성 1,500kcal 부근)은 KDRIs 고유 수치가 아니라 일반적인 저열량식이 안전 기준(의료 상담 권고 기준)에 가깝다 — 스펙이 요구한 "공인 권고치"로 인용하려면 이 숫자보다는 **"필요량 − 500kcal 계산 결과가 자신의 BMR(기초대사량)보다 낮아지지 않게 한다"**를 1차 방어선으로 두고, 화면에는 "이 계산기는 참고용이며 극단적으로 낮은 목표는 권장하지 않는다"는 문구(스펙 §21 "의료 조언이 아니라 참고용")로 감싸는 편이 안전. KDRIs 최소 에너지 필요추정량(EER) 원문 확인은 후속 작업으로 남긴다.

## 6. 4b-2 데이터 접근 방식 추천

1. **로컬 캐시 테이블 우선, 온디맨드 조회 + 캐시** (스펙 §21이 이미 이 구조를 명시: `food_nutrients(food_code UNIQUE, name, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg, source)`).
   - "자주 쓰는 식품을 미리 시드"보다는(레시피 재료 이름 공간이 넓고 사전 시드는 커버리지가 낮음) **레시피 저장/식단 계산 시점에 이름 매칭 → API 조회 → `food_nutrients`에 upsert**가 ponytail에 맞다. COOKRCP01처럼 배치로 전량 동기화할 이유가 없다(레시피 6만+ vs 자주 쓰는 재료 수백 개 수준).
   - 캐시 키는 `FOOD_CD`(API가 주는 고유 식별자). 재조회 방지.
2. **재료→식품 매칭은 기존 `app/matching.normalize` 그대로 재사용** — 스펙 §21이 "이름 매칭(4절) 후보를 보여주고 사용자가 확정"이라 명시했고, §23이 "이름 매칭 오탐 수정은 `names_match` 한곳에 적용하므로 3·4·4b단계 매칭에도 그대로 쓰인다"고 이미 못박음. 새 매칭 로직을 만들 필요 없음 — `normalize()`로 후보를 좁히고 `names_match`/`match_prepared`로 API 검색 결과(`DESC_KOR`) 후보 리스트와 비교해 사용자에게 후보를 보여주면 됨. 확정 결과는 스펙대로 `food_matches`(사용자별)에 저장.
3. **단위 환산(개·모·단·봉)**: `app/amounts.py`의 `parse_amount`는 재료 텍스트를 `(수량, 단위)`로만 쪼갤 뿐, 단위→그램 환산표는 없다(확인 완료 — `개`/`모`/`단` 같은 셀 수 있는 단위는 그대로 "개" 단위로 남는다). API의 `SERVING_SIZE`(1회 섭취참고량, 보통 g 단위)가 **식품별 기본 중량**에 해당하므로, 그램 환산이 필요한 식품은 이 필드를 쓰고, 없거나 매칭 실패 시 스펙이 이미 정한 대로 AI 추정 + 화면에 "추정" 표시로 폴백한다. 전역 "개=몇g" 표를 새로 만들 필요는 없다 — 식품 단위로 이미 API가 준다.
4. 계산 파이프라인: 레시피 재료 텍스트 → `parse_amount`(수량/단위 파싱, 기존 §23 D4 로직 재사용) → `matching.normalize` 후보 → 사용자가 `food_matches`에서 확정한 `food_code` → `food_nutrients` 캐시 조회(없으면 API 호출 후 upsert) → 인분/양 비율로 스케일 → 레시피/끼니/하루/식단 기간 단위로 합산.
5. 키 확보 순서 제안: ① `FOOD_NUTRITION_API_KEY`(이미 `.env`에 있음, data.go.kr 계열로 추정)로 3절 엔드포인트를 먼저 시도 → ② 안 되면 K-FIND(various.foodsafetykorea.go.kr) 최신 API 신청 → ③ 그래도 안 되면 식품안전나라에 I2790/I0750 개별 서비스 신청 문의(1899-5590).

## 블로커 / 후속 확인 필요

- **현재 키로는 4b-2를 실제 데이터로 구현할 수 없다** — 새 키 신청(1~2 서비스 중 하나) 또는 이미 있는 `FOOD_NUTRITION_API_KEY`의 실제 동작 확인이 선행돼야 함(이번 조사 범위 밖).
- I2790 서비스가 살아있는지, K-FIND로 완전히 대체됐는지 **실측 확인 안 됨**(문서 검색 정황상 이전 가능성 높음).
- I2790 응답 필드명·타입은 3자 출처(GitHub 예제, 검색 요약)로 재구성한 것이라 **실제 페이로드로 재검증 필요**(키가 뚫리는 대로 1~2 rows로 재확인).
- KDRIs 2020 원문에서 "다이어트 최소 kcal" 관련 직접 문구를 찾지 못함 — 원문 PDF 확인 필요.

## data.go.kr 키 실측 (2026-09-15)

**결과: 동작함(YES)** — `.env`의 `FOOD_NUTRITION_API_KEY`(길이 102, Decoding 키)로 공공데이터포털
`식품의약품안전처_식품영양성분DB정보`(15127578) 호출 성공. `backend/.venv/bin/python` + `dotenv_values()`로
키를 변수에만 로드, URL에는 항상 REDACTED로만 출력(스크립트: 스크래치 디렉터리 `test_datagokr.py`, 커밋 대상 아님).

- **엔드포인트**: `GET https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02`
  파라미터: `serviceKey`(**키를 그대로 raw로 붙일 것** — `urllib.parse.quote()`로 추가 인코딩하면
  `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(HTTP 403, returnReasonCode 30)로 실패함. 즉 이 키는 이미
  Decoding 형태라 재인코딩하면 깨짐), `FOOD_NM_KR`(국문 식품명), `type=json`, `numOfRows`, `pageNo`.
- **응답 형태**: `{"header":{"resultCode":"00","resultMsg":"NORMAL SERVICE."},"body":{"pageNo":,"totalCount":,"numOfRows":,"items":[...]}}`
  (COOKRCP01류의 `response.header/body`가 아니라 최상위에 바로 `header`/`body` — 파싱 코드에서 이 차이 주의).
- 5개 쿼리 전부 HTTP 200 / resultCode `00` NORMAL SERVICE로 성공: 두부(totalCount 3167), 대파(415),
  달걀(165), 김치찌개(375), 돼지고기(547).

### 필드 매핑 (실측 + 웹 검색으로 교차 확인)

`AMT_NUM1`~`AMT_NUM157`이 영양성분 157개 슬롯. 앞쪽 순서가 실측값과 정확히 일치:

| 필드 | 의미 | 실측 근거 |
|---|---|---|
| `AMT_NUM1` | 에너지 (kcal) | 김치찌개_돼지고기 45kcal, 덮밥_돼지고기(제육) 202kcal — 요리 특성과 부합 |
| `AMT_NUM2` | 수분 (g) | 달걀탕_순두부 94.70g — 국물 요리라 수분 비중 매우 높음, 부합 |
| `AMT_NUM3` | 단백질 (g) | |
| `AMT_NUM4` | 지방 (g) | |
| `AMT_NUM5` | 회분 (g) | |
| `AMT_NUM6` | **탄수화물 (g)** | |
| `AMT_NUM7` | **당류 (g)** | |
| `AMT_NUM8` | 식이섬유 (g) | |
| `AMT_NUM9` | 칼슘 (mg) | |
| `AMT_NUM13` | **나트륨 (mg)** | 김치찌개_돼지고기 207mg, 덮밥_돼지고기 174mg — 요리 규모에 맞는 자연스러운 값 |

(순서 출처: 웹 검색으로 확인한 공공데이터포털 공식 항목 순서 — 식품코드/식품명/분류 코드·명 다음
"영양성분함량 기준량, 에너지, 수분, 단백질, 지방, 회분, 탄수화물, 당류, 식이섬유, 칼슘, 철, 인, 칼륨, 나트륨…"
과 실측값이 정합적으로 일치함.)

- **기준(basis)**: 모든 샘플에서 `SERVING_SIZE = "100g"` — AMT_NUM 값들은 **100g당** 함량. 별도로
  `Z10500` 필드가 "350.000g" / "200.000g" / "470.000g" 처럼 존재하는데, 이건 **완제품/1인분 총 중량**으로
  보이며 100g 기준값과는 별개(스케일링에 쓸 수 있는 후보). `NUTRI_AMOUNT_SERVING`, `DISH_ONE_SERVING`은
  5개 쿼리 전부 빈 값/null — 이 필드들에 의존하지 말 것.
- **식품 분류 필드**: `DB_GRP_CM`/`DB_GRP_NM` — 실측된 값은 전부 `"D"`/`"음식"`(요리/조리식품). 원재료성
  식품·가공식품 값(예상되는 값 체계: 원재료성식품/가공식품)은 이번 5개 쿼리에서 관측 못 함 — 두부·대파·달걀·
  돼지고기로 검색해도 전부 그 재료가 **들어간 요리 이름**만 매칭됐기 때문(아래 검색 동작 참고). 실제 구현
  시 `DB_GRP_NM`으로 필터링해 원재료 행을 걸러내는 로직이 필요.

### 검색(이름 매칭) 동작

- **부분(substring) 일치, 정렬은 관련도순이 아님.** `FOOD_NM_KR=두부`로 검색하면 totalCount 3167인데
  1번 결과가 "달걀탕_순두부"(순두부가 들어간 국 요리) — 정확히 "두부"인 원재료 행이 상단에 오지 않음.
  `FOOD_NM_KR=대파` → "꼬치구이_닭고기_대파", "바게트_대파 바게트볼"처럼 이름에 "대파"가 포함된 요리가
  전부 반환됨. `FOOD_NM_KR=김치찌개` → "김치찌개_꽁치", "김치찌개_돼지고기", "김치찌개_어묵" 등 하위 변형이
  다수(총 375건) — 이 경우는 오히려 자연스러움(김치찌개가 실제로 dish 개념이라).
- **페이징**: `numOfRows`/`pageNo` 표준 방식, `totalCount`가 실제 전체 매칭 건수를 반환(위 예시들은
  수백~수천 건). 서비스 자체의 콜 한도는 이번 실측 범위 밖(문서상 개발단계 1만 콜/일 통상 수준으로 추정,
  4b-1 조사와 동일 가정 유지).

### 4b-2 매칭 전략 권장

1. **레시피 재료(두부/대파처럼 원재료성 단어)는 `DB_GRP_NM="음식"` 결과를 그대로 쓰면 안 된다** — 부분
   일치라 요리 이름에 그 단어가 들어간 온갖 항목이 섞여 나온다. `numOfRows`를 넉넉히(예: 50~100) 받아
   클라이언트에서 `FOOD_NM_KR`이 **재료명과 정확히 일치**하는 행을 우선 채택(정확히 "두부", "대파(생)"
   등 원재료 표기 행 우선), 없으면 기존 `app/matching.normalize`/`names_match`로 후보를 좁혀 사용자
   확인(`food_matches`)을 거치게 한다 — 4b-1 문서가 이미 정한 방식과 동일하게 유지.
2. **김치찌개 같은 완성 요리명(dish rows)은 그대로 사용 가능** — "음식" 카테고리 자체가 그 요리이므로
   부분 일치가 오히려 원하는 하위 변형(김치찌개_돼지고기 등)을 잘 찾아준다. 다만 어떤 하위 변형을 쓸지는
   여전히 사용자 확인이 필요(레시피가 어떤 재료 조합인지 API가 모름).
3. **캐시 키는 `FOOD_CD`, 영양값은 100g 기준(`AMT_NUM1/3/4/6/7/13` 등)으로 저장** 후 재료 실제 중량
   (g 환산, 기존 `parse_amount` + `Z10500`/AI 추정 폴백)으로 스케일링 — 4b-1 문서의 파이프라인 그대로
   적용 가능, 엔드포인트/필드명만 이번 실측값으로 교체하면 됨.
