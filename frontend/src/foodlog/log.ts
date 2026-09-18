// 먹은 기록 달력 순수 로직(스펙 24절, 4b-3). 브라우저 API 없음 — 오늘은 인자로 받는다(scripts/check-foodlog.mjs가 node로 읽는다).
import type { DishItem, FoodLog, FoodLogMonthDay, FoodLogMonthSummary, FoodLogNutrition, FoodPlace, Incomplete, MealKind } from "../api";
import { slotDateText } from "../meals/plan.ts";
import { kcalNumber } from "../nutrition/body.ts";
import { addIncomplete, incompleteNotes, isIncomplete, nutrientText } from "../nutrition/day.ts";

export const PLACE_LABEL: Record<FoodPlace, string> = { home: "집밥", out: "외식" };
export const monthOf = (iso: string) => iso.slice(0, 7);

/** "2026-01", -1 → "2025-12" */
export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const total = y * 12 + (m - 1) + delta;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}

/** "2026-09" → "2026년 9월" */
export const monthLabel = (month: string) => `${Number(month.slice(0, 4))}년 ${Number(month.slice(5, 7))}월`;

/** 달력 칸 작은 kcal "1,420" · "약 1,780" · "" */
export const cellKcalText = (day: Pick<FoodLogMonthDay, "kcal" | "approx"> | undefined) =>
  day?.kcal == null ? "" : `${day.approx ? "약 " : ""}${kcalNumber(day.kcal)}`;

/** 칸 버튼 이름 "9월 14일 월요일, 끼니 3개, 약 1,190kcal, 사진 있음" / "9월 15일 화요일 · 오늘, 기록 없음" */
export function cellLabel(date: string, day: FoodLogMonthDay | undefined, today: string): string {
  const base = slotDateText(date, today);
  if (!day) return `${base}, 기록 없음`;
  return [base, day.meals > 0 && `끼니 ${day.meals}개`, day.kcal != null && `${cellKcalText(day)}kcal`, day.photo_url && "사진 있음", day.cooked && "요리 일기 있음"].filter(Boolean).join(", ");
}

/** 월 요약 카드(시안 MONTH) */
export function summaryView(s: FoodLogMonthSummary) {
  return {
    days: `${s.logged_days}일`,
    kcal: s.avg_kcal == null ? "—" : `${s.avg_approx ? "약 " : ""}${kcalNumber(s.avg_kcal)}`,
    home: s.home_percent == null ? "—" : `${s.home_percent}%`,
    split: s.home_percent == null ? null : ([s.home_percent, 100 - s.home_percent] as [number, number]),
    note: s.home + s.out ? `집밥 ${s.home}끼 · 외식 ${s.out}끼 · 기록한 날 기준이에요` : "집밥·외식을 고르면 비율을 보여줘요",
  };
}

/** 더보기 줄 부제(결정 20). 아직 못 받았으면 "" */
export function todayRowSub(logs: Pick<FoodLog, "meal">[] | undefined): string {
  if (!logs) return "";
  const meals = new Set(logs.map((l) => l.meal)).size;
  return meals ? `오늘 ${meals}끼 남겼어요` : "먹은 것·사진을 달력에 남겨요";
}

// ---- 날짜 상세 시트(Task 8) ----

export interface DayTotals { kcal: number; approx: boolean; sugars_g: number; sodium_mg: number; incomplete: Incomplete }
/** kcal 있는 기록만 더한다(결정 11·15). 당류·나트륨은 값 있는 것만 더하고, 빠진 이름(기록마다 서버가 준 incomplete)을 모은다. kcal 있는 기록이 없으면 null.
 *  (이름 없는 사진 기록 수는 세지 않는다 — dayDescription이 logs.some으로 본다, 개정 1 D7) */
export function dayTotals(logs: Pick<FoodLog, "nutrition" | "approx" | "incomplete">[]): DayTotals | null {
  const counted = logs.filter((l) => l.nutrition);
  if (!counted.length) return null;
  const t: DayTotals = { kcal: 0, approx: false, sugars_g: 0, sodium_mg: 0, incomplete: {} };
  for (const l of counted) {
    t.kcal += l.nutrition!.kcal;
    t.approx ||= l.approx;
    t.sugars_g += l.nutrition!.sugars_g ?? 0;
    t.sodium_mg += l.nutrition!.sodium_mg ?? 0;
    addIncomplete(t.incomplete, l.incomplete);
  }
  return t;
}

/** 이 시트가 보여주는 당류·나트륨 중 빼고 더한 것 안내 */
export const dayLeftOutNotes = (t: DayTotals) => incompleteNotes(t.incomplete, ["sugars_g", "sodium_mg"]);

/** 시트 설명(시안 DAY·PHOTO FIRST) */
export function dayDescription(logs: Pick<FoodLog, "nutrition" | "approx" | "title" | "incomplete">[], goal: number | null): string {
  if (!logs.length) return "아직 남긴 기록이 없어요";
  const t = dayTotals(logs);
  const hint = logs.some((l) => l.title === null) ? "이름을 넣으면 kcal을 계산해요" : "";
  // 기록은 있는데 kcal을 낼 수 없는 자리다. "기록이 없어요"라고 하면 바로 아래 줄에 기록이 보이는 화면과 어긋나 읽힌다(2026-09-19 운영 화면 확인)
  if (!t) return hint || "남긴 기록에 kcal 정보가 없어요";
  return [
    `${t.approx ? "약 " : ""}${kcalNumber(t.kcal)}${goal ? ` / 목표 ${kcalNumber(goal)}` : ""}kcal`,
    // 합이 0이면 숨기되(값이 다 있는 0), 빼고 더한 값이 있으면 "알 수 없어요"까지 보여준다(결정 14 개정 2)
    t.sugars_g || isIncomplete(t.incomplete, "sugars_g") ? `당류 ${nutrientText(t.sugars_g, "g", t.incomplete, "sugars_g")}` : "",
    t.sodium_mg || isIncomplete(t.incomplete, "sodium_mg") ? `나트륨 ${nutrientText(t.sodium_mg, "mg", t.incomplete, "sodium_mg")}` : "",
    hint,
  ].filter(Boolean).join(" · ");
}

/** 끼니 머리 오른쪽 "310kcal" / "약 400kcal" / "" */
export const mealKcalText = (logs: Pick<FoodLog, "nutrition" | "approx" | "title" | "incomplete">[]) => {
  const t = dayTotals(logs);
  return t ? `${t.approx ? "약 " : ""}${kcalNumber(t.kcal)}kcal` : "";
};

/** 0.5 → "½인분", 1.5 → "1½인분", 2 → "2인분" */
export const servingsText = (n: number) => `${Math.floor(n) || ""}${n % 1 ? "½" : ""}인분`;

/** 서울 시각 "12:41" */
export const timeText = (iso: string) => new Date(iso).toLocaleString("sv-SE", { timeZone: "Asia/Seoul" }).slice(11, 16);

/** 기록 줄 보조 글자 "1인분 · 310kcal" / "2인분 중 1인분 · 약 480kcal" / "300g · 약 555kcal" / 사진 기록 "12:41 · 누르면 무엇을 먹었는지 채워요" */
export function logSubText(log: Pick<FoodLog, "title" | "servings" | "grams" | "slot_servings" | "nutrition" | "approx" | "created_at">): string {
  if (log.title === null) return `${timeText(log.created_at)} · 누르면 무엇을 먹었는지 채워요`;
  const amount = log.grams !== null ? `${log.grams}g`
    : log.servings === null ? ""
    : log.slot_servings && log.slot_servings > log.servings ? `${log.slot_servings}인분 중 ${servingsText(log.servings)}` : servingsText(log.servings);
  const kcal = log.nutrition ? `${log.approx ? "약 " : ""}${kcalNumber(log.nutrition.kcal)}kcal` : "";
  return [amount, kcal].filter(Boolean).join(" · ");
}

/** 만족도 별 글자 "★★★★☆"(aria는 "만족도 4점") */
export const starsText = (rating: number) => "★".repeat(rating) + "☆".repeat(5 - rating);


// ---- 먹은 것 추가·고치기 시트(Task 9) ----

export const MIN_SERVINGS = 0.5;
export const MAX_SERVINGS = 20;
/** −/+ 0.5씩, 0.5~20 */
export const stepServings = (n: number, delta: 1 | -1) => Math.min(MAX_SERVINGS, Math.max(MIN_SERVINGS, n + delta * 0.5));

/** 서버 scaled(_round0/_round1, .5 올림)와 같은 반올림(kcal·mg 정수, g 소수 첫째). 인자 타입은 FoodLogNutrition 한 벌(개정 1 D8·S3) */
export function scaleNutrition(per: FoodLogNutrition, factor: number): FoodLogNutrition {
  const g = (v: number | null) => (v === null ? null : Math.round(v * factor * 10) / 10);
  return { kcal: Math.round(per.kcal * factor), carbs_g: g(per.carbs_g), protein_g: g(per.protein_g), fat_g: g(per.fat_g), sugars_g: g(per.sugars_g), sodium_mg: per.sodium_mg === null ? null : Math.round(per.sodium_mg * factor) };
}

export type Amount = { servings: number } | { grams: number };

/** 음식 먹은 g: g 입력이면 그대로, 인분이면 1인분 무게 × 인분(무게 없으면 null) */
export const dishGrams = (item: Pick<DishItem, "serving_g">, amount: Amount) =>
  "grams" in amount ? amount.grams : item.serving_g === null ? null : item.serving_g * amount.servings;

/** 미리보기 "약 370kcal · 당류 11g · 나트륨 820mg"(레시피에서 빼고 더한 값은 dayDescription과 같은 규칙) */
export function previewText(n: FoodLogNutrition | null, approx: boolean, incomplete: Incomplete = {}): string {
  if (!n) return "";
  return [
    `${approx ? "약 " : ""}${kcalNumber(n.kcal)}kcal`,
    n.sugars_g || isIncomplete(incomplete, "sugars_g") ? `당류 ${nutrientText(n.sugars_g ?? 0, "g", incomplete, "sugars_g")}` : "",
    n.sodium_mg || isIncomplete(incomplete, "sodium_mg") ? `나트륨 ${nutrientText(n.sodium_mg ?? 0, "mg", incomplete, "sodium_mg")}` : "",
  ].filter(Boolean).join(" · ");
}

/** 음식 후보 설명 "음식 · 1인분(400g) 약 740kcal" / "가공식품 · 100g당 185kcal"(앞머리는 응답 group, Ruling C6) */
export const dishSub = (item: Pick<DishItem, "group" | "serving_g" | "kcal">) =>
  item.serving_g === null ? `${item.group} · 100g당 ${kcalNumber(item.kcal)}kcal` : `${item.group} · 1인분(${kcalNumber(item.serving_g)}g) 약 ${kcalNumber((item.kcal * item.serving_g) / 100)}kcal`;

/** g 입력 → 1~3000 정수, 아니면 null */
export function parseGrams(text: string): number | null {
  const n = Number(text.trim());
  return Number.isInteger(n) && n >= 1 && n <= 3000 ? n : null;
}

/** 양 칸이 숨었을 때(`바꾸기`만 누르고 아직 안 고름) 보낼 원래 양 — patchBody가 바뀌지 않았다고 본다 */
export const keptAmount = (log: Pick<FoodLog, "servings" | "grams">): Amount =>
  log.grams !== null ? { grams: log.grams } : { servings: log.servings ?? 1 };

/** 무엇 네 갈래(결정 3) */
export type LogKind = "plan" | "recipe" | "food" | "direct";
export const KIND_LABEL: Record<LogKind, string> = { plan: "식단에서", recipe: "내 레시피", food: "음식", direct: "직접" };
export type WhatPick =
  | { kind: "plan"; slotId: number }
  | { kind: "recipe"; recipeId: number }
  | { kind: "food"; foodCode: string }
  | { kind: "direct"; title: string };

/** 시트 입력 한 벌. memo는 입력 그대로(보낼 때 앞뒤 공백을 빼고 비면 null) */
export interface LogForm { meal: MealKind; what: WhatPick | null; amount: Amount; place: FoodPlace | null; rating: number | null; memo: string }

/** 기록이 어떤 갈래로 남았는지(고치기 `바꾸기` 줄) */
export const logKind = (log: Pick<FoodLog, "meal_slot_id" | "recipe_id" | "food_code">): LogKind =>
  log.meal_slot_id !== null ? "plan" : log.recipe_id !== null ? "recipe" : log.food_code !== null ? "food" : "direct";

const whatFields = (what: WhatPick) =>
  what.kind === "plan" ? { meal_slot_id: what.slotId }
  : what.kind === "recipe" ? { recipe_id: what.recipeId }
  : what.kind === "food" ? { food_code: what.foodCode }
  : { title: what.title.trim() };

const memoValue = (memo: string) => memo.trim() || null;

/** POST /api/food-logs body. 식단 칸은 날짜·끼니를 칸에서 가져오므로 보내지 않는다 */
export function createBody(date: string, form: LogForm & { what: WhatPick }) {
  const when = form.what.kind === "plan" ? {} : { eaten_on: date, meal: form.meal };
  return { ...when, ...whatFields(form.what), ...form.amount, place: form.place, rating: form.rating, memo: memoValue(form.memo) };
}

/** PATCH body: 바뀐 칸만. 무엇을 새로 골랐으면 양도 함께(안 보내면 서버가 1인분으로 둔다). 사진 기록(제목 없음)은 무엇 없이 양을 보내지 않는다 */
export function patchBody(log: Pick<FoodLog, "meal" | "title" | "servings" | "grams" | "place" | "rating" | "memo">, form: LogForm) {
  const body: Record<string, unknown> = {};
  if (form.meal !== log.meal) body.meal = form.meal;
  if (form.what) Object.assign(body, whatFields(form.what), form.amount);
  else if (log.title !== null && ("grams" in form.amount ? form.amount.grams !== log.grams : form.amount.servings !== log.servings)) Object.assign(body, form.amount);
  if (form.place !== log.place) body.place = form.place;
  if (form.rating !== log.rating) body.rating = form.rating;
  if (memoValue(form.memo) !== log.memo) body.memo = memoValue(form.memo);
  return body;
}
