import { useCallback, useEffect, useRef, useState } from "react";
import { applyPage, emptyState, type ListState, type Page } from "./listPage";
import { cache } from "./useResource";

export type { ListState, Page };

// ponytail: useResource와 같은 모듈 Map에 목록 상태(항목·커서)를 둔다. 상세를 오가도 목록·스크롤이 그대로다.
// deps가 바뀌면(필터·검색) 캐시가 없을 때만 처음부터 다시 받는다.
export function useInfiniteList<T extends { id: number | string }>(
  fetchPage: (cursor: string | null) => Promise<Page<T>>,
  deps: unknown[],
) {
  const key = "list:" + JSON.stringify(deps);
  const [state, setState] = useState<ListState<T>>(() => (cache.get(key) as ListState<T>) ?? emptyState<T>());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const loadingRef = useRef(false);
  // deps가 바뀌거나 reload될 때마다 하나씩 늘어난다. 응답이 오면 이 값과 비교해 오래된 요청인지 안다.
  const genRef = useRef(0);
  const fetchPageRef = useRef(fetchPage);
  fetchPageRef.current = fetchPage;

  const loadPage = useCallback(
    (cursor: string | null, replace: boolean, gen: number) => {
      loadingRef.current = true;
      setLoading(true);
      setError("");
      fetchPageRef
        .current(cursor)
        .then(
          (page) => {
            if (gen !== genRef.current) return; // 응답이 오는 사이 deps가 바뀌거나 reload됐다
            setState((prev) => {
              const next = applyPage(prev, gen, genRef.current, page, replace);
              cache.set(key, next);
              return next;
            });
          },
          (e: Error) => {
            if (gen === genRef.current) setError(e.message);
          },
        )
        .finally(() => {
          if (gen === genRef.current) {
            loadingRef.current = false;
            setLoading(false);
          }
        });
    },
    [key],
  );

  // key(deps)가 바뀌면: 새 세대를 시작하고, 캐시에 있으면 그대로 보여 주고 없으면 처음부터 받는다.
  useEffect(() => {
    genRef.current += 1;
    const gen = genRef.current;
    loadingRef.current = false;
    const cached = cache.get(key) as ListState<T> | undefined;
    if (cached) {
      // 이전 키의 요청이 아직 진행 중이었어도(응답은 gen이 달라 무시된다) 불러오는 중·오류 표시가 남지 않게
      setState(cached);
      setLoading(false);
      setError("");
    } else {
      setState(emptyState<T>());
      loadPage(null, true, gen);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const loadMore = useCallback(() => {
    if (loadingRef.current || !state.hasMore) return;
    loadPage(state.cursor, false, genRef.current);
  }, [loadPage, state.hasMore, state.cursor]);

  // 요청이 진행 중이어도 새 세대로 다시 받는다(이전 응답은 gen이 달라 무시된다).
  const reload = useCallback(() => {
    genRef.current += 1;
    const gen = genRef.current;
    cache.delete(key);
    setState(emptyState<T>());
    loadPage(null, true, gen);
  }, [key, loadPage]);

  return { items: state.items, loading, error, hasMore: state.hasMore, multiPage: state.multiPage, loadMore, reload };
}
