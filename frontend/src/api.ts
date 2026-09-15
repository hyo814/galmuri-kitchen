import type { StoreId } from "./storeLinks";

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
  /** 로그인한 방법(더보기 계정 묶음 표시용). demo는 로그인 없이 체험하기로 만든 하루짜리 계정 */
  provider: "kakao" | "naver" | "google" | "dev" | "demo";
  scan: ScanMode;
  scan_limit: number;
  recipe_limit: number;
  /** on: 요리 채널 영상 / sample: 키 없는 개발 모드의 예시 영상 / off: 영상 칸 숨김 */
  videos: ScanMode;
  /** on: 식품영양성분 DB / sample: 키 없는 개발 모드 예시 식품 / off: 영양 칸 숨김 */
  nutrition: ScanMode;
  /** 제휴 링크를 쓸 수 있는 쇼핑몰만 true(쿠팡은 서버에 파트너스 키가 있을 때). 링크는 storeLinks.ts에서 만든다 */
  shop_affiliates: Partial<Record<StoreId, boolean>>;
}

/** 재료를 지우는 이유(선택): 다 먹었어요 / 버렸어요 */
export type DeleteReason = "eaten" | "discarded";

export type ScanKind = "fridge" | "receipt" | "order" | "memo";

export interface ScanItem {
  name: string;
  quantity: number;
  unit: string;
  location_kind: LocationKind;
  price: number | null;
  /** 생활용품(memo 스캔만) — 장보기에는 담고 재고에는 넣지 않는다 */
  household?: boolean;
}

export interface ScanResult {
  items: ScanItem[];
  purchased_on: string | null;
  sample: boolean;
}

export interface AuthOptions {
  providers: string[];
  dev_login: boolean;
  /** 로그인 화면의 '로그인 없이 체험하기' */
  demo_login: boolean;
}

export interface IngredientInput {
  name: string;
  quantity: number;
  unit: string;
  /** 구입일 모름(기억 안 나요)이면 null */
  purchased_on: string | null;
  expires_on: string | null;
  price?: number | null;
  location_id: number;
}

export interface Ingredient extends IngredientInput {
  id: number;
  status: Status;
  days_left: number | null;
  days_since_purchase: number | null;
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

export type RecipeSource = "mine" | "public" | "ai" | "youtube" | "instagram" | "blog" | "text" | "photo";

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
  source: "youtube" | "instagram" | "blog" | "text" | "photo";
  source_url: string | null;
  source_card?: SourceCard | null;
  sample?: boolean;
}

export interface AiUsage {
  scan: { used: number; limit: number };
  recipe: { used: number; limit: number };
}

/** GET /api/export/summary: 내보낼 항목 수와 오늘 남은 횟수 */
export interface ExportSummary {
  ingredients: number;
  recipes: number;
  seasonings: number;
  shopping: number;
  memos: number;
  meals: number;
  limit: number;
  remaining: number;
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

export type ShoppingSource = "manual" | "recipe" | "staple" | "urgent" | "meal_plan" | "memo";

/** 장보기 항목(스펙 16절). 날짜는 YYYY-MM-DD, 시각은 ISO */
export interface ShoppingItem {
  id: number;
  client_id: string | null;
  name: string;
  quantity: number;
  unit: string;
  planned_on: string | null;
  location_id: number | null;
  location_name: string | null;
  source: ShoppingSource;
  source_label: string | null;
  /** 생활용품(휴지·세제 등). 재고에 넣기에서 기본으로 산 것으로만 옮긴다 */
  household: boolean;
  done_at: string | null;
  done_changed_at: string | null;
  stocked_at: string | null;
  created_at: string;
}

export interface ShoppingNotePhoto {
  id: number;
  client_id: string | null;
  url: string;
}

/** 장보기 메모(스펙 19절) */
export interface ShoppingNote {
  id: number;
  client_id: string | null;
  place: string | null;
  body: string;
  updated_at: string;
  photos: ShoppingNotePhoto[];
}

/** GET /api/shopping — 오프라인 보관용으로 한 번에 받는다. stocked: 최근 7일 산 것 */
export interface ShoppingSnapshot {
  items: ShoppingItem[];
  stocked: ShoppingItem[];
  notes: ShoppingNote[];
  today: string;
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
  /** raw: 성공하면 본문을 읽지 않고 Response를 그대로 돌려준다(파일 내려받기). 오류 처리는 같다 */
  options: { method?: string; body?: unknown; signal?: AbortSignal; raw?: boolean } = {},
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
  if (options.raw && res.ok) return res as T;
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

// ---- 식단(스펙 20절, 4b-1) ----
export type MealKind = "breakfast" | "lunch" | "dinner" | "snack";

export interface MealPlanSummary {
  id: number;
  name: string;
  start_on: string;
  end_on: string;
  days: number;
  default_servings: number;
  filled: number;
  total: number;
}

export interface Nutrients {
  kcal: number;
  carbs_g: number;
  protein_g: number;
  fat_g: number;
  sugars_g: number;
  sodium_mg: number;
}

/** 칸 1인분 영양. source ai면 kcal만(AI 초안 추정), 나머지는 null */
export interface SlotNutrition {
  kcal: number;
  carbs_g: number | null;
  protein_g: number | null;
  fat_g: number | null;
  sugars_g: number | null;
  sodium_mg: number | null;
  approx: boolean;
  source: "calc" | "ai";
}

/** 식단 한 칸. recipe_id가 있으면 재고 매칭(have_count·total_count·urgent_names), 없으면 null·[] */
export interface MealSlot {
  id: number;
  date: string;
  meal: MealKind;
  recipe_id: number | null;
  title: string;
  servings: number;
  est_kcal: number | null;
  have_count: number | null;
  total_count: number | null;
  urgent_names: string[];
  nutrition: SlotNutrition | null;
}

export interface MealPlan extends MealPlanSummary {
  goal_kcal: number | null;
  goal_note: string | null;
  slots: MealSlot[];
  nutrition_pending_recipe_ids: number[];
}

/** GET /api/recipes/choices 한 줄: 칸 채우기 시트의 내 레시피(재고 일치) */
export interface RecipeChoice {
  id: number;
  title: string;
  servings: number;
  have_count: number;
  total_count: number;
  urgent_names: string[];
}

/** GET /api/meal-plans/<id>/shopping-preview 한 줄(오늘 이후 끼니만). quantity·unit은 담을 양(skip 줄도 값이 있다) */
export interface MealShoppingRow { name: string; quantity: number; unit: string; planned_on: string; need: { quantity: number; unit: string }[]; need_extra: string[]; have: { quantity: number; unit: string }[]; reason: "listed" | "enough" | null }
export interface MealShoppingPreview { /** 식단 이름(담기 source_label) */ name: string; start_on: string; end_on: string; recipe_slot_count: number; buy: MealShoppingRow[]; manual: MealShoppingRow[]; skip: MealShoppingRow[] }

/** GET /api/meal-plans. default_servings: 마지막으로 만든 식단의 기본 인분(없으면 1) */
export interface MealPlanList {
  items: MealPlanSummary[];
  default_servings: number;
}

/** POST /api/meal-plans/<id>/ai-draft 의 요리 한 개. recipe_id가 있으면 내 레시피, 없으면 새 요리(넣을 때 내 레시피로 저장) */
export interface MealDraftDish {
  recipe_id: number | null;
  title: string;
  servings: number;
  est_kcal: number | null;
  ingredients: RecipeIngredient[];
  steps: string[];
  urgent_names: string[];
  image_url: string | null;
}

/** AI 식단 초안: 칸마다 options(dishes 번호, 첫 번째가 추천·나머지는 `다른 걸로` 후보), kept는 이미 채워 그대로 둘 칸 */
export interface MealDraft {
  dishes: MealDraftDish[];
  slots: { date: string; meal: MealKind; options: number[] }[];
  kept: { date: string; meal: MealKind; title: string }[];
  sample: boolean;
}

// ---- 하루 칼로리 목표(스펙 21절, 4b-2) ----
export type Sex = "female" | "male";
export type Activity = "sedentary" | "light" | "moderate" | "active" | "very_active";
export type BodyGoal = "maintain" | "lose" | "gain";

/** GET/PUT /api/body-profile. 건강 정보라 본인만 조회(Cache-Control: no-store) */
export interface BodyProfile {
  sex: Sex;
  birth_year: number;
  height_cm: number;
  weight_kg: number;
  activity: Activity;
  goal: BodyGoal;
  updated_at: string;
}

export interface BodyProfileResponse {
  profile: BodyProfile | null;
}

// ---- 레시피 1인분 영양·식품 고르기(스펙 21절, 4b-2 Task 3·8) ----
export type NutritionStatus = "ok" | "estimated" | "trace" | "unmatched" | "needs_weight" | "no_estimate" | "unknown_amount" | "pending";

export interface NutritionIngredient {
  name: string;
  amount: string;
  key: string;
  status: NutritionStatus;
  pending_reason: "search" | "weight" | "food" | null;
  countable: boolean;
  quantity: number | null;
  unit: string | null;
  grams: number | null;
  unit_grams: number | null;
  unit_grams_source: "user" | "ai" | "sample" | null;
  food: { food_code: string; name: string; group: string; kcal: number } | null;
  estimate_food: boolean;
  kcal_per_serving: number | null;
}

export interface RecipeNutrition {
  servings: number;
  per_serving: Nutrients | null;
  approx: boolean;
  estimated_count: number;
  missing_count: number;
  pending: boolean;
  usable: boolean;
  ingredients: NutritionIngredient[];
}

export interface FoodSearchItem {
  food_code: string;
  name: string;
  group: string;
  kcal: number;
}

export interface FoodSearchResult {
  items: FoodSearchItem[];
  searched: boolean;
}
