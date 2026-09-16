import { Fragment } from "react";
import type { MealSlot } from "../api";
import { kcalNumber } from "../nutrition/body";
import { daySum, incompleteNotes, isIncomplete, macroSplit, meterPercent, NUTRIENT_KEYS, nutrientText, slotKcalText, sodiumDay, sugarDay } from "../nutrition/day";
import { dayHead, MEALS } from "../meals/plan";
import Sheet from "./Sheet";

interface Props {
  date: string;
  /** 그날 채운 칸(빈 칸 제외) */
  slots: MealSlot[];
  goal: number | null;
  onClose: () => void;
}

/** 시안 DAY SUMMARY: 하루 머리를 눌러 여는 그날 영양 합계 시트 */
export default function DayNutritionSheet({ date, slots, goal, onClose }: Props) {
  const sum = daySum(slots);
  if (!sum) return null; // 방어: 여는 사이 칸이 모두 지워졌으면 아무것도 그리지 않는다(시트는 곧 닫힘)

  const head = dayHead(date);
  const description =
    sum.filled === sum.counted ? `채운 칸 ${sum.filled}개 · 1인분씩 더했어요` : `채운 칸 ${sum.filled}개 중 ${sum.counted}개 · 1인분씩 더했어요`;
  const over = goal !== null && sum.kcal > goal;
  const hasCalc = slots.some((s) => s.nutrition?.source === "calc");
  const [carbPct, proteinPct, fatPct] = macroSplit(sum.carbs_g, sum.protein_g, sum.fat_g);
  // 값이 빠진 영양소는 "이상"(아는 값이 없으면 "알 수 없어요")으로 보여주고 비율·막대는 확실할 때만(결정 14 개정 2, RecipeNutrition과 같게)
  const { incomplete } = sum;
  const splitKnown = !(["carbs_g", "protein_g", "fat_g"] as const).some((k) => isIncomplete(incomplete, k));
  const sugar = sugarDay(sum.sugars_g, sum.calcKcal, isIncomplete(incomplete, "sugars_g"));
  const sodium = sodiumDay(sum.sodium_mg, isIncomplete(incomplete, "sodium_mg"));
  const bySlot = new Map(slots.map((s) => [s.meal, s]));

  return (
    <Sheet title={`${head.day} ${head.dow} 식단 영양`} description={description} onClose={onClose}>
      <div className="nt-row">
        <span className="nt-big">
          {sum.approx ? "약 " : ""}
          {kcalNumber(sum.kcal)}
        </span>
        <span className="muted">{goal !== null ? ` / 목표 ${kcalNumber(goal)}kcal` : " kcal"}</span>
      </div>
      {goal !== null && (
        <div className={over ? "nt-meter warn" : "nt-meter"} style={{ height: 10 }} aria-hidden="true">
          <i style={{ width: `${meterPercent(sum.kcal, goal)}%` }} />
        </div>
      )}
      {hasCalc && (
        <>
          {splitKnown && (
            <div className="nt-split" role="img" aria-label={`탄수화물 ${carbPct}%, 단백질 ${proteinPct}%, 지방 ${fatPct}%`}>
              <i style={{ flex: carbPct }} />
              <i style={{ flex: proteinPct }} />
              <i style={{ flex: fatPct }} />
            </div>
          )}
          <div className="nt-legend">
            <span className="c">
              탄수화물 <b>{nutrientText(sum.carbs_g, "g", incomplete, "carbs_g")}</b>
            </span>
            <span className="p">
              단백질 <b>{nutrientText(sum.protein_g, "g", incomplete, "protein_g")}</b>
            </span>
            <span className="f">
              지방 <b>{nutrientText(sum.fat_g, "g", incomplete, "fat_g")}</b>
            </span>
          </div>
          <div className="nt-card field-bg">
            <div className="nt-row">
              <span className="muted" style={{ flex: "1 1 auto", minWidth: 0 }}>
                당류 <b style={{ color: "var(--text)" }}>{nutrientText(sum.sugars_g, "g", incomplete, "sugars_g")}</b>
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
                나트륨 <b style={{ color: "var(--text)" }}>{nutrientText(sum.sodium_mg, "mg", incomplete, "sodium_mg")}</b>
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
      )}
      {sum.hasAi && <p className="muted">kcal 일부는 추정치예요</p>}
      <div className="nt-kv">
        {MEALS.filter(([meal]) => bySlot.has(meal)).map(([meal, label]) => {
          const slot = bySlot.get(meal)!;
          return (
            <Fragment key={meal}>
              <span>
                {label} · {slot.title}
              </span>
              <b>{slotKcalText(slot.nutrition) || "—"}</b>
            </Fragment>
          );
        })}
      </div>
      <p className="nt-src">
        식단은 계획이라 실제로 먹은 양과 달라요. 먹은 기록은 더보기 ‘먹은 기록’에서 남길 수 있어요. 의료 조언이 아니라 참고용이에요.
      </p>
    </Sheet>
  );
}
