export type Status = "danger" | "urgent" | "old" | "ok";

export type LocationKind = "fridge" | "freezer" | "room";

export interface StorageLocation {
  id: number;
  name: string;
  kind: LocationKind;
  item_count: number;
}

export interface Staple {
  id: number;
  name: string;
  category: string;
  in_stock: boolean;
  matched_name: string | null;
}

export interface ItemRule {
  id: number;
  keyword: string;
  warn_days: number;
  danger_days: number;
  source: "mfds" | "user";
}

export type ToolCategory = "조리도구" | "조리기구" | "칼·도마" | "기타";

export interface KitchenToolInput {
  name: string;
  category: ToolCategory;
  bought_on: string | null;
  check_every_months: number | null;
}

export interface KitchenTool extends KitchenToolInput {
  id: number;
  last_checked_on: string | null;
  due_on: string | null;
  is_due: boolean;
  days_until_due: number | null;
}

/** on: AI 인식 / sample: API 키 없는 개발 모드의 예시 결과 / off: 사진으로 추가 숨김 */
export type ScanMode = "on" | "sample" | "off";

export interface User {
  id: number;
  nickname: string;
  scan: ScanMode;
  scan_limit: number;
}

export type ScanKind = "fridge" | "receipt" | "order";

export interface ScanItem {
  name: string;
  quantity: number;
  unit: string;
  location_kind: LocationKind;
}

export interface ScanResult {
  items: ScanItem[];
  purchased_on: string | null;
  sample: boolean;
}

export interface AuthOptions {
  providers: string[];
  dev_login: boolean;
}

export interface IngredientInput {
  name: string;
  quantity: number;
  unit: string;
  purchased_on: string;
  expires_on: string | null;
  location_id: number;
}

export interface Ingredient extends IngredientInput {
  id: number;
  status: Status;
  days_left: number | null;
  days_since_purchase: number;
  location_name: string;
  location_kind: LocationKind;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public errors?: { index: number; error: string }[],
  ) {
    super(message);
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** 401 응답을 한 곳에서 처리하기 위한 핸들러 등록 (스펙 §8) */
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const { body } = options;
  // FormData(사진 업로드)는 브라우저가 multipart 경계를 넣은 Content-Type을 직접 붙인다
  const json = body !== undefined && !(body instanceof FormData);
  let res;
  try {
    res = await fetch(path, {
      method: options.method ?? "GET",
      headers: { "X-Requested-With": "fetch", ...(json ? { "Content-Type": "application/json" } : {}) },
      body: body instanceof FormData ? body : json ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
      signal: options.signal,
    });
  } catch (e) {
    if (options.signal?.aborted) throw e; // 사용자가 취소한 요청은 호출한 쪽이 처리한다
    throw new ApiError(0, "네트워크에 연결할 수 없어요. 연결을 확인해주세요.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) unauthorizedHandler?.();
    throw new ApiError(
      res.status,
      data.error ?? "문제가 생겼어요. 잠시 후 다시 시도해주세요.",
      Array.isArray(data.errors) ? data.errors : undefined,
    );
  }
  return data as T;
}

/** 오늘 날짜 YYYY-MM-DD, 서울 기준(서버도 서울 기준으로 계산하므로 기기 시간대와 상관없이 맞춘다) */
export const localToday = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
