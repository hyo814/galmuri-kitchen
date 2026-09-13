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
