// 무한 스크롤 목록의 순수 상태 전이. 의존성이 없어(React·fetch 없음) Node에서 바로 검증할 수 있다.

export interface Page<T> {
  items: T[];
  next: string | null;
}

export interface ListState<T> {
  items: T[];
  cursor: string | null;
  hasMore: boolean;
}

export function emptyState<T>(): ListState<T> {
  return { items: [], cursor: null, hasMore: true };
}

/**
 * 받아 온 페이지를 목록 상태에 반영한다. gen이 지금 세대(currentGen)와 다르면(요청을 보낸 뒤
 * deps가 바뀌었거나 reload가 끼어든 경우) 응답을 버리고 이전 상태를 그대로 돌려준다 — 오래된
 * 요청이 늦게 와도 최신 목록에 끼어들 수 없다.
 */
export function applyPage<T>(
  state: ListState<T>,
  gen: number,
  currentGen: number,
  page: Page<T>,
  replace: boolean,
): ListState<T> {
  if (gen !== currentGen) return state;
  const items = replace ? page.items : [...state.items, ...page.items];
  return { items, cursor: page.next, hasMore: page.next !== null };
}
