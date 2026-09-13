import { useState, type FormEvent } from "react";
import { localToday, type KitchenTool, type KitchenToolInput, type ToolCategory } from "../api";
import { cycleLabel, formatDate } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

const CATEGORIES: ToolCategory[] = ["조리도구", "조리기구", "칼·도마", "기타"];
const STANDARD_CYCLES: (number | null)[] = [null, 1, 3, 6, 12];
// 식약처는 기간이 아니라 상태(코팅 30% 이상 벗겨짐) 기준으로 교체를 권고한다 → 6개월마다 '점검'을 제안 (스펙 18절)
// "논코팅"·"무코팅"은 코팅 제품이 아니므로 제외한다.
const isCoated = (name: string) => /프라이팬|코팅/.test(name) && !/논코팅|무코팅/.test(name);

interface Props {
  initial: KitchenTool | null;
  onSubmit: (input: KitchenToolInput) => Promise<void>;
  onChecked?: () => Promise<void>;
  onReplaced?: () => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

export default function ToolForm({ initial, onSubmit, onChecked, onReplaced, onDelete, onClose }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState<ToolCategory>(initial?.category ?? "조리도구");
  const [cycle, setCycle] = useState<number | null>(initial?.check_every_months ?? null);
  const [cycleTouched, setCycleTouched] = useState(false);
  const [boughtOn, setBoughtOn] = useState(initial?.bought_on ?? "");
  const { busy, error, run } = useAsyncAction();

  // 저장된 주기가 표준 목록(안 함/1/3/6/12개월)에 없으면 선택 상태를 잃지 않도록 추가해 보여준다.
  const CYCLES =
    initial?.check_every_months && !STANDARD_CYCLES.includes(initial.check_every_months)
      ? [...STANDARD_CYCLES, initial.check_every_months]
      : STANDARD_CYCLES;

  const changeName = (value: string) => {
    setName(value);
    // 새 도구를 입력할 때 코팅 제품이면 6개월 점검을 미리 골라 준다(사용자가 주기를 직접 고르면 건드리지 않음)
    if (!initial && !cycleTouched && isCoated(value)) setCycle(6);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(() => onSubmit({ name: name.trim(), category, bought_on: boughtOn || null, check_every_months: cycle }));
  };

  return (
    <Sheet title={initial ? "도구 수정" : "도구 추가"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        {initial?.check_every_months && (
          <div className={`status-box${initial.is_due ? " due" : ""}`}>
            <span>
              {initial.is_due
                ? "점검할 때가 됐어요"
                : `다음 점검 ${initial.due_on ? formatDate(initial.due_on) : ""}`}
            </span>
            <div className="grid-2">
              <button type="button" className="btn secondary" disabled={busy} onClick={() => onChecked && run(onChecked)}>
                <Icon name="check" size={18} />
                점검했어요
              </button>
              <button
                type="button"
                className="btn secondary"
                disabled={busy}
                onClick={() =>
                  onReplaced && confirm("구매일과 점검일을 오늘로 바꿀까요?") && run(onReplaced)
                }
              >
                교체했어요
              </button>
            </div>
          </div>
        )}

        <label className="field">
          <span className="field-label">이름</span>
          <input
            className="input"
            id="tool-name"
            value={name}
            onChange={(e) => changeName(e.target.value)}
            required
            maxLength={30}
            placeholder="예: 코팅 프라이팬"
            autoFocus
          />
        </label>

        <div className="field" role="group" aria-label="분류">
          <span className="field-label">분류</span>
          <div className="choices">
            {CATEGORIES.map((c) => (
              <button key={c} type="button" className="choice" aria-pressed={category === c} onClick={() => setCategory(c)}>
                {c}
              </button>
            ))}
          </div>
        </div>

        <div className="field" role="group" aria-label="점검 주기">
          <span className="field-label">점검 주기</span>
          <div className="choices">
            {CYCLES.map((c) => (
              <button
                key={c ?? "none"}
                type="button"
                className="choice"
                aria-pressed={cycle === c}
                onClick={() => {
                  setCycle(c);
                  setCycleTouched(true);
                }}
              >
                {c === null ? "안 함" : cycleLabel(c)}
              </button>
            ))}
          </div>
          {isCoated(name) && (
            <p className="hint">코팅이 30% 이상 벗겨졌다면 교체를 권장해요(식약처 기준). 6개월마다 상태를 확인해 보세요.</p>
          )}
        </div>

        <label className="field">
          <span className="field-label">
            구매일 <span className="optional">(선택)</span>
          </span>
          <input
            className="input"
            id="tool-bought"
            type="date"
            value={boughtOn}
            max={localToday()}
            onChange={(e) => setBoughtOn(e.target.value)}
          />
        </label>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn secondary" onClick={onClose}>
            취소
          </button>
          <button className="btn primary" disabled={busy}>
            {busy ? "저장 중…" : "저장"}
          </button>
        </div>
        {onDelete && (
          <button type="button" className="btn danger-text" disabled={busy} onClick={() => run(onDelete)}>
            이 도구 삭제
          </button>
        )}
      </form>
    </Sheet>
  );
}
