import { useId, useRef, useState } from "react";
import { api, type FoodLog, type MealSlot, type User } from "../api";
import { slotDateText } from "../meals/plan";
import { openFoodLog } from "../pages/FoodLog";
import { urgentLabel } from "../pages/Recipes";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import { forgetResources } from "../useResource";
import CookSheet, { toastSaved } from "./CookSheet";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  slot: MealSlot;
  today: string;
  /** 요리했어요 시트의 사진·체험 계정 자동 추정 판단(결정 28) */
  user: User;
  /** 인분을 저장했거나 칸을 비웠거나 먹었어요를 남겼다(닫힐 때 식단을 다시 받는다) */
  onChanged: () => void;
  /** 다른 걸로 바꾸기: 이 시트를 닫고 같은 칸의 채우기 시트를 연다 */
  onReplace: (slot: MealSlot) => void;
  onClose: () => void;
}

/** 시안 SlotDetail: 칸 상세. 인분은 누를 때마다 바로 저장, 칸 비우기는 확인 없이(다시 채우면 된다) */
export default function MealSlotSheet({ slot: initial, today, user, onChanged, onReplace, onClose }: Props) {
  const [slot, setSlot] = useState(initial);
  const [servings, setServings] = useState(initial.servings);
  const [saveError, setSaveError] = useState("");
  const { busy, error: removeError, run } = useAsyncAction();
  const { busy: eatenBusy, error: eatenError, run: runEaten } = useAsyncAction();
  const [ateHint, setAteHint] = useState(false);
  /** 요리했어요 시트(결정 28) — 칸 상세와 형제로 그려진다(칸 상세 위에 얹는 게 아니다), 저장하면 칸 상세도 함께 닫힌다 */
  const [cooking, setCooking] = useState(false);
  const servingsLabel = useId();
  // 빠르게 여러 번 눌러도 누른 차례대로 저장되게 요청을 줄 세운다. 실패하면 마지막으로 저장된 값으로 되돌린다
  const queue = useRef(Promise.resolve());
  const latest = useRef(0);
  const saved = useRef(initial.servings);

  const change = (next: number) => {
    const mine = ++latest.current;
    setServings(next);
    setSaveError("");
    queue.current = queue.current.then(async () => {
      try {
        const updated = await api<MealSlot>(`/api/meal-slots/${slot.id}`, { method: "PATCH", body: { servings: next } });
        saved.current = updated.servings;
        onChanged();
        if (mine === latest.current) {
          setSlot(updated);
          setServings(updated.servings);
        }
      } catch (e) {
        if (mine === latest.current) {
          setServings(saved.current);
          setSaveError((e as Error).message);
        }
      }
    });
  };

  const clear = () =>
    run(async () => {
      await queue.current; // 누른 인분 저장이 끝난 뒤에 지운다(지운 칸에 PATCH가 가 404가 나지 않게)
      await api(`/api/meal-slots/${slot.id}`, { method: "DELETE" });
      onChanged();
      onClose();
    });

  const markEaten = () =>
    runEaten(async () => {
      await queue.current; // 인분 저장이 끝난 뒤에 보낸다
      const log = await api<FoodLog>(`/api/meal-slots/${slot.id}/eaten`, { method: "POST" });
      setSlot({ ...slot, eaten_log_id: log.id });
      forgetResources("/api/food-logs");
      forgetResources("/api/cook-report"); // 기록한 날·집밥 비율(FoodLogSheet와 같게)
      onChanged();
      setAteHint(true);
    });

  const showEaten = slot.date <= today;

  const isRecipe = slot.recipe_id !== null;
  return (
    <>
      <Sheet title={slot.title} description={slotDateText(slot.date, today, slot.meal)} onClose={onClose}>
        {isRecipe && (slot.urgent_names.length > 0 || !!slot.total_count) && (
          <div className="ml-detail-meta">
            {slot.urgent_names.length > 0 && <span className="sh-tag warn">{urgentLabel(slot.urgent_names)}</span>}
            {!!slot.total_count && (
              <span className="rc-match">
                재료 {slot.total_count}개 중 <b>{slot.have_count}개</b> 있어요
              </span>
            )}
          </div>
        )}

        {showEaten &&
          (slot.eaten_log_id === null ? (
            <button type="button" className="btn primary" disabled={eatenBusy} onClick={markEaten}>
              <Icon name="check" />
              {eatenBusy ? "남기는 중…" : "먹었어요 · 먹은 기록에 남기기"}
            </button>
          ) : (
            <button
              type="button"
              className="btn secondary"
              onClick={() => {
                openFoodLog({ date: slot.date, logId: slot.eaten_log_id! });
                onClose();
                navigate("/food-log");
              }}
            >
              <Icon name="check" />
              먹었어요 · 기록 보기
            </button>
          ))}
        {showEaten && ateHint && (
          <p className="hint" role="status">
            먹은 기록에 남겼어요
          </p>
        )}
        {showEaten && eatenError && (
          <p className="error" role="alert">
            {eatenError}
          </p>
        )}

        {showEaten && slot.recipe_id !== null && (
          <button type="button" className="btn outline" aria-haspopup="dialog" onClick={() => void queue.current.then(() => setCooking(true))}>
            <Icon name="pan" />
            요리했어요
          </button>
        )}

        <div className="field ml-serv-field" role="group" aria-labelledby={servingsLabel}>
          <span className="field-label" id={servingsLabel}>
            인분
          </span>
          <div className="stepper">
            <button type="button" className="icon-btn" aria-label="인분 줄이기" disabled={servings <= 1} onClick={() => change(servings - 1)}>
              <Icon name="minus" />
            </button>
            <output className="input rc-count" aria-live="polite">
              {servings}인분
            </output>
            <button type="button" className="icon-btn" aria-label="인분 늘리기" disabled={servings >= 20} onClick={() => change(servings + 1)}>
              <Icon name="plus" />
            </button>
          </div>
          <p className="ml-hint">바꾸면 바로 저장돼요 · 장보기 양도 이 인분으로 계산해요</p>
          {saveError && (
            <p className="error" role="alert">
              {saveError}
            </p>
          )}
        </div>

        <div className="ml-stack">
          {isRecipe && (
            <a
              className="btn outline"
              href={`#/recipes/mine/${slot.recipe_id}`}
              onClick={(e) => {
                e.preventDefault();
                navigate(`/recipes/mine/${slot.recipe_id}`);
              }}
            >
              <Icon name="book" />
              레시피 보기
            </a>
          )}
          <button type="button" className="btn secondary" onClick={() => onReplace({ ...slot, servings })}>
            <Icon name="refresh" />
            다른 걸로 바꾸기
          </button>
        </div>

        {removeError && (
          <p className="error" role="alert">
            {removeError}
          </p>
        )}
        <button type="button" className="btn danger-text" disabled={busy} onClick={clear}>
          {busy ? "비우는 중…" : "칸 비우기"}
        </button>
      </Sheet>
      {cooking && slot.recipe_id !== null && (
        <CookSheet
          recipeId={slot.recipe_id}
          user={user}
          start={{ servings, date: slot.date, meal: slot.meal, slotId: slot.id, slotEaten: slot.eaten_log_id !== null }}
          onSaved={(r) => {
            // 되돌리면 App이 undone 카운트로 화면 전체를 새로 만든다(RecipeDetail·CookDiary와 같게) — onUndone 콜백은 필요 없다
            toastSaved(r);
            onChanged();
            onClose();
          }}
          onClose={() => setCooking(false)}
        />
      )}
    </>
  );
}
