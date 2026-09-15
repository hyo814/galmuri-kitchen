import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api, type DishItem, type DishSearchResult, type FoodLog, type FoodLogDay, type FoodPlace, type MealKind, type RecipeChoice, type RecipeNutrition, type User } from "../api";
import {
  KIND_LABEL,
  MAX_SERVINGS,
  MIN_SERVINGS,
  PLACE_LABEL,
  createBody,
  dishGrams,
  dishSub,
  keptAmount,
  logKind,
  parseGrams,
  patchBody,
  previewText,
  scaleNutrition,
  servingsText,
  stepServings,
  type LogKind,
  type WhatPick,
} from "../foodlog/log.ts";
import { MEALS, mealLabel, slotDateText } from "../meals/plan.ts";
import { MAX_FILL_ATTEMPTS } from "../nutrition/day.ts";
import { useAsyncAction } from "../useAsyncAction";
import { forgetResources } from "../useResource";
import { fillAttempted } from "./FoodLogDaySheet";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  date: string;
  meal: MealKind;
  day: FoodLogDay;
  /** 있으면 고치기 */
  log?: FoodLog;
  user: User;
  onSaved: (log: FoodLog) => void;
  onDeleted: () => void;
  onClose: () => void;
}

const PLACES: FoodPlace[] = ["home", "out"];

/** 시안 3 · ADD: 먹은 것 추가·고치기. 무엇 네 갈래(식단에서·내 레시피·음식 찾기·직접) → 양 → 어디서 → 만족도 → 메모 */
export default function FoodLogSheet({ date, meal: initialMeal, day, log, user, onSaved, onDeleted, onClose }: Props) {
  const nutritionOn = user.nutrition !== "off";
  const tabs = (Object.keys(KIND_LABEL) as LogKind[]).filter((k) => k !== "food" || nutritionOn);
  const isPhotoLog = log !== undefined && log.title === null;

  const [meal, setMeal] = useState(initialMeal);
  // 고치기(사진 기록 아님)는 `바꾸기`를 누르기 전에는 무엇 칸을 보이지도 보내지도 않는다
  const [changing, setChanging] = useState(!log || isPhotoLog);
  const [tab, setTab] = useState<LogKind>(() =>
    isPhotoLog ? (nutritionOn ? "food" : "direct") : day.plan_slots.some((s) => s.meal === initialMeal) ? "plan" : "recipe",
  );
  const [slotId, setSlotId] = useState<number | null>(null);
  const [recipeId, setRecipeId] = useState<number | null>(null);
  const [dish, setDish] = useState<DishItem | null>(null);
  const [title, setTitle] = useState("");

  const [servings, setServings] = useState(log?.servings ?? 1);
  const [unit, setUnit] = useState<"servings" | "grams">(log?.grams != null ? "grams" : "servings");
  const [gramsText, setGramsText] = useState(log?.grams != null ? String(log.grams) : "100");
  const [place, setPlace] = useState<FoodPlace | null>(log?.place ?? null);
  const placeTouched = useRef(false);
  const [rating, setRating] = useState<number | null>(log?.rating ?? null);
  const [memo, setMemo] = useState(log?.memo ?? "");
  const [whatError, setWhatError] = useState(false);

  const save = useAsyncAction();
  const remove = useAsyncAction();
  const whatInput = useRef<HTMLInputElement>(null);
  const whatTabs = useRef<HTMLDivElement>(null);
  const gramsInput = useRef<HTMLInputElement>(null);
  const ids = { meal: useId(), amount: useId(), place: useId(), memo: useId(), grams: useId(), gramsErr: useId(), radio: useId() };

  // ---- 내 레시피: 300ms 뒤 찾기(빈 칸이면 바로), 앞 요청은 끊는다 ----
  const [recipeQ, setRecipeQ] = useState("");
  const [recipes, setRecipes] = useState<{ items: RecipeChoice[] } | null>(null);
  const [recipeError, setRecipeError] = useState("");
  const recipeTabOpen = changing && tab === "recipe";
  useEffect(() => {
    if (!recipeTabOpen) return;
    const q = recipeQ.trim();
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const data = await api<{ items: RecipeChoice[] }>(`/api/recipes/choices?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        setRecipes(data);
        setRecipeId((id) => (data.items.some((r) => r.id === id) ? id : null)); // 새 목록에 없으면 숨은 선택으로 저장하지 않게
        setRecipeError("");
      } catch (e) {
        if (!controller.signal.aborted) setRecipeError((e as Error).message);
      }
    }, q ? 300 : 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [recipeQ, recipeTabOpen]);

  // 고른 레시피 1인분 영양(미리보기). 계산 중이면 날짜 상세와 같은 시도 횟수 Map으로 채우기를 부른 뒤 다시 받는다(개정 1 S10, Ruling 18)
  const [recipeNutrition, setRecipeNutrition] = useState<{ id: number; data: RecipeNutrition } | null>(null);
  useEffect(() => {
    if (recipeId === null || !nutritionOn) return;
    let alive = true;
    const url = `/api/recipes/${recipeId}/nutrition`;
    (async () => {
      try {
        let data = await api<RecipeNutrition>(url);
        while (alive && data.pending && (fillAttempted.get(recipeId) ?? 0) < MAX_FILL_ATTEMPTS) {
          setRecipeNutrition({ id: recipeId, data });
          fillAttempted.set(recipeId, (fillAttempted.get(recipeId) ?? 0) + 1); // 요청 전에 센다
          await api("/api/nutrition/fill", { method: "POST", body: { recipe_ids: [recipeId] } }).catch(() => {});
          data = await api<RecipeNutrition>(url);
        }
        if (alive) setRecipeNutrition({ id: recipeId, data });
      } catch {
        // 미리보기만 비워 둔다 — 저장은 서버가 계산한다
      }
    })();
    return () => {
      alive = false;
    };
  }, [recipeId, nutritionOn]);

  // ---- 음식 찾기: 2글자 이상이면 입력이 멈추고 600ms 뒤, Enter는 바로(개정 1 P2 — 검색마다 식품 DB 요청이 나간다) ----
  const [dishQ, setDishQ] = useState("");
  const [dishes, setDishes] = useState<(DishSearchResult & { q: string }) | null>(null);
  const [dishLoading, setDishLoading] = useState(false);
  const [dishError, setDishError] = useState("");
  const dishTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const dishAbort = useRef<AbortController | null>(null);
  const stopDishSearch = () => {
    clearTimeout(dishTimer.current);
    dishAbort.current?.abort();
    setDishLoading(false);
  };
  useEffect(() => stopDishSearch, []);

  async function searchDishes(text: string) {
    stopDishSearch();
    const q = text.trim();
    if (!q) return;
    const controller = new AbortController();
    dishAbort.current = controller;
    setDishLoading(true);
    setDishError("");
    try {
      const data = await api<DishSearchResult>(`/api/foods/dishes?q=${encodeURIComponent(q)}`, { signal: controller.signal });
      setDishes({ ...data, q });
    } catch (e) {
      if (!controller.signal.aborted) setDishError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setDishLoading(false);
    }
  }

  function changeDishQ(text: string) {
    setDishQ(text);
    setDishes(null);
    setDish(null); // 목록이 바뀌면 숨은 선택으로 저장하지 않게
    setDishError("");
    stopDishSearch();
    if (text.trim().length >= 2) {
      setDishLoading(true);
      dishTimer.current = setTimeout(() => void searchDishes(text), 600);
    }
  }

  // ---- 고른 것·양 ----
  const autoPlace = (value: FoodPlace) => {
    if (!placeTouched.current) setPlace(value);
  };

  const what: WhatPick | null = !changing
    ? null
    : tab === "plan"
      ? slotId === null ? null : { kind: "plan", slotId }
      : tab === "recipe"
        ? recipeId === null ? null : { kind: "recipe", recipeId }
        : tab === "food"
          ? dish === null ? null : { kind: "food", foodCode: dish.food_code }
          : title.trim() ? { kind: "direct", title } : null;

  // 사진 기록·`바꾸기` 중인 고치기는 무엇을 고르기 전에는 양 칸이 없다
  const showAmount = !log || !changing || what !== null;
  const pickedDish = changing && tab === "food" ? dish : null;
  const isFood = pickedDish !== null || (!changing && log?.food_code != null);
  const effectiveUnit = !isFood ? "servings" : pickedDish?.serving_g === null ? "grams" : unit;
  const grams = effectiveUnit === "grams" ? parseGrams(gramsText) : null;
  const gramsInvalid = effectiveUnit === "grams" && grams === null && showAmount;
  // 양 칸이 숨었으면 원래 양 그대로(patchBody가 바뀌지 않았다고 본다)
  const amount = !showAmount && log ? keptAmount(log)
    : effectiveUnit === "grams" ? { grams: grams ?? 0 } : { servings };
  // 인분·g을 고를 수 있나: 고른 음식에 1인분 무게가 있거나, 인분으로 남긴 음식 기록(서버가 무게 있는 음식만 인분을 받는다)
  const canToggleUnit = pickedDish ? pickedDish.serving_g !== null : !changing && log?.food_code != null && log.servings !== null;

  let preview = "";
  if (pickedDish) {
    const g = dishGrams(pickedDish, amount);
    preview = g ? previewText(scaleNutrition(pickedDish, g / 100), true) : "";
  } else if (changing && tab === "recipe" && recipeNutrition?.id === recipeId && recipeNutrition.data.per_serving) {
    const r = recipeNutrition.data;
    preview = previewText(scaleNutrition(r.per_serving!, servings), r.approx || !r.usable);
  }
  // 식단에서·직접은 비운다 — 식단 칸 저장값은 칸 AI 추정이 먼저일 수 있어 레시피 값과 다를 수 있다(개정 1 P10)

  const needWhat = !log && what === null;
  const planSlots = [...day.plan_slots].sort((a, b) => Number(a.meal !== initialMeal) - Number(b.meal !== initialMeal));

  function submit() {
    if (needWhat) {
      setWhatError(true);
      // 입력 칸이 없으면(식단 칸이 없는 식단에서) 지금 고른 갈래 버튼으로
      (whatInput.current ?? whatTabs.current?.querySelector<HTMLElement>('[aria-pressed="true"]'))?.focus();
      return;
    }
    if (gramsInvalid) {
      gramsInput.current?.focus();
      return;
    }
    const form = { meal, what, amount, place, rating, memo };
    void save.run(async () => {
      let saved: FoodLog;
      if (log) {
        const body = patchBody(log, form);
        if (!Object.keys(body).length) return onClose();
        saved = await api<FoodLog>(`/api/food-logs/${log.id}`, { method: "PATCH", body });
      } else {
        saved = await api<FoodLog>("/api/food-logs", { method: "POST", body: createBody(date, { ...form, what: what! }) });
      }
      forgetResources("/api/food-logs");
      if (what?.kind === "plan" || log?.meal_slot_id != null) forgetResources("/api/meal-plans");
      onSaved(saved);
    });
  }

  function deleteLog() {
    if (!log || !confirm("이 기록을 지울까요? 사진도 함께 지워져요.")) return;
    void remove.run(async () => {
      await api(`/api/food-logs/${log.id}`, { method: "DELETE" });
      forgetResources("/api/food-logs");
      if (log.meal_slot_id !== null) forgetResources("/api/meal-plans");
      onDeleted();
    });
  }

  // 별 라디오: 화살표로 점수를 옮기고 켠다(roving tabindex)
  function starKey(e: KeyboardEvent<HTMLButtonElement>) {
    const delta = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = Math.min(5, Math.max(1, (rating ?? 0) + delta));
    setRating(next);
    (e.currentTarget.parentElement!.children[next - 1] as HTMLElement).focus();
  }

  const busy = save.busy || remove.busy;
  const error = save.error || remove.error;
  const q = dishQ.trim();

  return (
    <Sheet title={`${mealLabel(meal)} · 먹은 것 ${log ? "고치기" : "추가"}`} description={slotDateText(date, "")} className="fl-add" focusTitle onClose={onClose}>
      {log && (
        <div className="field" role="group" aria-labelledby={ids.meal}>
          <span className="field-label" id={ids.meal}>
            끼니
          </span>
          <div className="chips">
            {MEALS.map(([key, label]) => (
              <button key={key} type="button" className="chip" aria-pressed={meal === key} onClick={() => setMeal(key)}>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!changing && log ? (
        <div className="fl-picked">
          <span>
            <b>{log.title}</b> <span className="muted">{KIND_LABEL[logKind(log)]}</span>
          </span>
          <button
            type="button"
            className="nt-link"
            onClick={() => {
              const kind = logKind(log);
              setTab(kind === "food" && !nutritionOn ? "direct" : kind);
              if (kind === "direct") setTitle(log.title ?? "");
              setChanging(true);
            }}
          >
            바꾸기
          </button>
        </div>
      ) : (
        <>
          <div ref={whatTabs} className="segmented fl-what" role="group" aria-label="무엇을 먹었나요">
            {tabs.map((k) => (
              <button key={k} type="button" aria-pressed={tab === k} onClick={() => setTab(k)}>
                {k === "food" ? "음식 찾기" : KIND_LABEL[k]}
              </button>
            ))}
          </div>

          {tab === "plan" &&
            (planSlots.length ? (
              <div className="fl-cands" role="radiogroup" aria-label="식단 칸">
                {planSlots.map((s, i) => (
                  <label key={s.id} className={s.id === slotId ? "nt-cand on" : "nt-cand"}>
                    <input
                      ref={i === 0 ? whatInput : undefined}
                      className="sr-only"
                      type="radio"
                      name={ids.radio}
                      checked={s.id === slotId}
                      onChange={() => {
                        setSlotId(s.id);
                        autoPlace("home");
                      }}
                    />
                    <span className="nt-radio" aria-hidden="true" />
                    <span>
                      <b>{s.title}</b>
                      <small>
                        {mealLabel(s.meal)} · {s.servings}인분
                      </small>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="muted">이 날 식단에 채운 칸이 없어요</p>
            ))}

          {tab === "recipe" && (
            <>
              <input
                ref={whatInput}
                className="input"
                type="search"
                placeholder="내 레시피 찾기"
                aria-label="내 레시피 찾기"
                maxLength={50}
                enterKeyHint="search"
                value={recipeQ}
                onChange={(e) => setRecipeQ(e.target.value)}
              />
              {recipeError ? (
                <p className="error" role="alert">
                  {recipeError}
                </p>
              ) : !recipes ? (
                <p className="muted" role="status">찾는 중…</p>
              ) : recipes.items.length ? (
                <div className="fl-cands" role="radiogroup" aria-label="내 레시피">
                  {recipes.items.map((r) => (
                    <label key={r.id} className={r.id === recipeId ? "nt-cand on" : "nt-cand"}>
                      <input
                        className="sr-only"
                        type="radio"
                        name={ids.radio}
                        checked={r.id === recipeId}
                        onChange={() => {
                          setRecipeId(r.id);
                          autoPlace("home");
                        }}
                      />
                      <span className="nt-radio" aria-hidden="true" />
                      <span>
                        <b>{r.title}</b>
                        <small>{r.servings}인분 기준</small>
                      </span>
                    </label>
                  ))}
                </div>
              ) : (
                <p className="muted" role="status">찾는 레시피가 없어요</p>
              )}
            </>
          )}

          {tab === "food" && (
            <>
              <div className="input-suffix nt-food-search">
                <input
                  ref={whatInput}
                  className="input"
                  type="search"
                  placeholder="먹은 음식 이름"
                  aria-label="먹은 음식 이름"
                  maxLength={30}
                  enterKeyHint="search"
                  value={dishQ}
                  onChange={(e) => changeDishQ(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
                    e.preventDefault();
                    void searchDishes(dishQ);
                  }}
                />
                <span className="suffix" aria-hidden="true">
                  <Icon name="search" size={18} />
                </span>
              </div>
              {q !== "" &&
                (dishLoading ? (
                  <p className="muted" role="status">찾는 중…</p>
                ) : dishError ? (
                  <p className="error" role="alert">
                    {dishError}
                  </p>
                ) : !dishes ? (
                  q.length < 2 && <p className="muted" role="status">두 글자 이상 입력하거나 Enter를 눌러주세요</p>
                ) : dishes.items.length ? (
                  <div className="fl-cands" role="radiogroup" aria-label="음식">
                    {dishes.items.map((item) => (
                      <label key={item.food_code} className={item.food_code === dish?.food_code ? "nt-cand on" : "nt-cand"}>
                        <input
                          className="sr-only"
                          type="radio"
                          name={ids.radio}
                          checked={item.food_code === dish?.food_code}
                          onChange={() => {
                            setDish(item);
                            setGramsText(String(dishGrams(item, { servings }) ?? 100));
                            autoPlace("out");
                          }}
                        />
                        <span className="nt-radio" aria-hidden="true" />
                        <span>
                          <b>{item.name}</b>
                          <small>{dishSub(item)}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : dishes.searched ? (
                  <>
                    <p className="muted" role="status">찾는 음식이 없어요. 이름만 남길 수 있어요</p>
                    <button
                      type="button"
                      className="btn secondary"
                      onClick={() => {
                        setTitle(dishes.q);
                        setTab("direct");
                      }}
                    >
                      ‘{dishes.q}’ 이름으로 남기기
                    </button>
                  </>
                ) : (
                  <p className="muted" role="status">지금은 음식을 찾지 못했어요. 잠시 후 다시 찾아주세요</p>
                ))}
            </>
          )}

          {tab === "direct" && (
            <>
              <input
                ref={whatInput}
                className="input"
                placeholder="무엇을 먹었나요?"
                aria-label="무엇을 먹었나요?"
                maxLength={60}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              {nutritionOn && <p className="hint">kcal은 음식 찾기에서 고르면 계산해줘요</p>}
            </>
          )}

          {whatError && needWhat && (
            <p className="error" role="alert">
              무엇을 먹었는지 골라주세요
            </p>
          )}
        </>
      )}

      {showAmount && (
        <div className="field" role="group" aria-labelledby={ids.amount}>
          <span className="field-label" id={ids.amount}>
            얼마나 먹었어요?
          </span>
          {canToggleUnit && (
            <div className="segmented fl-unit" role="group" aria-label="양 단위">
              <button type="button" aria-pressed={unit === "servings"} onClick={() => setUnit("servings")}>
                인분
              </button>
              <button
                type="button"
                aria-pressed={unit === "grams"}
                onClick={() => {
                  if (unit !== "grams") setGramsText(String((pickedDish && dishGrams(pickedDish, { servings })) ?? 100));
                  setUnit("grams");
                }}
              >
                g
              </button>
            </div>
          )}
          {effectiveUnit === "servings" ? (
            <div className="stepper">
              <button type="button" className="icon-btn" aria-label="인분 줄이기" disabled={servings <= MIN_SERVINGS} onClick={() => setServings((n) => stepServings(n, -1))}>
                <Icon name="minus" />
              </button>
              <output className="input rc-count" aria-live="polite">
                {servingsText(servings)}
              </output>
              <button type="button" className="icon-btn" aria-label="인분 늘리기" disabled={servings >= MAX_SERVINGS} onClick={() => setServings((n) => stepServings(n, 1))}>
                <Icon name="plus" />
              </button>
            </div>
          ) : (
            <>
              <div className="input-suffix">
                <input
                  ref={gramsInput}
                  id={ids.grams}
                  className={gramsInvalid ? "input invalid" : "input"}
                  inputMode="numeric"
                  aria-label="먹은 양(g)"
                  aria-invalid={gramsInvalid || undefined}
                  aria-describedby={gramsInvalid ? ids.gramsErr : undefined}
                  value={gramsText}
                  onChange={(e) => setGramsText(e.target.value)}
                />
                <span className="suffix" aria-hidden="true">
                  g
                </span>
              </div>
              {gramsInvalid && (
                <p className="hint nt-invalid" id={ids.gramsErr}>
                  1~3000g 사이로 입력해주세요
                </p>
              )}
            </>
          )}
          {preview && <span className="muted">{preview}</span>}
        </div>
      )}

      <div className="field" role="group" aria-labelledby={ids.place}>
        <span className="field-label" id={ids.place}>
          어디서
        </span>
        <div className="chips">
          {PLACES.map((p) => (
            <button
              key={p}
              type="button"
              className="chip"
              aria-pressed={place === p}
              onClick={() => {
                placeTouched.current = true;
                setPlace(place === p ? null : p);
              }}
            >
              {PLACE_LABEL[p]}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field-label" aria-hidden="true">
          만족도 <span className="optional">(선택)</span>
        </span>
        <div className="fl-bigstars" role="radiogroup" aria-label="만족도">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={rating === n}
              aria-label={`${n}점`}
              tabIndex={n === (rating ?? 1) ? 0 : -1}
              className={rating !== null && n <= rating ? "on" : undefined}
              onClick={() => setRating(rating === n ? null : n)}
              onKeyDown={starKey}
            >
              ★
            </button>
          ))}
        </div>
      </div>

      <div className="field fl-memo">
        <label className="field-label" htmlFor={ids.memo}>
          메모 <span className="optional">(선택)</span>
        </label>
        <textarea id={ids.memo} className="input" rows={2} maxLength={200} value={memo} onChange={(e) => setMemo(e.target.value)} />
        <span className="muted" aria-hidden="true">
          {memo.length} / 200
        </span>
      </div>

      {log && (
        <button type="button" className="btn danger-text" disabled={busy} onClick={deleteLog}>
          기록 지우기
        </button>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="scan-foot">
        <div className="nt-pick-actions">
          <button type="button" className="btn secondary" onClick={onClose}>
            취소
          </button>
          <button type="button" className="btn primary" disabled={busy} aria-disabled={needWhat || gramsInvalid || undefined} onClick={submit}>
            {save.busy ? (log ? "저장하는 중…" : "남기는 중…") : log ? "저장" : "남기기"}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
