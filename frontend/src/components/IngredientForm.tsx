import { useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  initial: Ingredient | null;
  locations: StorageLocation[];
  defaultLocationId: number;
  onSubmit: (input: IngredientInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const UNITS = ["개", "g", "kg", "ml", "L", "팩", "봉", "병", "모", "단"];

export default function IngredientForm({ initial, locations, defaultLocationId, onSubmit, onDelete, onClose }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? "개");
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [locationId, setLocationId] = useState(initial?.location_id ?? defaultLocationId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(() =>
      onSubmit({
        name: name.trim(),
        quantity: Number(quantity),
        unit: unit.trim() || "개",
        purchased_on: purchasedOn,
        expires_on: expiresOn || null,
        location_id: locationId,
      }),
    );
  };

  return (
    <Sheet title={initial ? "재료 수정" : "재료 추가"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">이름</span>
          <input
            className="input"
            id="ingredient-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={50}
            placeholder="예: 대파"
          />
        </label>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">수량</span>
            <input
              className="input"
              id="ingredient-quantity"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">단위</span>
            <input
              className="input"
              id="ingredient-unit"
              list="units"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              maxLength={10}
            />
            <datalist id="units">
              {UNITS.map((u) => (
                <option key={u} value={u} />
              ))}
            </datalist>
          </label>
        </div>
        <div className="field" role="group" aria-label="보관 위치">
          <span className="field-label">보관 위치</span>
          <div className="choices">
            {locations.map((location) => (
              <button
                key={location.id}
                type="button"
                className="choice"
                aria-pressed={locationId === location.id}
                onClick={() => setLocationId(location.id)}
              >
                {locationId === location.id && <Icon name="check" size={16} />}
                {location.name}
              </button>
            ))}
          </div>
        </div>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">구입일</span>
            <input
              className="input"
              id="ingredient-purchased"
              type="date"
              value={purchasedOn}
              onChange={(e) => setPurchasedOn(e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">
              유통기한 <span className="optional">(선택)</span>
            </span>
            <input
              className="input"
              id="ingredient-expires"
              type="date"
              value={expiresOn}
              onChange={(e) => setExpiresOn(e.target.value)}
            />
          </label>
        </div>
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
            이 재료 삭제
          </button>
        )}
      </form>
    </Sheet>
  );
}
