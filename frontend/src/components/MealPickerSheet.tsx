import type { MealPlanSummary } from "../api";
import { rangeText } from "../meals/plan";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  items: MealPlanSummary[];
  currentId: number;
  onPick: (id: number) => void;
  onCreate: () => void;
  onClose: () => void;
}

/** 식단 고르기(결정 3: 시안 프레임 없이 기존 시트 모양) */
export default function MealPickerSheet({ items, currentId, onPick, onCreate, onClose }: Props) {
  return (
    <Sheet title="식단 고르기" onClose={onClose}>
      <ul className="plain-list mo-menu">
        {items.map((plan) => (
          <li key={plan.id}>
            <button
              className="plain-row menu-row"
              aria-current={plan.id === currentId ? "true" : undefined}
              onClick={() => onPick(plan.id)}
            >
              <span className="row-main">
                <span className="row-title">{plan.name}</span>
                <span className="row-sub">
                  {rangeText(plan.start_on, plan.end_on)} · {plan.total}칸 중 {plan.filled}칸
                </span>
              </span>
              {plan.id === currentId && <Icon name="check" color="var(--accent-strong)" />}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="btn outline" onClick={onCreate}>
        <Icon name="plus" />새 식단 만들기
      </button>
    </Sheet>
  );
}
