import { useEffect, useRef, useSyncExternalStore } from "react";

export interface UndoToastInput {
  message: string;
  /** 둘째 줄 굵은 초록 글자(시안 `약 10,800원 아꼈어요`) */
  strong?: string;
  /** 되돌리기. 끝나면 보여줄 글자를 돌려준다(실패는 throw → 오류 글자) */
  onUndo: () => Promise<string>;
}

export const UNDO_TOAST_MS = 10_000;
const DONE_MS = 3_000;
const ERROR_MS = 5_000;

type Toast = UndoToastInput & { id: number; phase: "ready" | "undoing" | "done" | "error"; text: string };

// 앱 전체에 알림 하나(되돌리기는 마지막 저장만) — 새 알림이 오면 앞 알림을 바꾼다
let toast: Toast | null = null;
let seq = 0;
const listeners = new Set<() => void>();

function setToast(next: Toast | null) {
  toast = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 그사이 다른 알림으로 바뀌었으면(새 저장·로그아웃) 옛 알림의 결과는 버린다 */
function patchToast(id: number, fields: Partial<Toast>) {
  if (toast?.id === id) setToast({ ...toast, ...fields });
}

export function showUndoToast(input: UndoToastInput): void {
  setToast({ ...input, id: ++seq, phase: "ready", text: "" });
}

export function hideUndoToast(): void {
  setToast(null);
}

/** 알림이 떠 있는지(레시피 상세 cta-bar를 올릴 때) */
export function useUndoToastVisible(): boolean {
  return useSyncExternalStore(subscribe, () => toast !== null);
}

/** 저장 뒤 아래 알림 + 되돌리기. 10초 뒤 사라지고, 손가락·마우스·포커스가 알림 위에 있으면 멈췄다가 떠나면 남은 시간부터(결정 7, WCAG 2.2.1) */
export default function UndoToast() {
  const current = useSyncExternalStore(subscribe, () => toast);
  const timer = useRef({ left: 0, since: 0, handle: undefined as number | undefined, hover: false, focus: false });
  const box = useRef<HTMLDivElement>(null);
  const id = current?.id;
  const phase = current?.phase;

  function pause() {
    const t = timer.current;
    if (t.handle === undefined) return;
    clearTimeout(t.handle);
    t.handle = undefined;
    t.left -= Date.now() - t.since;
  }

  function resume() {
    const t = timer.current;
    if (t.handle !== undefined || t.hover || t.focus || !toast || toast.phase === "undoing") return;
    const target = toast.id;
    t.since = Date.now();
    t.handle = window.setTimeout(() => {
      t.handle = undefined;
      if (toast?.id === target) hideUndoToast();
    }, Math.max(t.left, 0));
  }

  // 새 알림: 앞 알림이 손가락·마우스 아래에서 사라졌으면 pointerleave가 오지 않으니 잊는다
  useEffect(() => {
    timer.current.hover = false;
  }, [id]);

  useEffect(() => {
    if (id === undefined || phase === "undoing") return;
    const t = timer.current;
    t.left = phase === "done" ? DONE_MS : phase === "error" ? ERROR_MS : UNDO_TOAST_MS;
    // 되돌리기 버튼이 사라지면 포커스도 함께 사라진다(blur가 안 올 수 있어 지금 값으로 본다)
    t.focus = !!box.current?.contains(document.activeElement);
    resume();
    return () => {
      clearTimeout(t.handle);
      t.handle = undefined;
    };
  }, [id, phase]);

  if (!current) return null;

  async function undo() {
    if (!toast || toast.phase !== "ready") return;
    const { id: target, onUndo } = toast;
    patchToast(target, { phase: "undoing" });
    try {
      patchToast(target, { phase: "done", text: await onUndo() });
    } catch (e) {
      patchToast(target, { phase: "error", text: (e as Error).message });
    }
  }

  const ready = current.phase === "ready";
  return (
    <div
      ref={box}
      className="ck-toast"
      role="status"
      aria-live="polite"
      onPointerEnter={() => {
        timer.current.hover = true;
        pause();
      }}
      onPointerLeave={() => {
        timer.current.hover = false;
        resume();
      }}
      onFocus={() => {
        timer.current.focus = true;
        pause();
      }}
      onBlur={(e) => {
        if (e.currentTarget.contains(e.relatedTarget)) return;
        timer.current.focus = false;
        resume();
      }}
    >
      {current.phase === "error" ? (
        <p>{current.text}</p>
      ) : current.phase === "done" ? (
        <span>{current.text}</span>
      ) : (
        <>
          <span>
            {current.message}
            {current.strong && (
              <>
                <br />
                <b className="ck-toast-strong">{current.strong}</b>
              </>
            )}
          </span>
          <button
            type="button"
            className="ck-toast-undo"
            aria-label={ready ? "방금 한 요리 되돌리기" : undefined}
            disabled={!ready}
            onClick={undo}
          >
            {ready ? "되돌리기" : "되돌리는 중…"}
          </button>
        </>
      )}
    </div>
  );
}
