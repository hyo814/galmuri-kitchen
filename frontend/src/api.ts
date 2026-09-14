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
  recipe_limit: number;
  /** on: 요리 채널 영상 / sample: 키 없는 개발 모드의 예시 영상 / off: 영상 칸 숨김 */
  videos: ScanMode;
}

export type ScanKind = "fridge" | "receipt" | "order";

export interface ScanItem {
  name: string;
  quantity: number;
  unit: string;
  location_kind: LocationKind;
  price: number | null;
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
  price?: number | null;
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

export interface RecipeIngredient {
  name: string;
  amount: string;
}

/** 상세 화면의 재료: 지금 재고와 매칭한 결과(matched_name은 재고 이름, 물처럼 늘 있는 재료는 null) */
export interface RecipeIngredientStatus extends RecipeIngredient {
  have: boolean;
  matched_name: string | null;
}

export interface RecipeInput {
  title: string;
  servings: number;
  ingredients: RecipeIngredient[];
  steps: string[];
}

export type RecipeSource = "mine" | "public" | "ai" | "youtube" | "instagram" | "blog" | "text";

/** POST /api/recommendations/ai 의 레시피 한 개(저장 전). image_url은 이름이 비슷한 공공 레시피 사진 */
export interface AiRecipe {
  title: string;
  servings: number;
  minutes: number | null;
  ingredients: RecipeIngredientStatus[];
  steps: string[];
  urgent_names: string[];
  image_url: string | null;
}

export interface AiSuggestions {
  recipes: AiRecipe[];
  urgent_first: string[];
  sample: boolean;
}

/** 가져온 링크의 제목·채널(사이트) 이름·썸네일. 썸네일은 외부 주소라 화면에만 보이고 저장하지 않는다 */
export interface SourceCard {
  title: string;
  author: string | null;
  thumbnail_url: string | null;
}

/** POST /api/recipes/import 결과(저장 전 초안) */
export interface RecipeDraft extends RecipeInput {
  source: "youtube" | "instagram" | "blog" | "text";
  source_url: string | null;
  source_card?: SourceCard | null;
  sample?: boolean;
}

export interface AiUsage {
  scan: { used: number; limit: number };
  recipe: { used: number; limit: number };
}

export interface RecipeSummary {
  id: number;
  title: string;
  servings: number;
  source: RecipeSource;
  image_url: string | null;
  ingredient_count: number;
  updated_at: string;
}

interface RecipeDetailBase {
  id: number;
  title: string;
  servings: number;
  category: string | null;
  ingredients: RecipeIngredientStatus[];
  steps: string[];
  image_url: string | null;
}

export interface MyRecipe extends RecipeDetailBase {
  kind: "mine";
  source: RecipeSource;
  source_url: string | null;
  public_recipe_id: number | null;
}

export interface PublicRecipeDetail extends RecipeDetailBase {
  kind: "public";
  method: string | null;
  kcal: number | null;
  is_sample: boolean;
}

export type RecipeDetail = MyRecipe | PublicRecipeDetail;

export interface RecommendationCard {
  kind: "mine" | "public";
  id: number;
  title: string;
  image_url: string | null;
  servings: number;
  match_rate: number;
  have_count: number;
  total_count: number;
  missing: string[];
  urgent_used: number;
  urgent_names: string[];
  score: number;
}

/**
 * GET /api/recommendations 응답(addendum: 페이지가 있다).
 * section=all(기본, 첫 페이지)만 mine·mine_total을 준다. section=public 페이지는 public·public_total·next_offset만 온다.
 */
export interface Recommendations {
  mine?: RecommendationCard[];
  mine_total?: number;
  public: RecommendationCard[];
  public_total: number;
  public_count: number; // 재고와 안 겹쳐도 세는 전체 공공 레시피 수(M11: 카탈로그가 아예 비었는지 구분용)
  next_offset: number | null;
  sample: boolean;
  inventory_count: number;
}

/** GET /api/videos 목록 한 줄. 썸네일은 유튜브 주소(예시 모드는 null) */
export interface Video {
  id: number;
  video_id: string;
  title: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  published_at: string;
  channel_id: number;
  channel_title: string;
}

export interface VideoDetail extends Video {
  description: string | null;
  channel_thumbnail_url: string | null;
}

export interface VideoPage {
  items: Video[];
  next_cursor: string | null;
  sample: boolean;
}

/** 요리 채널. is_default면 기본 채널(숨기기만), 아니면 내 채널(빼기). unavailable: 삭제·비공개된 채널 */
export interface Channel {
  id: number;
  title: string;
  thumbnail_url: string | null;
  video_count: number | null;
  is_default: boolean;
  hidden: boolean;
  unavailable: boolean;
}

export interface ChannelList {
  items: Channel[];
  mine_count: number;
  mine_limit: number;
  sample: boolean;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public errors?: { index: number; error: string }[],
    /** 오류 JSON 본문 전체(예: 422 need_text) */
    public body?: Record<string, unknown>,
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
      data,
    );
  }
  return data as T;
}

/** 오늘 날짜 YYYY-MM-DD, 서울 기준(서버도 서울 기준으로 계산하므로 기기 시간대와 상관없이 맞춘다) */
export const localToday = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
