import { useCallback, useRef, useState } from "react";

/** 저장·삭제 같은 비동기 동작의 진행 중 상태와 오류 메시지를 한곳에서 관리한다. */
export function useAsyncAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // busy는 다음 렌더에야 버튼을 막으므로, 빠른 연타로 같은 요청이 두 번 가지 않게 즉시 막는다
  const inFlight = useRef(false);

  const run = useCallback(async (action: () => Promise<unknown>) => {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }, []);

  return { busy, error, setError, run };
}
