import { useId, useState, type FormEvent } from "react";
import { api, type MealPlan } from "../api";
import { dateWithDow, defaultPlanName, PERIODS, planEnd, rangeText } from "../meals/plan";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  today: string;
  /** 목록의 default_servings(마지막으로 만든 식단의 기본 인분) */
  defaultServings: number;
  onCreated: (plan: MealPlan) => Promise<void>;
  onClose: () => void;
}

/** 시안 CreateSheet: 식단 만들기 */
export default function MealPlanSheet({ today, defaultServings, onCreated, onClose }: Props) {
  const [start, setStart] = useState(today);
  const [period, setPeriod] = useState<number | null>(7);
  const [days, setDays] = useState(7);
  const [servings, setServings] = useState(defaultServings);
  /** 사용자가 이름을 고치기 전까지는 시작일·기간을 따라 바뀐다 */
  const [typedName, setTypedName] = useState<string | null>(null);
  const { busy, error, run } = useAsyncAction();
  const servingsLabel = useId();
  const name = typedName ?? defaultPlanName(start, days);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const plan = await api<MealPlan>("/api/meal-plans", {
        method: "POST",
        body: { name: name.trim(), start_on: start, days, default_servings: servings },
      });
      await onCreated(plan);
    });
  };

  return (
    <Sheet title="식단 만들기" focusTitle onClose={onClose}>
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
          <p className="ml-hint">새 칸에 먼저 넣을 인분이에요. 처음엔 1인분, 다음 식단부터는 마지막으로 고른 값으로 시작해요</p>
        </div>

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
            {busy ? "만드는 중…" : "만들기"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
