// 오프라인 장보기 순수 로직(스펙 19절, 4단계 계획 Task 6). 브라우저 API·Date.now()를 부르지 않는다 — 시각·id는 인자로 받는다.
// scripts/check-shopping-sync.mjs가 그냥 node로 읽으므로 값 import는 .ts 확장자를 붙인다.
// ponytail: 대기열은 배열 통째로 다룬다(수백 개 이하). 느려지면 op별 키로 나눈다.
import type { ShoppingItem, ShoppingNote, ShoppingSnapshot, ShoppingSource } from "../api";
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

export type Op =
  | { op: "add"; client_id: string; fields: ItemFields; at: string }
  | { op: "edit"; ref: Ref; fields: EditFields; at: string }
  | { op: "check"; ref: Ref; done: boolean; at: string }
  | { op: "delete"; ref: Ref; at: string }
  | { op: "note_add"; client_id: string; fields: NoteFields; at: string }
  | { op: "note_save"; ref: Ref; fields: NoteFields; edited_at: string }
  | { op: "note_delete"; ref: Ref; at: string }
  | { op: "photo_add"; note: Ref; client_id: string; blob_key: string; at: string }
  | { op: "photo_delete"; note: Ref; photo: Ref; at: string };

/** 아직 안 보낸 항목·메모·사진은 id가 없고 pending: true. 사진은 서버 것이면 url, 기기 것이면 blob_key */
export type ViewItem = Omit<ShoppingItem, "id"> & { id?: number; pending: boolean };
export interface ViewPhoto { id?: number; client_id: string | null; url?: string; blob_key?: string; pending: boolean }
export type ViewNote = Omit<ShoppingNote, "id" | "photos"> & { id?: number; photos: ViewPhoto[]; pending: boolean };
export interface ShoppingView { items: ViewItem[]; stocked: ShoppingItem[]; notes: ViewNote[]; today: string }

const sameRef = (a: Ref, b: Ref) => ("id" in a ? "id" in b && a.id === b.id : "client_id" in b && a.client_id === b.client_id);
const isClient = (ref: Ref, clientId: string) => "client_id" in ref && ref.client_id === clientId;
const matches = (x: { id?: number; client_id: string | null }, ref: Ref) => ("id" in ref ? x.id === ref.id : x.client_id === ref.client_id);

/** 새 변경을 대기열에 넣으며 합친다(계획 합치기 규칙 1~7). dropBlobs: 더 이상 보낼 필요 없는 사진 blob 키(호출 측이 기기에서 지움) */
export function enqueue(queue: Op[], next: Op): { queue: Op[]; dropBlobs: string[] } {
  const q = [...queue];
  const dropBlobs: string[] = [];
  const replaceAt = (i: number, op: Op) => { q[i] = op; return { queue: q, dropBlobs }; };
  switch (next.op) {
    case "check": { // 1. 같은 대상 check는 마지막 것만(처음 자리)
      const i = q.findIndex((o) => o.op === "check" && sameRef(o.ref, next.ref));
      if (i >= 0) return replaceAt(i, next);
      break;
    }
    case "edit": { // 2. 안 보낸 add에 합친다
      const i = q.findIndex((o) => o.op === "add" && isClient(next.ref, o.client_id));
      const add = q[i];
      if (add?.op === "add") return replaceAt(i, { ...add, fields: { ...add.fields, ...next.fields } });
      break;
    }
    case "delete": { // 3. 안 보낸 add면 흔적 없이 지운다 / 4. 서버 항목이면 앞의 변경을 지우고 delete를 넣는다
      const unsent = q.some((o) => o.op === "add" && isClient(next.ref, o.client_id));
      const kept = q.filter((o) => !(
        (o.op === "add" && isClient(next.ref, o.client_id)) ||
        ((o.op === "edit" || o.op === "check" || o.op === "delete") && sameRef(o.ref, next.ref))
      ));
      return { queue: unsent ? kept : [...kept, next], dropBlobs };
    }
    case "note_save": { // 5. 안 보낸 note_add의 fields에, 아니면 앞의 note_save 자리에 마지막 것으로
      const i = q.findIndex((o) => (o.op === "note_add" && isClient(next.ref, o.client_id)) || (o.op === "note_save" && sameRef(o.ref, next.ref)));
      const prev = q[i];
      if (prev?.op === "note_add") return replaceAt(i, { ...prev, fields: next.fields });
      if (prev) return replaceAt(i, next);
      break;
    }
    case "note_delete": { // 3·4. 메모에 딸린 변경을 모두 지우고, 사진 blob은 dropBlobs로
      const unsent = q.some((o) => o.op === "note_add" && isClient(next.ref, o.client_id));
      const kept = q.filter((o) => {
        const hit = (o.op === "note_add" && isClient(next.ref, o.client_id)) ||
          ((o.op === "note_save" || o.op === "note_delete") && sameRef(o.ref, next.ref)) ||
          ((o.op === "photo_add" || o.op === "photo_delete") && sameRef(o.note, next.ref));
        if (hit && o.op === "photo_add") dropBlobs.push(o.blob_key);
        return !hit;
      });
      return { queue: unsent ? kept : [...kept, next], dropBlobs };
    }
    case "photo_delete": { // 6. 안 보낸 photo_add면 둘 다 없앤다
      const kept = q.filter((o) => {
        const hit = o.op === "photo_add" && isClient(next.photo, o.client_id);
        if (hit) dropBlobs.push(o.blob_key);
        return !hit;
      });
      if (dropBlobs.length) return { queue: kept, dropBlobs };
      break;
    }
  }
  q.push(next); // 7. 나머지는 들어온 순서대로
  return { queue: q, dropBlobs };
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
      case "check": { // 다른 기기가 더 늦게 바꿨으면 서버가 무시하므로 화면도 서버 값(스펙 19절)
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

/** add·note_add·photo_add 성공 후 뒤 변경들의 client_id 참조를 서버 id로 바꾼다(성공한 op 자신은 호출 측이 뺀다) */
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

/** 보낸 결과 분류: ok(빼고 다음) · retry(멈추고 나중에: 네트워크 0·5xx·408·429) · auth(멈춤: 401) ·
 *  drop(빼고 실패 목록에: 400·413·415, 사진 저장소가 꺼진 photo_add 503) · conflict(note_save 409). 지우기·체크의 404는 이미 없으니 ok */
export function classify(op: Op, status: number): "ok" | "retry" | "auth" | "drop" | "conflict" {
  if (status >= 200 && status < 300) return "ok";
  if (status === 401) return "auth";
  if (status === 409 && op.op === "note_save") return "conflict";
  if (status === 404 && (op.op === "check" || op.op === "delete" || op.op === "note_delete" || op.op === "photo_delete")) return "ok";
  if (status === 503 && op.op === "photo_add") return "drop";
  if (status === 0 || status === 408 || status === 429 || status >= 500) return "retry";
  return "drop";
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
