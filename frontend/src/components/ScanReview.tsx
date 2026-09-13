import { useState, type FormEvent } from "react";
import { api, localToday, type ScanKind, type ScanResult, type StorageLocation } from "../api";
import { formatQuantity } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";

interface Row {
  key: number;
  checked: boolean;
  name: string;
  quantity: string;
  unit: string;
  locationId: number;
}

interface Props {
  kind: ScanKind;
  result: ScanResult;
  locations: StorageLocation[];
  onRetake: () => void;
  onAdded: (count: number) => Promise<void>;
}

const DATE_SOURCE: Partial<Record<ScanKind, string>> = {
  receipt: "영수증 날짜로 채웠어요",
  order: "주문 날짜로 채웠어요",
};

export default function ScanReview({ kind, result, locations, onRetake, onAdded }: Props) {
  const today = localToday();
  const [rows, setRows] = useState<Row[]>(() =>
    result.items.map((item, key) => ({
      key,
      checked: true,
      name: item.name,
      quantity: String(item.quantity),
      unit: item.unit,
      // AI가 추정한 보관 종류의 첫 위치, 그런 위치가 없으면 첫 위치 (스펙 15절)
      locationId: (locations.find((l) => l.kind === item.location_kind) ?? locations[0]).id,
    })),
  );
  const [openKey, setOpenKey] = useState<number | null>(null);
  const [purchasedOn, setPurchasedOn] = useState(result.purchased_on ?? today);
  const { busy, error, setError, run } = useAsyncAction();

  const chosen = rows.filter((r) => r.checked);
  const update = (key: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const locationName = (id: number) => locations.find((l) => l.id === id)?.name ?? "";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bad = chosen.find((r) => !r.name.trim() || !(Number(r.quantity) > 0));
    if (bad) {
      setOpenKey(bad.key);
      setError("이름과 수량(0보다 큰 숫자)을 확인해 주세요.");
      return;
    }
    if (!purchasedOn || purchasedOn > today) {
      setError("구입일은 오늘이나 그 전 날짜로 골라 주세요.");
      return;
    }
    run(async () => {
      const items = chosen.map((r) => ({
        name: r.name.trim(),
        quantity: Number(r.quantity),
        unit: r.unit.trim() || "개",
        purchased_on: purchasedOn,
        location_id: r.locationId,
      }));
      await api("/api/ingredients/bulk", { method: "POST", body: { items } });
      await onAdded(items.length);
    });
  };

  return (
    <form className="form scan-review" onSubmit={submit}>
      {result.sample && (
        <span className="badge old scan-sample">
          <Icon name="info" size={16} />
          예시 결과예요 (API 키 없음)
        </span>
      )}

      <label className="field scan-date">
        <span className="field-label">구입일</span>
        <input
          className="input"
          type="date"
          value={purchasedOn}
          max={today}
          required
          onChange={(e) => setPurchasedOn(e.target.value)}
        />
        {result.purchased_on && purchasedOn === result.purchased_on && DATE_SOURCE[kind] && (
          <span className="hint">
            <Icon name="check" size={14} />
            {DATE_SOURCE[kind]}
          </span>
        )}
      </label>

      <ul className="scan-items">
        {rows.map((row) => {
          const open = openKey === row.key;
          const toggle = () => setOpenKey(open ? null : row.key);
          return (
            <li key={row.key} className={`scan-item${row.checked ? "" : " off"}${open ? " open" : ""}`}>
              <button
                type="button"
                className={`checkbox${row.checked ? "" : " off"}`}
                role="checkbox"
                aria-checked={row.checked}
                aria-label={`${row.name || "재료"} 넣기`}
                onClick={() => update(row.key, { checked: !row.checked })}
              >
                <span>{row.checked && <Icon name="check" size={16} />}</span>
              </button>
              {open ? (
                <input
                  className="input"
                  aria-label="이름"
                  value={row.name}
                  maxLength={50}
                  onChange={(e) => update(row.key, { name: e.target.value })}
                />
              ) : (
                <button type="button" className="row-main scan-item-main" onClick={toggle}>
                  <span className="row-title">{row.name}</span>
                  <span className="row-sub">
                    {formatQuantity(Number(row.quantity) || 0)}
                    {row.unit} · {locationName(row.locationId)}
                  </span>
                </button>
              )}
              <button
                type="button"
                className="icon-btn"
                aria-label={open ? "접기" : `${row.name} 고치기`}
                aria-expanded={open}
                onClick={toggle}
              >
                <Icon name={open ? "up" : "down"} />
              </button>
              {open && (
                <div className="scan-edit">
                  <label className="field">
                    <span className="field-label">수량</span>
                    <input
                      className="input"
                      type="number"
                      inputMode="decimal"
                      min="0.01"
                      step="any"
                      value={row.quantity}
                      onChange={(e) => update(row.key, { quantity: e.target.value })}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">단위</span>
                    <input
                      className="input"
                      value={row.unit}
                      maxLength={10}
                      onChange={(e) => update(row.key, { unit: e.target.value })}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">보관 위치</span>
                    <select
                      className="input"
                      value={row.locationId}
                      onChange={(e) => update(row.key, { locationId: Number(e.target.value) })}
                    >
                      {locations.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="scan-foot">
        <div className="actions">
          <button type="button" className="btn secondary" disabled={busy} onClick={onRetake}>
            다시 찍기
          </button>
          <button className="btn primary" disabled={busy || chosen.length === 0}>
            {busy ? "넣는 중…" : `${chosen.length}개 재고에 넣기`}
          </button>
        </div>
      </div>
    </form>
  );
}
