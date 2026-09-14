// 기기 저장소(스펙 19절, 4단계 계획 Task 7). IndexedDB `galmuri` v1 — kv(owner·me·snapshot·queue·failed·backups·fetched_at), blobs(사진).
// ponytail: IndexedDB를 못 열거나 쓰기가 실패한 값만 메모리 Map에 둔다(사생활 모드·저장 공간) — 그 값은 앱을 닫으면 사라진다.
export type Store = "kv" | "blobs";

/** IndexedDB에 못 쓴 값만. 쓰기가 다시 성공하면 뺀다(사진이 메모리에 끝없이 쌓이지 않게) */
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
      req.onsuccess = () => {
        const db = req.result;
        // 다른 탭이 새 버전으로 열려고 하면 비켜 주고, 다음 요청 때 다시 연다
        db.onversionchange = () => {
          db.close();
          opening = null;
        };
        resolve(db);
      };
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null); // 옛 버전 연결이 안 닫힘 → 이번에는 메모리로
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
  if (memory[store].has(key)) return memory[store].get(key) as T;
  return run<T | undefined>(store, "readonly", (s) => s.get(key)).catch(() => undefined);
}

export async function set(store: Store, key: string, value: unknown): Promise<void> {
  try {
    await run(store, "readwrite", (s) => s.put(value, key));
    memory[store].delete(key);
  } catch {
    memory[store].set(key, value);
  }
}

export async function del(store: Store, key: string): Promise<void> {
  memory[store].delete(key);
  await run(store, "readwrite", (s) => s.delete(key)).catch(() => {});
}

export async function keys(store: Store): Promise<string[]> {
  const saved = await run<IDBValidKey[]>(store, "readonly", (s) => s.getAllKeys()).catch((): IDBValidKey[] => []);
  return [...new Set([...saved.map(String), ...memory[store].keys()])];
}

/** 로그아웃·다른 사용자: 기기에 남은 장보기 데이터를 모두 지운다 */
export async function clearAll(): Promise<void> {
  for (const store of ["kv", "blobs"] as const) {
    memory[store].clear();
    await run(store, "readwrite", (s) => s.clear()).catch(() => {});
  }
}
