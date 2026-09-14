// 장보기 기기 보관·보내기(스펙 19·28절, 4단계 계획 Task 7). install.ts처럼 모듈 상태 + 구독.
// 보내기는 sync.ts 맨 위 약속 그대로: 한 번에 하나, 보낸 횟수를 저장한 뒤 보내고, 항상 최신 대기열에서 qid로 찾는다.
// 탭이 여러 개면 Web Locks로 줄을 세운다 — QUEUE_LOCK: 기기 저장소를 다시 읽고 고치고 저장하는 짧은 구간(act·보낸 결과 반영),
// SEND_LOCK: 보내기·새로 받기 전체(한 탭만 서버에 보낸다). 순서는 늘 SEND → QUEUE라 서로 막히지 않는다.
import { useEffect, useState } from "react";
import { ApiError, api, localToday, type ShoppingItem, type ShoppingSnapshot, type ShoppingSource, type User } from "../api";
import * as idb from "./idb";
import {
  applyQueue, applyServerResult, classify, dropWithDependents, enqueue, markAttempt, markServerError, newClientId, opRequest,
  remapRef, removeOp, retryDelay, sameOwner, shouldRefresh, type NoteFields, type Op, type Ref, type ShoppingView,
} from "./sync";

export interface FailedOp { op: Op; error: string }
export interface NoteBackup { note_ref: Ref; fields: NoteFields; saved_at: string }
/** 기기 장보기 데이터의 주인 */
type Owner = { provider: string; id: number };

const FALLBACK_ERROR = "문제가 생겼어요. 잠시 후 다시 시도해주세요.";
const QUEUE_LOCK = "galmuri-shopping";
const SEND_LOCK = "galmuri-shopping-send";

let snapshot: ShoppingSnapshot | null = null;
let queue: Op[] = [];
let failed: FailedOp[] = [];
let backups: NoteBackup[] = [];
/** 마지막으로 GET /api/shopping을 받은 시각(ms) */
let fetchedAt: number | null = null;
let view: ShoppingView | null = null;
/** 마지막 요청이 네트워크에 닿지 못했다 */
let networkDown = false;
let loading: Promise<void> | null = null;
/** 로그인한 사용자가 있을 때만 보낸다(startShopping) */
let started = false;
let flushing = false;
/** 401을 받으면 같은 사람이 다시 로그인할 때까지 보내지 않는다(대기열은 남긴다) */
let authStopped = false;
/** clearShoppingDevice마다 늘려, 진행 중이던 보내기·받기 결과를 버린다 */
let generation = 0;
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

async function readState() {
  const gen = generation;
  const reads = await Promise.all([
    idb.read<ShoppingSnapshot>("kv", "snapshot"), idb.read<Op[]>("kv", "queue"), idb.read<FailedOp[]>("kv", "failed"),
    idb.read<NoteBackup[]>("kv", "backups"), idb.read<number>("kv", "fetched_at"),
  ]);
  if (gen !== generation) return;
  // 읽기에 실패하면 메모리의 마지막 값을 그대로 둔다 — 빈 값으로 바꾸면 다음 저장이 기기의 대기열을 지운다
  if (reads.some((r) => !r.ok)) return;
  const [s, q, f, b, t] = reads;
  snapshot = s.value ?? null;
  queue = q.value ?? [];
  failed = f.value ?? [];
  backups = b.value ?? [];
  fetchedAt = t.value ?? null;
}

/** 저장은 늘 QUEUE_LOCK 안에서(다른 탭이 고친 대기열을 옛 메모리 값으로 덮지 않게) */
const persist = () =>
  Promise.all([
    idb.set("kv", "snapshot", snapshot), idb.set("kv", "queue", queue), idb.set("kv", "failed", failed),
    idb.set("kv", "backups", backups), idb.set("kv", "fetched_at", fetchedAt),
  ]);

const dropBlobs = (keys: string[]) => keys.forEach((key) => void idb.del("blobs", key));

function load(): Promise<void> {
  loading ??= readState().then(changed);
  return loading;
}

const locks: LockManager | undefined = navigator.locks;

/** 기기 저장소를 다시 읽은 뒤 fn으로 고친다.
 *  ponytail: Web Locks가 없는 브라우저는 잠그지 않고 메모리 값을 쓴다 — 탭 하나면 문제없고, 탭 여러 개면 대기열을 서로 덮을 수 있다 */
function withQueue<T>(fn: () => Promise<T>): Promise<T> {
  return locks ? locks.request(QUEUE_LOCK, async () => (await readState(), fn())) : fn();
}

const withSend = <T,>(fn: () => Promise<T>): Promise<T> => (locks ? locks.request(SEND_LOCK, fn) : fn());

function scheduleRetry() {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(() => void flush(), retryDelay(retryStep++));
}

type Sent = { status: number; body: unknown; error: string };

/** 요청 하나를 보내고 상태 코드·본문을 돌려준다(네트워크 없음은 0). 서버 id를 모르거나 사진이 기기에 없으면 400으로 본다 */
async function send(op: Op): Promise<Sent> {
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

/** 보낸 결과를 대기열·스냅숏에 반영한다(QUEUE_LOCK 안). 멈춰야 하면(retry·auth) true */
async function applyResult(qid: number, { status, body, error }: Sent): Promise<boolean> {
  const gen = generation;
  const op = queue.find((o) => o.qid === qid);
  networkDown = status === 0;
  if (!op) return false;
  const result = classify(op, status);
  if (result === "retry" || result === "auth") {
    if (status >= 500) queue = markServerError(queue, qid);
    if (result === "auth") authStopped = true;
    else scheduleRetry();
    await persist();
    return true;
  }
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
        if (gen !== generation) return true;
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
  await persist();
  return false;
}

/** 대기열을 앞에서부터 보낸다. 탭 안에서도 탭 사이에서도 한 번에 하나만 돌고, 다 보내면 새로 받는다 */
async function flush(): Promise<void> {
  // 기기가 오프라인이라고 확실히 알 때는 보내지 않는다(보낸 횟수가 붙으면 뒤 변경과 합칠 수 없다). online 이벤트가 다시 부른다
  if (!started || flushing || authStopped || !navigator.onLine) return;
  flushing = true;
  clearTimeout(retryTimer);
  const gen = generation;
  let sentAny = false;
  let drained = false;
  try {
    await load();
    await withSend(async () => {
      for (;;) {
        const op = await withQueue(async () => {
          if (gen !== generation || !started || authStopped || !queue.length) return null;
          const qid = queue[0].qid!;
          queue = markAttempt(queue, qid);
          await persist(); // 보낸 뒤에 앱이 꺼져도 "보냈을 수 있음"이 남게
          return queue[0];
        });
        if (gen !== generation) return;
        changed();
        if (!op) {
          drained = !queue.length;
          return;
        }
        const res = await send(op);
        if (gen !== generation) return;
        const stop = await withQueue(() => applyResult(op.qid!, res));
        if (gen !== generation) return;
        changed();
        if (stop) return;
        sentAny = true;
      }
    });
  } finally {
    if (gen === generation) flushing = false;
  }
  if (drained && gen === generation) await fetchSnapshot(sentAny);
}

/** GET /api/shopping → 스냅숏 저장. 대기열이 있으면 먼저 보낸다. force가 아니면 60초에 한 번(장보기 화면이 열려 있으면 늘) */
async function fetchSnapshot(force: boolean): Promise<void> {
  if (!started || authStopped) return;
  await load();
  if (queue.length) return flush();
  if (!force && !shouldRefresh(fetchedAt, Date.now(), queue.length, listeners.size > 0)) return;
  const gen = generation;
  // SEND_LOCK: 받는 동안 다른 탭이 보내지 않으니 받은 스냅숏 위에 대기 변경을 얹으면 맞다
  await withSend(async () => {
    try {
      const next = await api<ShoppingSnapshot>("/api/shopping");
      if (gen !== generation) return;
      networkDown = false;
      await withQueue(async () => {
        if (gen !== generation) return;
        snapshot = next;
        fetchedAt = Date.now();
        await persist();
        // 서버에서 지워진 사진의 기기 파일은 버린다
        const keep = new Set([
          ...next.notes.flatMap((n) => n.photos.map((p) => `photo:${p.id}`)),
          ...queue.flatMap((o) => (o.op === "photo_add" ? [o.blob_key] : [])),
        ]);
        dropBlobs((await idb.keys("blobs")).filter((key) => key.startsWith("photo:") && !keep.has(key)));
      });
    } catch (e) {
      if (gen === generation && e instanceof ApiError && e.status === 0) networkDown = true;
    }
  });
  if (gen === generation) changed();
}

export const refresh = () => fetchSnapshot(true);

/** 변경 하나: (다시 읽고) 합쳐 넣기 → 저장 → 화면 갱신 → 보내기 */
function act(op: Op) {
  const gen = generation;
  void load()
    .then(() =>
      withQueue(async () => {
        if (gen !== generation) return;
        const current = applyQueue(base(), queue);
        const notePhotos = op.op === "note_delete" ? current.notes.find((n) => ("id" in op.ref ? n.id === op.ref.id : n.client_id === op.ref.client_id))?.photos ?? [] : [];
        const next = enqueue(queue, op); // qid도 여기서(잠근 채 최신 대기열 기준으로) 붙는다
        queue = next.queue;
        dropBlobs(next.dropBlobs);
        // 서버 사진·메모를 지우면 받아 둔 사진 파일도 지운다
        if (op.op === "photo_delete" && "id" in op.photo) dropBlobs([`photo:${op.photo.id}`]);
        dropBlobs(notePhotos.flatMap((p) => (p.id === undefined ? [] : [`photo:${p.id}`])));
        await persist();
      }),
    )
    .then(() => {
      changed();
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

const dismissFailed = () =>
  void withQueue(async () => {
    failed = [];
    await persist();
  }).then(changed);

const dismissBackup = (index: number) =>
  void withQueue(async () => {
    backups = backups.filter((_, i) => i !== index);
    await persist();
  }).then(changed);

// 연결되면·앱으로 돌아오면 보낸다(대기열이 비었으면 60초에 한 번 새로 받는다)
window.addEventListener("online", () => {
  retryStep = 0;
  void flush();
});
window.addEventListener("offline", changed);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void flush();
});

/** 로그인한 사용자가 정해진 뒤(App·장보기 화면) 부른다: 기기에 남은 변경을 보내고 새로 받는다 */
export function startShopping() {
  started = true;
  authStopped = false;
  void load(); // 오프라인이면 flush가 바로 멈추므로 기기에 보관한 목록은 따로 읽는다
  void flush();
}

/** 401(세션 만료): 보내기를 멈추고 오프라인으로 열 사용자만 잊는다. 대기열·목록·사진은 주인(owner)과 함께 남겨
 *  같은 사람이 다시 로그인하면 이어서 보낸다 */
export function pauseShopping() {
  started = false;
  authStopped = true;
  clearTimeout(retryTimer);
  void idb.del("kv", "me");
}

/** 로그인한 사용자를 기기에 기억한다. 기기 장보기 데이터의 주인이 다른 사람(로그인 방법·id)이면 먼저 모두 지운다 */
export async function rememberUser(me: User): Promise<void> {
  const owner = await idb.get<Owner>("kv", "owner");
  if (!sameOwner(owner, me)) {
    await clearShoppingDevice();
    await idb.set("kv", "owner", { provider: me.provider, id: me.id } satisfies Owner);
  }
  await idb.set("kv", "me", me);
}

/** 인터넷 없이 앱을 열 때 쓸 마지막 사용자(401·로그아웃 뒤에는 없다) */
export const savedUser = () => idb.get<User>("kv", "me");

/** 로그아웃 확인용: 아직 서버에 못 보낸 변경 수 */
export const pendingShoppingChanges = async () => (await idb.get<Op[]>("kv", "queue"))?.length ?? 0;

/** 로그아웃·다른 사용자: 같은 폰을 다른 사람이 써도 목록이 남지 않게 기기 데이터를 모두 지운다 */
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
  fetchedAt = null;
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
