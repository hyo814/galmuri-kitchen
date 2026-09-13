import type { LocationKind } from "./api";

/** 1 → "1", 0.25 → "0.25", 1.5 → "1.5" (소수 둘째 자리까지) */
export const formatQuantity = (q: number) => String(Number(q.toFixed(2)));

/** 3480 → "3,480원" */
export const formatWon = (price: number) => `${price.toLocaleString("ko-KR")}원`;

/** "2026-09-10" → "9월 10일" (올해가 아니면 "2025년 9월 10일") */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const md = `${m}월 ${d}일`;
  return y === new Date().getFullYear() ? md : `${y}년 ${md}`;
}

export const KIND_LABEL: Record<LocationKind, string> = { fridge: "냉장", freezer: "냉동", room: "실온" };

/** 6 → "6개월", 12 → "1년", 24 → "2년" */
export const cycleLabel = (months: number) => (months % 12 === 0 ? `${months / 12}년` : `${months}개월`);

/** 받침에 맞는 조사를 붙인다. withJosa("애호박", "을", "를") → "애호박을". 한글이 아니면 "을(를)" */
export function withJosa(word: string, withBatchim: string, withoutBatchim: string): string {
  const code = word.trim().charCodeAt(word.trim().length - 1) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return `${word}${withBatchim}(${withoutBatchim})`;
  return word + (code % 28 ? withBatchim : withoutBatchim);
}

/** "2026-09-13" + 3 → "2026-09-16" (기기 로컬 날짜 기준) */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString("sv-SE");
}

/** 식약처 사진은 http 주소로 오지만 https로도 열린다(2026-09-13 확인). https 화면에서 섞인 콘텐츠로 막히지 않게 바꾼다. */
export function imageSrc(url: string | null): string | null {
  return url ? url.replace(/^http:\/\/(www|openapi)\.foodsafetykorea\.go\.kr\//, "https://$1.foodsafetykorea.go.kr/") : null;
}

// 숟가락으로 뜰 수 있는 분수 (스펙 22절과 같은 기호)
const SNAPS: [number, string][] = [[0, ""], [1 / 4, "¼"], [1 / 3, "⅓"], [1 / 2, "½"], [2 / 3, "⅔"], [3 / 4, "¾"], [1, ""]];
const FRACTIONS = Object.fromEntries(SNAPS.filter(([, symbol]) => symbol).map(([value, symbol]) => [symbol, value]));

/** 0.5 → "½", 1.5 → "1½", 0.4 → "0.4", 112.5 → "113". 10 이상은 정수, 그 아래는 가까운 분수가 있으면 분수 */
export function formatAmountNumber(value: number): string {
  if (value >= 10) return String(Math.round(value));
  const whole = Math.floor(value);
  const snap = SNAPS.find(([fraction]) => Math.abs(value - whole - fraction) < 0.04);
  if (!snap) return String(Number(value.toFixed(1)));
  const [fraction, symbol] = snap;
  return symbol ? `${whole || ""}${symbol}` : String(whole + fraction);
}

/**
 * 인분 조절: 양의 앞 숫자만 배율로 바꾼다(화면에서만, 저장하지 않음 — 스펙 23절 D1).
 * "200g" ×2 → "400g", "1/2모(150g)" ×2 → "1모(150g)", "1½큰술" ×2 → "3큰술". "약간"·"10~15개"는 그대로
 */
export function scaleAmount(amount: string, ratio: number): string {
  const match = amount.match(/^(\d+(?:\.\d+)?)?(?:([¼⅓½⅔¾])|\/(\d+))?/);
  if (ratio === 1 || !match || (match[1] === undefined && match[2] === undefined)) return amount;
  if (match[3] !== undefined && (match[1] === undefined || Number(match[3]) === 0)) return amount;
  const rest = amount.slice(match[0].length);
  if (/^\s*[~-]\s*\d/.test(rest)) return amount; // 범위(10~15개)는 어느 숫자를 바꿀지 애매해서 그대로
  let value = Number(match[1] ?? 0) + (match[2] ? FRACTIONS[match[2]] : 0);
  if (match[3] !== undefined) value /= Number(match[3]);
  return formatAmountNumber(value * ratio) + rest;
}
