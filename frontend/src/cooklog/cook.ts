// 요리 일기 순수 로직(스펙 29절, 5단계). 브라우저 API 없음 — 오늘·시각은 인자로 받는다(scripts/check-cooklog.mjs가 node로 읽는다).
import type { CookDraftRow, CookLogItem, CookLogListItem, CookReport, MealKind } from "../api";
import { formatQuantity, formatWon, withJosa } from "../format.ts";
import { monthLabel } from "../foodlog/log.ts";
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
const MAX_AMOUNT = 100_000; // 서버 cooklog.MAX_AMOUNT
/** 서버처럼 소수 셋째 자리로 반올림(cooklog.parse_usages) */
const round3 = (n: number) => Math.round(n * 1000) / 1000;
/** 쓴 양 입력 "1.5"·"0,3" → 셋째 자리 반올림 뒤 0 < n ≤ 100000, 아니면 null */
export function parseAmountInput(text: string): number | null {
  const n = Number(text.trim().replace(",", "."));
  return text.trim() !== "" && Number.isFinite(n) && round3(n) > 0 && round3(n) <= MAX_AMOUNT ? n : null;
}
/** 저장을 누른 뒤 쓴 양 칸 안내(없으면 null). 서버 상한을 넘으면 서버가 돌려주는 문구 그대로(cooklog.AMOUNT_ERROR) */
export function amountHint(text: string): string | null {
  if (parseAmountInput(text) !== null) return null;
  const n = Number(text.trim().replace(",", "."));
  return Number.isFinite(n) && round3(n) > MAX_AMOUNT ? "쓴 양은 0보다 커야 해요." : "쓴 양을 입력하거나, 안 썼으면 체크를 꺼주세요";
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
/** 결정 15: 100원 반올림 뒤에도 음수일 때만 '더 들었어요'(aboutWon의 절댓값 반올림과 같다 — -50부터) */
export const overSpent = (n: number) => n <= -50;
/** 결정 15 */
export const savedText = (saved: number) => `${aboutWon(saved)} ${overSpent(saved) ? "더 들었어요" : "아꼈어요"}`;
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
/** 되돌린 뒤 알림. 재고에서 뺀 게 없던 저장이면 일기(와 먹은 기록)만 지운 것 */
export const undoneText = (r: { restored: string[]; skipped: string[] }) =>
  r.skipped.length
    ? `재고를 되돌렸어요 · ${withJosa(r.skipped.join("·"), "은", "는")} 그사이 바뀌어 그대로 뒀어요`
    : r.restored.length
      ? "재고를 되돌렸어요"
      : "요리 일기를 지웠어요";
/** 쓴 양 칸 옆 "재고 600g" */
export const stockText = (row: Pick<CookDraftRow, "stock_quantity" | "stock_unit">) =>
  row.stock_quantity === null ? "재고에 없어요" : `재고 ${formatQuantity(row.stock_quantity)}${row.stock_unit ?? ""}`;
/** 레시피 상세 "마지막 9월 15일 · ★★★★☆" */
export function cookedLine(c: { last_on: string; last_rating: number | null }, stars: (n: number) => string): string {
  const day = `마지막 ${Number(c.last_on.slice(5, 7))}월 ${Number(c.last_on.slice(8, 10))}일`;
  return c.last_rating === null ? day : `${day} · ${stars(c.last_rating)}`;
}

// ---- Task 10: 요리 일기 목록·상세(시안 3·4) ----
/** 목록 행 아낀 돈 조각(결정 14·15). good이면 초록 글자 */
export function savedRowText(log: Pick<CookLogListItem, "saved" | "eat_out_price" | "excluded_count">): { text: string; good: boolean } {
  if (log.saved !== null) return overSpent(log.saved) ? { text: `${aboutWon(log.saved)} 더 듦`, good: false } : { text: `${aboutWon(log.saved)} 아낌`, good: true };
  if (log.eat_out_price === null) return { text: "사 먹으면 얼마 모름", good: false };
  return { text: log.excluded_count ? `재료 ${log.excluded_count}개 가격 모름` : "재료 가격 모름", good: false };
}
/** "9월 15일 · 2인분" */
export const diaryDateText = (log: Pick<CookLogListItem, "cooked_on" | "servings">) =>
  `${Number(log.cooked_on.slice(5, 7))}월 ${Number(log.cooked_on.slice(8, 10))}일 · ${log.servings}인분`;
/** 메모 첫 줄 */
export const firstLine = (memo: string | null) => (memo ?? "").split("\n")[0].trim();
/** 목록 위 카드 "9월 요리 12번 · 약 86,000원 아꼈어요" */
export function diaryHeader(r: Pick<CookReport, "month" | "cooked" | "counted" | "saved_total">): string {
  const head = `${Number(r.month.slice(5, 7))}월 요리 ${r.cooked}번`;
  return r.counted ? `${head} · ${savedText(r.saved_total)}` : head;
}
/** 계산표 사 먹으면 줄 "사 먹으면 9,000원 × 2인분" */
export const eatOutLine = (price: number, servings: number) => `사 먹으면 ${formatWon(price)} × ${servings}인분`;
/** 계산표 재료 줄 "김치 0.3kg / 1kg 12,900원" (가격 있는 줄만) */
export const costLine = (i: Pick<CookLogItem, "name" | "used" | "unit" | "price" | "price_quantity">) =>
  `${i.name} ${formatQuantity(i.used ?? 0)}${i.unit ?? ""} / ${formatQuantity(i.price_quantity ?? 0)}${i.unit ?? ""} ${formatWon(i.price ?? 0)}`;
/** 은/는(개정 1 T10②): withJosa는 한글로 안 끝나면 "은(는)"을 돌려주므로 영문 단위·숫자 끝은 읽는 소리로 고른다.
 *  g·kg·mg(그램)→은, ml·l(리터)→는, 숫자는 끝자리(영·일·삼·육·칠·팔→은, 이·사·오·구→는), 그 밖은 withJosa */
const UNIT_BATCHIM: Record<string, boolean> = { g: true, kg: true, mg: true, ml: false, l: false };
const DIGIT_BATCHIM = [true, true, false, true, false, false, true, true, true, false];
export function withEunNeun(word: string): string {
  const unit = /([a-z]+)$/i.exec(word)?.[1].toLowerCase();
  if (unit !== undefined && unit in UNIT_BATCHIM) return word + (UNIT_BATCHIM[unit] ? "은" : "는");
  if (/\d$/.test(word)) return word + (DIGIT_BATCHIM[Number(word.slice(-1))] ? "은" : "는");
  return withJosa(word, "은", "는");
}
/** 계산표 아래 안내(시안 4) */
export function excludedNote(items: Pick<CookLogItem, "name" | "used" | "unit" | "amount_text" | "excluded">[]): string {
  const unknown = items.filter((i) => i.excluded === "no_price");
  const label = (i: (typeof unknown)[number]) => `${i.name} ${i.used !== null ? `${formatQuantity(i.used)}${i.unit ?? ""}` : (i.amount_text ?? "")}`.trim();
  const parts = [];
  if (unknown.length === 1) parts.push(`${withEunNeun(label(unknown[0]))} 가격 모름이라 뺐어요`);
  if (unknown.length > 1) parts.push(`${label(unknown[0])} 외 ${unknown.length - 1}개는 가격 모름이라 뺐어요`);
  if (items.some((i) => i.excluded === "seasoning")) parts.push("양념은 계산에 넣지 않아요");
  parts.push("참고용이에요");
  return parts.join(" · ");
}

// ---- Task 11: 집밥 리포트(시안 5) ----
/** 리포트 머리 "2026년 9월 집밥 리포트" */
export const reportTitle = (month: string) => `${monthLabel(month)} 집밥 리포트`;
/** 큰 숫자 위 글자: 이번 달이면 "이번 달 집밥으로", 올해면 "9월 집밥으로", 다른 해면 "2025년 9월 집밥으로" */
export const reportLead = (month: string, today: string) =>
  month === today.slice(0, 7)
    ? "이번 달 집밥으로"
    : `${month.slice(0, 4) === today.slice(0, 4) ? `${Number(month.slice(5, 7))}월` : monthLabel(month)} 집밥으로`;
/** 합계 아래 "요리 12번 중 10번 계산 · 재료 5개 가격 제외 · 참고용이에요" */
export function reportNote(r: Pick<CookReport, "cooked" | "counted" | "excluded_ingredients">): string {
  const head = `요리 ${r.cooked}번 중 ${r.counted}번 계산`;
  return [head, r.excluded_ingredients ? `재료 ${r.excluded_ingredients}개 가격 제외` : "", "참고용이에요"].filter(Boolean).join(" · ");
}
/** 결정 22. 지난달 기록이 없으면 null */
export function compareLine(r: Pick<CookReport, "cooked" | "discarded" | "previous">): string | null {
  const { cooked, discarded } = r.previous;
  if (!cooked && !discarded) return null;
  const dc = r.cooked - cooked, dd = r.discarded - discarded;
  const cook = dc > 0 ? `지난달보다 요리 ${dc}번 더` : dc < 0 ? `지난달보다 요리 ${-dc}번 덜` : "지난달과 요리 횟수가 같아요";
  const waste = dd < 0 ? `버린 재료 ${-dd}개 줄었어요` : dd > 0 ? `버린 재료 ${dd}개 늘었어요` : "버린 재료는 그대로예요";
  return `${cook} · ${waste}`;
}
/** 막대 폭 %(1등 대비, 최소 4) */
export const barWidths = (rows: { saved: number }[]) => rows.map((r) => Math.max(4, Math.round((r.saved * 100) / Math.max(rows[0]?.saved ?? 1, 1))));
