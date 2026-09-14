import { useId, useState, type FormEvent } from "react";
import { api, type MealPlan } from "../api";
import { dateWithDow, defaultPlanName, PERIODS, planEnd, rangeText, slotsOutside } from "../meals/plan";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  today: string;
  /** 목록의 default_servings(마지막으로 만든 식단의 기본 인분). 고치기에서는 식단 값을 쓴다 */
  defaultServings: number;
  /** 있으면 고치기(시안 CreateSheet와 같은 칸, 제목 `식단 고치기`) */
  plan?: MealPlan;
  onSaved: (plan: MealPlan) => Promise<void>;
  onClose: () => void;
}

/** 시안 CreateSheet: 식단 만들기·고치기 */
export default function MealPlanSheet({ today, defaultServings, plan, onSaved, onClose }: Props) {
  const [start, setStart] = useState(plan?.start_on ?? today);
  const [days, setDays] = useState(plan?.days ?? 7);
  const [period, setPeriod] = useState<number | null>(PERIODS.some(([, v]) => v === days) ? days : null);
  const [servings, setServings] = useState(plan?.default_servings ?? defaultServings);
  /** 사용자가 이름을 고치기 전까지는 시작일·기간을 따라 바뀐다(고치기는 지금 이름으로 시작) */
  const [typedName, setTypedName] = useState<string | null>(plan?.name ?? null);
  const { busy, error, run } = useAsyncAction();
  const servingsLabel = useId();
  const name = typedName ?? defaultPlanName(start, days);
  const outside = plan ? slotsOutside(plan.slots, start, days) : 0;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const saved = await api<MealPlan>(plan ? `/api/meal-plans/${plan.id}` : "/api/meal-plans", {
        method: plan ? "PATCH" : "POST",
        body: { name: name.trim(), start_on: start, days, default_servings: servings },
      });
      await onSaved(saved);
    });
  };

  return (
    <Sheet title={plan ? "식단 고치기" : "식단 만들기"} focusTitle onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">이름</span>
          <input className="input" value={name} maxLength={30} required onChange={(e) => setTypedName(e.target.value)} />
        </label>

        <label className="field">
          <span className="field-label">시작일</span>
          <span className="input sh-date ml-kcal">
            {dateWithDow(start)}
            {start === today && " · 오늘"}
            <Icon name="calendar" />
            <input
              type="date"
              value={start}
              required
              onClick={(e) => e.currentTarget.showPicker?.()}
              onChange={(e) => e.target.value && setStart(e.target.value)}
            />
          </span>
        </label>

        <div className="field" role="group" aria-label="기간">
          <span className="field-label">기간</span>
          <div className="sh-when ml-period">
            {PERIODS.map(([label, value]) => (
              <button
                key={label}
                type="button"
                aria-pressed={period === value}
                onClick={() => {
                  setPeriod(value);
                  if (value) setDays(value);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="ml-hint">
            {rangeText(start, planEnd(start, days))} · {days}일이에요. 직접 고르면 1~31일로 정할 수 있어요
          </p>
          {period === null && (
            <div className="stepper">
              <button type="button" className="icon-btn" aria-label="기간 줄이기" disabled={days <= 1} onClick={() => setDays(days - 1)}>
                <Icon name="minus" />
              </button>
              <output className="input rc-count" aria-label={`기간 ${days}일`} aria-live="polite">
                {days}일
              </output>
              <button type="button" className="icon-btn" aria-label="기간 늘리기" disabled={days >= 31} onClick={() => setDays(days + 1)}>
                <Icon name="plus" />
              </button>
            </div>
          )}
        </div>

        <div className="field ml-serv-field" role="group" aria-labelledby={servingsLabel}>
          <span className="field-label" id={servingsLabel}>
            기본 인분
          </span>
          <div className="stepper">
            <button
              type="button"
              className="icon-btn"
              aria-label="기본 인분 줄이기"
              disabled={servings <= 1}
              onClick={() => setServings(servings - 1)}
            >
              <Icon name="minus" />
            </button>
            <output className="input rc-count" aria-live="polite">
              {servings}인분
            </output>
            <button
              type="button"
              className="icon-btn"
              aria-label="기본 인분 늘리기"
              disabled={servings >= 20}
              onClick={() => setServings(servings + 1)}
            >
              <Icon name="plus" />
            </button>
          </div>
          <p className="ml-hint">
            {plan ? "새 칸에 먼저 넣을 인분이에요" : "새 칸에 먼저 넣을 인분이에요. 처음엔 1인분, 다음 식단부터는 마지막으로 고른 값으로 시작해요"}
          </p>
        </div>

        {outside > 0 && (
          <p className="mo-note warn" role="alert">
            <Icon name="alert" size={16} />
            <span>기간 밖에 채운 칸 {outside}개는 지워져요.</span>
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn outline" onClick={onClose}>
            취소
          </button>
          <button className="btn primary" disabled={busy}>
            {plan ? (busy ? "저장하는 중…" : "저장") : busy ? "만드는 중…" : "만들기"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
