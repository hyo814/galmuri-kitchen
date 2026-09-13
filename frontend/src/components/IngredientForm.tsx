import { useRef, useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import { addDays, withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  initial: Ingredient | null;
  initialName?: string;
  locations: StorageLocation[];
  defaultLocationId: number;
  onSubmit: (input: IngredientInput, keepOpen: boolean) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const UNITS = ["개", "g", "ml", "팩", "봉", "병", "모", "단"];
const COUNT_UNITS = new Set(["개", "팩", "봉", "병", "모", "단"]);
const EXPIRY_PRESETS = [1, 3, 7];

/** −/+ 한 번에 바뀌는 양: 개수 단위는 1(1개 이하에서는 0.5), g·ml은 100, 그 외 0.5 */
function stepFor(unit: string, quantity: number) {
  if (COUNT_UNITS.has(unit)) return quantity <= 1 ? 0.5 : 1;
  if (unit === "g" || unit === "ml") return 100;
  return 0.5;
}

export default function IngredientForm({
  initial,
  initialName,
  locations,
  defaultLocationId,
  onSubmit,
  onDelete,
  onClose,
}: Props) {
  const [name, setName] = useState(initial?.name ?? initialName ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? "개");
  const [customUnit, setCustomUnit] = useState(!!initial && !UNITS.includes(initial.unit));
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [locationId, setLocationId] = useState(initial?.location_id ?? defaultLocationId);
  const [lastAdded, setLastAdded] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAsyncAction();

  const qty = Number(quantity) || 0;
  const usedUp = !!initial && !!onDelete && quantity.trim() !== "" && Number(quantity) === 0;

  const input = (): IngredientInput => ({
    name: name.trim(),
    quantity: qty,
    unit: unit.trim() || "개",
    purchased_on: purchasedOn,
    expires_on: expiresOn || null,
    location_id: locationId,
  });

  const changeQuantity = (direction: 1 | -1) => {
    const min = initial ? 0 : 0.01;
    const next = Math.max(min, Math.round((qty + direction * stepFor(unit, qty)) * 100) / 100);
    setQuantity(String(next));
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (usedUp && onDelete) run(onDelete);
    else run(() => onSubmit(input(), false));
  };

  // 장 본 뒤 여러 개를 이어서 넣는 흐름: 이름·수량·유통기한만 비우고 단위·위치·구입일은 유지 (사용성 점검 C1)
  const saveAndContinue = async () => {
    if (nameRef.current?.form && !nameRef.current.form.reportValidity()) return;
    const added = name.trim();
    setLastAdded("");
    if (await run(() => onSubmit(input(), true))) {
      setName("");
      setQuantity("1");
      setExpiresOn("");
      setLastAdded(added);
      nameRef.current?.focus();
    }
  };

  return (
    <Sheet title={initial ? "재료 수정" : "재료 추가"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        {lastAdded && (
          <p className="notice" role="status">
            {withJosa(lastAdded, "을", "를")} 추가했어요. 다음 재료를 입력하세요.
          </p>
        )}

        <label className="field">
          <span className="field-label">이름</span>
          <input
            ref={nameRef}
            className="input"
            id="ingredient-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={50}
            placeholder="예: 대파"
            autoFocus={!initial}
          />
        </label>

        <div className="field">
          <span className="field-label" id="ingredient-quantity-label">
            수량
          </span>
          <div className="stepper">
            <button type="button" className="icon-btn" aria-label="수량 줄이기" onClick={() => changeQuantity(-1)}>
              <Icon name="minus" />
            </button>
            <input
              className="input"
              id="ingredient-quantity"
              aria-labelledby="ingredient-quantity-label"
              type="number"
              inputMode="decimal"
              min={initial ? "0" : "0.01"}
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
            <button type="button" className="icon-btn" aria-label="수량 늘리기" onClick={() => changeQuantity(1)}>
              <Icon name="plus" />
            </button>
          </div>
        </div>

        <div className="field" role="group" aria-label="단위">
          <span className="field-label">단위</span>
          <div className="choices">
            {UNITS.map((u) => (
              <button
                key={u}
                type="button"
                className="choice"
                aria-pressed={!customUnit && unit === u}
                onClick={() => {
                  setCustomUnit(false);
                  setUnit(u);
                }}
              >
                {u}
              </button>
            ))}
            <button
              type="button"
              className="choice"
              aria-pressed={customUnit}
              onClick={() => {
                setCustomUnit(true);
                if (UNITS.includes(unit)) setUnit("");
              }}
            >
              직접 입력
            </button>
          </div>
          {customUnit && (
            <input
              className="input"
              id="ingredient-unit"
              aria-label="단위 직접 입력"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              maxLength={10}
              placeholder="예: 줄, 판, kg"
            />
          )}
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
              max={localToday()}
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
        <div className="choices" role="group" aria-label="유통기한 빠르게 넣기">
          {EXPIRY_PRESETS.map((days) => (
            <button
              key={days}
              type="button"
              className="choice"
              aria-pressed={expiresOn === addDays(purchasedOn, days)}
              disabled={!purchasedOn}
              onClick={() => setExpiresOn(addDays(purchasedOn, days))}
            >
              구입일 +{days}일
            </button>
          ))}
          {expiresOn && (
            <button type="button" className="choice" onClick={() => setExpiresOn("")}>
              유통기한 지우기
            </button>
          )}
        </div>

        {name.includes("우유") && !expiresOn && (
          <p className="hint">우유는 포장에 적힌 소비기한을 입력하면 가장 정확해요.</p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!initial && (
          <button type="button" className="btn secondary" disabled={busy} onClick={saveAndContinue}>
            <Icon name="plus" />
            저장하고 계속 추가
          </button>
        )}
        <div className="actions">
          <button type="button" className="btn secondary" onClick={onClose}>
            {lastAdded ? "닫기" : "취소"}
          </button>
          <button className={`btn ${usedUp ? "used-up" : "primary"}`} disabled={busy}>
            {busy ? "저장 중…" : usedUp ? "다 썼어요 (삭제)" : "저장"}
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
