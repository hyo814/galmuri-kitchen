// 오프라인 장보기 순수 로직 검사 (4단계 계획 Task 6). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
  enqueue, applyQueue, remapRef, classify, groupItems, plannedOnFor, parseQuantityText, quantityText, sourceTag,
} from "../src/shopping/sync.ts";

const T = (m) => `2026-09-14T01:${String(m).padStart(2, "0")}:00.000Z`;
const F = { name: "두부", quantity: 1, unit: "모", planned_on: null, location_id: null };
/** 대기열에 차례로 넣고 마지막 결과와 모인 dropBlobs를 돌려준다 */
function run(ops, start = []) {
  let queue = start;
  const dropped = [];
  for (const op of ops) {
    const r = enqueue(queue, op);
    queue = r.queue;
    dropped.push(...r.dropBlobs);
  }
  return { queue, dropped };
}

// ---- enqueue 합치기 규칙 ----
// 1. 같은 대상 check 뒤 check → 마지막 것만(처음 자리)
{
  const { queue } = run([
    { op: "check", ref: { id: 1 }, done: true, at: T(1) },
    { op: "edit", ref: { id: 2 }, fields: { name: "대파" }, at: T(2) },
    { op: "check", ref: { id: 1 }, done: false, at: T(3) },
    { op: "check", ref: { id: 3 }, done: true, at: T(4) },
  ]);
  assert.deepEqual(queue.map((o) => [o.op, o.ref.id]), [["check", 1], ["edit", 2], ["check", 3]]);
  assert.equal(queue[0].done, false); assert.equal(queue[0].at, T(3));
}
// 서버 id와 client_id가 같은 숫자처럼 보여도 다른 대상
{
  const { queue } = run([
    { op: "check", ref: { id: 1 }, done: true, at: T(1) },
    { op: "check", ref: { client_id: "1" }, done: true, at: T(2) },
  ]);
  assert.equal(queue.length, 2);
}
// 2. 안 보낸 add 뒤 edit → add fields에 합침, check → 그대로 뒤에
{
  const { queue } = run([
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "edit", ref: { client_id: "a" }, fields: { quantity: 2, planned_on: "2026-09-15" }, at: T(2) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(3) },
  ]);
  assert.equal(queue.length, 2);
  assert.deepEqual(queue[0], { op: "add", client_id: "a", fields: { ...F, quantity: 2, planned_on: "2026-09-15" }, at: T(1) });
  assert.equal(queue[1].op, "check");
}
// 3. 안 보낸 add 뒤 delete → add와 그 대상의 모든 변경을 지우고 delete도 안 넣음
{
  const { queue, dropped } = run([
    { op: "check", ref: { id: 9 }, done: true, at: T(0) },
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(2) },
    { op: "delete", ref: { client_id: "a" }, at: T(3) },
  ]);
  assert.deepEqual(queue, [{ op: "check", ref: { id: 9 }, done: true, at: T(0) }]);
  assert.deepEqual(dropped, []);
}
// 3. 메모도 같음 — note_add + note_delete → 사진 blob 키를 dropBlobs로
{
  const { queue, dropped } = run([
    { op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(1) },
    { op: "note_save", ref: { client_id: "n" }, fields: { place: "이마트", body: "계란" }, edited_at: T(2) },
    { op: "photo_add", note: { client_id: "n" }, client_id: "p1", blob_key: "b1", at: T(3) },
    { op: "photo_add", note: { client_id: "n" }, client_id: "p2", blob_key: "b2", at: T(4) },
    { op: "photo_delete", note: { client_id: "n" }, photo: { client_id: "p2" }, at: T(5) },
    { op: "photo_add", note: { id: 7 }, client_id: "p3", blob_key: "b3", at: T(6) },
    { op: "note_delete", ref: { client_id: "n" }, at: T(7) },
  ]);
  assert.deepEqual(queue.map((o) => o.op), ["photo_add"]);
  assert.equal(queue[0].blob_key, "b3");
  assert.deepEqual(dropped.sort(), ["b1", "b2"]);
}
// 4. 서버 항목 delete → 앞의 같은 대상 edit·check를 지우고 delete는 넣음(다른 대상은 그대로)
{
  const { queue } = run([
    { op: "edit", ref: { id: 1 }, fields: { name: "대파" }, at: T(1) },
    { op: "check", ref: { id: 2 }, done: true, at: T(2) },
    { op: "check", ref: { id: 1 }, done: true, at: T(3) },
    { op: "delete", ref: { id: 1 }, at: T(4) },
  ]);
  assert.deepEqual(queue.map((o) => [o.op, o.ref.id]), [["check", 2], ["delete", 1]]);
}
// 4. 서버 메모 note_delete → 앞의 note_save·그 메모 photo_add(blob) 지움, 다른 메모는 그대로
{
  const { queue, dropped } = run([
    { op: "note_save", ref: { id: 5 }, fields: { place: null, body: "a" }, edited_at: T(1) },
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(2) },
    { op: "photo_delete", note: { id: 5 }, photo: { id: 40 }, at: T(3) },
    { op: "note_save", ref: { id: 6 }, fields: { place: null, body: "b" }, edited_at: T(4) },
    { op: "note_delete", ref: { id: 5 }, at: T(5) },
  ]);
  assert.deepEqual(queue.map((o) => o.op), ["note_save", "note_delete"]);
  assert.equal(queue[0].ref.id, 6);
  assert.deepEqual(dropped, ["b"]);
}
// 5. note_save 뒤 note_save → 마지막 fields·edited_at으로 하나(처음 자리)
{
  const { queue } = run([
    { op: "note_save", ref: { id: 5 }, fields: { place: null, body: "계" }, edited_at: T(1) },
    { op: "check", ref: { id: 1 }, done: true, at: T(2) },
    { op: "note_save", ref: { id: 5 }, fields: { place: "이마트", body: "계란 30구" }, edited_at: T(3) },
  ]);
  assert.deepEqual(queue.map((o) => o.op), ["note_save", "check"]);
  assert.deepEqual(queue[0], { op: "note_save", ref: { id: 5 }, fields: { place: "이마트", body: "계란 30구" }, edited_at: T(3) });
}
// 5. 안 보낸 note_add면 그 fields에 합침
{
  const { queue } = run([
    { op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(1) },
    { op: "note_save", ref: { client_id: "n" }, fields: { place: "시장", body: "대파" }, edited_at: T(2) },
    { op: "note_save", ref: { client_id: "n" }, fields: { place: "시장", body: "대파 1단" }, edited_at: T(3) },
  ]);
  assert.deepEqual(queue, [{ op: "note_add", client_id: "n", fields: { place: "시장", body: "대파 1단" }, at: T(1) }]);
}
// 6. 안 보낸 photo_add 뒤 photo_delete → 둘 다 없앰 + dropBlobs. 서버 사진 photo_delete는 그대로 넣음
{
  const { queue, dropped } = run([
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(1) },
    { op: "photo_delete", note: { id: 5 }, photo: { client_id: "p" }, at: T(2) },
    { op: "photo_delete", note: { id: 5 }, photo: { id: 41 }, at: T(3) },
  ]);
  assert.deepEqual(queue, [{ op: "photo_delete", note: { id: 5 }, photo: { id: 41 }, at: T(3) }]);
  assert.deepEqual(dropped, ["b"]);
}
// 7. 순서는 들어온 순서, 입력 대기열은 바꾸지 않는다
{
  const start = [{ op: "check", ref: { id: 1 }, done: true, at: T(1) }];
  const frozen = structuredClone(start);
  const { queue } = enqueue(start, { op: "check", ref: { id: 1 }, done: false, at: T(2) });
  assert.deepEqual(start, frozen);
  assert.equal(queue[0].done, false);
  const r = run([
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "edit", ref: { id: 3 }, fields: { name: "x" }, at: T(2) },
    { op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(3) },
    { op: "edit", ref: { client_id: "a" }, fields: { name: "순두부" }, at: T(4) },
  ]);
  assert.deepEqual(r.queue.map((o) => o.op), ["add", "edit", "note_add"]);
  assert.equal(r.queue[0].fields.name, "순두부");
}

// ---- applyQueue ----
const item = (id, extra = {}) => ({
  id, client_id: null, name: `항목${id}`, quantity: 1, unit: "개", planned_on: null, location_id: null, location_name: null,
  source: "manual", source_label: null, done_at: null, done_changed_at: null, stocked_at: null, created_at: T(0), ...extra,
});
const SNAP = {
  items: [item(1), item(2), item(3, { client_id: "old" })],
  stocked: [item(10, { stocked_at: T(0) })],
  notes: [{ id: 5, client_id: null, place: "이마트 성수점", body: "세일 수요일까지", updated_at: T(0), photos: [{ id: 40, client_id: null, url: "/api/photos/shopping/1/x.jpg" }] }],
  today: "2026-09-14",
};
{
  const frozen = structuredClone(SNAP);
  const { queue } = run([
    { op: "check", ref: { id: 1 }, done: true, at: T(5) },
    { op: "add", client_id: "new", fields: { ...F, source: "recipe", source_label: "두부조림" }, at: T(6) },
    { op: "delete", ref: { id: 2 }, at: T(7) },
    { op: "note_save", ref: { id: 5 }, fields: { place: "이마트 성수점", body: "계란은 30구로" }, edited_at: T(8) },
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "blob-p", at: T(9) },
    { op: "photo_delete", note: { id: 5 }, photo: { id: 40 }, at: T(9) },
    { op: "note_add", client_id: "n2", fields: { place: null, body: "두 번째" }, at: T(10) },
  ]);
  const view = applyQueue(SNAP, queue);
  assert.deepEqual(SNAP, frozen, "스냅숏은 바꾸지 않는다");
  assert.deepEqual(view.items.map((i) => i.id), [1, 3, undefined]);
  assert.equal(view.items[0].done_at, T(5)); assert.equal(view.items[0].done_changed_at, T(5)); assert.equal(view.items[0].pending, true);
  assert.equal(view.items[1].pending, false);
  const added = view.items[2];
  assert.equal(added.client_id, "new"); assert.equal(added.pending, true); assert.equal(added.name, "두부");
  assert.equal(added.source, "recipe"); assert.equal(added.source_label, "두부조림"); assert.equal(added.created_at, T(6));
  assert.equal(added.done_at, null); assert.equal(added.stocked_at, null);
  assert.deepEqual(view.stocked, SNAP.stocked);
  assert.equal(view.today, "2026-09-14");
  // 최근 고친 메모가 앞(서버 순서와 같게)
  assert.deepEqual(view.notes[0], { client_id: "n2", place: null, body: "두 번째", updated_at: T(10), photos: [], pending: true });
  assert.equal(view.notes[1].id, 5);
  assert.equal(view.notes[1].body, "계란은 30구로"); assert.equal(view.notes[1].updated_at, T(8)); assert.equal(view.notes[1].pending, true);
  assert.deepEqual(view.notes[1].photos, [{ client_id: "p", blob_key: "blob-p", pending: true }]);
  assert.equal(SNAP.notes[0].photos.length, 1);
}
// 기본값: source 없으면 manual, 해제 체크는 done_at null
{
  const view = applyQueue(SNAP, [
    { op: "add", client_id: "x", fields: F, at: T(1) },
    { op: "check", ref: { client_id: "x" }, done: true, at: T(2) },
    { op: "check", ref: { id: 1 }, done: false, at: T(3) },
    { op: "edit", ref: { id: 3 }, fields: { name: "순두부", location_id: 4 }, at: T(4) },
  ]);
  const x = view.items.find((i) => i.client_id === "x");
  assert.equal(x.source, "manual"); assert.equal(x.done_at, T(2));
  assert.equal(view.items[0].done_at, null); assert.equal(view.items[0].done_changed_at, T(3));
  assert.equal(view.items[2].name, "순두부"); assert.equal(view.items[2].location_id, 4); assert.equal(view.items[2].location_name, null);
}
// 다른 기기가 더 늦게 바꾼 체크는 서버가 무시하므로 화면도 서버 값(19절 마지막 변경 우선)
{
  const snap = { ...SNAP, items: [item(1, { done_at: T(9), done_changed_at: "2026-09-14T01:09:00+00:00" })] };
  const view = applyQueue(snap, [{ op: "check", ref: { id: 1 }, done: false, at: T(5) }]);
  assert.equal(view.items[0].done_at, T(9));
}
// 보냈지만 응답을 못 받은 add(서버에 이미 같은 client_id) → 두 번 보이지 않음, client_id 참조가 서버 항목을 찾음
{
  const view = applyQueue(SNAP, [
    { op: "add", client_id: "old", fields: F, at: T(1) },
    { op: "check", ref: { client_id: "old" }, done: true, at: T(2) },
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(3) },
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(3) },
  ]);
  assert.equal(view.items.length, 3);
  assert.equal(view.items[2].done_at, T(2));
  assert.equal(view.notes[0].photos.length, 2);
}
// 없는 대상을 가리키는 변경은 조용히 넘어간다
assert.equal(applyQueue(SNAP, [{ op: "edit", ref: { id: 99 }, fields: { name: "x" }, at: T(1) }, { op: "photo_add", note: { id: 99 }, client_id: "p", blob_key: "b", at: T(1) }]).items.length, 3);

// ---- remapRef ----
{
  const queue = [
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "edit", ref: { client_id: "a" }, fields: { name: "x" }, at: T(2) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(3) },
    { op: "delete", ref: { client_id: "b" }, at: T(4) },
    { op: "delete", ref: { client_id: "a" }, at: T(5) },
    { op: "photo_add", note: { client_id: "a" }, client_id: "p", blob_key: "k", at: T(6) },
    { op: "photo_delete", note: { client_id: "a" }, photo: { client_id: "a" }, at: T(7) },
    { op: "note_save", ref: { client_id: "a" }, fields: { place: null, body: "" }, edited_at: T(8) },
    { op: "note_delete", ref: { id: 3 }, at: T(9) },
  ];
  const frozen = structuredClone(queue);
  const out = remapRef(queue, "a", 42);
  assert.deepEqual(queue, frozen);
  assert.deepEqual(out[0], queue[0], "add 자신의 client_id는 그대로");
  assert.deepEqual(out[1].ref, { id: 42 }); assert.deepEqual(out[2].ref, { id: 42 }); assert.deepEqual(out[4].ref, { id: 42 });
  assert.deepEqual(out[3].ref, { client_id: "b" }, "다른 client_id는 그대로");
  assert.deepEqual(out[5].note, { id: 42 }); assert.equal(out[5].client_id, "p");
  assert.deepEqual(out[6].note, { id: 42 }); assert.deepEqual(out[6].photo, { id: 42 });
  assert.deepEqual(out[7].ref, { id: 42 }); assert.deepEqual(out[8].ref, { id: 3 });
}

// ---- classify ----
const OP = {
  add: { op: "add", client_id: "a", fields: F, at: T(1) },
  edit: { op: "edit", ref: { id: 1 }, fields: {}, at: T(1) },
  check: { op: "check", ref: { id: 1 }, done: true, at: T(1) },
  delete: { op: "delete", ref: { id: 1 }, at: T(1) },
  note_add: { op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(1) },
  note_save: { op: "note_save", ref: { id: 1 }, fields: { place: null, body: "" }, edited_at: T(1) },
  note_delete: { op: "note_delete", ref: { id: 1 }, at: T(1) },
  photo_add: { op: "photo_add", note: { id: 1 }, client_id: "p", blob_key: "b", at: T(1) },
  photo_delete: { op: "photo_delete", note: { id: 1 }, photo: { id: 2 }, at: T(1) },
};
for (const [name, status, expected] of [
  ["check", 404, "ok"], ["delete", 404, "ok"], ["note_delete", 404, "ok"], ["photo_delete", 404, "ok"],
  ["edit", 404, "drop"], ["note_save", 404, "drop"], ["photo_add", 404, "drop"],
  ["add", 400, "drop"], ["add", 413, "drop"], ["photo_add", 413, "drop"], ["photo_add", 415, "drop"], ["photo_add", 503, "drop"],
  ["edit", 503, "retry"], ["add", 500, "retry"], ["note_save", 502, "retry"], ["check", 408, "retry"],
  ["note_save", 409, "conflict"], ["edit", 409, "drop"],
  ["add", 200, "ok"], ["add", 201, "ok"], ["delete", 204, "ok"], ["note_save", 200, "ok"],
]) assert.equal(classify(OP[name], status), expected, `${name} ${status}`);
for (const op of Object.values(OP)) {
  assert.equal(classify(op, 0), "retry", `${op.op} 0`);
  assert.equal(classify(op, 429), "retry", `${op.op} 429`);
  assert.equal(classify(op, 401), "auth", `${op.op} 401`);
}

// ---- groupItems / plannedOnFor ----
{
  const it = (name, planned_on, created_at = T(0), extra = {}) => ({ name, planned_on, created_at, ...extra });
  const items = [
    it("미정2", null, T(5)),
    it("나중", "2026-09-21"),
    it("이번주끝", "2026-09-20"),
    it("오늘체크", "2026-09-14", T(3), { done_at: T(4) }),
    it("지남", "2026-09-10"),
    it("오늘", "2026-09-14", T(1)),
    it("내일", "2026-09-15"),
    it("미정1", null, T(1)),
  ];
  const groups = groupItems(items, "2026-09-14");
  assert.deepEqual(groups.map((g) => [g.key, g.title]), [["today", "오늘"], ["week", "이번 주"], ["later", "나중에"], ["undated", "날짜 미정"]]);
  assert.deepEqual(groups.map((g) => g.items.map((i) => i.name)), [["지남", "오늘", "오늘체크"], ["내일", "이번주끝"], ["나중"], ["미정1", "미정2"]]);
  assert.equal(groups[0].items[2], items[3], "같은 객체를 돌려준다");
  // 체크해도 자리 그대로
  const unchecked = items.map((i) => ({ ...i, done_at: null }));
  assert.deepEqual(groupItems(unchecked, "2026-09-14").map((g) => g.items.map((i) => i.name)), groups.map((g) => g.items.map((i) => i.name)));
  // 빈 묶음은 뺀다
  assert.deepEqual(groupItems([it("a", null)], "2026-09-14").map((g) => g.key), ["undated"]);
  assert.deepEqual(groupItems([], "2026-09-14"), []);
  // created_at은 시각으로 비교(서버 +00:00, 기기 Z 섞임)
  assert.deepEqual(groupItems([it("b", null, "2026-09-14T01:05:00+00:00"), it("a", null, "2026-09-14T01:04:00.000Z")], "2026-09-14")[0].items.map((i) => i.name), ["a", "b"]);
  // 연말: today+6
  assert.deepEqual(groupItems([it("a", "2027-01-04"), it("b", "2027-01-05")], "2026-12-29").map((g) => g.key), ["week", "later"]);
}
assert.equal(plannedOnFor("today", "2026-09-14"), "2026-09-14");
assert.equal(plannedOnFor("week", "2026-09-14"), "2026-09-20");
assert.equal(plannedOnFor("week", "2026-12-29"), "2027-01-04");
assert.equal(plannedOnFor("undated", "2026-09-14"), null);

// ---- parseQuantityText / quantityText ----
for (const [text, quantity, unit] of [
  ["1모", 1, "모"], ["30구", 30, "구"], ["1L", 1, "L"], ["½봉", 0.5, "봉"], ["1/2대", 0.5, "대"], ["2", 2, "개"], ["모", 1, "모"], ["", 1, "개"],
  [" 1 모 ", 1, "모"], ["1½봉", 1.5, "봉"], ["1 1/2컵", 1.5, "컵"], ["0.5kg", 0.5, "kg"], ["300g", 300, "g"], ["가나다라마바사아자차", 1, "가나다라마바사아자차"],
]) assert.deepEqual(parseQuantityText(text), { quantity, unit }, text);
for (const text of ["0개", "-1개", "1가나다라마바사아자차카", "1/0개", "1-2개", "10001개", "1모2", "½½봉"]) assert.equal(parseQuantityText(text), null, text);
for (const [q, u, text] of [[0.5, "봉", "½봉"], [1, "모", "1모"], [30, "구", "30구"], [1.5, "봉", "1½봉"], [12.5, "g", "12.5g"], [0.33, "개", "0.33개"]]) {
  assert.equal(quantityText(q, u), text);
  assert.deepEqual(parseQuantityText(text), { quantity: q, unit: u }, `되돌리기 ${text}`);
}

// ---- sourceTag ----
assert.deepEqual(sourceTag({ source: "recipe", source_label: "두부조림" }), { text: "레시피 · 두부조림", tone: "info" });
assert.deepEqual(sourceTag({ source: "recipe", source_label: null }), { text: "레시피", tone: "info" });
assert.deepEqual(sourceTag({ source: "urgent", source_label: null }), { text: "곧 떨어져요", tone: "warn" });
assert.deepEqual(sourceTag({ source: "staple", source_label: null }), { text: "필수품", tone: "" });
assert.deepEqual(sourceTag({ source: "memo", source_label: null }), { text: "메모 사진", tone: "" });
assert.equal(sourceTag({ source: "manual", source_label: null }), null);

// ---- 속성 검사: 고정 시드 무작위 op 200개 → applyQueue가 같은 id·client_id를 두 번 내지 않는다 ----
{
  let seed = 20260914;
  const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const pick = (list) => list[Math.floor(rand() * list.length)];
  const itemRef = () => (rand() < 0.5 ? { id: pick([1, 2, 3, 4]) } : { client_id: pick(["c1", "c2", "c3", "old"]) });
  const noteRef = () => (rand() < 0.5 ? { id: 5 } : { client_id: pick(["n1", "n2"]) });
  const makers = [
    () => ({ op: "add", client_id: pick(["c1", "c2", "c3", "old"]), fields: F, at: T(1) }),
    () => ({ op: "edit", ref: itemRef(), fields: { name: "x" }, at: T(1) }),
    () => ({ op: "check", ref: itemRef(), done: rand() < 0.5, at: T(1) }),
    () => ({ op: "delete", ref: itemRef(), at: T(1) }),
    () => ({ op: "note_add", client_id: pick(["n1", "n2"]), fields: { place: null, body: "" }, at: T(1) }),
    () => ({ op: "note_save", ref: noteRef(), fields: { place: null, body: "y" }, edited_at: T(2) }),
    () => ({ op: "note_delete", ref: noteRef(), at: T(1) }),
    () => { const c = pick(["p1", "p2", "p3"]); return { op: "photo_add", note: noteRef(), client_id: c, blob_key: `blob-${c}`, at: T(1) }; },
    () => ({ op: "photo_delete", note: noteRef(), photo: rand() < 0.5 ? { id: 40 } : { client_id: pick(["p1", "p2", "p3"]) }, at: T(1) }),
  ];
  const noDupes = (list, key, label) => {
    const values = list.map((x) => x[key]).filter((v) => v != null);
    assert.equal(new Set(values).size, values.length, `${label} ${key} 중복`);
  };
  let queue = [];
  for (let n = 0; n < 200; n++) {
    queue = enqueue(queue, pick(makers)()).queue;
    const view = applyQueue(SNAP, queue);
    noDupes(view.items, "id", "항목"); noDupes(view.items, "client_id", "항목");
    noDupes(view.notes, "id", "메모"); noDupes(view.notes, "client_id", "메모");
    for (const note of view.notes) { noDupes(note.photos, "id", "사진"); noDupes(note.photos, "client_id", "사진"); }
    const checks = queue.filter((o) => o.op === "check").map((o) => JSON.stringify(o.ref));
    assert.equal(new Set(checks).size, checks.length, "같은 대상 check는 하나");
  }
}

console.log("shopping sync ok");
