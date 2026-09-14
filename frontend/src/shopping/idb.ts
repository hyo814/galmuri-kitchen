// 기기 저장소(스펙 19절, 4단계 계획 Task 7). IndexedDB `galmuri` v1 — kv(me·snapshot·queue·failed·backups), blobs(사진).
// ponytail: IndexedDB를 못 열거나 쓰기가 실패하면(사생활 모드·저장 공간) 메모리 Map으로 대신한다 — 그때는 앱을 닫으면 사라진다.
export type Store = "kv" | "blobs";

const memory: Record<Store, Map<string, unknown>> = { kv: new Map(), blobs: new Map() };
let opening: Promise<IDBDatabase | null> | null = null;

function open(): Promise<IDBDatabase | null> {
  opening ??= new Promise((resolve) => {
    try {
      const req = indexedDB.open("galmuri", 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore("kv");
        req.result.createObjectStore("blobs");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return opening;
}

/** 한 요청짜리 트랜잭션. 쓰기는 트랜잭션이 끝나야(oncomplete) 성공으로 본다 */
async function run<T>(store: Store, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await open();
  if (!db) throw new Error("no indexeddb");
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const req = fn(tx.objectStore(store));
    tx.oncomplete = () => resolve(req.result as T);
    tx.onerror = tx.onabort = () => reject(tx.error);
  });
}

export async function get<T>(store: Store, key: string): Promise<T | undefined> {
  try {
    const value = await run<T | undefined>(store, "readonly", (s) => s.get(key));
    if (value !== undefined) return value;
  } catch {
    // 메모리에서 찾는다
  }
  return memory[store].get(key) as T | undefined;
}

export async function set(store: Store, key: string, value: unknown): Promise<void> {
  memory[store].set(key, value);
  await run(store, "readwrite", (s) => s.put(value, key)).catch(() => {});
}

export async function del(store: Store, key: string): Promise<void> {
  memory[store].delete(key);
  await run(store, "readwrite", (s) => s.delete(key)).catch(() => {});
}

/** 로그아웃·다른 사용자: 기기에 남은 장보기 데이터를 모두 지운다 */
export async function clearAll(): Promise<void> {
  for (const store of ["kv", "blobs"] as const) {
    memory[store].clear();
    await run(store, "readwrite", (s) => s.clear()).catch(() => {});
  }
}
