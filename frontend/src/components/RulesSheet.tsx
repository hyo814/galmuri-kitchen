import { useState, type FormEvent } from "react";
import { api, type ItemRule } from "../api";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Draft {
  keyword: string;
  warn: string;
  danger: string;
}

const EMPTY: Draft = { keyword: "", warn: "", danger: "" };

const toBody = (d: Draft) => ({ keyword: d.keyword, warn_days: Number(d.warn), danger_days: Number(d.danger) });

function RuleFields({ draft, onChange, idPrefix }: { draft: Draft; onChange: (d: Draft) => void; idPrefix: string }) {
  return (
    <>
      <input
        className="input"
        id={`${idPrefix}-keyword`}
        aria-label="품목 이름"
        placeholder="예: 닭가슴살"
        maxLength={20}
        required
        value={draft.keyword}
        onChange={(e) => onChange({ ...draft, keyword: e.target.value })}
      />
      <div className="grid-2">
        <label className="field">
          <span className="field-label">노랑 (구입 후 일)</span>
          <input
            className="input"
            id={`${idPrefix}-warn`}
            type="number"
            inputMode="numeric"
            min="1"
            max="3650"
            step="1"
            required
            value={draft.warn}
            onChange={(e) => onChange({ ...draft, warn: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field-label">빨강 (구입 후 일)</span>
          <input
            className="input"
            id={`${idPrefix}-danger`}
            type="number"
            inputMode="numeric"
            min="1"
            max="3650"
            step="1"
            required
            value={draft.danger}
            onChange={(e) => onChange({ ...draft, danger: e.target.value })}
          />
        </label>
      </div>
    </>
  );
}

interface Props {
  rules: ItemRule[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function RulesSheet({ rules, onChanged, onClose }: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<Draft>(EMPTY);
  const [newDraft, setNewDraft] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (rule: ItemRule) => {
    setEditingId(rule.id);
    setEditDraft({ keyword: rule.keyword, warn: String(rule.warn_days), danger: String(rule.danger_days) });
    setError("");
  };

  const saveEdit = async (e: FormEvent) => {
    e.preventDefault();
    const body = toBody(editDraft);
    if (await run(() => api(`/api/item-rules/${editingId}`, { method: "PATCH", body }))) setEditingId(null);
  };

  const remove = async (rule: ItemRule) => {
    if (!confirm(`${rule.keyword} 경고를 삭제할까요?`)) return;
    if (await run(() => api(`/api/item-rules/${rule.id}`, { method: "DELETE" }))) setEditingId(null);
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const body = toBody(newDraft);
    if (await run(() => api("/api/item-rules", { method: "POST", body }))) setNewDraft(EMPTY);
  };

  return (
    <Sheet
      title="품목별 경고"
      description="구입일부터 센 날짜예요. 포장에 소비기한이 적혀 있으면 재료에 직접 입력하는 게 가장 정확해요."
      onClose={onClose}
    >
      <ul className="plain-list">
        {rules.map((rule) => (
          <li key={rule.id}>
            {editingId === rule.id ? (
              <form className="form edit-block" onSubmit={saveEdit}>
                <RuleFields draft={editDraft} onChange={setEditDraft} idPrefix={`rule-${rule.id}`} />
                <div className="actions">
                  <button type="button" className="btn secondary" onClick={() => setEditingId(null)}>
                    취소
                  </button>
                  <button className="btn primary" disabled={busy}>
                    저장
                  </button>
                </div>
                <button type="button" className="btn danger-text" disabled={busy} onClick={() => remove(rule)}>
                  이 경고 삭제
                </button>
              </form>
            ) : (
              <div className="plain-row location-row">
                <div className="row-main">
                  <span className="row-title">
                    {rule.keyword}
                    {rule.source === "mfds" && <span className="source-tag">식약처 참고값</span>}
                  </span>
                  <span className="row-sub">
                    노랑 {rule.warn_days}일 · 빨강 {rule.danger_days}일
                  </span>
                </div>
                <button className="icon-btn" aria-label={`${rule.keyword} 수정`} onClick={() => startEdit(rule)}>
                  <Icon name="more" />
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form className="form compact divider-top" onSubmit={add}>
        <span className="field-label">새 경고</span>
        <RuleFields draft={newDraft} onChange={setNewDraft} idPrefix="new-rule" />
        <button className="btn primary" disabled={busy}>
          경고 추가
        </button>
      </form>
    </Sheet>
  );
}
