// 요리 일기 순수 로직(스펙 29절, 5단계). 브라우저 API 없음 — 오늘·시각은 인자로 받는다(scripts/check-cooklog.mjs가 node로 읽는다).
import type { CookDraftRow, MealKind } from "../api";
import { formatQuantity, formatWon, withJosa } from "../format.ts";
import { mealLabel } from "../meals/plan.ts";

export const MAX_COOK_SERVINGS = 20;
export const MAX_EAT_OUT = 1_000_000;
/** 23절 D2: 레시피 양 × 인분 배율(재고 단위, 소수 셋째), 모르면 1 */
export const defaultAmount = (row: Pick<CookDraftRow, "base_amount">, servings: number, recipeServings: number) =>
  row.base_amount === null ? 1 : Math.round(((row.base_amount * servings) / Math.max(recipeServings, 1)) * 1000) / 1000;
/** 처음 체크: 재고에 있고 양념이 아니면 */
export const defaultChecked = (row: Pick<CookDraftRow, "ingredient_id" | "seasoning">) => row.ingredient_id !== null && !row.seasoning;
/** 결정 6: 쓴 양이 재고 이상이면 `마저 써요` */
export const usesUp = (amount: number, stock: number) => amount >= stock - 0.0005;
/** 쓴 양 입력 "1.5"·"0,3" → 0 < n ≤ 100000, 아니면 null */
export function parseAmountInput(text: string): number | null {
  const n = Number(text.trim().replace(",", "."));
  return text.trim() !== "" && Number.isFinite(n) && n > 0 && n <= 100000 ? n : null;
}
/** 사 먹으면 얼마 입력 "9,000원" → 9000, "" → null, 틀리면 undefined */
export function parseWon(text: string): number | null | undefined {
  const digits = text.replace(/[,\s원]/g, "");
  if (digits === "") return null;
  if (!/^\d+$/.test(digits)) return undefined;
  const n = Number(digits);
  return n <= MAX_EAT_OUT ? n : undefined;
}
/** 입력 칸 표시: 9000 → "9,000", null → "", 틀린 입력(undefined)은 쓴 글자 그대로(개정 1 T8① — 한 글자 칠 때 죽지 않게) */
export const wonFieldText = (n: number | null | undefined, typed: string) => (n === undefined ? typed : n === null ? "" : n.toLocaleString("ko-KR"));
/** 결정 13: 100원 단위 반올림 "약 10,800원"(부호는 호출 측) */
export const aboutWon = (n: number) => `약 ${formatWon(Math.round(Math.abs(n) / 100) * 100)}`;
/** 결정 15 */
export const savedText = (saved: number) => (saved >= 0 ? `${aboutWon(saved)} 아꼈어요` : `${aboutWon(saved)} 더 들었어요`);
/** 결정 16: 식단 칸 끼니 → 오늘이면 시각(5–9 아침·10–14 점심·15–20 저녁·그 밖 간식) → 지난 날은 저녁.
 *  ponytail: 서버 food_logs.meal_for_time과 같은 시간표 — 바꾸면 둘 다(시트 설명 줄에 끼니를 보여줘야 해서 화면에도 둔다, 개정 1 D16) */
export function cookMeal(date: string, today: string, hour: number, slotMeal?: MealKind): MealKind {
  if (slotMeal) return slotMeal;
  if (date < today) return "dinner";
  return hour >= 5 && hour < 10 ? "breakfast" : hour >= 10 && hour < 15 ? "lunch" : hour >= 15 && hour < 21 ? "dinner" : "snack";
}
/** 서울 시(時) — 화면이 new Date()를 넘긴다 */
export const seoulHour = (d: Date) => Number(d.toLocaleString("en-US", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }));
/** 먹은 기록 스위치 설명 "9월 15일 저녁 · 집밥" */
export const foodLogLine = (date: string, meal: MealKind) => `${Number(date.slice(5, 7))}월 ${Number(date.slice(8, 10))}일 ${mealLabel(meal)} · 집밥`;
/** 언제 칩 */
export function dateChip(date: string, today: string, yesterday: string): "today" | "yesterday" | "pick" {
  return date === today ? "today" : date === yesterday ? "yesterday" : "pick";
}
/** 저장 후 알림 첫 줄(시안 2) */
export function deductedText(names: string[]): string {
  if (!names.length) return "요리 일기에 남겼어요";
  const shown = names.length <= 3 ? names.join("·") : `${names.slice(0, 3).join("·")} 외 ${names.length - 3}개`;
  return `재고에서 ${withJosa(shown, "을", "를")} 뺐어요`; // withJosa는 낱말 + 조사를 돌려준다
}
/** 되돌린 뒤 알림 */
export const undoneText = (r: { skipped: string[] }) =>
  r.skipped.length ? `재고를 되돌렸어요 · ${withJosa(r.skipped.join("·"), "은", "는")} 그사이 바뀌어 그대로 뒀어요` : "재고를 되돌렸어요";
/** 쓴 양 칸 옆 "재고 600g" */
export const stockText = (row: Pick<CookDraftRow, "stock_quantity" | "stock_unit">) =>
  row.stock_quantity === null ? "재고에 없어요" : `재고 ${formatQuantity(row.stock_quantity)}${row.stock_unit ?? ""}`;
/** 레시피 상세 "마지막 9월 15일 · ★★★★☆" */
export function cookedLine(c: { last_on: string; last_rating: number | null }, stars: (n: number) => string): string {
  const day = `마지막 ${Number(c.last_on.slice(5, 7))}월 ${Number(c.last_on.slice(8, 10))}일`;
  return c.last_rating === null ? day : `${day} · ${stars(c.last_rating)}`;
}
