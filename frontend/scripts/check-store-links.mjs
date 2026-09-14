// 쇼핑몰 링크 모듈 검사 (4단계 계획 Task 5). `npm run check`. 네트워크는 부르지 않는다(주소를 열지 않음).
// `node scripts/check-store-links.mjs --print` — Task 9 폰 검증용으로 검색어별 링크를 모두 출력한다.
import assert from "node:assert/strict";
import { SORTS, STORES, searchQuery, storeLinks } from "../src/storeLinks.ts";

if (process.argv.includes("--print")) {
  for (const word of ["대파", "두부 한 모", "참기름"]) {
    console.log(`\n# ${word}`);
    for (const s of storeLinks(word, {})) for (const l of s.links) console.log(`${s.name} · ${l.label}\t${l.url}`);
  }
  process.exit(0);
}

assert.deepEqual(storeLinks("", {}), []);
assert.deepEqual(storeLinks("   ", {}), []);
assert.equal(searchQuery(" 대파(국산) "), "대파");
assert.equal(searchQuery("두부 (부침용) 한 모"), "두부 한 모");
assert.equal(searchQuery("가".repeat(60)).length, 50);

const ids = STORES.map((s) => s.id);
assert.deepEqual(ids, ["coupang", "naver", "kurly", "emart", "homeplus", "lottemart", "gmarket"]);
assert.equal(new Set(ids).size, 7);
assert.deepEqual(STORES.map((s) => s.name), ["쿠팡", "네이버 쇼핑", "컬리", "이마트몰", "홈플러스", "롯데마트", "G마켓"]);
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

const formats = { gmarket: (u, id) => u + "&aff=" + id };
const withAd = storeLinks("대파", { gmarket: "X", coupang: "Y" }, { formats });
assert.deepEqual(withAd.map((r) => r.store), ids); // 제휴가 붙어도 순서 그대로
for (const r of withAd) {
  assert.equal(r.ad, r.store === "gmarket", r.store); // coupang은 ID가 있어도 형식이 없어 광고 아님
  for (const l of r.links) assert.equal(new URL(l.url).searchParams.get("aff"), r.store === "gmarket" ? "X" : null, l.url);
}
assert.ok(storeLinks("대파", { coupang: "Y" }).every((r) => !r.ad)); // 기본 AFFILIATE_FORMATS는 비어 있다

assert.deepEqual(storeLinks("대파", {}, { onlyVerified: true }).map((r) => r.store), ids.filter((id) => STORES.find((s) => s.id === id).verified));

console.log("store links ok");
