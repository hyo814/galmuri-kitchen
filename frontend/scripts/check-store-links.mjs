// 쇼핑몰 링크 모듈 검사 (4단계 계획 Task 5). `npm run check`. 네트워크는 부르지 않는다(주소를 열지 않음).
// `node scripts/check-store-links.mjs --print` — Task 9 폰 검증용으로 검색어별 링크를 모두 출력한다.
import assert from "node:assert/strict";
import { SORTS, STORES, searchQuery, storeLinks } from "../src/storeLinks.ts";

const PHONE_WORDS = ["대파", "두부 한 모", "참기름"];
if (process.argv.includes("--print")) {
  for (const word of PHONE_WORDS) {
    console.log(`\n# ${word}`);
    for (const s of storeLinks(word, {})) for (const l of s.links) console.log(`${s.name} · ${l.label}\t${l.url}`);
  }
  process.exit(0);
}
// `--checklist` — 같은 링크를 폰 확인표(Markdown 표)로 출력한다(docs/superpowers/store-links-phone-check.md)
if (process.argv.includes("--checklist")) {
  for (const word of PHONE_WORDS) {
    console.log(`\n## ${word}\n\n| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |\n|---|---|---|---|---|---|`);
    for (const s of storeLinks(word, {})) {
      for (const l of s.links) console.log(`| ${s.name} · ${l.label} | [열기](${l.url}) | ☐ | ${l.sort ? "☐" : "정렬 후보 없음"} | ☐ |  |`);
    }
  }
  process.exit(0);
}

assert.deepEqual(storeLinks("", {}), []);
assert.deepEqual(storeLinks("   ", {}), []);
assert.equal(searchQuery(" 대파(국산) "), "대파");
assert.equal(searchQuery("두부 (부침용) 한 모"), "두부 한 모");
assert.equal(searchQuery("가".repeat(60)).length, 50);

const ids = STORES.map((s) => s.id);
assert.deepEqual(ids, ["coupang", "naver", "kurly", "emart", "lottemart", "gmarket"]);
assert.equal(new Set(ids).size, 6);
assert.deepEqual(STORES.map((s) => s.name), ["쿠팡", "네이버 쇼핑", "컬리", "이마트몰", "롯데마트", "G마켓"]);
assert.deepEqual(SORTS.map((s) => s.label), ["낮은 가격순", "많이 산 순", "새 상품순"]);
for (const s of STORES) {
  assert.ok(s.search.includes("{q}"), s.id);
  for (const t of Object.values(s.sorts)) assert.ok(t.includes("{q}"), s.id);
}

assert.equal(Array.from(searchQuery("가".repeat(49) + "😀😀")).length, 50); // 이모지를 반으로 자르지 않는다
assert.doesNotThrow(() => storeLinks("가".repeat(49) + "😀", {}));
for (const word of ["대파", "두부 한 모", "A&B #1 100%", "a+b 1", "대파😀"]) {
  const result = storeLinks(word, {});
  assert.deepEqual(result.map((r) => r.store), ids, word);
  for (const r of result) {
    const store = STORES.find((s) => s.id === r.store);
    assert.equal(r.ad, false);
    assert.equal(r.name, store.name);
    const sorts = Object.keys(store.sorts);
    if (sorts.length === 0) assert.deepEqual(r.links.map((l) => [l.sort, l.label]), [[null, "검색 결과"]], r.store);
    else assert.deepEqual(r.links.map((l) => l.sort), SORTS.map((o) => o.id).filter((id) => sorts.includes(id)), r.store);
    for (const l of r.links) {
      const url = new URL(l.url);
      assert.equal(url.protocol, "https:", l.url);
      assert.equal(url.host, store.host, l.url);
      assert.ok(l.url.includes(encodeURIComponent(word)), l.url);
      assert.ok([...url.searchParams.values()].includes(word), l.url);
      assert.equal(url.hash, "", l.url);
    }
  }
}

const order = (opts, affiliates = {}) => storeLinks("대파", affiliates, opts).map((r) => r.store);
assert.deepEqual(order({ lastUsed: "kurly" }), ["kurly", ...ids.filter((id) => id !== "kurly")]);
assert.deepEqual(order({ lastUsed: "nope" }), ids);
assert.deepEqual(order({ lastUsed: null }), ids);

const formats = { gmarket: (u) => u + "&aff=1" };
const withAd = storeLinks("대파", { gmarket: true, coupang: true }, { formats });
assert.deepEqual(withAd.map((r) => r.store), ids); // 제휴가 붙어도 순서 그대로
for (const r of withAd) {
  assert.equal(r.ad, r.store === "gmarket", r.store); // coupang은 켜져 있어도 이 formats에 형식이 없어 광고 아님
  for (const l of r.links) assert.equal(new URL(l.url).searchParams.get("aff"), r.store === "gmarket" ? "1" : null, l.url);
}
assert.ok(storeLinks("대파", { gmarket: true }).every((r) => !r.ad)); // 기본 AFFILIATE_FORMATS에는 쿠팡만 있다
assert.ok(storeLinks("대파", { coupang: false }).every((r) => !r.ad));
assert.ok(storeLinks("대파", { coupang: "AF123" }).every((r) => !r.ad)); // 옛 /api/me 모양(제휴 ID)

// 쿠팡 제휴(기본 형식): 같은 주소의 이동 엔드포인트가 원래 검색 주소를 url로 그대로 넘긴다. 다른 쇼핑몰은 그대로
for (const onlyVerified of [false, true]) {
  const before = storeLinks("A&B #1 대파", {}, { onlyVerified });
  const after = storeLinks("A&B #1 대파", { coupang: true }, { onlyVerified });
  for (const [i, r] of after.entries()) {
    assert.equal(r.ad, r.store === "coupang", r.store);
    for (const [j, l] of r.links.entries()) {
      const was = before[i].links[j];
      if (r.store !== "coupang") { assert.deepEqual(l, was); continue; }
      const go = new URL(l.url, "https://galmuri.example");
      assert.equal(go.origin + go.pathname, "https://galmuri.example/api/shop-links/coupang/go", l.url);
      assert.deepEqual([...go.searchParams.keys()], ["url"]);
      assert.equal(go.searchParams.get("url"), was.url);
      const target = new URL(was.url); // 서버 검사(coupang.plain_search_url)와 같은 조건
      assert.equal(target.host + target.pathname, "www.coupang.com/np/search");
      assert.ok([...target.searchParams.keys()].every((k) => k === "q" || k === "sorter"), was.url);
      assert.ok([null, "salePriceAsc", "saleCountDesc", "latestAsc"].includes(target.searchParams.get("sorter")), was.url); // backend coupang.SORTERS
    }
  }
}

// 운영(onlyVerified): 쇼핑몰은 모두 보이고, 폰 확인 전 쇼핑몰은 정렬 칩 없이 검색 주소 하나만
for (const r of storeLinks("대파", {}, { onlyVerified: true })) {
  const store = STORES.find((s) => s.id === r.store);
  if (store.verified) assert.deepEqual(r.links, storeLinks("대파", {}).find((x) => x.store === r.store).links, r.store);
  else assert.deepEqual(r.links, [{ sort: null, label: "검색 결과", url: store.search.replace("{q}", encodeURIComponent("대파")) }], r.store);
}
assert.deepEqual(storeLinks("대파", {}, { onlyVerified: true }).map((r) => r.store), ids);

console.log("store links ok");
