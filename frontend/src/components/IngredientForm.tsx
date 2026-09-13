import { useEffect, useRef, useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput } from "../api";

interface Props {
  initial: Ingredient | null;
  onSubmit: (input: IngredientInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const UNITS = ["개", "g", "kg", "ml", "L", "팩", "봉", "병", "모"];

export default function IngredientForm({ initial, onSubmit, onDelete, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(initial?.name ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? "개");
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal(); // StrictMode 이중 실행 대비
  }, []);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
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
      }),
    );
  };

  return (
    <dialog ref={ref} className="sheet" onClose={onClose} aria-labelledby="ingredient-form-title">
      <form onSubmit={submit}>
        <h2 id="ingredient-form-title">{initial ? "재료 수정" : "재료 추가"}</h2>
        <label className="field">
          이름
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={50} placeholder="예: 대파" />
        </label>
        <div className="row">
          <label className="field">
            수량
            <input
              type="number"
              inputMode="decimal"
              min="0.1"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
          </label>
          <label className="field">
            단위
            <input list="units" value={unit} onChange={(e) => setUnit(e.target.value)} maxLength={10} />
            <datalist id="units">
              {UNITS.map((u) => (
                <option key={u} value={u} />
              ))}
            </datalist>
          </label>
        </div>
        <div className="row">
          <label className="field">
            구입일
            <input type="date" value={purchasedOn} onChange={(e) => setPurchasedOn(e.target.value)} required />
          </label>
          <label className="field">
            유통기한 (선택)
            <input type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
          </label>
        </div>
        <button className="btn primary" disabled={busy}>
          {busy ? "저장 중…" : "저장"}
        </button>
        {onDelete && (
          <button type="button" className="btn danger" disabled={busy} onClick={() => run(onDelete)}>
            삭제
          </button>
        )}
        <button type="button" className="btn ghost" onClick={onClose}>
          취소
        </button>
      </form>
    </dialog>
  );
}
