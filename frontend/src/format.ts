import type { LocationKind } from "./api";

/** 1 → "1", 0.25 → "0.25", 1.5 → "1.5" (소수 둘째 자리까지) */
export const formatQuantity = (q: number) => String(Number(q.toFixed(2)));

/** "2026-09-10" → "9월 10일" (올해가 아니면 "2025년 9월 10일") */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const md = `${m}월 ${d}일`;
  return y === new Date().getFullYear() ? md : `${y}년 ${md}`;
}

export const KIND_LABEL: Record<LocationKind, string> = { fridge: "냉장", freezer: "냉동", room: "실온" };

/** 6 → "6개월", 12 → "1년", 24 → "2년" */
export const cycleLabel = (months: number) => (months % 12 === 0 ? `${months / 12}년` : `${months}개월`);

/** 받침에 맞는 조사를 붙인다. withJosa("애호박", "을", "를") → "애호박을". 한글이 아니면 "을(를)" */
export function withJosa(word: string, withBatchim: string, withoutBatchim: string): string {
  const code = word.trim().charCodeAt(word.trim().length - 1) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return `${word}${withBatchim}(${withoutBatchim})`;
  return word + (code % 28 ? withBatchim : withoutBatchim);
}

/** "2026-09-13" + 3 → "2026-09-16" (기기 로컬 날짜 기준) */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString("sv-SE");
}
