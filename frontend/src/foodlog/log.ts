// 먹은 기록 달력 순수 로직(스펙 24절, 4b-3). 브라우저 API 없음 — 오늘은 인자로 받는다(scripts/check-foodlog.mjs가 node로 읽는다).
import type { FoodLog, FoodLogMonthDay, FoodLogMonthSummary, FoodPlace } from "../api";
import { slotDateText } from "../meals/plan.ts";
import { kcalNumber } from "../nutrition/body.ts";

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
  return [base, `끼니 ${day.meals}개`, day.kcal != null && `${cellKcalText(day)}kcal`, day.photo_url && "사진 있음"].filter(Boolean).join(", ");
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

export interface DayTotals { kcal: number; approx: boolean; sugars_g: number; sodium_mg: number }
/** kcal 있는 기록만 더한다(결정 11·15). 당류·나트륨은 값 있는 것만. kcal 있는 기록이 없으면 null.
 *  (이름 없는 사진 기록 수는 세지 않는다 — dayDescription이 logs.some으로 본다, 개정 1 D7) */
export function dayTotals(logs: Pick<FoodLog, "nutrition" | "approx">[]): DayTotals | null {
  const counted = logs.filter((l) => l.nutrition);
  if (!counted.length) return null;
  const t: DayTotals = { kcal: 0, approx: false, sugars_g: 0, sodium_mg: 0 };
  for (const l of counted) {
    t.kcal += l.nutrition!.kcal;
    t.approx ||= l.approx;
    t.sugars_g += l.nutrition!.sugars_g ?? 0;
    t.sodium_mg += l.nutrition!.sodium_mg ?? 0;
  }
  return t;
}

/** 시트 설명(시안 DAY·PHOTO FIRST) */
export function dayDescription(logs: Pick<FoodLog, "nutrition" | "approx" | "title">[], goal: number | null): string {
  if (!logs.length) return "아직 남긴 기록이 없어요";
  const t = dayTotals(logs);
  const hint = logs.some((l) => l.title === null) ? "이름을 넣으면 kcal을 계산해요" : "";
  if (!t) return hint || "kcal을 계산할 수 있는 기록이 없어요";
  return [
    `${t.approx ? "약 " : ""}${kcalNumber(t.kcal)}${goal ? ` / 목표 ${kcalNumber(goal)}` : ""}kcal`,
    t.sugars_g ? `당류 ${Math.round(t.sugars_g)}g` : "",
    t.sodium_mg ? `나트륨 ${kcalNumber(t.sodium_mg)}mg` : "",
    hint,
  ].filter(Boolean).join(" · ");
}

/** 끼니 머리 오른쪽 "310kcal" / "약 400kcal" / "" */
export const mealKcalText = (logs: Pick<FoodLog, "nutrition" | "approx" | "title">[]) => {
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
