import { useRef, type KeyboardEvent } from "react";

/** 별점 라디오 1~5(4b-3 FoodLogSheet 만족도 마크업·키보드 그대로, 개정 1 P10). 같은 점수를 다시 누르면 null.
 *  점수가 있으면 아래 `{label} 빼기`(`별점 빼기`·`만족도 빼기`) — 키보드·스크린리더는 같은 별 다시 누르기로 지울 수 없어서(R10-F2) */
export default function StarPicker({ value, label, onChange }: { value: number | null; label: string; onChange: (n: number | null) => void }) {
  const group = useRef<HTMLDivElement>(null);
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
    <div className="ck-starpick">
      <div ref={group} className="fl-bigstars" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={`${n}점`}
            tabIndex={n === (value ?? 1) ? 0 : -1}
            className={value !== null && n <= value ? "on" : undefined}
            // 같은 별 다시 누르기로 지우는 것은 손가락·마우스만(detail > 0) — 화살표로 고른 뒤 Space·Enter·스크린리더 두 번 탭은 그 점수 그대로
            onClick={(e) => onChange(value === n && e.detail > 0 ? null : n)}
            onKeyDown={starKey}
          >
            ★
          </button>
        ))}
      </div>
      {value !== null && (
        <button
          type="button"
          className="nt-link"
          onClick={() => {
            onChange(null);
            group.current?.querySelector<HTMLElement>('[role="radio"]')?.focus(); // 누른 버튼이 사라지므로 별 묶음으로
          }}
        >
          {label} 빼기
        </button>
      )}
    </div>
  );
}
