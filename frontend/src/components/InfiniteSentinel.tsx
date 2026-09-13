import { useEffect, useRef } from "react";
import Icon from "./Icon";

interface Props {
  onVisible: () => void;
  hasMore: boolean;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
}

/**
 * 목록 끝의 무한 스크롤 손잡이. 화면에 들어오면 자동으로 더 받고(IntersectionObserver),
 * 안 되는 환경에서도 "더 보기" 버튼으로 그대로 동작한다(접근성 대체 수단).
 */
export default function InfiniteSentinel({ onVisible, hasMore, loading, error, onRetry }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!hasMore || loading || error) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) onVisible();
      },
      { rootMargin: "400px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [onVisible, hasMore, loading, error]);

  if (!hasMore)
    return (
      <p className="list-end muted" role="status" aria-live="polite">
        다 봤어요
      </p>
    );

  if (error)
    return (
      <div className="list-end">
        <p className="error" role="alert">
          {error}
        </p>
        <button className="btn secondary inline" onClick={onRetry}>
          <Icon name="refresh" size={16} />
          다시 불러오기
        </button>
      </div>
    );

  return (
    <div ref={ref} className="list-end">
      {loading ? (
        <p className="muted" role="status" aria-live="polite">
          불러오는 중…
        </p>
      ) : (
        <button className="btn secondary inline" onClick={onVisible}>
          더 보기
        </button>
      )}
    </div>
  );
}
