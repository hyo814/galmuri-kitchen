// 체험 계정 첫 30초 안내(스펙 30절 C) 글자 만들기. 순수 함수라 scripts/check-demo-guide.mjs가 node로 바로 읽는다.
import type { Ingredient } from "./api";
import { withJosa } from "./format.ts";

type Dated = Pick<Ingredient, "name" | "days_left" | "status">;

/** 유통기한이 가까운(빨간 D-n, 아직 안 지난) 재료를 남은 날 적은 순으로. 같은 날이면 목록 순서 그대로 */
export function urgentItems(items: Dated[]): Dated[] {
  return items
    .filter((i) => i.status === "urgent" && i.days_left !== null && i.days_left >= 0)
    .sort((a, b) => a.days_left! - b.days_left!);
}

/** "두부" → "두부로", "김치찌개" → "김치찌개로", "살" → "살로"(ㄹ받침), "떡국" → "떡국으로". 한글이 아니면 "(으)로" */
export function withRo(word: string): string {
  const code = word.trim().charCodeAt(word.trim().length - 1) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return `${word}(으)로`;
  const batchim = code % 28;
  return word + (batchim === 0 || batchim === 8 ? "로" : "으로");
}

/** 0 → "오늘까지예요", 1 → "내일까지예요", 3 → "3일 남았어요" */
export const dueText = (days: number) => (days === 0 ? "오늘까지예요" : days === 1 ? "내일까지예요" : `${days}일 남았어요`);

/** 재고 화면 안내 카드 문장을 [앞, 굵게, 뒤]로 */
export function guideText(items: Dated[]): [string, string, string] {
  const first = urgentItems(items)[0];
  if (!first) return ["냉장고를 미리 채워뒀어요. 곧 먹어야 할 재료로 뭘 만들 수 있을지 같이 볼까요?", "", ""];
  return ["냉장고를 미리 채워뒀어요. 그런데 ", `${withJosa(first.name, "이", "가")} ${dueText(first.days_left!)}!`, ` ${withRo(first.name)} 뭘 만들 수 있을지 같이 볼까요?`];
}

/** 레시피 추천 칸 AI 카드 말풍선. names는 급한 재료 이름(앞 두 개만 쓴다), limit은 하루 AI 레시피 횟수 */
export function spotlightTip(names: string[], limit: number): string {
  const [a, b] = names;
  const what = b ? `${withJosa(a, "이랑", "랑")} ${b}부터` : a ? `${a}부터` : "곧 먹어야 할 재료부터";
  return `여기를 눌러보세요. ${what} 쓰는 요리 3가지를 바로 만들어줘요. 체험은 하루 ${limit}번까지 돼요.`;
}
