import type { Seasoning } from "../seasoning";

// 기본 양념(스펙 22절). id는 화면 경로(#/recipes/seasonings/preset/:id)에 쓰여서 바꾸지 않는다. 목록 순서 = 표시 순서.
//
// 값의 출처는 둘이고, 조건이 더 깨끗한 쪽을 먼저 쓴다(2026-09-19).
//
// ① 한식진흥원 「한식 정밀레시피(밥류)」 — data.go.kr 15142529, HWPX 30개, 공공누리 제1유형(출처표시).
//    조리법 항목에 `고추장 1큰술(16g)`처럼 기관이 정한 큰술 환산이 함께 적혀 있어 우리가 밀도를 가정할 필요가 없다.
//    밥류 30종뿐이라 겹치는 양념(제육·불고기·잡채·쌈장·나물무침·초고추장·양념간장)에만 쓴다. 모두 4인 기준이다.
//
// ② 농림수산식품교육문화정보원 「식품 레시피」 — data.mafra.go.kr, 레시피 537건·재료 6,104줄(사용자 인증키로 전량 수집).
//    계량이 큰술·작은술·컵 그대로 들어 있고 재료타입에 `양념`이 있어 양념만 뽑아낼 수 있다. ①에 없는 양념에 쓴다.
//    이용허락범위가 `저작권표시 + 동일조건변경허락`이라 표를 옮겨 담지 않고, 어느 레시피와 맞춰 본 값인지만 적는다.
//
// 읽을 때 조심할 것 셋:
//   - ②는 재료타입 태깅이 어긋난 레시피가 있다. 「제육불고기」는 `양념` 칸에 곁들이는 쌈장(된장·고추장·식초)이 들어가 있고
//     진짜 양념장은 `부재료` 칸에 있다. 타입만 믿지 말고 줄을 읽어야 한다.
//   - ②의 `약간`은 우리 단위에 없다. 소금·후추는 `1꼬집`, 참기름·깨는 `1작은술`로 옮겼다. ①은 `1/3작은술`까지 적혀 있어 그대로 쓴다.
//   - ①은 채소까지 든 완성 요리 기준이다. 주재료 무게를 기준으로 삼은 프리셋은 그 레시피의 주재료 무게를 그대로 기준량으로 둔다
//     (예: 제육볶음은 돼지고기 300g). 마음대로 600g으로 환산하면 채소 몫까지 고기에 얹혀 양념이 과해진다.
//
// 같은 양념이 어느 쪽에도 없는 것(비빔국수)은 집밥에서 흔히 쓰는 비율 그대로 두고 그렇다고 화면에 적는다.
const H = (recipe: string, basis: string) => `한식진흥원 한식 정밀레시피 '${recipe}'(4인 기준, ${basis}) · 공공누리 제1유형 · 2026-09-19 확인`;
const M = (recipe: string, basis: string) => `농림수산식품교육문화정보원 식품 레시피 '${recipe}'(${basis}) · 2026-09-19 확인`;
const F = (recipe: string, basis: string) => `식품의약품안전처 조리식품 레시피 DB '${recipe}'(${basis}, 나트륨·당류 저감 레시피라 간이 약해요) · 2026-09-19 확인`;
const OURS = "공공데이터에 같은 양념이 없어 집밥에서 흔히 쓰는 비율로 넣었어요 · 2026-09-19";

export const SEASONING_PRESETS: Seasoning[] = [
  {
    id: 1, name: "제육볶음 양념", basis: "main_weight", basis_amount: 300, basis_unit: "g", main_ingredient: "돼지고기",
    items: [
      { name: "고춧가루", amount: 4, unit: "큰술" },
      { name: "간장", amount: 2, unit: "큰술" },
      { name: "물엿", amount: 2, unit: "큰술" },
      { name: "청주", amount: 2, unit: "큰술" },
      { name: "고추장", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "생강즙", amount: 1, unit: "작은술" },
      { name: "소금", amount: 1 / 3, unit: "작은술" },
      { name: "후추", amount: 1 / 3, unit: "작은술" },
    ],
    // 같은 기관의 「제육비빔밥」은 고추장 2큰술·고춧가루 2큰술로 고추장 쪽이 더 많다. 볶아서 얹는 쪽인 「제육덮밥」을 기본으로 삼았다.
    source: "default", source_note: H("제육덮밥", "돼지고기 300g"),
  },
  {
    id: 2, name: "불고기 양념", basis: "main_weight", basis_amount: 450, basis_unit: "g", main_ingredient: "소고기",
    items: [
      { name: "물", amount: 1, unit: "컵" },
      { name: "간장", amount: 4, unit: "큰술" },
      { name: "설탕", amount: 3, unit: "큰술" },
      { name: "물엿", amount: 2, unit: "큰술" },
      { name: "다진 파", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "소금", amount: 1, unit: "작은술" },
      { name: "후추", amount: 1 / 3, unit: "작은술" },
    ],
    source: "default", source_note: H("불고기덮밥", "소고기 등심 450g"),
  },
  {
    id: 3, name: "간장조림 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "물", amount: 3, unit: "큰술" },
      { name: "간장", amount: 1.5, unit: "큰술" },
      { name: "설탕", amount: 0.5, unit: "큰술" },
      { name: "물엿", amount: 0.5, unit: "큰술" },
      { name: "맛술", amount: 0.5, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
    ],
    source: "default", source_note: M("두부양념조림'·'연근조림", "2인분·4인분"),
  },
  {
    id: 4, name: "초고추장", basis: "yield", basis_amount: 0.75, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "고추장", amount: 4, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "물", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 1, unit: "큰술" },
      { name: "식초", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "작은술" },
      { name: "생강즙", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: H("회덮밥", "완성 약 ¾컵"),
  },
  {
    id: 5, name: "쌈장", basis: "yield", basis_amount: 1, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "된장", amount: 4, unit: "큰술" },
      { name: "물", amount: 0.25, unit: "컵" },
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "참기름", amount: 2, unit: "큰술" },
      { name: "잣", amount: 2, unit: "큰술" },
      { name: "다진 풋고추", amount: 30, unit: "g" },
      { name: "고춧가루", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: H("쌈밥", "완성 약 1컵"),
  },
  {
    id: 6, name: "갈비 양념", basis: "main_weight", basis_amount: 1200, basis_unit: "g", main_ingredient: "소갈비",
    items: [
      { name: "간장", amount: 0.25, unit: "컵" },
      { name: "물", amount: 0.25, unit: "컵" },
      { name: "배즙", amount: 4, unit: "큰술" },
      { name: "양파즙", amount: 2, unit: "큰술" },
      { name: "물엿", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "맛술", amount: 2, unit: "큰술" },
      { name: "다진 파", amount: 1.5, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "생강즙", amount: 1, unit: "작은술" },
      { name: "참기름", amount: 1, unit: "작은술" },
      { name: "후추", amount: 1, unit: "꼬집" },
    ],
    // 같은 갈비라도 찜은 국물이 있어 훨씬 진하다(원본 「갈비찜」은 1.2kg에 간장 1컵). 구이 쪽을 기본으로 삼았다.
    source: "default", source_note: M("갈비구이", "4인분, 갈비 1.2kg"),
  },
  {
    id: 7, name: "닭갈비 양념", basis: "main_weight", basis_amount: 300, basis_unit: "g", main_ingredient: "닭고기",
    items: [
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "간장", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "생강즙", amount: 1, unit: "큰술" },
      { name: "깨", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: M("닭갈비", "2인분, 닭 300g"),
  },
  {
    id: 8, name: "생선조림 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "물", amount: 2 / 3, unit: "컵" },
      { name: "다진 파", amount: 3, unit: "큰술" },
      { name: "간장", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 2, unit: "큰술" },
      { name: "고추장", amount: 1, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 1, unit: "큰술" },
      { name: "맛술", amount: 1, unit: "큰술" },
      { name: "생강즙", amount: 1, unit: "큰술" },
      { name: "후추", amount: 0.25, unit: "작은술" },
    ],
    source: "default", source_note: M("고등어무조림", "2인분, 고등어 1마리"),
  },
  {
    id: 9, name: "김치찌개 양념", basis: "servings", basis_amount: 4, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "고춧가루", amount: 3, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "생강즙", amount: 0.5, unit: "작은술" },
      { name: "참기름", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: M("김치찌개", "4인분"),
  },
  {
    id: 10, name: "된장찌개 양념", basis: "servings", basis_amount: 4, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "물", amount: 4, unit: "컵" }, // 원본은 국물 양을 따로 적지 않는다
      { name: "된장", amount: 4, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
      { name: "국간장", amount: 0.5, unit: "큰술" },
      { name: "생강즙", amount: 0.5, unit: "작은술" },
    ],
    source: "default", source_note: M("우거지된장찌개", "4인분"),
  },
  {
    id: 11, name: "떡볶이 양념", basis: "servings", basis_amount: 4, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "물", amount: 1.5, unit: "컵" },
      { name: "고추장", amount: 3, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "물엿", amount: 1, unit: "큰술" },
    ],
    source: "default", source_note: M("떡볶이", "4인분"),
  },
  {
    id: 12, name: "잡채 양념", basis: "main_weight", basis_amount: 100, basis_unit: "g", main_ingredient: "당면",
    items: [
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "청주", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 0.5, unit: "큰술" },
      { name: "후추", amount: 1 / 3, unit: "작은술" },
    ],
    source: "default", source_note: H("잡채덮밥", "당면 100g"),
  },
  {
    id: 13, name: "나물무침 양념", basis: "main_weight", basis_amount: 250, basis_unit: "g", main_ingredient: "나물",
    items: [
      { name: "국간장", amount: 4, unit: "큰술" },
      { name: "다진 파", amount: 4, unit: "큰술" },
      { name: "들기름", amount: 4, unit: "큰술" },
      { name: "다진 마늘", amount: 2, unit: "작은술" },
    ],
    // 원본은 취나물 90g·고사리 90g·표고버섯 74g(합계 254g)에 쓰는 양이다. 기준량은 250g으로 반올림했다.
    source: "default", source_note: H("산채비빔밥", "나물 약 250g"),
  },
  {
    id: 14, name: "겉절이 양념", basis: "servings", basis_amount: 4, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "고춧가루", amount: 0.25, unit: "컵" },
      { name: "다진 파", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "새우젓", amount: 1, unit: "큰술" },
      { name: "다진 생강", amount: 0.5, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: M("배추겉절이", "4인분, 배추 ¼통"),
  },
  {
    id: 15, name: "비빔국수 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "식초", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 1.5, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "깨", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: OURS,
  },
  {
    id: 16, name: "양념간장", basis: "yield", basis_amount: 1.5, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "물", amount: 0.5, unit: "컵" },
      { name: "간장", amount: 5, unit: "큰술" },
      { name: "고춧가루", amount: 2, unit: "큰술" },
      { name: "다진 풋고추", amount: 2, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "실파", amount: 15, unit: "g" },
      { name: "다진 마늘", amount: 1, unit: "작은술" },
      { name: "깨", amount: 1, unit: "작은술" },
      { name: "소금", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: H("콩나물밥", "완성 약 1½컵"),
  },
  {
    id: 17, name: "돼지갈비 양념", basis: "main_weight", basis_amount: 600, basis_unit: "g", main_ingredient: "돼지갈비",
    items: [
      { name: "진간장", amount: 5, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "생강즙", amount: 2, unit: "큰술" },
      { name: "청주", amount: 2, unit: "큰술" },
      { name: "다진 파", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
    ],
    // 원본은 술 2큰술이라고만 적혀 있어 구이 양념에 흔한 청주로 적었다. 깨소금은 양념이 아니라 부재료 칸이라 뺐다.
    // 소갈비(id 6)와 기준이 다르다. 저쪽은 1.2kg 구이, 이쪽은 돼지갈비 600g이다.
    source: "default", source_note: M("돼지갈비구이", "4인분, 돼지갈비 600g"),
  },
  {
    id: 18, name: "돼지불고기 양념", basis: "main_weight", basis_amount: 200, basis_unit: "g", main_ingredient: "돼지고기",
    items: [
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 2, unit: "큰술" },
      { name: "미림", amount: 25, unit: "g" },
      { name: "간장", amount: 0.5, unit: "큰술" },
      { name: "설탕", amount: 0.5, unit: "큰술" },
      { name: "다진 파", amount: 1, unit: "작은술" },
      { name: "다진 마늘", amount: 1, unit: "작은술" },
      { name: "물엿", amount: 1, unit: "작은술" },
      { name: "깨소금", amount: 1, unit: "작은술" },
      { name: "참기름", amount: 1, unit: "작은술" },
      { name: "후추", amount: 1, unit: "꼬집" },
    ],
    // 제육볶음(id 1)은 고춧가루가 앞서는 덮밥용이고 이쪽은 고추장·고춧가루가 같은 양인 고깃집식이다.
    // 원본의 `약간`은 이 파일 규칙대로 옮겼다(후추 → 1꼬집, 참기름·깨소금 → 1작은술). 다진 파·마늘도 같은 규칙으로 1작은술.
    source: "default", source_note: M("돼지불고기", "2인분, 돼지고기 200g"),
  },
  {
    id: 19, name: "LA갈비 양념", basis: "main_weight", basis_amount: 200, basis_unit: "g", main_ingredient: "LA갈비",
    items: [
      { name: "저염간장", amount: 20, unit: "g" },
      { name: "올리고당", amount: 20, unit: "g" },
      { name: "다진 대파", amount: 20, unit: "g" },
      { name: "다진 마늘", amount: 20, unit: "g" },
      { name: "설탕", amount: 10, unit: "g" },
      { name: "정종", amount: 10, unit: "g" },
      { name: "매실액", amount: 10, unit: "g" },
      { name: "통깨", amount: 5, unit: "g" },
      { name: "월계수잎", amount: 5, unit: "g" },
      { name: "통후추", amount: 5, unit: "g" },
      { name: "참기름", amount: 3, unit: "g" },
    ],
    // 식약처 DB는 g만 주고 우리 단위에 g가 있어 환산 없이 그대로 담았다. 함께 재우는 배 20g·양파 20g은 양념 칸이 아니라 재료 칸이라 뺐다.
    source: "default", source_note: F("L..A갈비구이", "LA갈비 200g"),
  },
  {
    id: 20, name: "찜닭 양념", basis: "main_weight", basis_amount: 170, basis_unit: "g", main_ingredient: "닭고기",
    items: [
      { name: "간장", amount: 10, unit: "g" },
      { name: "올리고당", amount: 9, unit: "g" },
      { name: "황설탕", amount: 8, unit: "g" },
      { name: "노두유", amount: 1, unit: "g" },
      { name: "후추", amount: 1, unit: "꼬집" },
    ],
    // 기준 170g은 토막 낸 닭 무게다(그중 살코기는 90g). 감자·양파·당근·당면과 함께 졸이는 양념이다.
    // 후추 0.25g은 `¼g`으로 보이면 읽기 어려워 이 파일 규칙대로 1꼬집으로 옮겼다.
    source: "default", source_note: F("수삼매운닭찜", "토막 낸 닭 170g"),
  },
  {
    id: 21, name: "어묵볶음 양념", basis: "main_weight", basis_amount: 100, basis_unit: "g", main_ingredient: "어묵",
    items: [
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "간장", amount: 0.5, unit: "큰술" },
      { name: "설탕", amount: 0.5, unit: "큰술" },
      { name: "마늘", amount: 2, unit: "개" },
      { name: "참기름", amount: 1, unit: "작은술" },
      { name: "깨소금", amount: 1, unit: "작은술" },
    ],
    // 원본은 마늘 2쪽이다. 우리 단위에 쪽이 없어 개로 뒀다. 함께 볶는 양파·피망·김치는 부재료 칸이라 뺐다.
    source: "default", source_note: M("어묵볶음", "2인분, 어묵 100g"),
  },
  {
    id: 22, name: "애호박볶음 양념", basis: "servings", basis_amount: 3, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "다진 파", amount: 2, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "새우젓국", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 2, unit: "작은술" },
      { name: "고춧가루", amount: 2, unit: "작은술" },
      { name: "참기름", amount: 1, unit: "작은술" },
      { name: "깨소금", amount: 1, unit: "작은술" },
    ],
    // 애호박 1개 기준이라 무게를 알 수 없어 인분으로 뒀다. 원본은 참기름이 두 줄(1작은술·약간)이라 1작은술로 합쳤다.
    source: "default", source_note: M("애호박무침", "3인분, 애호박 1개"),
  },
  {
    id: 23, name: "장조림 양념", basis: "main_weight", basis_amount: 400, basis_unit: "g", main_ingredient: "쇠고기",
    items: [
      { name: "물", amount: 4, unit: "컵" },
      { name: "진간장", amount: 1, unit: "컵" },
      { name: "설탕", amount: 0.25, unit: "컵" },
      { name: "참기름", amount: 1, unit: "작은술" },
    ],
    // 물 4컵은 원본에서 부재료 칸이지만 고기를 잠기게 삶는 양이라 함께 담았다. 간장조림(id 3)은 2인분 조림용이라 컵 단위인 이쪽과 결이 다르다.
    source: "default", source_note: M("쇠고기장조림", "4인분, 쇠고기 400g"),
  },
];
