import { nameKey } from "../shopping/sync.ts"; // 검사 스크립트가 node로 바로 읽는다

/** 장보기 줄 아래에 보여줄 것(2026-09-19·20 사용자 결정). 이름에 keyword가 들어가면 그 줄 아래 한 묶음이 붙는다.
 *  - products: 믿고 사는 제품. 누르면 그 이름으로 쇼핑몰 찾기 시트를 연다(상품명에 브랜드가 그대로 적혀 검색이 된다).
 *  - note: 누를 것 없는 메모 한 줄. 농부님 이름은 국내 몰 상품명에 거의 안 적혀서(2026-09-20 확인: 컬리 검색 API로 12개 조합 —
 *    이름이 든 상품 0개, 느슨한 검색이라 이름을 붙이면 엉뚱한 상품이 1등) 검색어로 쓰지 않고, 마트 진열대에서 라벨을 볼 때 떠올리도록 글자만 보여준다.
 *  keyword는 nameKey(괄호·띄어쓰기·대소문자 무시)를 거친 이름과 맞춰 보고, 먼저 적은 것이 이긴다. 늘어나면 줄만 더한다 — 표·DB는 만들지 않는다. */
export interface Pick {
  keyword: string;
  products?: string[];
  note?: string;
}

export const PICKS: Pick[] = [
  { keyword: "밀가루", products: ["한살림 우리밀 중력 밀가루", "맥선 유기농 밀가루", "유기농 우리밀 앉은뱅이 밀가루"] },
  // 마트에서 보이면 무조건 사는 과일 — 물건이 아니라 농부님 이름으로 고른다. `샤인`은 샤인머스캣·샤인머스켓 두 표기를 다 잡는다
  { keyword: "거봉", note: "이재석 농부님" },
  { keyword: "샤인", note: "신장호 · 이기석 농부님" },
  { keyword: "자두", note: "김병국 농부님" },
  { keyword: "딸기", note: "이홍재 농부님" },
  { keyword: "토마토", note: "이호동 · 설귀숙 농부님" },
  { keyword: "복숭아", note: "정익훈 · 김동철 농부님" },
  { keyword: "블루베리", note: "정성규 농부님" },
  { keyword: "참외", note: "김현수 농부님" },
  { keyword: "메론", note: "이원재 농부님" },
  { keyword: "멜론", note: "이원재 농부님" }, // '메론'으로 적어도 '멜론'으로 적어도 걸리게
];

/** 가공품 줄에는 생과일 메모가 어울리지 않는다 — 토마토소스 아래 농부님 이름이 뜨지 않게 */
const PROCESSED = /소스|케첩|잼|주스|즙|퓨레|페이스트|통조림|말랭이/;

/** 장보기 항목 이름 → 보여줄 것(없으면 null) */
export function pickFor(name: string): Pick | null {
  const key = nameKey(name);
  if (PROCESSED.test(key)) return null;
  return PICKS.find((p) => key.includes(p.keyword)) ?? null;
}
