import { useEffect, useId, useState } from "react";
import { api, type NutritionIngredient, type RecipeNutrition, type User } from "../api";
import { kcalNumber } from "../nutrition/body";
import {
  dailyValue, incompleteNotes, ingredientKcalText, ingredientNote, isIncomplete, macroSplit, MAX_FILL_ATTEMPTS, NUTRIENT_KEYS, nutrientText, SODIUM_DAILY_MG,
  SUGARS_DAILY_G,
} from "../nutrition/day";
import { useResource } from "../useResource";
import FoodPickSheet from "./FoodPickSheet";
import LoadError from "./LoadError";

/** 레시피별 채우기 부른 횟수. MAX_FILL_ATTEMPTS번까지만 부른다(레시피 상세를 오가도 계속 부르지 않게, Meals.tsx의 attempted와 같은 생각) */
const filled = new Map<number, number>();

/** 로그아웃 등 화면을 전부 리셋할 때(App.tsx `resetScreens`) 함께 비운다 — 다른 사용자로 들어와도 이전 계정이 이미 시도한 레시피로 남지 않게 */
export function resetRecipeNutrition() {
  filled.clear();
}

/** 레시피를 고쳐 저장했을 때(RecipeForm): 새 재료를 다시 채우도록 그 레시피를 시도 목록에서 뺀다 */
export function forgetRecipeNutritionFill(recipeId: number) {
  filled.delete(recipeId);
}

/** 시안 RECIPE NUTRITION: 재료 아래 영양 칸(1인분)과 재료별 kcal·식품 고르기 진입점 */
export default function RecipeNutrition({ recipeId, user }: { recipeId: number; user: User }) {
  const { data, error, reload } = useResource<RecipeNutrition>(`/api/recipes/${recipeId}/nutrition`);
  const [pickRow, setPickRow] = useState<NutritionIngredient | null>(null);
  const headId = useId();

  useEffect(() => {
    const tries = filled.get(recipeId) ?? 0;
    if (!data?.pending || tries >= MAX_FILL_ATTEMPTS) return;
    filled.set(recipeId, tries + 1);
    (async () => {
      try {
        await api("/api/nutrition/fill", { method: "POST", body: { recipe_ids: [recipeId] } });
      } catch {
        // 조용히 실패: 남은 횟수가 있으면 다시 받은 결과가 아직 계산 중일 때 한 번 더 부른다
      }
      await reload();
    })();
  }, [data?.pending, recipeId, reload]);

  if (!data) {
    if (error) return <LoadError error={error} onRetry={reload} />;
    return <p className="muted">영양을 계산하고 있어요</p>;
  }

  const { per_serving, incomplete } = data;
  const [carbPct, proteinPct, fatPct] = per_serving ? macroSplit(per_serving.carbs_g, per_serving.protein_g, per_serving.fat_g) : [0, 0, 0];
  // 값이 빠진 영양소는 "이상"(아는 값이 없으면 "알 수 없어요")으로 보여주고 비율·막대는 확실할 때만(결정 14 개정 2)
  const splitKnown = !(["carbs_g", "protein_g", "fat_g"] as const).some((k) => isIncomplete(incomplete, k));
  const sugar = per_serving ? dailyValue(per_serving.sugars_g, SUGARS_DAILY_G, isIncomplete(incomplete, "sugars_g")) : null;
  const sodium = per_serving ? dailyValue(per_serving.sodium_mg, SODIUM_DAILY_MG, isIncomplete(incomplete, "sodium_mg")) : null;

  return (
    <>
      <section className="nt-card" aria-labelledby={headId}>
        <div className="nt-row">
          <h2 id={headId} style={{ flex: 1, minWidth: 0 }}>
            영양 · 1인분
          </h2>
          {data.estimated_count > 0 && <span className="badge old">재료 {data.estimated_count}개 추정</span>}
          {data.missing_count > 0 && <span className="badge">재료 {data.missing_count}개 빠짐</span>}
        </div>
        {per_serving ? (
          <>
            <div className="nt-row">
              <span className="nt-big">
                {data.approx ? "약 " : ""}
                {kcalNumber(per_serving.kcal)}
              </span>
              <span className="muted">kcal</span>
            </div>
            {splitKnown && (
              <div className="nt-split" role="img" aria-label={`탄수화물 ${carbPct}%, 단백질 ${proteinPct}%, 지방 ${fatPct}%`}>
                <i style={{ flex: carbPct }} />
                <i style={{ flex: proteinPct }} />
                <i style={{ flex: fatPct }} />
              </div>
            )}
            <div className="nt-legend">
              <span className="c">
                탄수화물 <b>{nutrientText(per_serving.carbs_g, "g", incomplete, "carbs_g")}</b>
              </span>
              <span className="p">
                단백질 <b>{nutrientText(per_serving.protein_g, "g", incomplete, "protein_g")}</b>
              </span>
              <span className="f">
                지방 <b>{nutrientText(per_serving.fat_g, "g", incomplete, "fat_g")}</b>
              </span>
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              <div className="nt-row">
                <span className="muted" style={{ flex: "1 1 auto", minWidth: 0 }}>
                  당류 <b style={{ color: "var(--text)" }}>{nutrientText(per_serving.sugars_g, "g", incomplete, "sugars_g")}</b>
                </span>
                {sugar && (
                  <span className="muted" style={sugar.warn ? { color: "var(--warn)" } : undefined}>
                    {sugar.text}
                  </span>
                )}
              </div>
              {sugar && (
                <div className={sugar.warn ? "nt-meter warn" : "nt-meter"}>
                  <i style={{ width: `${sugar.percent}%` }} />
                </div>
              )}
              <div className="nt-row">
                <span className="muted" style={{ flex: "1 1 auto", minWidth: 0 }}>
                  나트륨 <b style={{ color: "var(--text)" }}>{nutrientText(per_serving.sodium_mg, "mg", incomplete, "sodium_mg")}</b>
                </span>
                {sodium && (
                  <span className="muted" style={sodium.warn ? { color: "var(--warn)" } : undefined}>
                    {sodium.text}
                  </span>
                )}
              </div>
              {sodium && (
                <div className={sodium.warn ? "nt-meter warn" : "nt-meter"}>
                  <i style={{ width: `${sodium.percent}%` }} />
                </div>
              )}
            </div>
            {incompleteNotes(incomplete, NUTRIENT_KEYS).map((note) => (
              <p key={note} className="nt-note">
                {note}
              </p>
            ))}
          </>
        ) : data.pending ? (
          <p className="muted">영양을 계산하고 있어요</p>
        ) : (
          <p className="muted">재료를 식품과 맞추면 영양을 계산해줘요</p>
        )}
        {user.nutrition === "sample" && <p className="muted">예시 영양값이에요</p>}
        <p className="nt-src">
          식약처 식품영양성분 DB(100g당)로 계산했어요. 당류 100g·나트륨 2,000mg은 하루 2,000kcal 기준 1일 기준치예요. 의료 조언이
          아니라 참고용이에요.
        </p>
      </section>

      <section className="nt-card" aria-label="재료별" style={{ gap: 0 }}>
        <div className="nt-row" style={{ paddingBottom: 8 }}>
          <b style={{ flex: 1, minWidth: 0 }}>재료별</b>
          <span className="muted">1인분 kcal</span>
        </div>
        {data.ingredients.map((row, i) => {
          const note = ingredientNote(row);
          return (
            <div className="nt-ing" key={i}>
              <span>
                {row.name} {row.amount}
                {row.status === "estimated" && <span className="badge old">추정</span>}
              </span>
              <small>
                {note.text}
                {note.action && (
                  <button
                    type="button"
                    className="nt-link"
                    aria-haspopup="dialog"
                    aria-label={`${row.name} 식품 ${note.action}`}
                    onClick={() => setPickRow(row)}
                  >
                    {note.action}
                  </button>
                )}
              </small>
              <span className="nt-ing-kcal">{ingredientKcalText(row)}</span>
            </div>
          );
        })}
      </section>

      {pickRow && (
        <FoodPickSheet
          row={pickRow}
          onSaved={() => {
            filled.delete(recipeId);
            setPickRow(null);
            void reload();
          }}
          onClose={() => setPickRow(null)}
        />
      )}
    </>
  );
}
