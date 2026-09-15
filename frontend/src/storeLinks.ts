// ⚠ 검증 전 — 아래 STORES 주소는 네트워크 없이 기억에 기대 적은 후보다(4단계 계획 Task 5). 틀릴 수 있다.
// Task 9 Step 2에서 사용자가 갤럭시 S22 Ultra(크롬·삼성 인터넷)로 `node scripts/check-store-links.mjs --print` 링크를
// 하나씩 열어 ① 검색어 ② 정렬 적용 ③ 앱 전환 뒤 검색어 유지를 확인한다. 통과한 칸만 남기고 안 되는 정렬 칸은 지우며
// (칩이 숨겨진다) verified에 확인 날짜를 적는다. 그 전에는 운영 화면(onlyVerified)에서 정렬 칩 없이 `검색 결과` 하나만 보여준다.
// 쇼핑몰 링크는 이 파일 한 곳에서만 만든다(스펙 16·25절). 순서는 제휴 여부와 무관하다.

export type StoreId = "coupang" | "naver" | "kurly" | "emart" | "homeplus" | "lottemart" | "gmarket";
export type SortId = "price_asc" | "popular" | "newest";

/** 시안 StoreSheet 칩 순서 */
export const SORTS: { id: SortId; label: string }[] = [
  { id: "price_asc", label: "낮은 가격순" },
  { id: "popular", label: "많이 산 순" },
  { id: "newest", label: "새 상품순" },
];

interface Store {
  id: StoreId;
  name: string;
  /** 검사용: 만든 주소의 호스트가 이것과 같아야 한다 */
  host: string;
  /** "{q}" 자리에 encodeURIComponent(검색어). 정렬이 하나도 없으면 `검색 결과` 칩 하나 */
  search: string;
  /** 정렬된 검색 주소("{q}" 포함). 지원 안 하거나 확인 못 한 정렬은 칸을 두지 않는다 */
  sorts: Partial<Record<SortId, string>>;
  /** "2026-09-xx 사용자 폰 확인" | null */
  verified: string | null;
}

/** 순서 = 기본 화면 순서(제휴와 무관). 이름은 시안 그대로 */
export const STORES: readonly Store[] = [
  {
    // 검증 전
    id: "coupang", name: "쿠팡", host: "www.coupang.com",
    search: "https://www.coupang.com/np/search?q={q}",
    sorts: {
      price_asc: "https://www.coupang.com/np/search?q={q}&sorter=salePriceAsc",
      popular: "https://www.coupang.com/np/search?q={q}&sorter=saleCountDesc",
      newest: "https://www.coupang.com/np/search?q={q}&sorter=latestAsc", // Asc가 오래된 순일 수 있음 — 폰 확인
    },
    verified: null,
  },
  {
    // 검증 전. 많이 산 순: 판매량 정렬 후보가 없어 칸을 두지 않음(리뷰 많은순 `&sort=review`만 후보 — 폰 확인 뒤 결정)
    id: "naver", name: "네이버 쇼핑", host: "search.shopping.naver.com",
    search: "https://search.shopping.naver.com/search/all?query={q}",
    sorts: {
      price_asc: "https://search.shopping.naver.com/search/all?query={q}&sort=price_asc",
      newest: "https://search.shopping.naver.com/search/all?query={q}&sort=date",
    },
    verified: null,
  },
  {
    // 검증 전. 정렬 후보 없음 — 폰에서 정렬을 바꾼 주소창 값을 받아 채운다
    id: "kurly", name: "컬리", host: "www.kurly.com",
    search: "https://www.kurly.com/search?sword={q}",
    sorts: {},
    verified: null,
  },
  {
    // 검증 전 (SSG 이마트몰)
    id: "emart", name: "이마트몰", host: "emart.ssg.com",
    search: "https://emart.ssg.com/search.ssg?query={q}",
    sorts: {
      price_asc: "https://emart.ssg.com/search.ssg?query={q}&sort=prcasc",
      popular: "https://emart.ssg.com/search.ssg?query={q}&sort=sale",
      newest: "https://emart.ssg.com/search.ssg?query={q}&sort=regdt",
    },
    verified: null,
  },
  {
    // 검증 전. 정렬 후보 없음
    id: "homeplus", name: "홈플러스", host: "front.homeplus.co.kr",
    search: "https://front.homeplus.co.kr/search?entry=direct&keyword={q}",
    sorts: {},
    verified: null,
  },
  {
    // 검증 전 (롯데온 롯데마트몰). 정렬 후보 없음
    id: "lottemart", name: "롯데마트", host: "www.lotteon.com",
    search: "https://www.lotteon.com/search/search/search.ecn?render=search&platform=pc&q={q}&mallId=4",
    sorts: {},
    verified: null,
  },
  {
    // 검증 전
    id: "gmarket", name: "G마켓", host: "www.gmarket.co.kr",
    search: "https://www.gmarket.co.kr/n/search?keyword={q}",
    sorts: {
      price_asc: "https://www.gmarket.co.kr/n/search?keyword={q}&s=1",
      popular: "https://www.gmarket.co.kr/n/search?keyword={q}&s=8",
      newest: "https://www.gmarket.co.kr/n/search?keyword={q}&s=3",
    },
    verified: null,
  },
];

/** 제휴 링크 모양(스펙 16·25절). /api/me의 shop_affiliates가 true인 쇼핑몰만 쓴다.
 *  쿠팡: 딥링크 API는 비밀키 서명이 필요해 서버(backend/app/coupang.py)가 만든다. 새 창 링크가 같은 주소의 이동 엔드포인트를 열고
 *  서버가 제휴 링크로 302 — 누른 순간 바로 여는 <a>라 팝업 차단에 걸리지 않는다. 서버는 www.coupang.com/np/search 주소만 받는다 */
export const AFFILIATE_FORMATS: Partial<Record<StoreId, (url: string) => string>> = {
  coupang: (url) => `/api/shop-links/coupang/go?url=${encodeURIComponent(url)}`,
};

export const LAST_STORE_KEY = "shopping-last-store"; // localStorage, 링크를 누를 때 저장(Task 9)

/** 앞뒤 공백·괄호 내용 제거, 50자 */
export function searchQuery(name: string): string {
  const cleaned = name.replace(/\([^)]*\)/g, " ").replace(/\s+/g, " ").trim();
  return Array.from(cleaned).slice(0, 50).join("").trim(); // 글자 단위로 자른다(이모지 반쪽 → encodeURIComponent URIError 방지)
}

export interface StoreLink { sort: SortId | null; label: string; url: string }

/** 쇼핑몰마다 링크(있는 정렬만, 하나도 없으면 [검색 결과]). 순서: lastUsed가 있으면 그 쇼핑몰 맨 위, 나머지는 STORES 순서.
 *  ad는 쇼핑몰 단위(시안: 이름 옆 `광고`) — 제휴가 켜져 있고 링크 형식이 있을 때만. 검색어가 비면 []. onlyVerified면 verified 없는 쇼핑몰은 [검색 결과]만 */
export function storeLinks(
  name: string,
  affiliates: Partial<Record<StoreId, boolean>>,
  options: { lastUsed?: StoreId | null; onlyVerified?: boolean; formats?: typeof AFFILIATE_FORMATS } = {},
): { store: StoreId; name: string; ad: boolean; links: StoreLink[] }[] {
  const q = searchQuery(name); // 호출하는 쪽이 잊어도 같은 검색어가 되게 여기서 정리한다
  if (!q) return [];
  const { lastUsed = null, onlyVerified = false, formats = AFFILIATE_FORMATS } = options;
  const last = STORES.filter((s) => s.id === lastUsed);
  return [...last, ...STORES.filter((s) => s.id !== lastUsed)]
    .map((s) => {
      const format = affiliates[s.id] === true ? formats[s.id] : undefined; // 기기에 남은 옛 /api/me 값(제휴 ID 문자열)은 제휴로 보지 않는다
      const ad = Boolean(format);
      const make = (template: string) => {
        const url = template.replace("{q}", encodeURIComponent(q));
        return format ? format(url) : url;
      };
      const sorted = SORTS.filter((o) => s.sorts[o.id] && (!onlyVerified || s.verified)).map((o) => ({ sort: o.id, label: o.label, url: make(s.sorts[o.id]!) }));
      const links = sorted.length ? sorted : [{ sort: null, label: "검색 결과", url: make(s.search) }];
      return { store: s.id, name: s.name, ad, links };
    });
}
