// AI 식단 초안 상태(식단 화면·AI 초안 화면이 같이 쓴다 — 두 페이지가 서로를 import하지 않게 따로 둔다)
import { api, type MealDraft, type MealKind } from "../api";
import { forgetResources } from "../useResource";

export interface DraftStore {
  planId: number;
  weekStart: string;
  meals: MealKind[];
  draft: MealDraft;
  /** 칸 "날짜|끼니" → 지금 고른 요리 번호 */
  choice: Record<string, number>;
  checked: Record<string, boolean>;
}

// ponytail: 만드는 중·확인·오류는 식단별 모듈 Map(뒤로가기·탭 이동 뒤에도 그대로, 새로고침하면 사라짐).
// 만드는 중에 화면을 떠나거나 다른 식단에서 만들어도 요청은 끊지 않는다(서버가 이미 횟수를 셌다) — 그 식단의 `취소`만 끊는다. RecipeAi와 같은 방식.
export const drafts = new Map<number, DraftStore>();
export const running = new Map<number, { weekStart: string; meals: MealKind[]; ctrl: AbortController }>();
/** 입력 화면 오류. weekStart: 어느 주를 만들다 난 오류인지(다른 주로 들어오면 지운다) */
export const errors = new Map<number, { weekStart: string; message: string }>();
let generation = 0; // 로그아웃 뒤에 도착한 옛 응답을 버리는 번호
let version = 0;
const listeners = new Set<() => void>();
export const emit = () => {
  version++;
  listeners.forEach((listener) => listener());
};
export const getVersion = () => version;
export const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const keyOf = (s: { date: string; meal: MealKind }) => `${s.date}|${s.meal}`;

/** 로그아웃(resetMealsView): 모든 식단의 초안·요청을 버린다. planId를 주면(식단 지우기) 그 식단 것만 */
export function forgetMealDraft(planId?: number) {
  if (planId !== undefined) {
    running.get(planId)?.ctrl.abort();
    running.delete(planId);
    drafts.delete(planId);
    errors.delete(planId);
    return emit();
  }
  generation++;
  running.forEach(({ ctrl }) => ctrl.abort());
  running.clear();
  drafts.clear();
  errors.clear();
  emit();
}

/** 초안을 버리고 입력 화면으로. message가 있으면 입력 화면 오류 자리에 보여준다 */
export function discardDraft(planId: number, message = "") {
  const weekStart = drafts.get(planId)?.weekStart ?? "";
  drafts.delete(planId);
  if (message) errors.set(planId, { weekStart, message });
  else errors.delete(planId);
  emit();
}

/** 만들기·다시 만들기. 이전 초안은 새 초안이 올 때까지 둔다(다시 만들기를 취소하면 그대로 돌아간다) */
export function startDraft(planId: number, weekStart: string, meals: MealKind[], body: object) {
  if (running.has(planId)) return; // 만드는 중에는 버튼이 없다 — 같은 식단 요청을 두 번 보내지 않는다
  const ctrl = new AbortController();
  const id = generation;
  running.set(planId, { weekStart, meals, ctrl });
  errors.delete(planId);
  emit();
  const mine = () => id === generation && running.get(planId)?.ctrl === ctrl;
  api<MealDraft>(`/api/meal-plans/${planId}/ai-draft`, { method: "POST", body, signal: ctrl.signal }).then(
    (draft) => {
      if (!mine()) return;
      running.delete(planId);
      drafts.set(planId, {
        planId,
        weekStart,
        meals,
        draft,
        choice: Object.fromEntries(draft.slots.map((s) => [keyOf(s), s.options[0]])),
        checked: Object.fromEntries(draft.slots.map((s) => [keyOf(s), true])),
      });
      forgetResources("/api/meal-plans"); // 목표 두 칸은 서버가 식단에 저장했다
      emit();
    },
    (e: unknown) => {
      if (!mine()) return;
      running.delete(planId);
      errors.set(planId, { weekStart, message: (e as Error).message });
      forgetResources("/api/meal-plans");
      emit();
    },
  );
}

export function cancelDraft(planId: number) {
  running.get(planId)?.ctrl.abort();
  running.delete(planId);
  forgetResources("/api/meal-plans"); // 끊어도 서버가 목표 두 칸을 이미 저장했을 수 있다
  emit();
}
