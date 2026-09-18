import type { Seasoning } from "../seasoning";

// 기본 양념(스펙 22절). id는 화면 경로(#/recipes/seasonings/preset/:id)에 쓰여서 바꾸지 않는다. 목록 순서 = 표시 순서.
// 재료 구성은 식품의약품안전처 조리식품 레시피 DB(공공데이터, 1,156건, 이용허락범위 제한 없음)의 같은 요리 양념장과 대조했다(2026-09-18).
// 양은 그 DB가 나트륨·당류 저감 레시피 모음이라 그대로 못 쓰고, 집밥에서 흔히 쓰는 비율로 넣었다. 화면에서도 "입맛에 맞게 조절"이라고 안내한다.
const SOURCE = "식품의약품안전처 조리식품 레시피 DB(공공데이터)와 재료 구성 대조 · 양은 집밥에서 흔히 쓰는 비율 (2026-09-18)";

export const SEASONING_PRESETS: Seasoning[] = [
  {
    id: 1, name: "제육볶음 양념", basis: "main_weight", basis_amount: 600, basis_unit: "g", main_ingredient: "돼지고기",
    items: [
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 2 / 3, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 2, name: "불고기 양념", basis: "main_weight", basis_amount: 600, basis_unit: "g", main_ingredient: "소고기",
    items: [
      { name: "간장", amount: 4, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "배즙", amount: 4, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "다진 파", amount: 2, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "후추", amount: 1, unit: "꼬집" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 3, name: "간장조림 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "간장", amount: 3, unit: "큰술" },
      { name: "물", amount: 0.5, unit: "컵" },
      { name: "설탕", amount: 1, unit: "큰술" },
      { name: "물엿", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 4, name: "초고추장", basis: "yield", basis_amount: 0.5, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "고추장", amount: 3, unit: "큰술" },
      { name: "식초", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 1.5, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 5, name: "쌈장", basis: "yield", basis_amount: 0.5, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "된장", amount: 3, unit: "큰술" },
      { name: "고추장", amount: 1.5, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "깨", amount: 0.5, unit: "큰술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 6, name: "갈비 양념", basis: "main_weight", basis_amount: 1000, basis_unit: "g", main_ingredient: "소갈비",
    items: [
      { name: "간장", amount: 7, unit: "큰술" },
      { name: "설탕", amount: 3, unit: "큰술" },
      { name: "배즙", amount: 0.5, unit: "컵" },
      { name: "맛술", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 2, unit: "큰술" },
      { name: "다진 파", amount: 3, unit: "큰술" },
      { name: "참기름", amount: 2, unit: "큰술" },
      { name: "후추", amount: 2, unit: "꼬집" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 7, name: "닭볶음탕 양념", basis: "main_weight", basis_amount: 1000, basis_unit: "g", main_ingredient: "닭고기",
    items: [
      { name: "고춧가루", amount: 4, unit: "큰술" },
      { name: "간장", amount: 4, unit: "큰술" },
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "맛술", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 2, unit: "큰술" },
      { name: "물", amount: 2, unit: "컵" },
      { name: "후추", amount: 2, unit: "꼬집" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 8, name: "생선조림 양념", basis: "main_weight", basis_amount: 500, basis_unit: "g", main_ingredient: "고등어",
    items: [
      { name: "간장", amount: 4, unit: "큰술" },
      { name: "고춧가루", amount: 2, unit: "큰술" },
      { name: "맛술", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "다진 생강", amount: 1 / 3, unit: "작은술" },
      { name: "물", amount: 1, unit: "컵" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 9, name: "김치찌개 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "국간장", amount: 1, unit: "큰술" },
      { name: "새우젓", amount: 1, unit: "작은술" },
      { name: "설탕", amount: 1, unit: "작은술" },
      { name: "참기름", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 10, name: "된장찌개 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "된장", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "작은술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "국간장", amount: 1, unit: "작은술" },
      { name: "물", amount: 2, unit: "컵" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 11, name: "떡볶이 양념", basis: "main_weight", basis_amount: 400, basis_unit: "g", main_ingredient: "떡",
    items: [
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
      { name: "물", amount: 2, unit: "컵" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 12, name: "잡채 양념", basis: "main_weight", basis_amount: 200, basis_unit: "g", main_ingredient: "당면",
    items: [
      { name: "간장", amount: 4, unit: "큰술" },
      { name: "설탕", amount: 2, unit: "큰술" },
      { name: "참기름", amount: 2, unit: "큰술" },
      { name: "깨", amount: 1, unit: "큰술" },
      { name: "후추", amount: 1, unit: "꼬집" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 13, name: "나물무침 양념", basis: "main_weight", basis_amount: 300, basis_unit: "g", main_ingredient: "데친 나물",
    items: [
      { name: "국간장", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "깨", amount: 1, unit: "큰술" },
      { name: "소금", amount: 1, unit: "꼬집" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 14, name: "겉절이 양념", basis: "main_weight", basis_amount: 500, basis_unit: "g", main_ingredient: "배추",
    items: [
      { name: "고춧가루", amount: 3, unit: "큰술" },
      { name: "멸치액젓", amount: 2, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "큰술" },
      { name: "설탕", amount: 1, unit: "큰술" },
      { name: "매실청", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "깨", amount: 1, unit: "큰술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 15, name: "비빔국수 양념", basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null,
    items: [
      { name: "고추장", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "식초", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 1.5, unit: "큰술" },
      { name: "간장", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "작은술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "깨", amount: 1, unit: "큰술" },
    ],
    source: "default", source_note: SOURCE,
  },
  {
    id: 16, name: "양념간장", basis: "yield", basis_amount: 0.75, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "간장", amount: 4, unit: "큰술" },
      { name: "물", amount: 2, unit: "큰술" },
      { name: "고춧가루", amount: 1, unit: "큰술" },
      { name: "다진 파", amount: 1, unit: "큰술" },
      { name: "참기름", amount: 1, unit: "큰술" },
      { name: "다진 마늘", amount: 1, unit: "작은술" },
      { name: "설탕", amount: 1, unit: "작은술" },
      { name: "깨", amount: 1, unit: "작은술" },
    ],
    source: "default", source_note: SOURCE,
  },
];
