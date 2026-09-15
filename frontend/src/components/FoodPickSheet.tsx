import { useEffect, useId, useRef, useState } from "react";
import { api, type FoodSearchItem, type FoodSearchResult, type NutritionIngredient } from "../api";
import { withJosa } from "../format";
import { closestMatch, candidateSub, gramsFieldValue, pickTitle, unitGramsFrom } from "../nutrition/day";
import { useAsyncAction } from "../useAsyncAction";
import { forgetRecipeCaches, forgetResources } from "../useResource";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  row: NutritionIngredient;
  onSaved: () => void;
  onClose: () => void;
}

/** 검색 칸 시작값: 괄호 속 설명을 뺀 이름("두부(3kg)" → "두부") */
const searchName = (name: string) => name.replace(/\([^)]*\)/g, "").trim();

/** 소수 첫째 자리까지만(kcalNumber처럼 반올림·자릿수 콤마를 넣지 않는다) */
const oneDecimal = (n: number) => String(Math.round(n * 10) / 10);

/** 시안 MATCH FOOD: 재료 ↔ 식품 고르기. 열면 바로 한 번 찾고, 고칠 때는 300ms 뒤(AbortController로 앞 요청 취소) */
export default function FoodPickSheet({ row, onSaved, onClose }: Props) {
  const [q, setQ] = useState(() => searchName(row.name));
  const [result, setResult] = useState<{ q: string; items: FoodSearchItem[]; searched: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchError, setSearchError] = useState("");
  const isFirst = useRef(true);
  const selectedOnce = useRef(false);
  const [foodCode, setFoodCode] = useState<string | null>(null);
  const [gramsInput, setGramsInput] = useState(() => gramsFieldValue(row));
  const { busy, error, run } = useAsyncAction();
  const radioName = useId();
  const gramsId = useId();
  const weightHintId = useId();
  const weightErrId = useId();

  useEffect(() => {
    const trimmed = q.trim();
    if (!trimmed) {
      setLoading(false);
      setSearchError("");
      setResult({ q: "", items: [], searched: false });
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    const delay = isFirst.current ? 0 : 300;
    const timer = setTimeout(async () => {
      isFirst.current = false;
      try {
        const data = await api<FoodSearchResult>(`/api/foods/search?q=${encodeURIComponent(trimmed)}`, { signal: controller.signal });
        setResult({ q: trimmed, items: data.items, searched: data.searched });
        setSearchError("");
      } catch (e) {
        if (!controller.signal.aborted) {
          setSearchError((e as Error).message);
          setResult(null); // 오래된(다른 검색어) 목록을 지금 것처럼 보여주지 않는다
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, delay);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q]);

  // 처음 결과가 오면 한 번만 기본 선택: 이미 고른 식품이 목록에 있으면 그것, 아니면 `가장 비슷` 줄
  useEffect(() => {
    if (!result || selectedOnce.current) return;
    selectedOnce.current = true;
    const items = result.items;
    if (row.food && items.some((i) => i.food_code === row.food!.food_code)) setFoodCode(row.food.food_code);
    else if (items[0] && closestMatch(items[0], result.q)) setFoodCode(items[0].food_code);
  }, [result, row.food]);

  // 검색 결과가 바뀌어 지금 고른 식품이 더는 목록에 없으면 선택을 지운다(숨어버린 선택으로 저장하지 않게)
  useEffect(() => {
    if (foodCode !== null && result && !result.items.some((i) => i.food_code === foodCode)) setFoodCode(null);
  }, [result, foodCode]);

  const initialGrams = gramsFieldValue(row);
  const gramsEdited = gramsInput !== initialGrams;
  const editedUnitGrams = gramsEdited ? unitGramsFrom(gramsInput, row.quantity) : null;
  const gramsInvalid = gramsEdited && editedUnitGrams === null;
  const weightEstimated = row.unit_grams_source === "ai" || row.unit_grams_source === "sample";
  const showWeightField = row.countable && row.quantity !== null;
  const weightBody = gramsEdited && editedUnitGrams !== null ? { unit: row.unit!, unit_grams: editedUnitGrams } : {};
  const weightDescribedBy = [weightEstimated && weightHintId, gramsInvalid && weightErrId].filter(Boolean).join(" ") || undefined;

  const save = (foodCodeValue: string | null) => {
    if (gramsInvalid) return;
    void run(async () => {
      await api("/api/food-matches", { method: "PUT", body: { name: row.name, food_code: foodCodeValue, ...weightBody } });
      // 같은 재료를 쓰는 모든 레시피·식단 값이 바뀐다
      forgetRecipeCaches();
      forgetResources("/api/meal-plans");
      onSaved();
    });
  };

  const trimmedQ = q.trim();

  return (
    <Sheet title={pickTitle(row.name)} description="고른 식품은 다른 레시피에도 똑같이 써요" focusTitle onClose={onClose}>
      <div className="input-suffix nt-food-search">
        <input
          className="input"
          type="search"
          placeholder="식품 이름으로 찾기"
          maxLength={50}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="suffix" aria-hidden="true">
          <Icon name="search" size={18} />
        </span>
      </div>

      {showWeightField && (
        <div className="field">
          <label className="field-label" htmlFor={gramsId}>
            {withJosa(row.amount, "은", "는")} 몇 g인가요?
          </label>
          <div className="input-suffix">
            <input
              id={gramsId}
              className={gramsInvalid ? "input invalid" : "input"}
              inputMode="decimal"
              value={gramsInput}
              aria-invalid={gramsInvalid || undefined}
              aria-describedby={weightDescribedBy}
              onChange={(e) => setGramsInput(e.target.value)}
            />
            <span className="suffix" aria-hidden="true">
              {weightEstimated ? `g · 1${row.unit} ≈ ${oneDecimal(row.unit_grams ?? 0)}g 추정` : "g"}
            </span>
          </div>
          {weightEstimated && (
            <p className="nt-src" id={weightHintId}>
              숫자를 고치면 추정 표시가 없어져요.
            </p>
          )}
          {gramsInvalid && (
            <p className="hint nt-invalid" id={weightErrId}>
              무게는 0.1~5000g 사이로 입력해주세요
            </p>
          )}
        </div>
      )}

      {trimmedQ !== "" &&
        (loading ? (
          <p className="muted">찾는 중…</p>
        ) : result ? (
          result.items.length ? (
            <div role="radiogroup" aria-label="식품" style={{ display: "grid", gap: 8 }}>
              {result.items.map((item, i) => (
                <label key={item.food_code} className={item.food_code === foodCode ? "nt-cand on" : "nt-cand"}>
                  <input
                    className="sr-only"
                    type="radio"
                    name={radioName}
                    checked={item.food_code === foodCode}
                    aria-label={`${item.name}, ${candidateSub(item.group, item.kcal)}`}
                    onChange={() => setFoodCode(item.food_code)}
                  />
                  <span className="nt-radio" aria-hidden="true" />
                  <span>
                    <b>{item.name}</b>
                    <small>{candidateSub(item.group, item.kcal)}</small>
                  </span>
                  {i === 0 && closestMatch(item, result.q) && <span className="badge">가장 비슷</span>}
                </label>
              ))}
            </div>
          ) : (
            <p className="muted">
              {result.searched ? "찾는 식품이 없어요. 다른 이름으로 찾아주세요" : "지금은 식품을 찾지 못했어요. 잠시 후 다시 찾아주세요"}
            </p>
          )
        ) : null)}
      {searchError && (
        <p className="error" role="alert">
          {searchError}
        </p>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="scan-foot">
        <div className="nt-pick-actions">
          <button
            type="button"
            className="btn secondary"
            disabled={busy}
            aria-disabled={gramsInvalid || undefined}
            onClick={() => !gramsInvalid && save(null)}
          >
            추정으로 두기
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            aria-disabled={!foodCode || gramsInvalid || undefined}
            onClick={() => foodCode && !gramsInvalid && save(foodCode)}
          >
            이 식품으로
          </button>
        </div>
      </div>
    </Sheet>
  );
}
