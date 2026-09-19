import { nameKey } from "../shopping/sync.ts"; // 검사 스크립트가 node로 바로 읽는다

/** 사용자가 믿고 사는 제품(2026-09-19 사용자 결정). 장보기 줄 이름에 keyword가 들어가면 그 줄 아래 추천으로 보여주고,
 *  누르면 그 제품 이름으로 쇼핑몰 찾기 시트를 연다. 제품이 늘면 줄만 더한다 — 표·DB는 만들지 않는다.
 *  keyword는 nameKey(괄호·띄어쓰기·대소문자 무시)를 거친 이름과 맞춰 본다. */
export const PICKS: { keyword: string; products: string[] }[] = [
  { keyword: "밀가루", products: ["한살림 우리밀 중력 밀가루", "맥선 유기농 밀가루", "유기농 우리밀 앉은뱅이 밀가루"] },
];

/** 장보기 항목 이름 → 추천 제품(없으면 빈 배열) */
export function picksFor(name: string): string[] {
  const key = nameKey(name);
  return PICKS.find((p) => key.includes(p.keyword))?.products ?? [];
}
