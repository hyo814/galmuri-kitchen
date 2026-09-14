// 장보기 기기 보관·보내기(스펙 19·28절, 4단계 계획 Task 7). install.ts처럼 모듈 상태 + 구독.
// 보내기는 sync.ts 맨 위 약속 그대로: 한 번에 하나, 보낸 횟수를 저장한 뒤 보내고, 항상 최신 대기열에서 qid로 찾는다.
import { useEffect, useState } from "react";
import { ApiError, api, localToday, type ShoppingItem, type ShoppingSnapshot, type ShoppingSource, type User } from "../api";
import * as idb from "./idb";
import {
  applyQueue, applyServerResult, classify, dropWithDependents, enqueue, markAttempt, markServerError, newClientId, opRequest,
  remapRef, removeOp, retryDelay, type NoteFields, type Op, type Ref, type ShoppingView,
} from "./sync";

export interface FailedOp { op: Op; error: string }
export interface NoteBackup { note_ref: Ref; fields: NoteFields; saved_at: string }

const FALLBACK_ERROR = "문제가 생겼어요. 잠시 후 다시 시도해주세요.";

let snapshot: ShoppingSnapshot | null = null;
let queue: Op[] = [];
let failed: FailedOp[] = [];
let backups: NoteBackup[] = [];
let view: ShoppingView | null = null;
/** 마지막 요청이 네트워크에 닿지 못했다 */
let networkDown = false;
let loading: Promise<void> | null = null;
/** 로그인한 사용자가 있을 때만 보낸다(startShopping) */
let started = false;
let flushing = false;
/** 401을 받으면 다시 로그인할 때까지 보내지 않는다 */
let authStopped = false;
/** clearShoppingDevice마다 늘려, 진행 중이던 보내기·받기 결과를 버린다 */
let generation = 0;
/** 서버에 반영된 변경 수. 받는 사이에 늘었으면 받은 스냅숏은 옛것이라 버린다 */
let serverWrites = 0;
let retryStep = 0;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

const isOffline = () => networkDown || !navigator.onLine;
const base = (): ShoppingSnapshot => snapshot ?? { items: [], stocked: [], notes: [], today: localToday() };

function changed() {
  // 한 번도 못 받았어도 오프라인이거나 기기에서 담은 게 있으면 빈 목록 위에 보여준다
  view = snapshot || queue.length || isOffline() ? applyQueue(base(), queue) : null;
  listeners.forEach((fn) => fn());
}

const persist = () =>
  Promise.all([idb.set("kv", "snapshot", snapshot), idb.set("kv", "queue", queue), idb.set("kv", "failed", failed), idb.set("kv", "backups", backups)]);

const dropBlobs = (keys: string[]) => keys.forEach((key) => void idb.del("blobs", key));

function load(): Promise<void> {
  loading ??= (async () => {
    const gen = generation;
    const [s, q, f, b] = await Promise.all([
      idb.get<ShoppingSnapshot>("kv", "snapshot"), idb.get<Op[]>("kv", "queue"), idb.get<FailedOp[]>("kv", "failed"), idb.get<NoteBackup[]>("kv", "backups"),
    ]);
    if (gen !== generation) return;
    snapshot = s ?? null;
    queue = q ?? [];
    failed = f ?? [];
    backups = b ?? [];
    changed();
  })();
  return loading;
}

function scheduleRetry() {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(() => void flush(), retryDelay(retryStep++));
}

/** 요청 하나를 보내고 상태 코드·본문을 돌려준다(네트워크 없음은 0). 서버 id를 모르거나 사진이 기기에 없으면 400으로 본다 */
async function send(op: Op): Promise<{ status: number; body: unknown; error: string }> {
  const req = opRequest(op);
  if (!req) return { status: 400, body: null, error: FALLBACK_ERROR };
  let body: Record<string, unknown> | FormData | undefined = req.body;
  if (op.op === "photo_add") {
    const blob = await idb.get<Blob>("blobs", op.blob_key);
    if (!blob) return { status: 400, body: null, error: FALLBACK_ERROR };
    const form = new FormData();
    form.append("image", blob, "photo");
    form.append("client_id", op.client_id);
    body = form;
  }
  try {
    return { status: 200, body: await api<unknown>(req.path, { method: req.method, body }), error: "" };
  } catch (e) {
    return e instanceof ApiError ? { status: e.status, body: e.body ?? null, error: e.message } : { status: 0, body: null, error: FALLBACK_ERROR };
  }
}

/** 대기열을 앞에서부터 보낸다. 한 번에 하나만 돌고, 다 보내면 새로 받는다 */
async function flush(): Promise<void> {
  // 기기가 오프라인이라고 확실히 알 때는 보내지 않는다(보낸 횟수가 붙으면 뒤 변경과 합칠 수 없다). online 이벤트가 다시 부른다
  if (!started || flushing || authStopped || !navigator.onLine) return;
  flushing = true;
  clearTimeout(retryTimer);
  const gen = generation;
  try {
    await load();
    while (gen === generation && queue.length) {
      const qid = queue[0].qid!;
      queue = markAttempt(queue, qid);
      await persist(); // 보낸 뒤에 앱이 꺼져도 "보냈을 수 있음"이 남게
      const sent = queue.find((o) => o.qid === qid);
      if (gen !== generation || !sent) return;
      const { status, body, error } = await send(sent);
      if (gen !== generation) return;
      const op = queue.find((o) => o.qid === qid) ?? sent;
      networkDown = status === 0;
      const result = classify(op, status);

      if (result === "retry" || result === "auth") {
        if (status >= 500) queue = markServerError(queue, qid);
        if (result === "auth") authStopped = true;
        else scheduleRetry();
        changed();
        await persist();
        return;
      }
      serverWrites++;
      if (result === "ok") {
        snapshot = applyServerResult(base(), op, body);
        const id = (body as { id?: unknown } | null)?.id;
        if ((op.op === "add" || op.op === "note_add" || op.op === "photo_add") && typeof id === "number") {
          queue = remapRef(queue, op.client_id, id);
          if (op.op === "photo_add") {
            // 올린 사진도 기기에 남겨 오프라인에서 보이게(서버 id 키로 옮김)
            const blob = await idb.get<Blob>("blobs", op.blob_key);
            if (blob) await idb.set("blobs", `photo:${id}`, blob);
            await idb.del("blobs", op.blob_key);
            if (gen !== generation) return;
          }
        }
        queue = removeOp(queue, qid);
      } else if (result === "drop") {
        const dropped = dropWithDependents(queue, qid);
        queue = dropped.queue;
        dropBlobs(dropped.dropBlobs);
        failed = [...failed, { op, error }];
      } else if (op.op === "note_save") {
        // conflict: 다른 기기가 먼저 고쳤거나(409) 지웠다(404). 이 기기에서 쓴 내용을 보관하고 서버 쪽을 받아들인다(스펙 19절)
        backups = [...backups, { note_ref: op.ref, fields: op.fields, saved_at: new Date().toISOString() }];
        const note = (body as { note?: unknown } | null)?.note;
        snapshot = status === 409 && note
          ? applyServerResult(base(), op, note)
          : applyServerResult(base(), { op: "note_delete", ref: op.ref, at: op.edited_at }, null);
        queue = removeOp(queue, qid);
      }
      retryStep = 0;
      changed();
      await persist();
    }
  } finally {
    if (gen === generation) flushing = false;
  }
  if (gen === generation && started && !authStopped && !queue.length) await refresh();
}

/** GET /api/shopping → 스냅숏 저장. 대기열이 남아 있으면 먼저 보낸다(보낸 뒤 flush가 다시 부른다) */
export async function refresh(): Promise<void> {
  if (!started || authStopped) return;
  await load();
  if (queue.length) return flush();
  const gen = generation;
  const writes = serverWrites;
  try {
    const next = await api<ShoppingSnapshot>("/api/shopping");
    if (gen !== generation) return;
    networkDown = false;
    if (writes === serverWrites) {
      snapshot = next;
      await persist();
    }
    changed();
  } catch (e) {
    if (gen !== generation) return;
    if (e instanceof ApiError && e.status === 0) {
      networkDown = true;
      changed();
    }
  }
}

/** 변경 하나: 합쳐 넣기 → 저장 → 화면 갱신 → 보내기 */
function act(op: Op) {
  void load().then(async () => {
    const notePhotos = op.op === "note_delete" ? view?.notes.find((n) => ("id" in op.ref ? n.id === op.ref.id : n.client_id === op.ref.client_id))?.photos ?? [] : [];
    const next = enqueue(queue, op);
    queue = next.queue;
    dropBlobs(next.dropBlobs);
    // 서버 사진·메모를 지우면 받아 둔 사진 파일도 지운다
    if (op.op === "photo_delete" && "id" in op.photo) dropBlobs([`photo:${op.photo.id}`]);
    dropBlobs(notePhotos.flatMap((p) => (p.id === undefined ? [] : [`photo:${p.id}`])));
    changed();
    await persist();
    void flush();
  });
}

function addPhoto(note: Ref, blob: Blob) {
  const client_id = newClientId();
  const blob_key = `local:${client_id}`;
  void idb.set("blobs", blob_key, blob).then(() => act({ op: "photo_add", note, client_id, blob_key, at: new Date().toISOString() }));
}

/** 기기에 있는 사진 → 없으면 서버에서 받아 기기에 남긴다 */
async function photoBlob(photo: { id?: number; url?: string; blob_key?: string }): Promise<Blob | null> {
  if (photo.blob_key) {
    const local = await idb.get<Blob>("blobs", photo.blob_key);
    if (local) return local;
  }
  if (photo.id === undefined) return null;
  const key = `photo:${photo.id}`;
  const saved = await idb.get<Blob>("blobs", key);
  if (saved || !photo.url) return saved ?? null;
  try {
    const res = await fetch(photo.url, { credentials: "same-origin" });
    if (!res.ok) return null;
    const blob = await res.blob();
    await idb.set("blobs", key, blob);
    return blob;
  } catch {
    return null;
  }
}

function dismissFailed() {
  failed = [];
  changed();
  void persist();
}

function dismissBackup(index: number) {
  backups = backups.filter((_, i) => i !== index);
  changed();
  void persist();
}

// 연결되면·앱으로 돌아오면 보낸다(대기열이 비었으면 새로 받는다)
window.addEventListener("online", () => {
  retryStep = 0;
  void flush();
});
window.addEventListener("offline", changed);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void flush();
});

/** 로그인한 사용자가 정해진 뒤(App) 부른다: 기기에 남은 변경을 보내고 새로 받는다 */
export function startShopping() {
  started = true;
  authStopped = false;
  void load(); // 오프라인이면 flush가 바로 멈추므로 기기에 보관한 목록은 따로 읽는다
  void flush();
}

/** /api/me로 확인한 사용자를 기기에 기억한다. 다른 사용자였으면 기기 장보기 데이터를 먼저 지운다 */
export async function rememberUser(me: User): Promise<void> {
  const saved = await idb.get<User>("kv", "me");
  if (saved && saved.id !== me.id) await clearShoppingDevice();
  await idb.set("kv", "me", me);
}

/** 인터넷 없이 앱을 열 때 쓸 마지막 사용자 */
export const savedUser = () => idb.get<User>("kv", "me");

/** 로그아웃·401: 같은 폰을 다른 사람이 써도 목록이 남지 않게 기기 데이터를 모두 지운다 */
export function clearShoppingDevice(): Promise<void> {
  generation++;
  started = false;
  flushing = false;
  authStopped = false;
  clearTimeout(retryTimer);
  retryStep = 0;
  snapshot = null;
  queue = [];
  failed = [];
  backups = [];
  networkDown = false;
  const cleared = idb.clearAll();
  loading = cleared; // 지우는 중에 다시 읽지 않게(상태는 이미 비었다)
  changed();
  return cleared;
}

/** 다른 화면에서 한 번에 담기(Task 11·13). 온라인 전용 */
export async function addMany(
  source: ShoppingSource,
  items: { name: string; quantity?: number; unit?: string; planned_on?: string | null; location_id?: number }[],
  sourceLabel?: string,
): Promise<{ created: number; skipped: string[] }> {
  const res = await api<{ created: ShoppingItem[]; skipped: string[] }>("/api/shopping/items/bulk", {
    method: "POST",
    body: { source, source_label: sourceLabel, items },
  });
  serverWrites++;
  await refresh();
  return { created: res.created.length, skipped: res.skipped };
}

export function useShopping() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const onChange = () => setTick((t) => t + 1);
    listeners.add(onChange);
    startShopping();
    return () => {
      listeners.delete(onChange);
    };
  }, []);

  return {
    view,
    offline: isOffline(),
    pending: queue.length,
    failed,
    backups,
    act,
    addPhoto,
    photoBlob,
    refresh,
    dismissFailed,
    dismissBackup,
  };
}
