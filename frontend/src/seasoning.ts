// 양념 비율 계산 — 단위 환산·배율·숟가락 표시·기준 문구 (스펙 22절, 시안 SeasoningCalc)
// Node 한 줄 검사에서 바로 읽히도록 값 import는 .ts 확장자를 붙인다.
import { SNAPS, formatAmountNumber } from "./format.ts";

export type SeasoningUnit = "큰술" | "작은술" | "컵" | "ml" | "g" | "개" | "꼬집";
export type Basis = "main_weight" | "servings" | "yield";
export type BasisUnit = "g" | "인분" | "컵" | "ml";
export interface SeasoningItem { name: string; amount: number; unit: SeasoningUnit }
export interface Seasoning {
  id: number; name: string; basis: Basis; basis_amount: number; basis_unit: BasisUnit;
  main_ingredient: string | null; items: SeasoningItem[];
  source: "default" | "user"; source_note: string | null;
}

/** 계량 기준(스펙 22절): 1큰술 15ml, 1작은술 5ml, 1컵 200ml */
export const SPOON_ML = { 큰술: 15, 작은술: 5, 컵: 200, ml: 1 } as const;
// 밥숟가락 1개 용량. 출처 미확인, 시안 기준(3큰술 → 약 4개, 1큰술 → 약 1개). 화면에서도 "대략"이라고 안내한다.
export const RICE_SPOON_ML = 12;
export const BASIS_UNITS: Record<Basis, BasisUnit[]> = { main_weight: ["g"], servings: ["인분"], yield: ["컵", "ml"] };

const isVolume = (unit: BasisUnit): unit is "컵" | "ml" => unit === "컵" || unit === "ml";
const toMl = (amount: number, unit: BasisUnit) => (isVolume(unit) ? amount * SPOON_ML[unit] : amount);

/** 입력량 ÷ 기준량. yield의 컵↔ml는 SPOON_ML로 맞춘다. 0 이하·NaN이면 null */
export function scaleFactor(s: Pick<Seasoning, "basis_amount" | "basis_unit">, input: number, inputUnit: BasisUnit): number | null {
  const sameKind = inputUnit === s.basis_unit || (isVolume(inputUnit) && isVolume(s.basis_unit));
  const factor = toMl(input, inputUnit) / toMl(s.basis_amount, s.basis_unit);
  return sameKind && input > 0 && s.basis_amount > 0 && Number.isFinite(factor) ? factor : null;
}

/** 0.33 → "⅓", 3.5 → "3½", 0.9 → "1", 12.4 → "12". 가장 가까운 ¼·⅓·½·⅔·¾ 또는 정수(10 이상은 정수) */
export function snapSpoon(value: number): string {
  if (value >= 10) return String(Math.round(value));
  const whole = Math.floor(value);
  const [fraction, symbol] = SNAPS.reduce((best, snap) =>
    Math.abs(value - whole - snap[0]) < Math.abs(value - whole - best[0]) ? snap : best);
  return symbol ? `${whole || ""}${symbol}` : String(whole + fraction);
}

/** 한 양념 줄 × 배율 → 시안 SeasoningCalc의 굵은 양(text)과 회색 보조 줄(sub) */
export function scaleItem(item: SeasoningItem, factor: number): { text: string; sub: string | null } {
  const scaled = item.amount * factor;
  if (item.unit === "ml") return { text: `${scaled >= 10 ? Math.round(scaled) : Number(scaled.toFixed(1))}ml`, sub: null };
  if (item.unit === "g" || item.unit === "개") return { text: formatAmountNumber(scaled) + item.unit, sub: null };
  if (item.unit === "꼬집") return { text: `${Math.max(1, Math.round(scaled))}꼬집`, sub: null };
  // 부피는 ml로 바꾼 뒤 ml만 보고 단위를 다시 고른다. toFixed로 ⅔×15×1.5 = 14.999… 같은 오차를 없앤다.
  // ponytail: 반올림 오차(110ml → ½컵)는 화면 안내 "입맛에 맞게 조절해주세요"로 둔다. 불만이 나오면 "½컵 + ⅔큰술" 같은 나머지 표시 추가.
  const ml = Number((scaled * SPOON_ML[item.unit]).toFixed(6));
  if (ml >= 100) return { text: `${snapSpoon(ml / 200)}컵`, sub: null };
  if (ml >= 15) return { text: `${snapSpoon(ml / 15)}큰술`, sub: `밥숟가락 약 ${Math.max(1, Math.round(ml / RICE_SPOON_ML))}개` };
  if (ml >= 1.25) return { text: `${snapSpoon(ml / 5)}작은술`, sub: ml >= 3.75 ? `${snapSpoon(ml / 15)}큰술` : null };
  return { text: "약간", sub: null };
}

/** 시안 SeasoningList·SeasoningCalc 보조 줄: "돼지고기 600g 기준", "2인분 기준", "완성 ½컵 기준", "완성 300ml 기준" */
export function basisLabel(s: Pick<Seasoning, "basis" | "basis_amount" | "basis_unit" | "main_ingredient">): string {
  const prefix = s.basis === "yield" ? "완성 " : s.basis === "main_weight" && s.main_ingredient ? `${s.main_ingredient} ` : "";
  return `${prefix}${formatAmountNumber(s.basis_amount)}${s.basis_unit} 기준`;
}

/** 계산 화면 배지: 1.5 → "×1.5", 1 → "×1", 1/3 → "×0.33" */
export const ratioLabel = (factor: number) => `×${Number(factor.toFixed(2))}`;

/** 폼 양 입력: "½"·"1½"·"1/2"·"1 1/2"·"0.5"·"3" → 숫자, 비었거나 0 이하·틀린 모양·"1/0" → null */
export function parseAmountInput(text: string): number | null {
  const match = text.trim().match(/^(?:(\d+(?:\.\d+)?)|(\d+)?\s*([¼⅓½⅔¾])|(?:(\d+)\s+)?(\d+)\/(\d+))$/);
  if (!match) return null;
  const [, decimal, symbolWhole, symbol, mixedWhole, num, denom] = match;
  const value = decimal !== undefined ? Number(decimal)
    : symbol !== undefined ? Number(symbolWhole ?? 0) + SNAPS.find(([, s]) => s === symbol)![0]
    : Number(mixedWhole ?? 0) + Number(num) / Number(denom);
  return value > 0 && Number.isFinite(value) ? value : null;
}
