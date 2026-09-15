import { useEffect, useState } from "react";
import { api, type BodyProfileResponse, type FoodLog, type FoodLogDay, type FoodLogPlanSlot, type MealKind, type User } from "../api";
import { withJosa } from "../format.ts";
import { PLACE_LABEL, dayDescription, dayTotals, logSubText, mealKcalText, starsText } from "../foodlog/log.ts";
import { MEALS, slotDateText } from "../meals/plan.ts";
import { dailyTarget } from "../nutrition/body.ts";
import { MAX_FILL_ATTEMPTS, meterPercent, sodiumDay } from "../nutrition/day.ts";
import { useAsyncAction } from "../useAsyncAction";
import { forgetResources, useResource } from "../useResource";
import Icon from "./Icon";
import Sheet from "./Sheet";

/** 채우기를 부른 횟수(레시피 id → 횟수, 날짜 상세·추가 시트 공용). MAX_FILL_ATTEMPTS번까지만 부른다
 * (4b-2 `Meals.tsx attempted`·`RecipeNutrition filled`와 같은 생각, Ruling 18). resetFoodLogView가 비운다 */
export const fillAttempted = new Map<number, number>();

/** 레시피를 고쳐 저장했을 때(RecipeForm): 새 재료를 다시 채우도록 그 레시피를 시도 목록에서 뺀다 */
export function forgetFoodLogNutritionFill(recipeId: number) {
  fillAttempted.delete(recipeId);
}

/** 시안 DAY·PHOTO FIRST: 날짜 하나의 목표 대비 kcal·끼니별 기록·식단 제안 */
export default function FoodLogDaySheet({
  date,
  today,
  user,
  onOpenLog,
  onAdd,
  onChanged,
  onClose,
  reloadTick = 0,
}: {
  date: string;
  today: string;
  user: User;
  onOpenLog: (log: FoodLog, day: FoodLogDay) => void;
  onAdd: (meal: MealKind, day: FoodLogDay) => void;
  onChanged: () => void;
  onClose: () => void;
  /** 고치기·추가 시트가 저장·삭제하면 올라간다 — 다시 마운트하지 않고 다시 받아 스크롤·포커스를 지킨다 */
  reloadTick?: number;
}) {
  const day = useResource<FoodLogDay>(`/api/food-logs?date=${date}`);
  const body = useResource<BodyProfileResponse>("/api/body-profile");
  const goal = body.data?.profile ? dailyTarget(body.data.profile, today).target : null;

  useEffect(() => {
    if (reloadTick) void day.reload();
  }, [reloadTick, day.reload]);

  const eaten = useAsyncAction();
  const [eatenBusyId, setEatenBusyId] = useState<number | null>(null);
  const [eatenErrorMeal, setEatenErrorMeal] = useState<MealKind | null>(null);

  // 채우기(개정 1 S10, fix round 1 I1): 레시피 id별 시도 횟수가 MAX_FILL_ATTEMPTS 미만인 것만, 요청 전에 횟수를 올린다
  // (날짜·조합 키로 기억하지 않아 pending이 줄어도 새로 부르지 않는다 — 4b-2 Task 7 리뷰와 같은 이유, Ruling 18)
  useEffect(() => {
    if (!day.data || user.nutrition === "off") return;
    const ids = day.data.nutrition_pending_recipe_ids.filter((id) => (fillAttempted.get(id) ?? 0) < MAX_FILL_ATTEMPTS).slice(0, 31);
    if (!ids.length) return;
    ids.forEach((id) => fillAttempted.set(id, (fillAttempted.get(id) ?? 0) + 1));
    (async () => {
      try {
        await api("/api/nutrition/fill", { method: "POST", body: { recipe_ids: ids } });
      } catch {
        // 조용히 실패 — 남은 횟수가 있으면 다시 계산 중일 때 한 번 더 부른다
      }
      await day.reload();
      onChanged();
    })();
  }, [day.data, user.nutrition, day.reload, onChanged]);

  async function markEaten(slot: FoodLogPlanSlot) {
    setEatenBusyId(slot.id);
    setEatenErrorMeal(null);
    const ok = await eaten.run(async () => {
      await api(`/api/meal-slots/${slot.id}/eaten`, { method: "POST" });
      forgetResources("/api/meal-plans");
      forgetResources("/api/food-logs");
      await day.reload();
      onChanged();
    });
    if (!ok) setEatenErrorMeal(slot.meal);
    setEatenBusyId(null);
  }

  const title = slotDateText(date, "");

  if (!day.data) {
    return (
      <Sheet title={title} className="fl-day" onClose={onClose}>
        {day.error ? (
          <>
            <p className="error" role="alert">{day.error}</p>
            <button type="button" className="btn secondary" onClick={day.reload}>다시 불러오기</button>
          </>
        ) : (
          <p className="muted" role="status">불러오는 중…</p>
        )}
      </Sheet>
    );
  }

  const { logs, plan_slots } = day.data;
  const t = dayTotals(logs);
  const over = goal !== null && !!t && t.kcal > goal;
  const sodium = t ? sodiumDay(t.sodium_mg) : null;

  return (
    <Sheet title={title} description={dayDescription(logs, goal)} className="fl-day" onClose={onClose}>
      {goal !== null && t && (
        <div className={over ? "nt-meter nt-dmeter warn" : "nt-meter nt-dmeter"} role="img" aria-label={`목표의 ${Math.round((t.kcal / goal) * 100)}%`}>
          <i style={{ width: `${meterPercent(t.kcal, goal)}%` }} />
        </div>
      )}
      {sodium?.warn && <p className="fl-warn">나트륨 {sodium.text}</p>}

      {MEALS.map(([meal, label]) => {
        const mealLogs = logs.filter((l) => l.meal === meal);
        const mealSlots = date <= today ? plan_slots.filter((s) => s.meal === meal) : [];
        const kcalText = mealKcalText(mealLogs);
        return (
          <section key={meal} className="fl-meal" aria-labelledby={`fl-mealh-${meal}`}>
            <div className="fl-mealh">
              <h3 id={`fl-mealh-${meal}`}>{label}</h3>
              {kcalText && <span className="fl-mk">{kcalText}</span>}
            </div>
            {mealLogs.map((log) => (
              <button key={log.id} type="button" className="fl-log" aria-haspopup="dialog" onClick={() => onOpenLog(log, day.data!)}>
                {log.photos[0] ? (
                  <img className="fl-ph" src={log.photos[0].url} alt="" />
                ) : (
                  <span className="fl-noph">
                    <Icon name="bowl" />
                  </span>
                )}
                <span>
                  <b>{log.title ?? "사진 기록"}</b>{" "}
                  {log.place && <span className={log.place === "home" ? "badge info" : "badge"}>{PLACE_LABEL[log.place]}</span>}{" "}
                  {log.title === null && <span className="badge old">이름 없음</span>}
                  <small>
                    {logSubText(log)}
                    {log.rating !== null && (
                      <>
                        {" · "}
                        <span className="fl-stars" role="img" aria-label={`만족도 ${log.rating}점`}>
                          {starsText(log.rating)}
                        </span>
                      </>
                    )}
                  </small>
                  {log.memo && <small>{log.memo}</small>}
                </span>
                <span className="sr-only"> 고치기</span>
              </button>
            ))}
            {mealSlots.map((slot) => (
              <div key={slot.id} className="fl-plan">
                <Icon name="calendar" />
                <span>
                  식단에 <b>{slot.title}</b>
                  {withJosa(slot.title, "이", "가").slice(slot.title.length)} 있었어요
                </span>
                <button
                  type="button"
                  className="nt-link"
                  aria-label={`식단 ${slot.title} 먹었어요`}
                  disabled={eaten.busy && eatenBusyId === slot.id}
                  onClick={() => markEaten(slot)}
                >
                  먹었어요
                </button>
              </div>
            ))}
            {eatenErrorMeal === meal && eaten.error && (
              <p className="error" role="alert">
                {eaten.error}
              </p>
            )}
            {date <= today && (
              <button type="button" className="fl-addrow" aria-label={`${label} 먹은 것 추가`} aria-haspopup="dialog" onClick={() => onAdd(meal, day.data!)}>
                <b>+</b>먹은 것
              </button>
            )}
          </section>
        );
      })}

      <p className="nt-src">의료 조언이 아니라 참고용이에요.</p>
    </Sheet>
  );
}
