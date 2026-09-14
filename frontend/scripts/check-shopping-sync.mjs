// 오프라인 장보기 순수 로직 검사 (4단계 계획 Task 6). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
  enqueue, markAttempt, markServerError, removeOp, dropWithDependents, applyQueue, applyServerResult, remapRef, classify, newClientId, MAX_ATTEMPTS,
  groupItems, plannedOnFor, parseQuantityText, quantityText, sourceTag,
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
const strip = (queue) => queue.map(({ qid, attempts, ...op }) => op);
const sendHead = (queue) => markAttempt(queue, queue[0].qid);

// ---- enqueue 합치기 규칙(아무것도 안 보냈을 때) ----
// 1. 같은 대상 check 뒤 check → 마지막 것만(처음 자리, 처음 qid)
{
  const { queue } = run([
    { op: "check", ref: { id: 1 }, done: true, at: T(1) },
    { op: "edit", ref: { id: 2 }, fields: { name: "대파" }, at: T(2) },
    { op: "check", ref: { id: 1 }, done: false, at: T(3) },
    { op: "check", ref: { id: 3 }, done: true, at: T(4) },
  ]);
  assert.deepEqual(queue.map((o) => [o.op, o.ref.id, o.qid]), [["check", 1, 1], ["edit", 2, 2], ["check", 3, 3]]);
  assert.equal(queue[0].done, false); assert.equal(queue[0].at, T(3));
}
// 서버 id와 client_id가 같은 숫자처럼 보여도 다른 대상
assert.equal(run([{ op: "check", ref: { id: 1 }, done: true, at: T(1) }, { op: "check", ref: { client_id: "1" }, done: true, at: T(2) }]).queue.length, 2);
// 2. 안 보낸 add 뒤 edit → add fields에 합침, check → 그대로 뒤에
{
  const { queue } = run([
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "edit", ref: { client_id: "a" }, fields: { quantity: 2, planned_on: "2026-09-15" }, at: T(2) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(3) },
  ]);
  assert.deepEqual(strip(queue), [
    { op: "add", client_id: "a", fields: { ...F, quantity: 2, planned_on: "2026-09-15" }, at: T(1) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(3) },
  ]);
}
// 3. 안 보낸 add 뒤 delete → add와 그 대상의 모든 변경을 지우고 delete도 안 넣음
{
  const { queue, dropped } = run([
    { op: "check", ref: { id: 9 }, done: true, at: T(0) },
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(2) },
    { op: "delete", ref: { client_id: "a" }, at: T(3) },
  ]);
  assert.deepEqual(strip(queue), [{ op: "check", ref: { id: 9 }, done: true, at: T(0) }]);
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
// 4. 서버 메모 note_delete → 앞의 note_save·그 메모 사진 변경을 지움(blob), 다른 메모는 그대로
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
  assert.deepEqual(strip(queue), [
    { op: "note_save", ref: { id: 5 }, fields: { place: "이마트", body: "계란 30구" }, edited_at: T(3) },
    { op: "check", ref: { id: 1 }, done: true, at: T(2) },
  ]);
}
// 5. 안 보낸 note_add면 그 fields에 합침(at은 마지막 저장 시각)
{
  const { queue } = run([
    { op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(1) },
    { op: "note_save", ref: { client_id: "n" }, fields: { place: "시장", body: "대파" }, edited_at: T(2) },
    { op: "note_save", ref: { client_id: "n" }, fields: { place: "시장", body: "대파 1단" }, edited_at: T(3) },
  ]);
  assert.deepEqual(strip(queue), [{ op: "note_add", client_id: "n", fields: { place: "시장", body: "대파 1단" }, at: T(3) }]);
}
// 6. 안 보낸 photo_add 뒤 photo_delete → 둘 다 없앰 + dropBlobs. 서버 사진·다른 메모의 사진은 그대로 넣음
{
  const { queue, dropped } = run([
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(1) },
    { op: "photo_delete", note: { id: 6 }, photo: { client_id: "p" }, at: T(2) },
    { op: "photo_delete", note: { id: 5 }, photo: { client_id: "p" }, at: T(2) },
    { op: "photo_delete", note: { id: 5 }, photo: { id: 41 }, at: T(3) },
  ]);
  assert.deepEqual(strip(queue), [
    { op: "photo_delete", note: { id: 6 }, photo: { client_id: "p" }, at: T(2) },
    { op: "photo_delete", note: { id: 5 }, photo: { id: 41 }, at: T(3) },
  ]);
  assert.deepEqual(dropped, ["b"]);
}
// 7. 순서는 들어온 순서, 입력 대기열은 바꾸지 않는다
{
  const start = run([{ op: "check", ref: { id: 1 }, done: true, at: T(1) }]).queue;
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

// ---- 한 번이라도 보낸 op는 합치거나 바꾸거나 지우지 않는다(서버에 닿았을 수 있음) ----
// 체크를 보내는 중에 다시 누름 → 뒤에 따로
{
  let { queue } = run([{ op: "check", ref: { id: 1 }, done: true, at: T(1) }]);
  queue = sendHead(queue);
  const sent = queue[0];
  queue = run([{ op: "check", ref: { id: 1 }, done: false, at: T(2) }, { op: "check", ref: { id: 1 }, done: true, at: T(3) }], queue).queue;
  assert.equal(queue.length, 2); assert.equal(queue[0], sent);
  assert.equal(queue[1].done, true); assert.equal(queue[1].attempts, undefined);
  // 보내는 중인 체크는 서버 항목 delete로도 안 지운다
  queue = run([{ op: "delete", ref: { id: 1 }, at: T(4) }], queue).queue;
  assert.deepEqual(queue.map((o) => o.op), ["check", "delete"]); assert.equal(queue[0], sent);
}
// add 보냄 + 응답 못 받음 → edit는 합치지 않고 따로(서버는 client_id가 있으면 fields를 무시하고 기존 항목만 준다) → 성공 후 remap으로 PATCH {id}
{
  let { queue } = run([{ op: "add", client_id: "a", fields: F, at: T(1) }]);
  queue = sendHead(queue);
  const add = queue[0];
  queue = run([{ op: "edit", ref: { client_id: "a" }, fields: { name: "순두부" }, at: T(2) }], queue).queue;
  assert.equal(queue[0], add); assert.equal(add.fields.name, "두부");
  assert.deepEqual(strip(queue.slice(1)), [{ op: "edit", ref: { client_id: "a" }, fields: { name: "순두부" }, at: T(2) }]);
  // 다시 보냈더니 200(기존 항목) → remap + removeOp
  queue = removeOp(remapRef(markAttempt(queue, add.qid), "a", 42), add.qid);
  assert.deepEqual(strip(queue), [{ op: "edit", ref: { id: 42 }, fields: { name: "순두부" }, at: T(2) }]);
}
// add 보냄 + 응답 못 받음 → delete는 대기열에 들어간다(안 보낸 체크는 지움)
{
  let { queue } = run([{ op: "add", client_id: "a", fields: F, at: T(1) }]);
  queue = sendHead(queue);
  queue = run([{ op: "check", ref: { client_id: "a" }, done: true, at: T(2) }, { op: "delete", ref: { client_id: "a" }, at: T(3) }], queue).queue;
  assert.deepEqual(queue.map((o) => o.op), ["add", "delete"]);
  const addQid = queue[0].qid;
  assert.deepEqual(strip(removeOp(remapRef(queue, "a", 42), addQid)), [{ op: "delete", ref: { id: 42 }, at: T(3) }]);
  assert.deepEqual(applyQueue({ items: [], stocked: [], notes: [], today: "2026-09-14" }, queue).items, []);
}
// note_add 보냄 → note_save는 따로, note_delete도 들어간다(보낸 사진은 남기고 안 보낸 사진 blob만 버림)
{
  let { queue } = run([{ op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(1) }]);
  queue = sendHead(queue);
  queue = run([{ op: "note_save", ref: { client_id: "n" }, fields: { place: null, body: "대파" }, edited_at: T(2) }], queue).queue;
  assert.deepEqual(queue.map((o) => o.op), ["note_add", "note_save"]);
  assert.equal(queue[0].fields.body, "");
  const r = run([
    { op: "photo_add", note: { client_id: "n" }, client_id: "p", blob_key: "b", at: T(3) },
    { op: "note_delete", ref: { client_id: "n" }, at: T(4) },
  ], queue);
  assert.deepEqual(r.queue.map((o) => o.op), ["note_add", "note_delete"]);
  assert.deepEqual(r.dropped, ["b"]);
}
// photo_add 보냄 → photo_delete는 둘 다 남고 blob도 버리지 않는다
{
  let { queue } = run([{ op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(1) }]);
  queue = sendHead(queue);
  const r = run([{ op: "photo_delete", note: { id: 5 }, photo: { client_id: "p" }, at: T(2) }], queue);
  assert.deepEqual(r.queue.map((o) => o.op), ["photo_add", "photo_delete"]);
  assert.deepEqual(r.dropped, []);
  assert.deepEqual(removeOp(remapRef(r.queue, "p", 40), r.queue[0].qid)[0].photo, { id: 40 });
}
// 보낸 note_save 뒤 저장은 따로, 그 뒤 저장끼리는 합친다
{
  let { queue } = run([{ op: "note_save", ref: { id: 5 }, fields: { place: null, body: "a" }, edited_at: T(1) }]);
  queue = sendHead(queue);
  queue = run([
    { op: "note_save", ref: { id: 5 }, fields: { place: null, body: "ab" }, edited_at: T(2) },
    { op: "note_save", ref: { id: 5 }, fields: { place: null, body: "abc" }, edited_at: T(3) },
  ], queue).queue;
  assert.deepEqual(queue.map((o) => o.fields.body), ["a", "abc"]);
}
// markAttempt·removeOp는 qid로 찾고 입력을 바꾸지 않는다, 새 qid는 겹치지 않는다
{
  const { queue } = run([{ op: "check", ref: { id: 1 }, done: true, at: T(1) }, { op: "check", ref: { id: 2 }, done: true, at: T(1) }]);
  const frozen = structuredClone(queue);
  assert.deepEqual(markAttempt(markAttempt(queue, 2), 2).map((o) => o.attempts), [undefined, 2]);
  assert.deepEqual(removeOp(queue, 1).map((o) => o.qid), [2]);
  assert.deepEqual(queue, frozen);
  assert.equal(enqueue(removeOp(queue, 1), { op: "delete", ref: { id: 7 }, at: T(2) }).queue[1].qid, 3);
}

// ---- dropWithDependents: 실패로 버린 add가 만들려던 대상을 가리키는 변경도 함께 뺀다 ----
{
  const { queue } = run([
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "check", ref: { id: 9 }, done: true, at: T(2) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(3) },
    { op: "note_add", client_id: "n", fields: { place: null, body: "" }, at: T(4) },
    { op: "photo_add", note: { client_id: "n" }, client_id: "p", blob_key: "b1", at: T(5) },
    { op: "photo_add", note: { client_id: "n" }, client_id: "q", blob_key: "b2", at: T(5) },
    { op: "photo_delete", note: { id: 5 }, photo: { client_id: "zz" }, at: T(6) },
    { op: "note_save", ref: { client_id: "n" }, fields: { place: null, body: "x" }, edited_at: T(7) },
    { op: "edit", ref: { client_id: "a" }, fields: { name: "순두부" }, at: T(8) },
    { op: "photo_add", note: { id: 5 }, client_id: "r", blob_key: "b3", at: T(9) },
    { op: "photo_delete", note: { id: 5 }, photo: { client_id: "r" }, at: T(10) },
  ]);
  // 위 대기열은 합치기로 note_save는 note_add에, r 사진은 이미 빠졌다
  assert.equal(queue.find((o) => o.op === "note_add").fields.body, "x");
  assert.equal(queue.some((o) => o.client_id === "r"), false);
  const frozen = structuredClone(queue);
  let r = dropWithDependents(queue, queue[0].qid);
  assert.deepEqual(queue, frozen);
  assert.deepEqual(r.queue.map((o) => o.op), ["check", "note_add", "photo_add", "photo_add", "photo_delete"]);
  r = dropWithDependents(r.queue, r.queue[1].qid);
  assert.deepEqual(strip(r.queue), [{ op: "check", ref: { id: 9 }, done: true, at: T(2) }, { op: "photo_delete", note: { id: 5 }, photo: { client_id: "zz" }, at: T(6) }]);
  assert.deepEqual(r.dropBlobs, ["b1", "b2"]);
  // photo_add 실패 → 자기 blob과 그 사진 삭제, 다른 op 실패 → 자기만
  const p = run([
    { op: "photo_add", note: { id: 5 }, client_id: "p", blob_key: "b", at: T(1) },
    { op: "check", ref: { id: 1 }, done: true, at: T(2) },
  ]).queue;
  const withSent = [...markAttempt(p, p[0].qid), { op: "photo_delete", note: { id: 5 }, photo: { client_id: "p" }, at: T(3), qid: 9 }];
  assert.deepEqual(dropWithDependents(withSent, withSent[0].qid), { queue: [withSent[1]], dropBlobs: ["b"] });
  assert.deepEqual(dropWithDependents(withSent, withSent[1].qid).queue, [withSent[0], withSent[2]]);
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
}
// 기본값: source 없으면 manual, 해제 체크는 done_at null, 위치를 바꾸면 위치 이름은 모름
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
// 다른 기기가 더 늦게 바꾼 체크는 서버가 무시하므로 화면도 서버 값, 같은 시각이면 기기 것(서버도 받아들인다)
{
  const snap = { ...SNAP, items: [item(1, { done_at: T(9), done_changed_at: "2026-09-14T01:09:00+00:00" })] };
  assert.equal(applyQueue(snap, [{ op: "check", ref: { id: 1 }, done: false, at: T(5) }]).items[0].done_at, T(9));
  const tie = applyQueue(snap, [{ op: "check", ref: { id: 1 }, done: false, at: T(9) }]).items[0];
  assert.equal(tie.done_at, null); assert.equal(tie.pending, true);
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

// ---- applyServerResult: 보낸 변경이 새로 받기 전까지 화면에서 사라지지 않는다 ----
{
  const frozen = structuredClone(SNAP);
  let snapshot = SNAP;
  let { queue } = run([
    { op: "add", client_id: "a", fields: F, at: T(1) },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(2) },
    { op: "note_add", client_id: "n", fields: { place: null, body: "메모" }, at: T(3) },
    { op: "photo_add", note: { client_id: "n" }, client_id: "p", blob_key: "b", at: T(4) },
  ]);
  const before = applyQueue(snapshot, queue);
  // add 성공
  let op = queue[0];
  queue = markAttempt(queue, op.qid);
  snapshot = applyServerResult(snapshot, op, item(42, { client_id: "a", name: "두부", unit: "모", created_at: T(1) }));
  queue = removeOp(remapRef(queue, "a", 42), op.qid);
  let view = applyQueue(snapshot, queue);
  assert.equal(view.items.length, before.items.length);
  assert.deepEqual(view.items.at(-1), { ...item(42, { client_id: "a", name: "두부", unit: "모", created_at: T(1) }), done_at: T(2), done_changed_at: T(2), pending: true });
  // check 성공
  op = queue[0];
  snapshot = applyServerResult(snapshot, op, item(42, { client_id: "a", name: "두부", unit: "모", created_at: T(1), done_at: T(2), done_changed_at: T(2) }));
  queue = removeOp(queue, op.qid);
  assert.equal(applyQueue(snapshot, queue).items.at(-1).pending, false);
  // 메모·사진 성공
  op = queue[0];
  snapshot = applyServerResult(snapshot, op, { id: 8, client_id: "n", place: null, body: "메모", updated_at: T(3), photos: [] });
  queue = removeOp(remapRef(queue, "n", 8), op.qid);
  op = queue[0];
  assert.deepEqual(op.note, { id: 8 });
  snapshot = applyServerResult(snapshot, op, { id: 50, client_id: "p", url: "/api/photos/shopping/1/p.jpg" });
  queue = removeOp(remapRef(queue, "p", 50), op.qid);
  view = applyQueue(snapshot, queue);
  assert.deepEqual(queue, []);
  assert.deepEqual(view.notes.map((n) => [n.id, n.photos.map((p) => p.id)]), [[8, [50]], [5, [40]]]);
  // 지우기
  snapshot = applyServerResult(snapshot, { op: "photo_delete", note: { id: 5 }, photo: { id: 40 }, at: T(5) }, null);
  snapshot = applyServerResult(snapshot, { op: "delete", ref: { id: 1 }, at: T(5) }, null);
  snapshot = applyServerResult(snapshot, { op: "note_delete", ref: { id: 8 }, at: T(5) }, null);
  assert.deepEqual(snapshot.items.map((i) => i.id), [2, 3, 42]);
  assert.deepEqual(snapshot.notes.map((n) => [n.id, n.photos.length]), [[5, 0]]);
  // 메모 저장 성공(또는 409의 body.note) → 교체 후 최근 순
  snapshot = applyServerResult(snapshot, { op: "note_save", ref: { id: 5 }, fields: { place: null, body: "" }, edited_at: T(6) }, { ...snapshot.notes[0], body: "서버", updated_at: T(6) });
  assert.equal(snapshot.notes[0].body, "서버"); assert.equal(snapshot.notes.length, 1);
  assert.deepEqual(SNAP, frozen, "원래 스냅숏은 그대로");
}

// ---- remapRef ----
{
  const queue = [
    { op: "add", client_id: "a", fields: F, at: T(1), qid: 1 },
    { op: "edit", ref: { client_id: "a" }, fields: { name: "x" }, at: T(2), qid: 2 },
    { op: "check", ref: { client_id: "a" }, done: true, at: T(3), qid: 3 },
    { op: "delete", ref: { client_id: "b" }, at: T(4), qid: 4 },
    { op: "note_save", ref: { client_id: "a" }, fields: { place: null, body: "" }, edited_at: T(8), qid: 5 },
    { op: "note_delete", ref: { id: 3 }, at: T(9), qid: 6 },
  ];
  const frozen = structuredClone(queue);
  const out = remapRef(markAttempt(queue, 1), "a", 42);
  assert.deepEqual(queue, frozen);
  assert.deepEqual(out[0], { ...queue[0], attempts: 1 }, "add 자신의 client_id는 그대로, qid·attempts 유지");
  assert.deepEqual(out[1].ref, { id: 42 }); assert.equal(out[1].qid, queue[1].qid);
  assert.deepEqual(out[2].ref, { id: 42 });
  assert.deepEqual(out[3].ref, { client_id: "b" }, "다른 client_id는 그대로");
  assert.deepEqual(out[4].ref, { id: 42 }); assert.deepEqual(out[5].ref, { id: 3 });
}
// 사진 삭제의 note·photo는 각자의 client_id로만 바뀐다
{
  const queue = [
    { op: "photo_add", note: { client_id: "n" }, client_id: "p", blob_key: "k", at: T(6), qid: 1 },
    { op: "photo_delete", note: { client_id: "n" }, photo: { client_id: "p" }, at: T(7), qid: 2 },
  ];
  const byNote = remapRef(queue, "n", 7);
  assert.deepEqual(byNote[0], { ...queue[0], note: { id: 7 } });
  assert.deepEqual(byNote[1], { ...queue[1], note: { id: 7 } });
  const byPhoto = remapRef(byNote, "p", 40);
  assert.deepEqual(byPhoto[0], byNote[0], "photo_add 자신의 client_id는 그대로");
  assert.deepEqual(byPhoto[1], { ...queue[1], note: { id: 7 }, photo: { id: 40 } });
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
  ["edit", 404, "drop"], ["photo_add", 404, "drop"], ["note_add", 404, "drop"],
  ["note_save", 404, "conflict"], ["note_save", 409, "conflict"],
  ["add", 400, "drop"], ["edit", 400, "drop"], ["add", 413, "drop"], ["photo_add", 413, "drop"], ["photo_add", 415, "drop"], ["photo_add", 503, "drop"],
  ["edit", 503, "retry"], ["add", 500, "retry"], ["note_save", 502, "retry"], ["check", 408, "retry"],
  ["add", 200, "ok"], ["add", 201, "ok"], ["delete", 204, "ok"], ["note_save", 200, "ok"],
]) assert.equal(classify(OP[name], status), expected, `${name} ${status}`);
for (const op of Object.values(OP)) {
  assert.equal(classify({ ...op, attempts: 99 }, 0), "retry", `${op.op} 0은 끝없이`);
  assert.equal(classify({ ...op, attempts: 99 }, 429), "retry", `${op.op} 429`);
  assert.equal(classify(op, 401), "auth", `${op.op} 401`);
}
// 5xx는 MAX_ATTEMPTS번째에 실패 목록으로
assert.equal(MAX_ATTEMPTS, 5);
assert.equal(classify({ ...OP.add, serverErrors: MAX_ATTEMPTS - 2 }, 500), "retry");
assert.equal(classify({ ...OP.add, serverErrors: MAX_ATTEMPTS - 1 }, 500), "drop");
assert.equal(classify({ ...OP.note_save, serverErrors: MAX_ATTEMPTS - 1 }, 502), "drop");
// 오프라인 재시도(0·429)는 5xx 횟수에 들어가지 않는다: 여러 번 보냈어도 첫 502는 retry
assert.equal(classify({ ...OP.add, attempts: 99 }, 502), "retry");
assert.deepEqual(markServerError([{ ...OP.add, qid: 1 }], 1)[0].serverErrors, 1);
// 체크 404(항목이 이미 없음)의 오류 body는 항목으로 들어가지 않고 그 항목을 뺀다
{
  const snap = { items: [{ id: 7, client_id: null, name: "두부" }], stocked: [], notes: [], today: "2026-09-14" };
  const out = applyServerResult(snap, { op: "check", ref: { id: 7 }, done: true, at: "2026-09-14T00:00:00Z" }, { error: "찾을 수 없어요." });
  assert.deepEqual(out.items, []);
}

// ---- newClientId: 서버 형식 [A-Za-z0-9-]{1,36} ----
{
  const CLIENT_ID = /^[A-Za-z0-9-]{1,36}$/;
  const ids = Array.from({ length: 50 }, newClientId);
  for (const id of ids) assert.match(id, CLIENT_ID);
  assert.equal(new Set(ids).size, ids.length);
  const original = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  Object.defineProperty(globalThis, "crypto", { value: {}, configurable: true }); // 보안 컨텍스트가 아닌 브라우저
  try {
    const fallback = Array.from({ length: 50 }, newClientId);
    for (const id of fallback) assert.match(id, CLIENT_ID);
    assert.equal(new Set(fallback).size, fallback.length);
  } finally {
    Object.defineProperty(globalThis, "crypto", original);
  }
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

// ---- 속성 검사: 합친 대기열로 만든 화면 == 합치지 않은 변경 전부로 만든 화면 ----
// 고정 시드 LCG. client_id는 늘 새것, 참조는 서버에 있거나 앞에서 추가한 대상만, 시각은 늘어나기만 한다.
// 가끔 맨 앞 op를 "보내는 중"으로 표시해 보낸 op가 그대로 남는지도 본다.
for (let round = 0; round < 20; round++) {
  let seed = 20260914 + round;
  const rand = () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 2 ** 32;
  const pick = (list) => list[Math.floor(rand() * list.length)];
  let clock = 0, serial = 0;
  const at = () => new Date(Date.parse(T(1)) + ++clock * 1000).toISOString();
  const fresh = (prefix) => `${prefix}${++serial}`;
  const addedItems = [], addedNotes = [], photos = [{ note: { id: 5 }, photo: { id: 40 } }];
  const itemRef = () => (addedItems.length && rand() < 0.5 ? { client_id: pick(addedItems) } : { id: pick([1, 2, 3]) });
  const noteRef = () => (addedNotes.length && rand() < 0.5 ? { client_id: pick(addedNotes) } : { id: 5 });
  const makers = [
    () => { const c = fresh("c"); addedItems.push(c); return { op: "add", client_id: c, fields: { ...F, name: c }, at: at() }; },
    () => ({ op: "edit", ref: itemRef(), fields: pick([{ name: fresh("이름") }, { quantity: 2, unit: "봉" }, { planned_on: "2026-09-16", location_id: pick([null, 4]) }]), at: at() }),
    () => ({ op: "check", ref: itemRef(), done: rand() < 0.5, at: at() }),
    () => ({ op: "check", ref: itemRef(), done: rand() < 0.5, at: at() }),
    () => ({ op: "delete", ref: itemRef(), at: at() }),
    () => { const c = fresh("n"); addedNotes.push(c); return { op: "note_add", client_id: c, fields: { place: null, body: "" }, at: at() }; },
    () => ({ op: "note_save", ref: noteRef(), fields: { place: pick([null, "시장"]), body: fresh("본문") }, edited_at: at() }),
    () => ({ op: "note_delete", ref: noteRef(), at: at() }),
    () => { const note = noteRef(), c = fresh("p"); photos.push({ note, photo: { client_id: c } }); return { op: "photo_add", note, client_id: c, blob_key: `blob-${c}`, at: at() }; },
    () => ({ op: "photo_delete", ...pick(photos), at: at() }),
  ];
  const noDupes = (list, key, label) => {
    const values = list.map((x) => x[key]).filter((v) => v != null);
    assert.equal(new Set(values).size, values.length, `${label} ${key} 중복`);
  };
  let queue = [];
  const raw = [];
  const dropped = new Set();
  for (let n = 0; n < 150; n++) {
    if (queue.length && rand() < 0.15) queue = sendHead(queue);
    const sentBefore = queue.filter((o) => o.attempts);
    const next = pick(makers)();
    raw.push(next);
    const r = enqueue(queue, next);
    queue = r.queue;
    r.dropBlobs.forEach((b) => dropped.add(b));
    for (const sent of sentBefore) assert.ok(queue.includes(sent), `보낸 op가 바뀌거나 지워짐 (round ${round}, ${n})`);
    assert.equal(new Set(queue.map((o) => o.qid)).size, queue.length, "qid 중복");
    for (const o of queue) if (o.op === "photo_add") assert.ok(!dropped.has(o.blob_key), "버린 blob을 아직 보냄");
    const view = applyQueue(SNAP, queue);
    assert.deepEqual(view, applyQueue(SNAP, raw), `화면이 다름 (round ${round}, ${n}, ${next.op})`);
    noDupes(view.items, "id", "항목"); noDupes(view.items, "client_id", "항목");
    noDupes(view.notes, "id", "메모"); noDupes(view.notes, "client_id", "메모");
    for (const note of view.notes) { noDupes(note.photos, "id", "사진"); noDupes(note.photos, "client_id", "사진"); }
  }
}

console.log("shopping sync ok");
