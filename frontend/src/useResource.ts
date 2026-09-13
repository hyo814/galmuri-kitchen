import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

// ponytail: 탭·상세를 오갈 때 마지막으로 받은 응답을 모듈 Map에 둔다(새로고침하면 비워짐). 먼저 보여 주고 뒤에서 다시 받는다.
// 캐시 무효화가 복잡해지면(여러 화면이 같은 데이터를 고침) TanStack Query 같은 라이브러리로 교체.
// export: useInfiniteList도 같은 Map을 써서 목록 상태(항목·커서)를 상세 화면을 오간 뒤에도 유지한다.
export const cache = new Map<string, unknown>();

/** prefix로 시작하는 URL의 캐시를 지운다. 저장·삭제 뒤 목록이 옛 내용을 잠깐 보여 주지 않게. "" = 전부(로그아웃) */
export function forgetResources(prefix = "") {
  for (const key of [...cache.keys()]) if (key.startsWith(prefix)) cache.delete(key);
}

/** GET url을 불러온다. 다시 불러오는 동안에도 마지막 data를 유지한다. 오류는 error 문자열로(401은 api()가 처리). */
export function useResource<T>(url: string) {
  const [data, setData] = useState<T | undefined>(() => cache.get(url) as T | undefined);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const next = await api<T>(url);
      cache.set(url, next);
      setData(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [url]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, reload };
}
