// 양념 비율 순수 함수 검사 (3c 계획 태스크 1). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import { snapSpoon, scaleItem, scaleFactor, basisLabel, ratioLabel, parseAmountInput, amountInputText, spoonHint, RICE_SPOON_ML } from "../src/seasoning.ts";
import { recipeQuantity } from "../src/shopping/sync.ts";
import { scaleAmount } from "../src/format.ts";
import { SEASONING_PRESETS } from "../src/data/seasoningPresets.ts";
assert.equal(snapSpoon(0.33), "⅓"); assert.equal(snapSpoon(3.5), "3½"); assert.equal(snapSpoon(0.9), "1"); assert.equal(snapSpoon(12.4), "12");
const item = (name, amount, unit, factor) => scaleItem({ name, amount, unit }, factor);
// 시안 SeasoningCalc: 돼지고기 600g 기준 → 900g(×1.5)
assert.equal(item("고추장", 2, "큰술", 1.5).text, "3큰술");
assert.equal(item("고춧가루", 1, "큰술", 1.5).text, "1½큰술");
assert.equal(item("설탕", 2 / 3, "큰술", 1.5).text, "1큰술");
assert.deepEqual(item("참기름", 1, "작은술", 1.5), { text: "1½작은술", sub: "½큰술" });
if (RICE_SPOON_ML === 12) {
  assert.equal(item("고추장", 2, "큰술", 1.5).sub, "밥숟가락 약 4개");
  assert.equal(item("고춧가루", 1, "큰술", 1.5).sub, "밥숟가락 약 2개");
  assert.equal(item("설탕", 2 / 3, "큰술", 1.5).sub, "밥숟가락 약 1개");
}
assert.equal(item("간장", 1, "큰술", 0.5).text, "1½작은술");      // 큰술이 작으면 작은술
assert.deepEqual(item("소금", 1, "작은술", 1 / 3), { text: "⅓작은술", sub: null });
assert.equal(item("소금", 1, "작은술", 0.1).text, "약간");
assert.deepEqual(item("물", 1, "컵", 2), { text: "2컵", sub: null });
assert.equal(item("간장", 10, "큰술", 1).text, "¾컵");             // 150ml → ½컵 이상은 컵
assert.equal(item("물", 150, "ml", 1.5).text, "225ml");
assert.deepEqual(item("고춧가루", 20, "g", 1.5), { text: "30g", sub: null });
assert.equal(item("후추", 1, "꼬집", 0.3).text, "1꼬집");
assert.equal(scaleFactor({ basis_amount: 600, basis_unit: "g" }, 900, "g"), 1.5);
assert.equal(scaleFactor({ basis_amount: 0.5, basis_unit: "컵" }, 100, "ml"), 1);
assert.equal(scaleFactor({ basis_amount: 2, basis_unit: "인분" }, 0, "인분"), null);
assert.equal(basisLabel({ basis: "main_weight", basis_amount: 600, basis_unit: "g", main_ingredient: "돼지고기" }), "돼지고기 600g 기준");
assert.equal(basisLabel({ basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null }), "2인분 기준");
assert.equal(basisLabel({ basis: "yield", basis_amount: 0.5, basis_unit: "컵", main_ingredient: null }), "완성 ½컵 기준");
assert.equal(basisLabel({ basis: "yield", basis_amount: 300, basis_unit: "ml", main_ingredient: null }), "완성 300ml 기준");
assert.equal(ratioLabel(1.5), "×1.5"); assert.equal(ratioLabel(1), "×1"); assert.equal(ratioLabel(1 / 3), "×0.33");
for (const [text, value] of [["½", 0.5], ["1½", 1.5], ["1/2", 0.5], ["1 1/2", 1.5], ["0.5", 0.5], ["3", 3]]) assert.equal(parseAmountInput(text), value, text);
for (const text of ["", "abc", "0", "-1", "1/0", "½½"]) assert.equal(parseAmountInput(text), null, text);
assert.equal(new Set(SEASONING_PRESETS.map((p) => p.id)).size, SEASONING_PRESETS.length);
for (const p of SEASONING_PRESETS) {
  assert.ok(p.items.length > 0 && p.basis_amount > 0 && p.source_note, p.name);
  for (const i of p.items) assert.ok(i.amount > 0 && i.name, `${p.name} ${i.name}`);
}
// 기본 양념은 서버 검사(seasonings.py)와 같은 범위 안에 있어야 "이 비율 고쳐서 내 비율로"가 400으로 튕기지 않는다
const UNITS = ["큰술", "작은술", "컵", "ml", "g", "개", "꼬집"];
const BASIS_UNITS = { main_weight: ["g"], servings: ["인분"], yield: ["컵", "ml"] };
for (const p of SEASONING_PRESETS) {
  assert.ok(/2026-\d\d-\d\d/.test(p.source_note), `${p.name} 출처 메모에 확인한 날짜가 없다`);
  assert.ok(p.name.length <= 30 && p.items.length <= 30, p.name);
  assert.ok(BASIS_UNITS[p.basis].includes(p.basis_unit), `${p.name} 기준 단위`);
  assert.ok(p.basis !== "servings" || (p.basis_amount <= 20 && p.basis_amount % 1 === 0), `${p.name} 인분`);
  for (const i of p.items) assert.ok(UNITS.includes(i.unit) && i.amount >= 0.01 && i.amount <= 10000, `${p.name} ${i.name}`);
}

// 단위 경계
assert.equal(item("간장", 1, "작은술", 3).text, "1큰술");              // 15ml
assert.equal(item("물", 1, "작은술", 20).text, "½컵");                 // 100ml
assert.equal(item("소금", 1, "작은술", 0.25).text, "¼작은술");         // 1.25ml
assert.deepEqual(item("간장", 1, "큰술", 0.25), { text: "¾작은술", sub: "¼큰술" }); // 3.75ml
assert.equal(item("소금", 1, "큰술", 0.05).text, "약간");              // 0.75ml
assert.equal(item("간장", 0.99, "큰술", 1).text, "1큰술");             // 14.85ml: 맞춘 값이 1큰술이면 큰술
// 부동소수 오차(15ml 근처)
assert.equal(item("설탕", 1 / 3, "큰술", 3).text, "1큰술");
assert.equal(item("설탕", 2 / 3, "큰술", 1.5).text, "1큰술");
// 분수 맞추기: 가장 가까운 값, 정확히 가운데면 작은 쪽
assert.equal(snapSpoon((1 / 4 + 1 / 3) / 2), "¼");
assert.equal(snapSpoon((1 / 3 + 1 / 2) / 2), "⅓");
assert.equal(snapSpoon((1 / 2 + 2 / 3) / 2), "½");
assert.equal(snapSpoon(1.3), "1⅓"); assert.equal(snapSpoon(-1), "0"); assert.equal(snapSpoon(NaN), "0");
// 배율이 이상하면 약간
for (const factor of [NaN, 0, -1, Infinity]) assert.deepEqual(item("간장", 1, "큰술", factor), { text: "약간", sub: null }, String(factor));
assert.equal(item("물", 0.01, "ml", 1).text, "약간");
assert.equal(item("고춧가루", 0.01, "g", 1).text, "약간");
// 단위가 안 맞거나 입력이 이상하면 null
assert.equal(scaleFactor({ basis_amount: 600, basis_unit: "g" }, 2, "인분"), null);
assert.equal(scaleFactor({ basis_amount: 600, basis_unit: "g" }, 100, "ml"), null);
for (const input of [NaN, -1]) assert.equal(scaleFactor({ basis_amount: 600, basis_unit: "g" }, input, "g"), null);
assert.equal(scaleFactor({ basis_amount: 0, basis_unit: "g" }, 600, "g"), null);
// 양 입력
assert.equal(parseAmountInput("2/4"), 0.5); assert.equal(parseAmountInput(" ½ "), 0.5);
assert.equal(parseAmountInput("10000"), 10000); assert.equal(parseAmountInput("10001"), null);
assert.equal(parseAmountInput("0.01"), 0.01); assert.equal(parseAmountInput("0.009"), null); // 서버 최소 0.01과 같다
// 폼에 채우는 양: 분수로 바꿔도 값이 거의 같을 때만 분수
for (const [value, text] of [[0.5, "½"], [2 / 3, "⅔"], [1.5, "1½"], [3, "3"], [600, "600"], [12.5, "12.5"], [0.03, "0.03"], [0.35, "0.35"], [0.33, "0.33"], [1 / 3, "⅓"], [0.255, "0.255"], [0.1 + 0.2, "0.3"], [15 / 7, "2.1429"]]) assert.equal(amountInputText(value), text, String(value));

// 인분 조절한 레시피 재료 양 아래 회색 줄(스펙 23절 D1): 계산기 scaleItem과 같은 규칙, 1큰술이 안 되거나 숟가락이 아니면 없음
const hint = (text) => spoonHint(recipeQuantity(text));
// 딱 떨어지지 않는 배율(10 → 11인분): 본문(scaleAmount, 소수 한 자리)과 줄(scaleItem, 분수로 맞춤)의 숫자가 달라서 줄은 늘 "약"
const at11 = (amount) => { const text = scaleAmount(amount, 11 / 10); return [text, hint(text)]; };
if (RICE_SPOON_ML === 12) {
  for (const [text, line] of [["3큰술", "밥숟가락 약 4개"], ["1½큰술", "밥숟가락 약 2개"], ["2큰술(30g)", "밥숟가락 약 3개"], ["0.9큰술", "밥숟가락 약 1개"]]) assert.equal(hint(text), line, text);
  assert.deepEqual(at11("2큰술"), ["2.2큰술", "밥숟가락 약 3개"]);
}
assert.deepEqual(at11("6작은술"), ["6.6작은술", "약 2¼큰술"]);
for (const [text, line] of [
  ["3작은술", "약 1큰술"], ["4½작은술", "약 1½큰술"], ["10큰술", "약 ¾컵"],  // 작은술은 큰술로, ½컵 이상은 컵으로(계산기의 굵은 양)
  ["½큰술", null], ["1½작은술", null], ["¼작은술", null],                   // 1큰술이 안 되면 계산기도 밥숟가락을 안 보여준다
  ["900g", null], ["약간", null], ["2개", null], ["1½컵", null], ["10~15개", null], ["1~2큰술", null], ["", null], ["2밥숟가락", null],
]) assert.equal(hint(text), line, text);

console.log("seasoning ok");

// 양념 비율 경로 (3c 계획 태스크 3). useHashRoute.ts는 불러올 때 history를 건드려서 빈 객체를 먼저 둔다.
globalThis.history ??= {};
const { matchRoute } = await import("../src/useHashRoute.ts");
assert.deepEqual(matchRoute("/recipes/seasonings/preset/3"), { path: "/recipes/seasonings/preset/3", pattern: "/recipes/seasonings/preset/:id", params: { id: "3" } });
assert.equal(matchRoute("/recipes/seasonings/7").pattern, "/recipes/seasonings/:id");
assert.deepEqual(matchRoute("/recipes/seasonings/7/edit").params, { id: "7" });
assert.equal(matchRoute("/recipes/seasonings/new").pattern, "/recipes/seasonings/new");
assert.equal(matchRoute("/recipes/seasonings/preset/abc"), null);
for (const path of ["/", "/recipes", "/recipes/new", "/recipes/mine/3", "/recipes/mine/3/edit", "/recipes/public/9", "/tools"]) assert.equal(matchRoute(path)?.path, path, path);
// AI 레시피 경로 (3b 계획 태스크 4)
assert.equal(matchRoute("/recipes/ai").pattern, "/recipes/ai");
assert.equal(matchRoute("/recipes/ai/2").params.n, "2");
assert.equal(matchRoute("/recipes/ai/x"), null);
// 장보기 메모 경로 (4단계 계획 Task 10)
assert.equal(matchRoute("/shopping/memos").pattern, "/shopping/memos");
assert.equal(matchRoute("/shopping/memos/new").pattern, "/shopping/memos/new");
assert.equal(matchRoute("/shopping/memos/local").pattern, "/shopping/memos/local");
assert.deepEqual(matchRoute("/shopping/memos/123").params, { id: "123" });
assert.equal(matchRoute("/shopping/memos/abc"), null);
console.log("matchRoute ok");

// AI 레시피 문구 (3b 계획 태스크 4)
const { namesLabel, remainingText, withJosa } = await import("../src/format.ts");
assert.equal(namesLabel(["두부"]), "두부");
assert.equal(namesLabel(["두부", "대파"]), "두부·대파");
assert.equal(withJosa(namesLabel(["두부", "대파", "애호박"]), "을", "를"), "두부 외 2개를");
assert.equal(remainingText(undefined), "");
assert.equal(remainingText({ scan: { used: 0, limit: 10 }, recipe: { used: 2, limit: 10 } }), " · 오늘 8번 남음");
assert.equal(remainingText({ scan: { used: 0, limit: 10 }, recipe: { used: 10, limit: 10 } }), " · 오늘은 다 썼어요");
assert.equal(remainingText({ scan: { used: 2, limit: 10 }, recipe: { used: 10, limit: 10 } }, "scan"), " · 오늘 8번 남음");
console.log("ai copy ok");

// 영상 경로·길이·올린 때 (3b 계획 태스크 5)
assert.equal(matchRoute("/recipes/videos/12").params.id, "12");
assert.equal(matchRoute("/recipes/videos/abc"), null);
assert.equal(matchRoute("/recipes/channels").pattern, "/recipes/channels");
const { formatDuration, timeAgo } = await import("../src/format.ts");
assert.equal(formatDuration(724), "12:04");
assert.equal(formatDuration(3602), "1:00:02");
assert.equal(formatDuration(3723), "1:02:03");
assert.equal(formatDuration(62), "1:02");
assert.equal(formatDuration(0), "0:00");
assert.equal(formatDuration(null), "");
const NOW = Date.parse("2026-09-14T01:00:00Z"); // 서울 10:00
const ago = (iso) => timeAgo(iso, NOW);
assert.equal(ago("2026-09-11T01:00:00Z"), "3일 전");
assert.equal(ago("2026-09-06T01:00:00Z"), "1주 전");
assert.equal(ago("2026-08-30T01:00:00Z"), "2주 전");
assert.equal(ago("2026-09-14T00:30:00Z"), "방금");
assert.equal(ago("2026-09-13T22:00:00Z"), "3시간 전");      // 서울 07:00, 같은 날
assert.equal(ago("2026-09-13T14:30:00Z"), "1일 전");        // 서울 전날 23:30 (UTC로는 같은 날)
assert.equal(ago("2026-09-13T15:30:00Z"), "9시간 전");      // 서울 00:30, 같은 날 (UTC로는 전날)
assert.equal(ago("2026-07-01T01:00:00Z"), "2달 전");
assert.equal(ago("2026-09-15T01:00:00Z"), "방금");          // 기기 시계가 늦어도 음수가 되지 않게
assert.equal(ago("nope"), "");
console.log("video format ok");
