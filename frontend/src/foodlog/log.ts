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
