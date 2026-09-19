import { nameKey } from "../shopping/sync.ts"; // 검사 스크립트가 node로 바로 읽는다

/** 사용자가 믿고 사는 제품(2026-09-19 사용자 결정). 장보기 줄 이름에 keyword가 들어가면 그 줄 아래 추천으로 보여주고,
 *  누르면 그 제품 이름으로 쇼핑몰 찾기 시트를 연다. 제품이 늘면 줄만 더한다 — 표·DB는 만들지 않는다.
 *  keyword는 nameKey(괄호·띄어쓰기·대소문자 무시)를 거친 이름과 맞춰 본다. */
export const PICKS: { keyword: string; products: string[] }[] = [
  { keyword: "밀가루", products: ["한살림 우리밀 중력 밀가루", "맥선 유기농 밀가루", "유기농 우리밀 앉은뱅이 밀가루"] },
  // 마트에서 보이면 무조건 사는 과일 — 물건이 아니라 농부님 이름으로 고른다
  { keyword: "거봉", products: ["이재석 농부님 거봉"] },
  { keyword: "샤인", products: ["신장호 농부님 샤인머스캣", "이기석 농부님 샤인머스캣"] },
  { keyword: "자두", products: ["김병국 농부님 자두"] },
  { keyword: "딸기", products: ["이홍재 농부님 딸기"] },
  { keyword: "토마토", products: ["이호동 농부님 토마토", "설귀숙 농부님 토마토"] },
  { keyword: "복숭아", products: ["정익훈 농부님 복숭아", "김동철 농부님 복숭아"] },
  { keyword: "블루베리", products: ["정성규 농부님 블루베리"] },
  { keyword: "참외", products: ["김현수 농부님 참외"] },
  { keyword: "메론", products: ["이원재 농부님 메론"] },
  { keyword: "멜론", products: ["이원재 농부님 메론"] }, // '메론'으로 적어도 '멜론'으로 적어도 걸리게
];

/** 가공품 줄에는 생과일 추천이 어울리지 않는다 — 토마토소스 아래 농부님 토마토가 뜨지 않게 */
const PROCESSED = /소스|케첩|잼|주스|즙|퓨레|페이스트|통조림|말랭이/;

/** 장보기 항목 이름 → 추천 제품(없으면 빈 배열) */
export function picksFor(name: string): string[] {
  const key = nameKey(name);
  if (PROCESSED.test(key)) return [];
  return PICKS.find((p) => key.includes(p.keyword))?.products ?? [];
}
