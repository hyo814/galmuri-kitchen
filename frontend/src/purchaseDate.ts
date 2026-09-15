// 재고 구입일 칩(시안 docs/design/scan-multi). 오늘은 인자로 받는다 — scripts/check-purchase-date.mjs가 node로 읽는다.
import { addDays, formatDate } from "./format.ts";
import { dateWithDow } from "./meals/plan.ts";

/** 오늘 · 어제 · 3일 전 · 1주 전 · 날짜 고르기 · 기억 안 나요 */
export type DateChip = "today" | "yesterday" | "3days" | "week" | "date" | "unknown";
/** 고른 칩. date는 `날짜 고르기`로 고른 날짜(다른 칩이면 쓰지 않는다) */
export interface DatePick {
  chip: DateChip;
  date: string;
}

export const PRESET_CHIPS: [DateChip, string, number][] = [
  ["today", "오늘", 0],
  ["yesterday", "어제", 1],
  ["3days", "3일 전", 3],
  ["week", "1주 전", 7],
];

/** 칩 → 넣을 구입일(ISO). 기억 안 나요는 null */
export function pickDate(pick: DatePick, today: string): string | null {
  if (pick.chip === "unknown") return null;
  if (pick.chip === "date") return pick.date;
  const preset = PRESET_CHIPS.find(([chip]) => chip === pick.chip)!;
  return addDays(today, -preset[2]);
}

/** 영수증·주문에서 읽은 날짜 → 처음 고른 칩: 오늘·어제면 그 칩, 다른 날이면 날짜 고르기, 못 읽었으면 오늘 */
export function detectedPick(iso: string | null, today: string): DatePick {
  if (!iso || iso === today) return { chip: "today", date: "" };
  if (iso === addDays(today, -1)) return { chip: "yesterday", date: "" };
  return { chip: "date", date: iso };
}

/** 칩 아래 줄: "9월 12일 (토) 구입으로 넣어요" / "구입일 없이 넣어요" */
export const pickedText = (iso: string | null) => (iso ? `${dateWithDow(iso)} 구입으로 넣어요` : "구입일 없이 넣어요");

/** 재료마다 다른 구입일(찾은 재료 보조 줄): "오늘 구입" / "어제 구입" / "9월 3일 구입" / "구입일 모름" */
export function ownDateText(iso: string | null, today: string): string {
  if (!iso) return "구입일 모름";
  if (iso === today) return "오늘 구입";
  if (iso === addDays(today, -1)) return "어제 구입";
  return `${formatDate(iso)} 구입`;
}
