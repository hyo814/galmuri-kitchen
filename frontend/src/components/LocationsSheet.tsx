import { useState, type FormEvent } from "react";
import { api, type LocationKind, type StorageLocation } from "../api";
import { KIND_LABEL } from "../format";
import Icon from "./Icon";
import Sheet from "./Sheet";

const KINDS: LocationKind[] = ["fridge", "freezer", "room"];

function KindPicker({ value, onChange }: { value: LocationKind; onChange: (kind: LocationKind) => void }) {
  return (
    <div className="segmented" role="group" aria-label="보관 종류">
      {KINDS.map((kind) => (
        <button key={kind} type="button" aria-pressed={value === kind} onClick={() => onChange(kind)}>
          {KIND_LABEL[kind]}
        </button>
      ))}
    </div>
  );
}

interface Props {
  locations: StorageLocation[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function LocationsSheet({ locations, onChanged, onClose }: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editKind, setEditKind] = useState<LocationKind>("fridge");
  const [newName, setNewName] = useState("");
  const [newKind, setNewKind] = useState<LocationKind>("fridge");
  const [busy, setBusy] = useState(false);
  const [editError, setEditError] = useState("");
  const [error, setError] = useState("");

  const run = async (action: () => Promise<unknown>, setFieldError: (message: string) => void) => {
    setBusy(true);
    setFieldError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (e) {
      setFieldError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (location: StorageLocation) => {
    setEditingId(location.id);
    setEditName(location.name);
    setEditKind(location.kind);
    setEditError("");
  };

  const saveEdit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { name: editName, kind: editKind };
    if (await run(() => api(`/api/locations/${editingId}`, { method: "PATCH", body }), setEditError)) setEditingId(null);
  };

  const remove = async (location: StorageLocation) => {
    if (!confirm(`${location.name}을(를) 삭제할까요?`)) return;
    if (await run(() => api(`/api/locations/${location.id}`, { method: "DELETE" }), setEditError)) setEditingId(null);
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const body = { name: newName, kind: newKind };
    if (await run(() => api("/api/locations", { method: "POST", body }), setError)) setNewName("");
  };

  return (
    <Sheet title="위치 관리" onClose={onClose}>
      <ul className="plain-list">
        {locations.map((location) => (
          <li key={location.id}>
            {editingId === location.id ? (
              <form className="form edit-block" onSubmit={saveEdit}>
                <input
                  className="input"
                  id={`location-name-${location.id}`}
                  aria-label="위치 이름"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  maxLength={20}
                  required
                />
                <KindPicker value={editKind} onChange={setEditKind} />
                <div className="actions">
                  <button type="button" className="btn secondary" onClick={() => setEditingId(null)}>
                    취소
                  </button>
                  <button className="btn primary" disabled={busy}>
                    저장
                  </button>
                </div>
                <button type="button" className="btn danger-text" disabled={busy} onClick={() => remove(location)}>
                  이 위치 삭제
                </button>
                {editError && (
                  <p className="error" role="alert">
                    {editError}
                  </p>
                )}
              </form>
            ) : (
              <div className="plain-row location-row">
                <div className="row-main">
                  <span className="row-title">{location.name}</span>
                  <span className="row-sub">
                    {KIND_LABEL[location.kind]} · {location.item_count > 0 ? `재료 ${location.item_count}개` : "비어 있음"}
                  </span>
                </div>
                <button className="icon-btn" aria-label={`${location.name} 수정`} onClick={() => startEdit(location)}>
                  <Icon name="more" />
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="hint">재료가 들어 있는 위치는 비운 뒤에 삭제할 수 있어요.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <form className="form compact divider-top" onSubmit={add}>
        <label className="field">
          <span className="field-label">새 위치</span>
          <input
            className="input"
            id="new-location-name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={20}
            placeholder="예: 베란다"
            required
          />
        </label>
        <KindPicker value={newKind} onChange={setNewKind} />
        <p className="hint">냉장은 구입 7일, 냉동은 60일이 지나면 '오래됨'으로 표시해요. 실온은 표시하지 않아요.</p>
        <button className="btn primary" disabled={busy}>
          위치 추가
        </button>
      </form>
    </Sheet>
  );
}
