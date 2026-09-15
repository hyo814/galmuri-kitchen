import { useId, useRef, useState } from "react";
import { api, type MealSlot } from "../api";
import { slotDateText } from "../meals/plan";
import { urgentLabel } from "../pages/Recipes";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  slot: MealSlot;
  today: string;
  /** 인분을 저장했거나 칸을 비웠다(닫힐 때 식단을 다시 받는다) */
  onChanged: () => void;
  /** 다른 걸로 바꾸기: 이 시트를 닫고 같은 칸의 채우기 시트를 연다 */
  onReplace: (slot: MealSlot) => void;
  onClose: () => void;
}

/** 시안 SlotDetail: 칸 상세. 인분은 누를 때마다 바로 저장, 칸 비우기는 확인 없이(다시 채우면 된다) */
export default function MealSlotSheet({ slot: initial, today, onChanged, onReplace, onClose }: Props) {
  const [slot, setSlot] = useState(initial);
  const [servings, setServings] = useState(initial.servings);
  const [saveError, setSaveError] = useState("");
  const { busy, error: removeError, run } = useAsyncAction();
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

  const isRecipe = slot.recipe_id !== null;
  return (
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
  );
}
