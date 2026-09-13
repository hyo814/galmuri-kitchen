import { useCallback, useEffect, useRef, useState } from "react";
import { cache } from "./useResource";

export interface Page<T> {
  items: T[];
  next: string | null;
}

interface ListState<T> {
  items: T[];
  cursor: string | null;
  hasMore: boolean;
}

function emptyState<T>(): ListState<T> {
  return { items: [], cursor: null, hasMore: true };
}

// ponytail: useResource와 같은 모듈 Map에 목록 상태(항목·커서)를 둔다. 상세를 오가도 목록·스크롤이 그대로다.
// deps가 바뀌면(필터·검색) 캐시가 없을 때만 처음부터 다시 받는다.
export function useInfiniteList<T>(fetchPage: (cursor: string | null) => Promise<Page<T>>, deps: unknown[]) {
  const key = "list:" + JSON.stringify(deps);
  const [state, setState] = useState<ListState<T>>(() => (cache.get(key) as ListState<T>) ?? emptyState<T>());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const loadingRef = useRef(false);
  const fetchPageRef = useRef(fetchPage);
  fetchPageRef.current = fetchPage;

  const loadPage = useCallback(
    (cursor: string | null, replace: boolean) => {
      if (loadingRef.current) return;
      loadingRef.current = true;
      setLoading(true);
      setError("");
      fetchPageRef
        .current(cursor)
        .then(
          (page) => {
            setState((prev) => {
              const items = replace ? page.items : [...prev.items, ...page.items];
              const next: ListState<T> = { items, cursor: page.next, hasMore: page.next !== null };
              cache.set(key, next);
              return next;
            });
          },
          (e: Error) => setError(e.message),
        )
        .finally(() => {
          loadingRef.current = false;
          setLoading(false);
        });
    },
    [key],
  );

  // key(deps)가 바뀌면: 캐시에 있으면 그대로 보여 주고, 없으면 처음부터 받는다.
  useEffect(() => {
    const cached = cache.get(key) as ListState<T> | undefined;
    if (cached) setState(cached);
    else {
      setState(emptyState<T>());
      loadPage(null, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const loadMore = useCallback(() => {
    if (state.hasMore) loadPage(state.cursor, false);
  }, [loadPage, state.hasMore, state.cursor]);

  const reload = useCallback(() => {
    cache.delete(key);
    setState(emptyState<T>());
    loadPage(null, true);
  }, [key, loadPage]);

  return { items: state.items, loading, error, hasMore: state.hasMore, loadMore, reload };
}
