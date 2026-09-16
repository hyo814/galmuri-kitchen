// 식단 날짜 계산(스펙 20절). 브라우저 API·Date.now()를 부르지 않고 오늘은 인자로 받는다 — scripts/check-meals.mjs가 node로 읽는다.
import type { MealKind, MealPlanSummary, MealShoppingRow } from "../api";
import { addDays } from "../format.ts";
import { amountInputText } from "../seasoning.ts";

export const MEALS: [MealKind, string][] = [["breakfast", "아침"], ["lunch", "점심"], ["dinner", "저녁"], ["snack", "간식"]];
export const mealLabel = (meal: MealKind) => MEALS.find(([k]) => k === meal)![1];
export const PERIODS: [string, number | null][] = [["1주", 7], ["2주", 14], ["1달", 30], ["직접", null]];
const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const ORDINALS = ["첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째"];
const parts = (iso: string) => iso.split("-").map(Number) as [number, number, number];
const weekday = (iso: string) => new Date(`${iso}T00:00:00`).getDay(); // 0=일
export const daysBetween = (a: string, b: string) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);

/** "2026-09-14" → "9월 셋째 주"(월요일 시작 주, 1일이 든 주가 첫째). 28일 이상이면 "9월 식단" */
export function defaultPlanName(start: string, days: number): string {
  const [, month, day] = parts(start);
  if (days >= 28) return `${month}월 식단`;
  const firstOffset = (weekday(`${start.slice(0, 8)}01`) + 6) % 7; // 월=0
  return `${month}월 ${ORDINALS[Math.floor((day - 1 + firstOffset) / 7)]} 주`;
}
export const planEnd = (start: string, days: number) => addDays(start, days - 1);
/** 기간을 바꾸면 밖으로 나가는 채운 칸 수(결정 1) */
export const slotsOutside = (slots: { date: string }[], start: string, days: number) =>
  slots.filter((s) => s.date < start || s.date > planEnd(start, days)).length;
/** 날짜 → 그 날짜가 든 주 페이지 시작일(식단 밖이면 null) */
export function weekOf(plan: Pick<MealPlanSummary, "start_on" | "days">, iso: string): string | null {
  if (iso < plan.start_on || iso > planEnd(plan.start_on, plan.days)) return null;
  return addDays(plan.start_on, Math.floor(daysBetween(plan.start_on, iso) / 7) * 7);
}
/** 주 보기 페이지: 시작일부터 7일씩 */
export const weekStarts = (plan: Pick<MealPlanSummary, "start_on" | "days">) =>
  Array.from({ length: Math.ceil(plan.days / 7) }, (_, i) => addDays(plan.start_on, i * 7));
/** 한 주 페이지의 날짜(식단 끝을 넘지 않게) */
export const weekDates = (weekStart: string, plan: Pick<MealPlanSummary, "start_on" | "days">) =>
  Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)).filter((d) => d <= planEnd(plan.start_on, plan.days));
/** 오늘이 든 주, 없으면 첫 주(오늘이 끝 뒤면 마지막 주) */
export function initialWeek(plan: Pick<MealPlanSummary, "start_on" | "days">, today: string): string {
  const weeks = weekStarts(plan);
  if (today < plan.start_on) return weeks[0];
  // tsconfig lib가 ES2022라 findLast 대신 filter
  return weeks.filter((w) => w <= today).at(-1) ?? weeks[0];
}
/** "9월 14일–20일", 달이 바뀌면 "9월 28일–10월 4일" */
export function rangeText(start: string, end: string): string {
  const [, m1, d1] = parts(start);
  const [, m2, d2] = parts(end);
  return m1 === m2 ? `${m1}월 ${d1}일–${d2}일` : `${m1}월 ${d1}일–${m2}월 ${d2}일`;
}
/** "9월 14일 (월)" */
export const dateWithDow = (iso: string) => `${parts(iso)[1]}월 ${parts(iso)[2]}일 (${DOW[weekday(iso)]})`;
/** 하루 카드 머리 {day: "14일", dow: "월요일"} */
export const dayHead = (iso: string) => ({ day: `${parts(iso)[2]}일`, dow: `${DOW[weekday(iso)]}요일` });
/** 시트 설명 "9월 14일 월요일 · 오늘" / "9월 14일 월요일 · 저녁" */
export function slotDateText(iso: string, today: string, meal?: MealKind): string {
  const base = `${parts(iso)[1]}월 ${parts(iso)[2]}일 ${DOW[weekday(iso)]}요일`;
  return meal ? `${base} · ${mealLabel(meal)}` : iso === today ? `${base} · 오늘` : base;
}
/** 월 보기 격자(월요일 시작, 그 달 1일이 든 주부터 말일이 든 주까지). 칸은 ISO 날짜 */
export function monthGrid(year: number, month: number): string[][] {
  const first = `${year}-${String(month).padStart(2, "0")}-01`;
  const start = addDays(first, -((weekday(first) + 6) % 7));
  const last = addDays(`${month === 12 ? year + 1 : year}-${String((month % 12) + 1).padStart(2, "0")}-01`, -1);
  const rows: string[][] = [];
  for (let w = start; w <= last; w = addDays(w, 7)) rows.push(Array.from({ length: 7 }, (_, i) => addDays(w, i)));
  return rows;
}
/** 복사할 수 있는 최대 주(1~4, 31일 상한). 0이면 복사 못 함 — 서버 copy-week와 같은 계산 */
export function copyMaxWeeks(plan: Pick<MealPlanSummary, "start_on">, weekStart: string): number {
  return Math.max(0, Math.min(4, Math.floor(daysBetween(addDays(weekStart, 6), addDays(plan.start_on, 30)) / 7)));
}
/** 복사로 들어갈 날(다음 주 시작 ~ 마지막 주 끝)과 늘어난 기간(늘지 않으면 null) */
export function copyTarget(plan: Pick<MealPlanSummary, "start_on" | "days">, weekStart: string, weeks: number) {
  const start = addDays(weekStart, 7);
  const end = addDays(weekStart, 7 * (weeks + 1) - 1);
  const days = daysBetween(plan.start_on, end) + 1;
  return { start, end, extendedDays: days > plan.days ? days : null };
}
/** 처음 보여줄 식단: 오늘이 기간 안인 것 중 시작일이 늦은 것 → 목록 첫 번째(시작일 내림차순) */
export function pickPlan(items: MealPlanSummary[], today: string): MealPlanSummary | undefined {
  return items.find((p) => p.start_on <= today && today <= p.end_on) ?? items[0];
}
/** 고른 끼니의 빈 칸 수(시안 `고른 끼니의 빈 칸 9개만 채워요`) */
export const emptySlotCount = (dates: string[], meals: MealKind[], slots: { date: string; meal: MealKind }[]) =>
  dates.length * meals.length - slots.filter((s) => dates.includes(s.date) && meals.includes(s.meal)).length;
/** "약 1,040kcal" — 값이 하나도 없으면 "" */
export function kcalText(values: (number | null)[]): string {
  const known = values.filter((v): v is number => v !== null);
  return known.length ? `약 ${known.reduce((a, b) => a + b, 0).toLocaleString("ko-KR")}kcal` : "";
}
/** 재료 칩 "두부 D-1"(유통기한 있으면), 없으면 이름만 */
export const urgentChip = (name: string, expiresOn: string | null, today: string) =>
  expiresOn ? `${name} D-${Math.max(0, daysBetween(today, expiresOn))}` : name;
/** 살 날 태그: 오늘(또는 지남) "오늘 사요", 아니면 "16일(수)에 사요" */
export const buyDayText = (plannedOn: string, today: string) =>
  plannedOn <= today ? "오늘 사요" : `${parts(plannedOn)[2]}일(${DOW[weekday(plannedOn)]})에 사요`;
type Amount = { quantity: number; unit: string };
/** 미리보기 필요·있음 수: 딱 떨어지는 분수(½·2½)는 그대로, 아니면 소수 첫째 자리까지(1.67 → 1.7, 아주 적어도 0.1) */
const shownNumber = (quantity: number) => {
  const text = amountInputText(quantity);
  return text.includes(".") ? String(Math.max(Number(quantity.toFixed(1)), 0.1)) : text;
};
const amounts = (list: Amount[], extra: string[] = [], number = (a: Amount) => shownNumber(a.quantity)) =>
  [...list.map((a) => number(a) + a.unit), ...extra].join(" + ");
/** 줄 설명: buy·enough "2모 필요 · 1모 있어요"/"2개 필요 · 없어요", seasoning "7큰술 + 약간 필요 · 없어요", manual "있음 8개 · 필요 2판", listed "장보기 목록에 이미 있어서 건너뛰어요" */
export function previewDetail(row: MealShoppingRow): string {
  if (row.reason === "listed") return "장보기 목록에 이미 있어서 건너뛰어요";
  // 필요·있음이 같은 단위에서 같은 글자로 보이는데 값이 다르면(1.04개 · 1개, 1개 · 0.96개) 그 수를 소수 둘째 자리까지 — `1개 담기` 옆에 `1개 필요 · 1개 있어요`가 없게
  const exact = (others: Amount[]) => (a: Amount) => {
    const text = shownNumber(a.quantity);
    const clash = others.some((o) => o.unit === a.unit && o.quantity !== a.quantity && shownNumber(o.quantity) === text);
    return clash ? String(Number(a.quantity.toFixed(2))) : text;
  };
  const needs = [...row.need, ...row.need_spoon];
  const need = amounts(needs, row.need_extra, exact(row.have)) || "조금";
  const have = amounts(row.have, [], exact(needs));
  if (row.reason === null && row.have.length && !row.need.some((n) => row.have.some((h) => h.unit === n.unit)))
    return `있음 ${have} · 필요 ${need}`;
  return `${need} 필요 · ${have ? `${have} 있어요` : "없어요"}`;
}
