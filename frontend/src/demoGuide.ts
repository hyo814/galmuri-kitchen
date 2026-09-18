// 체험 계정 첫 30초 안내(스펙 30절 C) 글자 만들기. 순수 함수라 scripts/check-demo-guide.mjs가 node로 바로 읽는다.
import type { Ingredient } from "./api";

type Dated = Pick<Ingredient, "name" | "days_left" | "status">;

/** 유통기한이 가까운(빨간 D-n, 아직 안 지난) 재료를 남은 날 적은 순으로. 같은 날이면 목록 순서 그대로 */
export function urgentItems(items: Dated[]): Dated[] {
  return items
    .filter((i) => i.status === "urgent" && i.days_left !== null && i.days_left >= 0)
    .sort((a, b) => a.days_left! - b.days_left!);
}

/** 받침에 맞는 조사를 붙인다(앞뒤 공백은 뗀다). 한글이 아니면 "(이)랑"처럼 괄호로(조사는 모두 받침 쪽 첫 글자만 괄호에 들어가는 모양). rieulRo면 ㄹ받침은 받침 없는 쪽(으로/로의 "로") */
function josa(word: string, withBatchim: string, withoutBatchim: string, rieulRo = false): string {
  const w = word.trim();
  const code = w.charCodeAt(w.length - 1) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return `${w}(${withBatchim[0]})${withoutBatchim}`; // (이)가·(이)랑·(으)로
  const batchim = code % 28;
  return w + (batchim === 0 || (rieulRo && batchim === 8) ? withoutBatchim : withBatchim);
}

/** "두부" → "두부로", "살" → "살로"(ㄹ받침), "떡국" → "떡국으로". 한글이 아니면 "(으)로" */
export const withRo = (word: string) => josa(word, "으로", "로", true);

/** 0 → "오늘까지예요", 1 → "내일까지예요", 3 → "3일 남았어요" */
export const dueText = (days: number) => (days === 0 ? "오늘까지예요" : days === 1 ? "내일까지예요" : `${days}일 남았어요`);

/** 재고 화면 안내 카드 문장을 [앞, 굵게, 뒤]로 */
export function guideText(items: Dated[]): [string, string, string] {
  const first = urgentItems(items)[0];
  if (!first) return ["갈무리부엌은 재료가 상하기 전에 알려주고, 그 재료로 만들 요리를 찾아줘요. 체험 냉장고를 채워뒀어요. 곧 먹어야 할 재료로 뭘 만들 수 있을지 같이 볼까요?", "", ""];
  return ["갈무리부엌은 재료가 상하기 전에 알려주고, 그 재료로 만들 요리를 찾아줘요. 체험 냉장고를 채워뒀는데 ", `${josa(first.name, "이", "가")} ${dueText(first.days_left!)}!`, ` ${withRo(first.name)} 뭘 만들 수 있을지 같이 볼까요?`];
}

/** 레시피 추천 칸 AI 카드 말풍선. names는 급한 재료 이름(앞 두 개만 쓴다). 으로/로는 마지막 이름을 따른다 */
export function spotlightTip(names: string[]): string {
  const [a, b] = names.map((n) => n.trim());
  const what = b ? `${josa(a, "이랑", "랑")} ${withRo(b)}` : a ? withRo(a) : "곧 먹어야 할 재료로";
  return `여기를 눌러보세요. ${what} 만들 요리를 바로 골라줘요.`;
}
