import type { KeyboardEvent } from "react";

/** 별점 라디오 1~5(4b-3 FoodLogSheet 만족도 마크업·키보드 그대로, 개정 1 P10). 같은 점수를 다시 누르면 null */
export default function StarPicker({ value, label, onChange }: { value: number | null; label: string; onChange: (n: number | null) => void }) {
  // 화살표로 점수를 옮기고 켠다(roving tabindex)
  function starKey(e: KeyboardEvent<HTMLButtonElement>) {
    const delta = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = Math.min(5, Math.max(1, (value ?? 0) + delta));
    onChange(next);
    (e.currentTarget.parentElement!.children[next - 1] as HTMLElement).focus();
  }

  return (
    <div className="fl-bigstars" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n}점`}
          tabIndex={n === (value ?? 1) ? 0 : -1}
          className={value !== null && n <= value ? "on" : undefined}
          onClick={() => onChange(value === n ? null : n)}
          onKeyDown={starKey}
        >
          ★
        </button>
      ))}
    </div>
  );
}
