// 오프라인 장보기 순수 로직(스펙 19·28절, 4단계 계획 Task 6). 브라우저 API·Date.now()를 부르지 않는다 — 시각은 인자로 받는다(newClientId만 예외).
// scripts/check-shopping-sync.mjs가 그냥 node로 읽으므로 값 import는 .ts 확장자를 붙인다.
// ponytail: 대기열은 배열 통째로 다룬다(수백 개 이하). 느려지면 op별 키로 나눈다.
//
// 보내는 쪽(Task 7) 약속 — 한 번에 하나, 항상 저장된 최신 대기열에서 qid로 찾는다(자리·객체로 찾지 않는다):
//   1. op = queue[0]; queue = markAttempt(queue, op.qid)를 **저장한 뒤** 보낸다. 한 번이라도 보낸 op는 서버에 닿았을 수 있어서
//      enqueue가 합치거나 지우지 않는다(뒤에 새 변경을 붙이고 remapRef가 참조를 고친다).
//   2. result = classify(최신 op, status)
//      - ok: snapshot = applyServerResult(snapshot, op, body) — 안 하면 방금 보낸 항목이 새로 받을 때까지 화면에서 사라진다.
//            add·note_add·photo_add면 queue = remapRef(queue, op.client_id, body.id). 그다음 queue = removeOp(queue, op.qid).
//      - drop: { queue, dropBlobs } = dropWithDependents(queue, op.qid) — 실패 목록에 op를 남겨 화면에 보여준다.
//      - conflict(note_save 409·404): 기기에서 쓴 fields를 backups에 남기고, 409면 applyServerResult(snapshot, op, body.note), removeOp.
//      - retry: 5xx였으면 queue = markServerError(queue, op.qid) 저장 후 멈춘다. auth: 멈춘다.
import type { ShoppingItem, ShoppingNote, ShoppingNotePhoto, ShoppingSnapshot, ShoppingSource } from "../api";
import { addDays } from "../format.ts";
import { amountInputText, parseAmountInput } from "../seasoning.ts";

/** 서버에 아직 없는 항목·메모·사진은 client_id로 가리킨다 */
export type Ref = { id: number } | { client_id: string };
export interface ItemFields {
  name: string; quantity: number; unit: string; planned_on: string | null; location_id?: number | null;
  source?: ShoppingSource; source_label?: string | null;
}
/** 고치기(PATCH)는 source를 받지 않는다 */
export type EditFields = Partial<Omit<ItemFields, "source" | "source_label">>;
export interface NoteFields { place: string | null; body: string }

/** qid: enqueue가 붙이는 대기열 안 번호(보내는 쪽이 이것으로 찾는다). attempts: 보낸 횟수(markAttempt). serverErrors: 5xx 받은 횟수(markServerError) */
export type Op = (
  | { op: "add"; client_id: string; fields: ItemFields; at: string }
  | { op: "edit"; ref: Ref; fields: EditFields; at: string }
  | { op: "check"; ref: Ref; done: boolean; at: string }
  | { op: "delete"; ref: Ref; at: string }
  | { op: "note_add"; client_id: string; fields: NoteFields; at: string }
  | { op: "note_save"; ref: Ref; fields: NoteFields; edited_at: string }
  | { op: "note_delete"; ref: Ref; at: string }
  | { op: "photo_add"; note: Ref; client_id: string; blob_key: string; at: string }
  | { op: "photo_delete"; note: Ref; photo: Ref; at: string }
) & { qid?: number; attempts?: number; serverErrors?: number };

/** 아직 안 보낸 항목·메모·사진은 id가 없고 pending: true. 사진은 서버 것이면 url, 기기 것이면 blob_key */
export type ViewItem = Omit<ShoppingItem, "id"> & { id?: number; pending: boolean };
export interface ViewPhoto { id?: number; client_id: string | null; url?: string; blob_key?: string; pending: boolean }
export type ViewNote = Omit<ShoppingNote, "id" | "photos"> & { id?: number; photos: ViewPhoto[]; pending: boolean };
export interface ShoppingView { items: ViewItem[]; stocked: ShoppingItem[]; notes: ViewNote[]; today: string }

/** 5xx는 이만큼 보내도 안 되면 실패 목록으로(네트워크 없음은 끝없이 기다린다) */
export const MAX_ATTEMPTS = 5;

const sameRef = (a: Ref, b: Ref) => ("id" in a ? "id" in b && a.id === b.id : "client_id" in b && a.client_id === b.client_id);
const isClient = (ref: Ref, clientId: string) => "client_id" in ref && ref.client_id === clientId;
const matches = (x: { id?: number; client_id: string | null }, ref: Ref) => ("id" in ref ? x.id === ref.id : x.client_id === ref.client_id);
const unsent = (o: Op) => !o.attempts;
/** op 안의 참조(ref·note·photo) 중 하나라도 이 client_id를 가리키나 */
const refersTo = (o: Op, clientId: string) =>
  ("ref" in o && isClient(o.ref, clientId)) || ("note" in o && isClient(o.note, clientId)) || ("photo" in o && isClient(o.photo, clientId));

/** 새 변경을 대기열에 넣으며 합친다(계획 합치기 규칙 1~7). **보낸 적 있는(attempts) op는 합치거나 바꾸거나 지우지 않는다.**
 *  dropBlobs: 더 이상 보낼 필요 없는 사진 blob 키(호출 측이 기기에서 지움) */
export function enqueue(queue: Op[], next: Op): { queue: Op[]; dropBlobs: string[] } {
  const q = [...queue];
  const dropBlobs: string[] = [];
  const incoming: Op = { ...next, qid: Math.max(0, ...queue.map((o) => o.qid ?? 0)) + 1 };
  const done = (list: Op[]) => ({ queue: list, dropBlobs });
  const replaceAt = (i: number, op: Op) => { q[i] = { ...op, qid: q[i].qid }; return done(q); };
  switch (next.op) {
    case "check": { // 1. 같은 대상 check는 마지막 것만(처음 자리)
      const i = q.findIndex((o) => unsent(o) && o.op === "check" && sameRef(o.ref, next.ref));
      if (i >= 0) return replaceAt(i, incoming);
      break;
    }
    case "edit": { // 2. 안 보낸 add에 합친다(보낸 add는 서버가 client_id로 기존 항목만 돌려주고 fields를 무시하므로 따로 보낸다)
      const i = q.findIndex((o) => unsent(o) && o.op === "add" && isClient(next.ref, o.client_id));
      const add = q[i];
      if (add?.op === "add") return replaceAt(i, { ...add, fields: { ...add.fields, ...next.fields } });
      break;
    }
    case "delete": { // 3. 안 보낸 add면 흔적 없이 지운다 / 4. 아니면 앞의 안 보낸 변경을 지우고 delete를 넣는다
      const addUnsent = q.some((o) => unsent(o) && o.op === "add" && isClient(next.ref, o.client_id));
      const kept = q.filter((o) => !(unsent(o) && (
        (o.op === "add" && isClient(next.ref, o.client_id)) ||
        ((o.op === "edit" || o.op === "check" || o.op === "delete") && sameRef(o.ref, next.ref))
      )));
      return done(addUnsent ? kept : [...kept, incoming]);
    }
    case "note_save": { // 5. 안 보낸 note_add의 fields에, 아니면 앞의 안 보낸 note_save 자리에 마지막 것으로
      const i = q.findIndex((o) => unsent(o) && ((o.op === "note_add" && isClient(next.ref, o.client_id)) || (o.op === "note_save" && sameRef(o.ref, next.ref))));
      const prev = q[i];
      if (prev?.op === "note_add") return replaceAt(i, { ...prev, fields: next.fields, at: next.edited_at });
      if (prev) return replaceAt(i, incoming);
      break;
    }
    case "note_delete": { // 3·4. 메모에 딸린 안 보낸 변경을 모두 지우고, 사진 blob은 dropBlobs로
      const addUnsent = q.some((o) => unsent(o) && o.op === "note_add" && isClient(next.ref, o.client_id));
      const kept = q.filter((o) => {
        const hit = unsent(o) && (
          (o.op === "note_add" && isClient(next.ref, o.client_id)) ||
          ((o.op === "note_save" || o.op === "note_delete") && sameRef(o.ref, next.ref)) ||
          ((o.op === "photo_add" || o.op === "photo_delete") && sameRef(o.note, next.ref)));
        if (hit && o.op === "photo_add") dropBlobs.push(o.blob_key);
        return !hit;
      });
      return done(addUnsent ? kept : [...kept, incoming]);
    }
    case "photo_delete": { // 6. 안 보낸 photo_add면 둘 다 없앤다
      const kept = q.filter((o) => {
        const hit = unsent(o) && o.op === "photo_add" && isClient(next.photo, o.client_id) && sameRef(o.note, next.note);
        if (hit) dropBlobs.push(o.blob_key);
        return !hit;
      });
      if (dropBlobs.length) return done(kept);
      break;
    }
  }
  q.push(incoming); // 7. 나머지는 들어온 순서대로
  return done(q);
}

/** 보내기 직전에 부른다(저장한 뒤 보냄) */
export const markAttempt = (queue: Op[], qid: number): Op[] =>
  queue.map((o) => (o.qid === qid ? { ...o, attempts: (o.attempts ?? 0) + 1 } : o));

/** 5xx를 받았을 때 센다(classify가 retry를 돌려준 뒤 저장). 네트워크 실패·408·429는 세지 않는다 */
export const markServerError = (queue: Op[], qid: number): Op[] =>
  queue.map((o) => (o.qid === qid ? { ...o, serverErrors: (o.serverErrors ?? 0) + 1 } : o));

/** 성공·충돌로 끝난 op를 뺀다 */
export const removeOp = (queue: Op[], qid: number): Op[] => queue.filter((o) => o.qid !== qid);

/** 실패로 버리는 op와, 그 op가 만들려던 항목·메모·사진(client_id)을 가리키는 변경을 함께 뺀다 */
export function dropWithDependents(queue: Op[], qid: number): { queue: Op[]; dropBlobs: string[] } {
  const target = queue.find((o) => o.qid === qid);
  const clientId = target && (target.op === "add" || target.op === "note_add" || target.op === "photo_add") ? target.client_id : null;
  const dropBlobs: string[] = [];
  const kept = queue.filter((o) => {
    const hit = o.qid === qid || (clientId !== null && refersTo(o, clientId));
    if (hit && o.op === "photo_add") dropBlobs.push(o.blob_key);
    return !hit;
  });
  return { queue: kept, dropBlobs };
}

/** 서버 스냅숏 위에 대기 변경을 얹은 화면용 목록. 스냅숏은 바꾸지 않는다 */
export function applyQueue(snapshot: ShoppingSnapshot, queue: Op[]): ShoppingView {
  let items: ViewItem[] = snapshot.items.map((item) => ({ ...item, pending: false }));
  let notes: ViewNote[] = snapshot.notes.map((note) => ({ ...note, photos: note.photos.map((p) => ({ ...p, pending: false })), pending: false }));
  for (const op of queue) {
    switch (op.op) {
      case "add": // 보냈지만 응답을 못 받은 add는 서버 항목이 이미 있으니 다시 만들지 않는다
        if (!items.some((i) => i.client_id === op.client_id)) {
          const { name, quantity, unit, planned_on, location_id, source, source_label } = op.fields;
          items.push({
            client_id: op.client_id, name, quantity, unit, planned_on, location_id: location_id ?? null, location_name: null,
            source: source ?? "manual", source_label: source_label ?? null,
            done_at: null, done_changed_at: null, stocked_at: null, created_at: op.at, pending: true,
          });
        }
        break;
      case "edit": {
        const item = items.find((i) => matches(i, op.ref));
        if (!item) break;
        if (op.fields.location_id !== undefined && op.fields.location_id !== item.location_id) item.location_name = null;
        Object.assign(item, op.fields, { pending: true });
        break;
      }
      case "check": { // 다른 기기가 더 늦게 바꿨으면 서버가 무시하므로 화면도 서버 값(같은 시각이면 기기 것, 스펙 19절)
        const item = items.find((i) => matches(i, op.ref));
        if (!item || (item.done_changed_at && Date.parse(item.done_changed_at) > Date.parse(op.at))) break;
        Object.assign(item, { done_at: op.done ? op.at : null, done_changed_at: op.at, pending: true });
        break;
      }
      case "delete":
        items = items.filter((i) => !matches(i, op.ref));
        break;
      case "note_add":
        if (!notes.some((n) => n.client_id === op.client_id)) notes.push({ client_id: op.client_id, ...op.fields, updated_at: op.at, photos: [], pending: true });
        break;
      case "note_save": {
        const note = notes.find((n) => matches(n, op.ref));
        if (note) Object.assign(note, op.fields, { updated_at: op.edited_at, pending: true });
        break;
      }
      case "note_delete":
        notes = notes.filter((n) => !matches(n, op.ref));
        break;
      case "photo_add": {
        const note = notes.find((n) => matches(n, op.note));
        if (note && !note.photos.some((p) => p.client_id === op.client_id)) note.photos.push({ client_id: op.client_id, blob_key: op.blob_key, pending: true });
        break;
      }
      case "photo_delete": {
        const note = notes.find((n) => matches(n, op.note));
        if (note) note.photos = note.photos.filter((p) => !matches(p, op.photo));
        break;
      }
    }
  }
  // 서버처럼 최근 고친 메모가 앞(카드는 notes[0])
  notes.sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  return { items, stocked: snapshot.stocked, notes, today: snapshot.today };
}

/** 2xx 응답을 스냅숏에 반영한다(새로 받기 전까지 보낸 변경이 화면에서 사라지지 않게). 스냅숏은 바꾸지 않고 새 객체를 돌려준다.
 *  body: add·edit·check → 항목, note_add·note_save → 메모(409 충돌이면 body.note), photo_add → 사진, 지우기는 무시 */
export function applyServerResult(snapshot: ShoppingSnapshot, op: Op, body: unknown): ShoppingSnapshot {
  const upsert = <T extends { id: number; client_id: string | null }>(list: T[], value: T) => {
    const i = list.findIndex((x) => x.id === value.id || (value.client_id !== null && x.client_id === value.client_id));
    return i >= 0 ? list.map((x, j) => (j === i ? value : x)) : [...list, value];
  };
  const hasId = typeof (body as { id?: unknown } | null)?.id === "number";
  switch (op.op) {
    case "add": case "edit": case "check":
      // 체크의 404(이미 없음)는 ok로 오므로, 항목이 아닌 body면 그 항목을 스냅숏에서 뺀다(고치기의 404는 classify가 drop)
      if (!hasId) return op.op === "add" ? snapshot : { ...snapshot, items: snapshot.items.filter((i) => !matches(i, op.ref)) };
      return { ...snapshot, items: upsert(snapshot.items, body as ShoppingItem) };
    case "delete":
      return { ...snapshot, items: snapshot.items.filter((i) => !matches(i, op.ref)) };
    case "note_add": case "note_save": {
      const notes = upsert(snapshot.notes, body as ShoppingNote).sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
      return { ...snapshot, notes };
    }
    case "note_delete":
      return { ...snapshot, notes: snapshot.notes.filter((n) => !matches(n, op.ref)) };
    case "photo_add": case "photo_delete": {
      const change = (photos: ShoppingNotePhoto[]) =>
        op.op === "photo_add" ? upsert(photos, body as ShoppingNotePhoto) : photos.filter((p) => !matches(p, op.photo));
      return { ...snapshot, notes: snapshot.notes.map((n) => (matches(n, op.note) ? { ...n, photos: change(n.photos) } : n)) };
    }
  }
}

/** add·note_add·photo_add 성공 후 뒤 변경들의 client_id 참조를 서버 id로 바꾼다(성공한 op 자신은 removeOp로 뺀다) */
export function remapRef(queue: Op[], client_id: string, id: number): Op[] {
  const swap = (ref: Ref): Ref => (isClient(ref, client_id) ? { id } : ref);
  return queue.map((o): Op => {
    switch (o.op) {
      case "edit": case "check": case "delete": case "note_save": case "note_delete": return { ...o, ref: swap(o.ref) };
      case "photo_add": return { ...o, note: swap(o.note) };
      case "photo_delete": return { ...o, note: swap(o.note), photo: swap(o.photo) };
      default: return o;
    }
  });
}

/** 보낸 결과 분류(op.serverErrors는 이전까지 받은 5xx 횟수):
 *  ok(빼고 다음) · retry(멈추고 나중에: 네트워크 0·408·429는 끝없이, 5xx는 MAX_ATTEMPTS번 전까지) · auth(멈춤: 401) ·
 *  drop(dropWithDependents 후 실패 목록에: 400·413·415, 사진 저장소가 꺼진 photo_add 503, 5xx가 MAX_ATTEMPTS번) ·
 *  conflict(note_save 409 다른 기기가 먼저 고침·404 다른 기기가 지움 — 둘 다 기기 사본을 보관, 스펙 19절). 지우기·체크의 404는 이미 없으니 ok, 고치기의 404는 drop */
export function classify(op: Op, status: number): "ok" | "retry" | "auth" | "drop" | "conflict" {
  if (status >= 200 && status < 300) return "ok";
  if (status === 401) return "auth";
  if (op.op === "note_save" && (status === 409 || status === 404)) return "conflict";
  if (status === 404 && (op.op === "check" || op.op === "delete" || op.op === "note_delete" || op.op === "photo_delete")) return "ok";
  if (status === 503 && op.op === "photo_add") return "drop";
  if (status === 0 || status === 408 || status === 429) return "retry";
  if (status >= 500) return (op.serverErrors ?? 0) + 1 >= MAX_ATTEMPTS ? "drop" : "retry"; // 이번 5xx까지 세서 MAX번째면 실패
  return "drop";
}

/** op → 보낼 요청(스펙 28절 API). photo_add는 호출 측이 body에 사진(image)을 붙여 multipart로 보낸다.
 *  대상이 아직 client_id뿐이면(서버 id를 모름 — 추가가 실패로 빠진 경우 등) null: 실패 목록으로 */
export function opRequest(op: Op): { method: "POST" | "PATCH" | "PUT" | "DELETE"; path: string; body?: Record<string, unknown> } | null {
  const idOf = (ref: Ref) => ("id" in ref ? ref.id : null);
  const items = "/api/shopping/items";
  const notes = "/api/shopping/notes";
  switch (op.op) {
    case "add": return { method: "POST", path: items, body: { ...op.fields, client_id: op.client_id } };
    // edited_at: 오프라인에서 만든 시각 — 그 뒤 기기에서 고친 PUT이 409가 나지 않게(서버 기본값은 받은 시각)
    case "note_add": return { method: "POST", path: notes, body: { ...op.fields, client_id: op.client_id, edited_at: op.at } };
  }
  const target = idOf("ref" in op ? op.ref : op.note);
  if (target === null) return null;
  switch (op.op) {
    case "edit": return { method: "PATCH", path: `${items}/${target}`, body: op.fields };
    case "check": return { method: "PATCH", path: `${items}/${target}`, body: { done: op.done, changed_at: op.at } };
    case "delete": return { method: "DELETE", path: `${items}/${target}` };
    case "note_save": return { method: "PUT", path: `${notes}/${target}`, body: { ...op.fields, edited_at: op.edited_at } };
    case "note_delete": return { method: "DELETE", path: `${notes}/${target}` };
    case "photo_add": return { method: "POST", path: `${notes}/${target}/photos`, body: { client_id: op.client_id } };
    case "photo_delete": {
      const photo = idOf(op.photo);
      return photo === null ? null : { method: "DELETE", path: `${notes}/${target}/photos/${photo}` };
    }
  }
}

/** 기기 장보기 데이터의 주인 비교(로그인 방법 + id). 둘 중 하나라도 없으면 다른 사람으로 본다 */
export const sameOwner = (a: { provider: string; id: number } | null | undefined, b: { provider: string; id: number } | null | undefined) =>
  !!a && !!b && a.provider === b.provider && a.id === b.id;

/** 앱 열기·다시 보일 때 GET /api/shopping을 할지: 대기열이 있거나 장보기 화면이 열려 있으면 늘, 아니면 마지막으로 받은 뒤 60초가 지났을 때만 */
export const REFRESH_EVERY_MS = 60_000;
export const shouldRefresh = (lastFetchedAt: number | null, now: number, pending: number, shoppingOpen: boolean) =>
  pending > 0 || shoppingOpen || lastFetchedAt === null || now - lastFetchedAt >= REFRESH_EVERY_MS;

/** 다시 보내기 대기 시간(ms): 2초부터 두 배씩, 5분까지. step은 연달아 실패한 횟수(0부터) */
export const retryDelay = (step: number) => Math.min(2000 * 2 ** Math.max(0, step), 5 * 60_000);

/** 서버 client_id 형식([A-Za-z0-9-] 1~36자). randomUUID는 보안 컨텍스트(https·localhost)에만 있어 없으면 같은 모양으로 만든다 */
export function newClientId(): string {
  const c = globalThis.crypto;
  if (typeof c?.randomUUID === "function") return c.randomUUID();
  // ponytail: Math.random 대체 — client_id는 사용자 안에서만 겹치지 않으면 되고 보안 용도가 아니다.
  const hex = (n: number) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  return `${hex(8)}-${hex(4)}-4${hex(3)}-${hex(4)}-${hex(12)}`;
}

const GROUPS = [["today", "오늘"], ["week", "이번 주"], ["later", "나중에"], ["undated", "날짜 미정"]] as const;
type GroupKey = (typeof GROUPS)[number][0];

/** 시안 ShoppingList 날짜 묶음(서울 날짜 문자열로만 계산). 지난 날짜는 오늘, 오늘+6까지 이번 주.
 *  묶음 안은 planned_on·created_at 오름차순, 체크(done_at)는 자리에 영향 없음. 빈 묶음은 뺀다 */
export function groupItems<T extends { planned_on: string | null; created_at: string }>(
  items: T[], today: string,
): { key: GroupKey; title: string; items: T[] }[] {
  const weekEnd = addDays(today, 6);
  const keyOf = (d: string | null): GroupKey => (d === null ? "undated" : d <= today ? "today" : d <= weekEnd ? "week" : "later");
  const byDate = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
  const sorted = [...items].sort((a, b) => byDate(a.planned_on ?? "", b.planned_on ?? "") || Date.parse(a.created_at) - Date.parse(b.created_at));
  return GROUPS.map(([key, title]) => ({ key, title, items: sorted.filter((i) => keyOf(i.planned_on) === key) })).filter((g) => g.items.length);
}

/** 시안 AddSheet `언제 살까요?` 칩 → planned_on. 이번 주는 오늘+6(이 날까지 사면 된다) */
export function plannedOnFor(choice: "today" | "week" | "undated", today: string): string | null {
  return choice === "today" ? today : choice === "week" ? addDays(today, 6) : null;
}

/** 시안 AddSheet 수량 칸 한 줄: "1모"·"30구"·"1L"·"½봉"·"1/2대"·"2"(→개)·"모"(→1)·""(→1개). 0 이하·틀린 숫자·단위 11자 이상은 null */
export function parseQuantityText(text: string): { quantity: number; unit: string } | null {
  const [, number, unit] = text.trim().match(/^([\d.\s/¼⅓½⅔¾]*)(.*)$/s)!;
  if (/[\d¼⅓½⅔¾/+-]/.test(unit) || [...unit].length > 10) return null;
  const quantity = number.trim() ? parseAmountInput(number) : 1;
  return quantity === null ? null : { quantity, unit: unit || "개" };
}

/** 1,"모" → "1모", 0.5,"봉" → "½봉", 12.5,"g" → "12.5g" (parseQuantityText로 되돌리면 같은 값) */
export const quantityText = (quantity: number, unit: string) => amountInputText(quantity) + unit;

/** 시안 ShoppingList 태그(.sh-tag + tone 클래스). 직접 담은 항목은 태그 없음 */
export function sourceTag(item: { source: string; source_label: string | null }): { text: string; tone: "" | "info" | "warn" } | null {
  switch (item.source) {
    case "recipe": return { text: item.source_label ? `레시피 · ${item.source_label}` : "레시피", tone: "info" };
    case "urgent": return { text: "곧 떨어져요", tone: "warn" };
    case "staple": return { text: "필수품", tone: "" };
    case "memo": return { text: "메모 사진", tone: "" };
    default: return null; // ponytail: meal_plan 태그 문구는 4b 식단 시안에서 정한다
  }
}
