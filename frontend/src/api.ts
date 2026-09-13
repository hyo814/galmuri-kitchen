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

export interface User {
  id: number;
  nickname: string;
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
  ) {
    super(message);
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** 401 응답을 한 곳에서 처리하기 위한 핸들러 등록 (스펙 §8) */
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const hasBody = options.body !== undefined;
  let res;
  try {
    res = await fetch(path, {
      method: options.method ?? "GET",
      headers: { "X-Requested-With": "fetch", ...(hasBody ? { "Content-Type": "application/json" } : {}) },
      body: hasBody ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "네트워크에 연결할 수 없어요. 연결을 확인해 주세요.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) unauthorizedHandler?.();
    throw new ApiError(res.status, data.error ?? "문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
  }
  return data as T;
}

/** 기기 로컬 날짜 YYYY-MM-DD (toISOString은 UTC라 새벽에 하루 밀림) */
export const localToday = () => new Date().toLocaleDateString("sv-SE");
