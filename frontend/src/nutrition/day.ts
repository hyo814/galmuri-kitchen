// 주 보기 kcal·하루 목표 막대·하루 영양 시트 순수 로직 (4b-2 Task 7), 레시피 상세 영양·식품 고르기 시트 (Task 8)
import type { Incomplete, MealSlot, NutritionIngredient, SlotNutrition } from "../api";
import { withJosa } from "../format.ts";
import { kcalNumber } from "./body.ts";

export const SUGARS_DAILY_G = 100; // 식품 표시 1일 영양성분기준치(하루 2,000kcal)
export const SODIUM_DAILY_MG = 2000;
export const WHO_SUGAR_RATIO = 0.1; // WHO 유리당: 총 에너지의 10% 미만

const NUTRIENT_LABEL = { carbs_g: "탄수화물", protein_g: "단백질", fat_g: "지방", sugars_g: "당류", sodium_mg: "나트륨" } as const;
type NutrientKey = keyof typeof NUTRIENT_LABEL;
export const NUTRIENT_KEYS = Object.keys(NUTRIENT_LABEL) as NutrientKey[];

/** 빠진 이름을 합계에 모은다(같은 이름은 한 번) */
export function addIncomplete(into: Incomplete, from: Incomplete) {
  for (const k of NUTRIENT_KEYS) if (from[k]?.length) into[k] = [...new Set([...(into[k] ?? []), ...from[k]])];
}

/** 값 뒤 " 이상" — 빼고 더한 값이 있어 실제로는 더 많을 수 있다(결정 14 개정 2) */
export const atLeast = (incomplete: Incomplete, key: NutrientKey) => (incomplete[key]?.length ? " 이상" : "");

/** "된장은 나트륨 값이 없어 빼고 계산했어요" · "된장 외 1개는 당류·나트륨 값이 …". keys는 화면에 보이는 영양소, 빠진 이름이 같은 영양소끼리 한 줄 */
export function incompleteNotes(incomplete: Incomplete, keys: readonly NutrientKey[]): string[] {
  const groups = new Map<string, { names: string[]; labels: string[] }>();
  for (const k of keys) {
    const names = incomplete[k];
    if (!names?.length) continue;
    const id = names.join("\n");
    if (!groups.has(id)) groups.set(id, { names, labels: [] });
    groups.get(id)!.labels.push(NUTRIENT_LABEL[k]);
  }
  return [...groups.values()].map(({ names, labels }) => {
    const who = names.length > 1 ? `${names[0]} 외 ${names.length - 1}개` : names[0];
    return `${withJosa(who, "은", "는")} ${labels.join("·")} 값이 없어 빼고 계산했어요`;
  });
}

/** "310kcal" / "약 480kcal", 없으면 "" */
export const slotKcalText = (n: SlotNutrition | null) => (n ? `${n.approx ? "약 " : ""}${kcalNumber(n.kcal)}kcal` : "");

export interface DaySum {
  kcal: number;
  carbs_g: number;
  protein_g: number;
  fat_g: number;
  sugars_g: number;
  sodium_mg: number;
  /** source calc 칸 kcal만 더한 값(당류 비율의 분모 — ai 칸의 kcal은 당류가 없어 총 kcal을 쓰면 비율이 실제보다 낮게 나온다) */
  calcKcal: number;
  filled: number;
  counted: number;
  approx: boolean;
  hasAi: boolean;
  /** source calc 칸에서 빼고 더한 영양소 → 재료 이름 */
  incomplete: Incomplete;
}

/** 그날 채운 칸의 1인분 값 합(결정 14·15). kcal 있는 칸이 없으면 null. 탄단지·당류·나트륨(과 빠진 이름)은 source calc 칸만 더한다 */
export function daySum(slots: Pick<MealSlot, "nutrition">[]): DaySum | null {
  const withKcal = slots.filter((s) => s.nutrition);
  if (!withKcal.length) return null;
  const sum: DaySum = {
    kcal: 0,
    carbs_g: 0,
    protein_g: 0,
    fat_g: 0,
    sugars_g: 0,
    sodium_mg: 0,
    calcKcal: 0,
    filled: slots.length,
    counted: withKcal.length,
    approx: withKcal.length < slots.length,
    hasAi: false,
    incomplete: {},
  };
  for (const { nutrition: n } of withKcal) {
    sum.kcal += n!.kcal;
    sum.approx ||= n!.approx;
    if (n!.source === "ai") sum.hasAi = true;
    else {
      sum.calcKcal += n!.kcal;
      for (const k of NUTRIENT_KEYS) sum[k] += n![k] ?? 0;
      addIncomplete(sum.incomplete, n!.incomplete);
    }
  }
  return sum;
}

/** 하루 머리 "약 1,190 / 1,294kcal" · "1,520 / 1,294kcal" · "약 1,420kcal" */
export const dayHeadText = (sum: DaySum, goal: number | null) =>
  `${sum.approx ? "약 " : ""}${kcalNumber(sum.kcal)}${goal ? ` / ${kcalNumber(goal)}` : ""}kcal`;

/** 막대 너비 0~100 */
export const meterPercent = (value: number, max: number) => (max > 0 ? Math.max(0, Math.min(100, Math.round((value / max) * 100))) : 0);

/** 탄단지 kcal 비율(4·4·9) 정수 %, 모두 0이면 [0, 0, 0] */
export function macroSplit(carbs: number, protein: number, fat: number): [number, number, number] {
  const kcal = [carbs * 4, protein * 4, fat * 9];
  const total = kcal[0] + kcal[1] + kcal[2];
  return total ? (kcal.map((k) => Math.round((k / total) * 100)) as [number, number, number]) : [0, 0, 0];
}

// 아래 셋의 incomplete: 빼고 더한 값(하한)이라 기준치를 넘은 게 확실할 때만 " 이상"을 붙여 돌려주고, 아니면 null(비율·막대를 그리지 않는다)

/** 레시피 1인분: "1일 기준치의 86%", warn은 33% 초과(결정 18) */
export function dailyValue(value: number, daily: number, incomplete = false) {
  const pct = Math.round((value / daily) * 100);
  const warn = value / daily > 1 / 3;
  if (incomplete && !warn) return null;
  return { text: `1일 기준치의 ${pct}%${incomplete ? " 이상" : ""}`, percent: Math.min(100, pct), warn };
}

/** 하루 당류: "총 에너지의 7% · WHO 10% 미만", 막대는 10% 대비, warn은 10% 이상 */
export function sugarDay(sugars_g: number, kcal: number, incomplete = false) {
  const ratio = kcal > 0 ? (sugars_g * 4) / kcal : 0;
  const warn = ratio >= WHO_SUGAR_RATIO;
  if (incomplete && !warn) return null;
  return { text: `총 에너지의 ${Math.round(ratio * 100)}%${incomplete ? " 이상" : ""} · WHO 10% 미만`, percent: meterPercent(ratio, WHO_SUGAR_RATIO), warn };
}

/** 하루 나트륨: 넘으면 "1일 기준치 넘었어요", 아니면 "1일 기준치의 N%" */
export function sodiumDay(mg: number, incomplete = false) {
  const over = mg > SODIUM_DAILY_MG;
  if (incomplete && !over) return null;
  return { text: over ? "1일 기준치 넘었어요" : `1일 기준치의 ${Math.round((mg / SODIUM_DAILY_MG) * 100)}%`, percent: meterPercent(mg, SODIUM_DAILY_MG), warn: over };
}

/** 막대 목표(결정 4): 몸 정보 목표 → 식단 goal_kcal → null */
export const goalFor = (profileTarget: number | null, planGoal: number | null) => profileTarget ?? planGoal ?? null;

/** 레시피 하나에 자동 채우기를 부르는 최대 횟수(한 세션). 처음 보는 재료가 많으면 첫 채우기는 식품 찾기에 시간 예산을 다 써서
 * AI 추정을 건너뛰므로, 아직 계산 중이면 한 번 더 부른다(Ruling 18) */
export const MAX_FILL_ATTEMPTS = 2;

/** 채우기를 부를 레시피: 보이는 날짜 칸의 레시피 중 pending 목록에 있는 것(중복 없이, 이미 시도한 건 빼고, 31개까지) */
export function fillTargets(
  slots: Pick<MealSlot, "date" | "recipe_id">[],
  dates: string[],
  pending: number[],
  attempted: Set<number> = new Set(),
): number[] {
  return [
    ...new Set(
      slots
        .filter((s) => s.recipe_id !== null && dates.includes(s.date) && pending.includes(s.recipe_id) && !attempted.has(s.recipe_id))
        .map((s) => s.recipe_id!),
    ),
  ].slice(0, 31);
}

// ---- 레시피 상세 영양·식품 고르기 시트 (4b-2 Task 8) ----

export const GROUP_LABEL: Record<string, string> = { 원재료성: "원재료", 가공식품: "가공식품", 음식: "음식" };

/** 후보 한 줄 설명 "원재료 · 100g당 84kcal" */
export const candidateSub = (group: string, kcal: number) => `${GROUP_LABEL[group] ?? group}${group ? " · " : ""}100g당 ${kcalNumber(kcal)}kcal`;

/** 괄호 속 내용·공백을 지우고 소문자로(백엔드 `matching.normalize`와 같은 생각의 화면판) */
const normalizeKey = (s: string) => s.replace(/\([^)]*\)/g, "").replace(/\s+/g, "").toLowerCase();

/** 이름을 `_`·`,`로 나눠 정규화한 조각 목록(백엔드 `foods.name_parts`와 같은 생각) */
const nameParts = (name: string) => name.split(/[_,]/).map(normalizeKey).filter(Boolean);

/** `가장 비슷`/처음 선택 판정(결정 14): 원재료성이고 검색어를 정규화한 키가 이름 조각 중 하나와 같을 때만 */
export function closestMatch(item: { name: string; group: string }, query: string): boolean {
  if (item.group !== "원재료성") return false;
  const key = normalizeKey(query);
  return key !== "" && nameParts(item.name).includes(key);
}

/** 시트 제목 "‘두부’는 어떤 식품인가요?" */
export const pickTitle = (name: string) => `‘${name}’${withJosa(name, "은", "는").slice(name.length)} 어떤 식품인가요?`;

/** 재료 줄 오른쪽: ok "198", estimated "약 45", trace "0", 나머지 "—" */
export function ingredientKcalText(row: NutritionIngredient): string {
  if (row.status === "trace") return "0";
  if (row.kcal_per_serving === null) return "—";
  return `${row.status === "estimated" ? "약 " : ""}${kcalNumber(row.kcal_per_serving)}`;
}

/** 재료 줄 작은 글자와 `고르기`/`바꾸기` 링크(시안 RECIPE NUTRITION) */
export function ingredientNote(row: NutritionIngredient): { text: string; action: "고르기" | "바꾸기" | null } {
  const label = row.food?.name ?? row.name;
  switch (row.status) {
    case "ok":
      return { text: label, action: "바꾸기" };
    case "estimated":
      return row.estimate_food
        ? { text: `${row.name} · AI로 추정했어요`, action: "바꾸기" }
        : { text: `${label} · ${row.amount} ≈ ${kcalNumber(row.grams ?? 0)}g으로 추정`, action: "바꾸기" };
    case "unmatched":
      return { text: `${row.name} · 맞는 식품을 골라주세요`, action: "고르기" };
    case "needs_weight":
      return { text: `${label} · 무게를 알려주세요`, action: "고르기" };
    case "no_estimate":
      return { text: `${row.name} · 추정할 수 없어요`, action: "고르기" };
    case "unknown_amount":
      return { text: "양을 알 수 없어 계산에서 뺐어요", action: null };
    case "trace":
      return { text: "조금이라 계산에서 뺐어요", action: null };
    default:
      return { text: "계산하는 중이에요", action: "고르기" }; // 한도·실패로 오래 남아도 직접 고를 수 있게
  }
}

/** 무게 칸 시작값: 1/2모 × 300g → "150", 모르면 "" */
export const gramsFieldValue = (row: Pick<NutritionIngredient, "quantity" | "unit_grams">) =>
  row.quantity !== null && row.unit_grams !== null ? String(Math.round(row.quantity * row.unit_grams * 10) / 10) : "";

/** 입력한 g → 한 단위 g(서버 0.1~5000). 틀리면 null */
export function unitGramsFrom(grams: string, quantity: number | null): number | null {
  const g = Number(grams.replace(",", "."));
  if (!quantity || !Number.isFinite(g) || g <= 0) return null;
  const unit = Math.round((g / quantity) * 10) / 10;
  return unit >= 0.1 && unit <= 5000 ? unit : null;
}
