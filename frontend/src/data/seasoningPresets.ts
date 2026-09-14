import type { Seasoning } from "../seasoning";

// 기본 양념(스펙 22절). id는 화면 경로(#/recipes/seasonings/preset/:id)에 쓰여서 바꾸지 않는다. 목록 순서 = 표시 순서.
// 수치는 흔히 쓰는 집밥 비율로 넣은 임시값이다. 출처 두 곳 이상과 비교해 사용자 확인을 받은 뒤 source_note를 출처 이름·날짜로 바꾼다.
const PENDING = "출처 확인 전 임시값 (2026-09-14)";

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
    source: "default", source_note: PENDING,
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
    source: "default", source_note: PENDING,
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
    source: "default", source_note: PENDING,
  },
  {
    id: 4, name: "초고추장", basis: "yield", basis_amount: 0.5, basis_unit: "컵", main_ingredient: null,
    items: [
      { name: "고추장", amount: 3, unit: "큰술" },
      { name: "식초", amount: 2, unit: "큰술" },
      { name: "설탕", amount: 1.5, unit: "큰술" },
      { name: "다진 마늘", amount: 0.5, unit: "큰술" },
    ],
    source: "default", source_note: PENDING,
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
    source: "default", source_note: PENDING,
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
    source: "default", source_note: PENDING,
  },
];
