import { useEffect, useState } from "react";

// beforeinstallprompt는 표준 lib.dom에 없는 크롬 전용 이벤트라 직접 타입을 붙인다.
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: BeforeInstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();

const notify = () => listeners.forEach((fn) => fn());

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferred = e as BeforeInstallPromptEvent;
  notify();
});

window.addEventListener("appinstalled", () => {
  deferred = null;
  installed = true;
  notify();
});

const isStandalone = () =>
  matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;

export function useInstallPrompt(): {
  canPrompt: boolean;
  installed: boolean;
  prompt(): Promise<"accepted" | "dismissed" | "unavailable">;
} {
  const [, setTick] = useState(0);

  useEffect(() => {
    const onChange = () => setTick((t) => t + 1);
    listeners.add(onChange);
    return () => {
      listeners.delete(onChange);
    };
  }, []);

  return {
    canPrompt: deferred !== null,
    installed: installed || isStandalone(),
    async prompt() {
      if (!deferred) return "unavailable";
      const e = deferred;
      deferred = null;
      notify();
      await e.prompt();
      const { outcome } = await e.userChoice;
      return outcome;
    },
  };
}
