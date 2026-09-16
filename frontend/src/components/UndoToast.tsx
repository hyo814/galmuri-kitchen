import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

export interface UndoToastInput {
  message: string;
  /** 둘째 줄 굵은 초록 글자(시안 `약 10,800원 아꼈어요`) */
  strong?: string;
  /** 둘째 줄이 `더 들었어요`면 초록을 빼고 알림 글자색으로 */
  over?: boolean;
  /** 되돌리기. 끝나면 보여줄 글자를 돌려준다(실패는 throw → 오류 글자) */
  onUndo: () => Promise<string>;
  /** 이 시각(Date.now() 기준 ms)이 지나면 어느 단계에서도 되돌리기 버튼을 두지 않는다(서버가 되돌리기를 받는 시간) */
  undoUntil?: number;
}

export const UNDO_TOAST_MS = 10_000;
const DONE_MS = 3_000;
const ERROR_MS = 5_000;

type Toast = UndoToastInput & { id: number; phase: "ready" | "undoing" | "done" | "error"; text: string; expired: boolean };

// 앱 전체에 알림 하나(되돌리기는 마지막 저장만) — 새 알림이 오면 앞 알림을 바꾼다
let toast: Toast | null = null;
let seq = 0;
let session = 0;
let undone = 0;
let expiryTimer: number | undefined;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((listener) => listener());

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 그사이 다른 알림으로 바뀌었으면(새 저장·로그아웃) 옛 알림의 결과는 버린다 */
function patchToast(id: number, fields: Partial<Toast>) {
  if (toast?.id !== id) return;
  toast = { ...toast, ...fields };
  emit();
}

export function showUndoToast(input: UndoToastInput): void {
  clearTimeout(expiryTimer);
  const id = ++seq;
  toast = { ...input, id, phase: "ready", text: "", expired: false };
  emit();
  if (input.undoUntil !== undefined) expiryTimer = window.setTimeout(() => patchToast(id, { expired: true }), Math.max(input.undoUntil - Date.now(), 0));
}

export function hideUndoToast(): void {
  clearTimeout(expiryTimer);
  toast = null;
  emit();
}

/** 로그아웃: 알림을 치우고 세션 번호를 올린다 — 로그아웃 전에 시작한 느린 저장이 끝나도 다음 계정 화면에 알림을 띄우지 않게 */
export function resetUndoToast(): void {
  session += 1;
  hideUndoToast();
}

/** 저장을 시작할 때 기억했다가 끝났을 때 다르면(그사이 로그아웃) 결과를 버린다 */
export const undoToastSession = () => session;

/** 되돌리기에 성공한 횟수. App이 화면 key에 넣어 지금 화면(재고·먹은 기록·레시피 상세…)을 되돌린 값으로 새로 받는다 */
export function useUndoneCount(): number {
  return useSyncExternalStore(subscribe, () => undone);
}

/** 되돌리기 버튼이 포커스를 가진 채 사라지면: 알림에 들어오기 전 요소 → (화면을 새로 받아 없어졌으면) 요리했어요 버튼 → 화면 제목.
 * 새 화면이 아직 불러오는 중이면 생길 때까지 잠깐 기다리고, 그사이 사용자가 포커스를 옮기면 그대로 둔다 */
function returnFocus(before: HTMLElement | null) {
  const move = () => {
    if (document.activeElement && document.activeElement !== document.body) return true;
    const target =
      (before?.isConnected ? before : null) ??
      document.querySelector<HTMLElement>("main.page [data-cook-button]") ??
      document.querySelector<HTMLElement>("main.page h1");
    if (!target) return false;
    if (target.tagName === "H1") target.tabIndex = -1;
    target.focus({ preventScroll: true });
    return true;
  };
  if (move()) return;
  const observer = new MutationObserver(() => {
    if (move()) observer.disconnect();
  });
  observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(() => observer.disconnect(), 3000);
}

/** 저장 뒤 아래 알림 + 되돌리기. 10초 뒤 사라지고, 손가락·마우스·포커스가 알림 위에 있으면 멈췄다가 떠나면 남은 시간부터(결정 7, WCAG 2.2.1).
 * 읽힘 영역(role=status)은 알림이 없을 때도 비워 두고 내용만 바꾼다 — 내용과 함께 새로 끼우면 TalkBack·VoiceOver가 자주 안 읽는다 */
export default function UndoToast() {
  const current = useSyncExternalStore(subscribe, () => toast);
  const timer = useRef({ left: 0, since: 0, handle: undefined as number | undefined, hover: false, focus: false });
  const box = useRef<HTMLDivElement>(null);
  const before = useRef<HTMLElement | null>(null); // 알림에 포커스가 들어오기 전 요소
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

  // 알림 실제 높이(줄바꿈 포함)를 CSS로 — 모든 화면의 아래 버튼을 그만큼 올리고 페이지 끝 여백을 더한다(styles.css 5 · Task 8)
  useEffect(() => {
    const el = box.current!;
    const root = document.documentElement;
    const observer = new ResizeObserver(() => root.style.setProperty("--ck-toast-h", `${el.offsetHeight}px`));
    observer.observe(el);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--ck-toast-h");
    };
  }, []);

  // 새 알림: 앞 알림이 손가락·마우스 아래에서 사라졌으면 pointerleave가 오지 않으니 잊는다
  useEffect(() => {
    timer.current.hover = false;
  }, [id]);

  useEffect(() => {
    if (id === undefined || phase === "undoing") return;
    const t = timer.current;
    t.left = phase === "done" ? DONE_MS : phase === "error" ? ERROR_MS : UNDO_TOAST_MS;
    t.focus = !!box.current?.contains(document.activeElement);
    resume();
    return () => {
      clearTimeout(t.handle);
      t.handle = undefined;
    };
  }, [id, phase]);

  // 버튼이 포커스를 가진 채 빠지면(성공·되돌리기 시간 지남) 멈춤을 풀고 포커스를 돌려준다.
  // 되돌리는 중에는 disabled 대신 aria-disabled라 포커스가 버튼에 남는다(실패하면 같은 버튼이 다시 되돌리기)
  const undoButton = useCallback((button: HTMLButtonElement | null) => {
    if (!button) return;
    return () => {
      if (document.activeElement !== button) return;
      timer.current.focus = false;
      requestAnimationFrame(() => {
        resume();
        returnFocus(before.current);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function undo() {
    if (!toast || (toast.phase !== "ready" && toast.phase !== "error") || toast.expired) return;
    const { id: target, onUndo } = toast;
    patchToast(target, { phase: "undoing" });
    try {
      const text = await onUndo();
      undone += 1; // 알림이 그사이 바뀌었어도 되돌린 것은 사실이라 화면은 새로 받는다
      if (toast?.id === target) toast = { ...toast, phase: "done", text };
      emit();
    } catch (e) {
      patchToast(target, { phase: "error", text: (e as Error).message });
    }
  }

  const showButton = !!current && (current.phase === "undoing" || ((current.phase === "ready" || current.phase === "error") && !current.expired));
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
      onFocus={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) before.current = e.relatedTarget instanceof HTMLElement ? e.relatedTarget : null;
        timer.current.focus = true;
        pause();
      }}
      onBlur={(e) => {
        if (e.currentTarget.contains(e.relatedTarget)) return;
        timer.current.focus = false;
        resume();
      }}
    >
      {current && (
        <>
          {current.phase === "error" ? (
            <p>{current.text}</p>
          ) : current.phase === "done" ? (
            <span>{current.text}</span>
          ) : (
            <span>
              {current.message}
              {current.strong && (
                <>
                  <br />
                  <b className={current.over ? undefined : "ck-toast-strong"}>{current.strong}</b>
                </>
              )}
            </span>
          )}
          {showButton && (
            <button
              ref={undoButton}
              type="button"
              className="ck-toast-undo"
              aria-label={current.phase === "undoing" ? undefined : "방금 한 요리 되돌리기"}
              aria-disabled={current.phase === "undoing" || undefined}
              onClick={undo}
            >
              {current.phase === "undoing" ? "되돌리는 중…" : "되돌리기"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
