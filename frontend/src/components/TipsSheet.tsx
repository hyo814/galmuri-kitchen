import { useRef, useState, type FormEvent } from "react";
import { api, type CookingTip } from "../api";
import { useAsyncAction } from "../useAsyncAction";
import Sheet from "./Sheet";

const MAX_TIPS = 30; // backend/app/cooking_tips.py MAX_TIPS와 같다
const MAX_LENGTH = 100;

interface Props {
  tips: CookingTip[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function TipsSheet({ tips, onChanged, onClose }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState<{ id: number; body: string } | null>(null);
  const bodyRef = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAsyncAction();

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(async () => {
      await api("/api/cooking-tips", { method: "POST", body: { body } });
      await onChanged();
    });
    if (ok) {
      setBody("");
      bodyRef.current?.focus();
    }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    const ok = await run(async () => {
      await api(`/api/cooking-tips/${editing.id}`, { method: "PATCH", body: { body: editing.body } });
      await onChanged();
    });
    if (ok) setEditing(null);
  };

  const remove = (tip: CookingTip) => {
    if (!confirm("이 비법을 지울까요?")) return;
    run(async () => {
      await api(`/api/cooking-tips/${tip.id}`, { method: "DELETE" });
      await onChanged();
    });
  };

  return (
    <Sheet
      title="우리 집 비법"
      description="적어 두면 AI 레시피를 만들 때 어울리는 것만 넣어드려요."
      action={
        tips.length > 0 && (
          <button className="text-btn strong" onClick={() => setEditMode(!editMode)}>
            {editMode ? "완료" : "편집"}
          </button>
        )
      }
      onClose={onClose}
    >
      <form className="form compact" onSubmit={add}>
        <div className="add-row">
          <input
            ref={bodyRef}
            className="input"
            id="new-tip-body"
            aria-label="비법"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={MAX_LENGTH}
            placeholder="예: 김치찌개엔 청국장 조금 넣는다"
            required
          />
          <button className="btn primary" disabled={busy || tips.length >= MAX_TIPS}>
            추가
          </button>
        </div>
        {tips.length >= MAX_TIPS && <p className="hint">비법은 {MAX_TIPS}개까지 적을 수 있어요.</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>

      {tips.length === 0 ? (
        <p className="hint">아직 적어 둔 비법이 없어요. 위에서 한 줄씩 적어보세요.</p>
      ) : (
        <ul className="plain-list divider-top">
          {tips.map((tip) => (
            <li key={tip.id}>
              {editing?.id === tip.id ? (
                <form className="form compact" onSubmit={save}>
                  <div className="add-row">
                    <input
                      className="input"
                      aria-label="비법 고치기"
                      value={editing.body}
                      onChange={(e) => setEditing({ ...editing, body: e.target.value })}
                      maxLength={MAX_LENGTH}
                      required
                    />
                    <button className="btn primary" disabled={busy}>
                      저장
                    </button>
                  </div>
                  <button type="button" className="text-btn" onClick={() => setEditing(null)}>
                    취소
                  </button>
                </form>
              ) : editMode ? (
                <div className="plain-row">
                  <span className="row-title">{tip.body}</span>
                  <span className="row-end">
                    <button className="text-btn strong" onClick={() => setEditing({ id: tip.id, body: tip.body })}>
                      고치기
                    </button>
                    <button className="btn danger-text inline" disabled={busy} onClick={() => remove(tip)}>
                      삭제
                    </button>
                  </span>
                </div>
              ) : (
                <div className="plain-row">
                  <span className="row-title">{tip.body}</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
