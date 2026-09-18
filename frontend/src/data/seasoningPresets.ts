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
];
