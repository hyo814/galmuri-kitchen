import { useEffect, useId, useState } from "react";
import { api, type NutritionIngredient, type RecipeNutrition, type User } from "../api";
import { kcalNumber } from "../nutrition/body";
import { dailyValue, ingredientKcalText, ingredientNote, macroSplit, SODIUM_DAILY_MG, SUGARS_DAILY_G } from "../nutrition/day";
import { LoadError } from "../pages/Meals";
import { useResource } from "../useResource";
import FoodPickSheet from "./FoodPickSheet";

/** 레시피별로 채우기를 한 번만 부른다(레시피 상세를 오가도 계속 부르지 않게, Meals.tsx의 attempted 패턴과 같은 생각) */
const filled = new Set<number>();

/** 시안 RECIPE NUTRITION: 재료 아래 영양 칸(1인분)과 재료별 kcal·식품 고르기 진입점 */
export default function RecipeNutrition({ recipeId, user }: { recipeId: number; user: User }) {
  const { data, error, reload } = useResource<RecipeNutrition>(`/api/recipes/${recipeId}/nutrition`);
  const [pickRow, setPickRow] = useState<NutritionIngredient | null>(null);
  const headId = useId();

  useEffect(() => {
    if (!data?.pending || filled.has(recipeId)) return;
    filled.add(recipeId);
    (async () => {
      try {
        await api("/api/nutrition/fill", { method: "POST", body: { recipe_ids: [recipeId] } });
      } catch {
        // 조용히 실패: 다음에 다시 열면 그때 채운다
      }
      await reload();
    })();
  }, [data?.pending, recipeId, reload]);

  if (!data) {
    if (error) return <LoadError error={error} onRetry={reload} />;
    return <p className="muted">영양을 계산하고 있어요</p>;
  }

  const { per_serving } = data;
  const [carbPct, proteinPct, fatPct] = per_serving ? macroSplit(per_serving.carbs_g, per_serving.protein_g, per_serving.fat_g) : [0, 0, 0];
  const sugar = per_serving ? dailyValue(per_serving.sugars_g, SUGARS_DAILY_G) : null;
  const sodium = per_serving ? dailyValue(per_serving.sodium_mg, SODIUM_DAILY_MG) : null;

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
        {per_serving && sugar && sodium ? (
          <>
            <div className="nt-row">
              <span className="nt-big">
                {data.approx ? "약 " : ""}
                {kcalNumber(per_serving.kcal)}
              </span>
              <span className="muted">kcal</span>
            </div>
            <div className="nt-split" role="img" aria-label={`탄수화물 ${carbPct}%, 단백질 ${proteinPct}%, 지방 ${fatPct}%`}>
              <i style={{ flex: carbPct }} />
              <i style={{ flex: proteinPct }} />
              <i style={{ flex: fatPct }} />
            </div>
            <div className="nt-legend">
              <span className="c">
                탄수화물 <b>{Math.round(per_serving.carbs_g)}g</b>
              </span>
              <span className="p">
                단백질 <b>{Math.round(per_serving.protein_g)}g</b>
              </span>
              <span className="f">
                지방 <b>{Math.round(per_serving.fat_g)}g</b>
              </span>
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              <div className="nt-row">
                <span className="muted" style={{ flex: 1, minWidth: 0 }}>
                  당류 <b style={{ color: "var(--text)" }}>{Math.round(per_serving.sugars_g)}g</b>
                </span>
                <span className="muted" style={sugar.warn ? { color: "var(--warn)" } : undefined}>
                  {sugar.text}
                </span>
              </div>
              <div className={sugar.warn ? "nt-meter warn" : "nt-meter"}>
                <i style={{ width: `${sugar.percent}%` }} />
              </div>
              <div className="nt-row">
                <span className="muted" style={{ flex: 1, minWidth: 0 }}>
                  나트륨 <b style={{ color: "var(--text)" }}>{kcalNumber(per_serving.sodium_mg)}mg</b>
                </span>
                <span className="muted" style={sodium.warn ? { color: "var(--warn)" } : undefined}>
                  {sodium.text}
                </span>
              </div>
              <div className={sodium.warn ? "nt-meter warn" : "nt-meter"}>
                <i style={{ width: `${sodium.percent}%` }} />
              </div>
            </div>
          </>
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
