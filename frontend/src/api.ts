export type Status = "urgent" | "old" | "ok";

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
}

export interface Ingredient extends IngredientInput {
  id: number;
  status: Status;
  days_left: number | null;
  days_since_purchase: number;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const hasBody = options.body !== undefined;
  const res = await fetch(path, {
    method: options.method ?? "GET",
    headers: { "X-Requested-With": "fetch", ...(hasBody ? { "Content-Type": "application/json" } : {}) },
    body: hasBody ? JSON.stringify(options.body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error ?? "문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
  return data as T;
}

/** 기기 로컬 날짜 YYYY-MM-DD (toISOString은 UTC라 새벽에 하루 밀림) */
export const localToday = () => new Date().toLocaleDateString("sv-SE");
