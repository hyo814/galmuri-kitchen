import { useState, type FormEvent } from "react";
import { api, type Staple } from "../api";
import Icon from "./Icon";
import Sheet from "./Sheet";

const CATEGORIES = ["조미료", "야채", "기타"];

interface Props {
  staples: Staple[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function StaplesSheet({ staples, onChanged, onClose }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);
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

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => api("/api/staples", { method: "POST", body: { name, category } }))) setName("");
  };

  const groups = [...CATEGORIES, ...new Set(staples.map((s) => s.category).filter((c) => !CATEGORIES.includes(c)))]
    .map((c) => ({ category: c, items: staples.filter((s) => s.category === c) }))
    .filter((g) => g.items.length > 0);

  return (
    <Sheet
      title="필수품"
      description="항상 있어야 하는 재료예요. 떨어지면 냉장고 화면에서 알려드려요."
      action={
        staples.length > 0 && (
          <button className="text-btn strong" onClick={() => setEditMode(!editMode)}>
            {editMode ? "완료" : "편집"}
          </button>
        )
      }
      onClose={onClose}
    >
      {groups.length === 0 ? (
        <p className="hint">아직 등록한 필수품이 없어요. 아래에서 추가해 보세요.</p>
      ) : (
        <div className="groups">
          {groups.map((group) => (
            <section key={group.category} className="group" aria-label={group.category}>
              <h3 className="section-label">{group.category}</h3>
              <ul className="plain-list">
                {group.items.map((staple) => (
                  <li key={staple.id} className="plain-row">
                    <span className="staple-name">{staple.name}</span>
                    {editMode ? (
                      <button
                        className="btn danger-text inline"
                        disabled={busy}
                        onClick={() => run(() => api(`/api/staples/${staple.id}`, { method: "DELETE" }))}
                      >
                        삭제
                      </button>
                    ) : staple.in_stock ? (
                      <span className="stock-ok">
                        <Icon name="check" size={16} />
                        있음
                      </span>
                    ) : (
                      <span className="badge danger">떨어짐</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form className="form compact divider-top" onSubmit={add}>
        <div className="add-row">
          <input
            className="input"
            id="new-staple-name"
            aria-label="필수품 이름"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={50}
            placeholder="예: 고춧가루"
            required
          />
          <button className="btn primary" disabled={busy}>
            추가
          </button>
        </div>
        <div className="choices" role="group" aria-label="분류">
          {CATEGORIES.map((c) => (
            <button key={c} type="button" className="choice" aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c}
            </button>
          ))}
        </div>
      </form>
    </Sheet>
  );
}
