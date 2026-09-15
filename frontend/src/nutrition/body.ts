// 하루 칼로리 목표 계산(4b-2 Task 6). 브라우저 API 없음, 오늘은 인자로 받는다.
import type { Activity, BodyGoal, BodyProfile, Sex } from "../api";

export const SEXES: [Sex, string][] = [
  ["female", "여성"],
  ["male", "남성"],
];

export const ACTIVITIES: { value: Activity; label: string; hint: string; factor: number }[] = [
  { value: "sedentary", label: "거의 없음", hint: "대부분 앉아서 지내요", factor: 1.2 },
  { value: "light", label: "가벼움", hint: "주 1~3번 가볍게 걷거나 운동해요", factor: 1.375 },
  { value: "moderate", label: "보통", hint: "주 3~5번 운동해요", factor: 1.55 },
  { value: "active", label: "많음", hint: "주 6~7번 운동해요", factor: 1.725 },
  { value: "very_active", label: "매우 많음", hint: "매일 힘든 운동이나 몸을 많이 쓰는 일을 해요", factor: 1.9 },
];

export const GOALS: [BodyGoal, string][] = [
  ["maintain", "유지"],
  ["lose", "감량"],
  ["gain", "증량"],
];

export const MIN_AGE = 20;
export const MAX_AGE = 99;
export const MAX_TARGET = 5000;

export const goalLabel = (goal: BodyGoal) => GOALS.find(([g]) => g === goal)![1];
export const kcalNumber = (n: number) => Math.round(n).toLocaleString("ko-KR");

/** 연 나이(결정 1): "2026-09-15", 1994 → 32 */
export const ageOf = (birthYear: number, today: string) => Number(today.slice(0, 4)) - birthYear;

export interface DailyTarget {
  bmr: number;
  tdee: number;
  target: number;
  floored: boolean;
  capped: boolean;
  factor: number;
}

/** Mifflin–St Jeor × 활동계수, 목표(결정 3). 모두 정수 반올림 */
export function dailyTarget(
  p: Pick<BodyProfile, "sex" | "birth_year" | "height_cm" | "weight_kg" | "activity" | "goal">,
  today: string,
): DailyTarget {
  const raw = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * ageOf(p.birth_year, today) + (p.sex === "male" ? 5 : -161);
  const factor = ACTIVITIES.find((a) => a.value === p.activity)!.factor;
  const bmr = Math.round(raw);
  const tdee = Math.round(raw * factor);
  if (p.goal === "lose") return { bmr, tdee, target: Math.max(tdee - 500, bmr), floored: tdee - 500 < bmr, capped: false, factor };
  if (p.goal === "gain")
    return { bmr, tdee, target: Math.min(tdee + 500, MAX_TARGET), floored: false, capped: tdee + 500 > MAX_TARGET, factor };
  return { bmr, tdee, target: tdee, floored: false, capped: false, factor };
}

/** 결과 상자 아래 설명(시안 BODY SHEET). 모든 경우 끝에 참고용 문구 */
export function targetNote(t: DailyTarget, goal: BodyGoal): string {
  const tail = `Mifflin–St Jeor 식 × 활동계수 ${t.factor} · 의료 조언이 아니라 참고용이에요.`;
  if (goal === "lose") return `${t.floored ? "필요량 − 500kcal이지만 기초대사량보다 낮게는 제안하지 않아요." : "필요량 − 500kcal이에요."} ${tail}`;
  if (goal === "gain") return `${t.capped ? "필요량 + 500kcal이지만 5,000kcal까지만 제안해요." : "필요량 + 500kcal이에요."} ${tail}`;
  return tail;
}

/** 입력 글자 → 저장할 값. 틀리면 칸별 안내 문구(화면 아래 줄), 비었으면 null 값 */
export function parseProfileInput(
  f: { sex: Sex | null; birthYear: string; height: string; weight: string; activity: Activity | null; goal: BodyGoal },
  today: string,
): { value: Omit<BodyProfile, "updated_at"> | null; errors: { birthYear?: string; height?: string; weight?: string } } {
  const year = Number(today.slice(0, 4));
  const num = (s: string) => (s.trim() === "" ? null : Number(s.replace(",", ".")));
  const birth = num(f.birthYear),
    height = num(f.height),
    weight = num(f.weight);
  const errors: { birthYear?: string; height?: string; weight?: string } = {};
  if (birth !== null && !(Number.isInteger(birth) && birth >= year - MAX_AGE && birth <= year - MIN_AGE))
    errors.birthYear = `${year - MAX_AGE}~${year - MIN_AGE}년 사이로 입력해주세요`;
  if (height !== null && !(height >= 120 && height <= 230)) errors.height = "120~230cm 사이로 입력해주세요";
  if (weight !== null && !(weight >= 30 && weight <= 250)) errors.weight = "30~250kg 사이로 입력해주세요";
  const complete = f.sex && f.activity && birth !== null && height !== null && weight !== null && !Object.keys(errors).length;
  return {
    value: complete
      ? { sex: f.sex!, birth_year: birth!, height_cm: Math.round(height! * 10) / 10, weight_kg: Math.round(weight! * 10) / 10, activity: f.activity!, goal: f.goal }
      : null,
    errors,
  };
}
