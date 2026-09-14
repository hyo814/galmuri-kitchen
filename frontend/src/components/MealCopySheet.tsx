import { useId, useState } from "react";
import { api, type MealPlan } from "../api";
import { copyMaxWeeks, copyTarget, rangeText, weekDates } from "../meals/plan";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

export interface CopyResult {
  plan: MealPlan;
  copied: number;
  kept: number;
}

interface Props {
  plan: MealPlan;
  /** 보고 있는 주 시작일 */
  week: string;
  onCopied: (result: CopyResult) => Promise<void>;
  onClose: () => void;
}

/** "10월 4일" */
const monthDay = (iso: string) => `${Number(iso.slice(5, 7))}월 ${Number(iso.slice(8))}일`;

/** 시안 CopyWeek: 이번 주 복사 */
export default function MealCopySheet({ plan, week, onCopied, onClose }: Props) {
  const dates = weekDates(week, plan);
  const filled = plan.slots.filter((s) => s.date >= week && s.date <= dates[dates.length - 1]).length;
  const max = copyMaxWeeks(plan, week);
  const [weeks, setWeeks] = useState(1);
  const { busy, error, run } = useAsyncAction();
  const label = useId();
  const target = copyTarget(plan, week, weeks);
  const can = filled > 0 && max > 0;

  const copy = () =>
    run(async () => {
      const result = await api<CopyResult>(`/api/meal-plans/${plan.id}/copy-week`, {
        method: "POST",
        body: { from_on: week, weeks },
      });
      await onCopied(result);
    });

  return (
    <Sheet
      title="이번 주 복사"
      description={can ? `${rangeText(dates[0], dates[dates.length - 1])}에 채운 ${filled}칸을 다음 주에도 똑같이 넣어요` : undefined}
      onClose={onClose}
    >
      {!can ? (
        <p className="mo-note">
          <Icon name="info" size={16} />
          <span>
            {filled === 0
              ? "이번 주에 채운 칸이 없어요. 칸을 채운 뒤 복사해주세요"
              : "이 주는 더 복사할 수 없어요. 식단은 31일까지 만들 수 있어요"}
          </span>
        </p>
      ) : (
        <>
          <div className="field" role="group" aria-labelledby={label}>
            <span className="field-label" id={label}>
              몇 주 복사할까요?
            </span>
            <div className="stepper">
              <button type="button" className="icon-btn" aria-label="복사할 주 줄이기" disabled={weeks <= 1} onClick={() => setWeeks(weeks - 1)}>
                <Icon name="minus" />
              </button>
              <output className="input rc-count" aria-live="polite">
                {weeks}주
              </output>
              <button type="button" className="icon-btn" aria-label="복사할 주 늘리기" disabled={weeks >= max} onClick={() => setWeeks(weeks + 1)}>
                <Icon name="plus" />
              </button>
            </div>
            <p className="ml-hint">{max === 4 ? "1~4주까지" : `1~4주까지 · 식단은 31일까지라 이 식단은 ${max}주까지 돼요`}</p>
          </div>
          <div className="ml-preview-line">
            <span>들어갈 날</span>
            <b>{rangeText(target.start, target.end).replace("–", " – ")}</b>
          </div>
          <div className="ml-stack">
            <p className="mo-note ok">
              <Icon name="check" size={16} />
              <span>이미 채운 칸은 그대로 두고 빈 칸만 채워요.</span>
            </p>
            {target.extendedDays && (
              <p className="mo-note">
                <Icon name="info" size={16} />
                <span>
                  식단 기간이 {monthDay(target.end)}까지({target.extendedDays}일)로 늘어나요.
                </span>
              </p>
            )}
          </div>
        </>
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
        <button type="button" className="btn primary" disabled={!can || busy} onClick={copy}>
          <Icon name="clipboard" />
          {busy ? "복사하는 중…" : `${weeks}주에 복사`}
        </button>
      </div>
    </Sheet>
  );
}
