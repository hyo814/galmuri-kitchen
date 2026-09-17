import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { localToday, type DeleteReason, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import { addDays, KIND_LABEL, withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import ShoppingAddButton, { cut } from "./ShoppingAddButton";
import Sheet from "./Sheet";

const MAX_PRICE = 10_000_000;

// value가 null이면 이유 없이(그냥) 지운다 — 기본값(시안 6)
const DELETE_REASONS: { value: DeleteReason | null; label: string; note?: string }[] = [
  { value: "eaten", label: "다 먹었어요" },
  { value: "discarded", label: "버렸어요", note: "집밥 리포트에 세요" },
  { value: null, label: "그냥 지우기" },
];

// 라디오 그룹 키보드: 위·아래 화살표는 포커스만 옮기고, 고르기는 Space·Enter·탭으로 (roving tabindex, More.tsx ThemeSheet와 같은 방식)
function onReasonKeyDown(e: KeyboardEvent<HTMLDivElement>) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const radios = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')];
  const i = radios.indexOf(document.activeElement as HTMLElement);
  radios[(i + (e.key === "ArrowDown" ? 1 : -1) + radios.length) % radios.length].focus();
}

interface Props {
  initial: Ingredient | null;
  initialName?: string;
  locations: StorageLocation[];
  defaultLocationId: number;
  onSubmit: (input: IngredientInput, keepOpen: boolean) => Promise<void>;
  /** reason: 지우는 이유(선택, 월간 리포트용). null이면 이유 없이 삭제 */
  onDelete?: (reason: DeleteReason | null) => Promise<void>;
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
  const [price, setPrice] = useState(initial?.price != null ? String(initial.price) : "");
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  // 기억 안 나요: 구입일 없이 저장(null). 구입일 모름인 재료를 고치면 켜진 채 시작 (시안 docs/design/scan-multi)
  const [unknownDate, setUnknownDate] = useState(initial?.purchased_on === null);
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [locationId, setLocationId] = useState(initial?.location_id ?? defaultLocationId);
  const [lastAdded, setLastAdded] = useState("");
  // 삭제 확인 시트: null이면 닫힘. reason은 고른 이유(다시 누르면 선택 해제)
  const [deleting, setDeleting] = useState<{ reason: DeleteReason | null } | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const { busy, error, setError, run } = useAsyncAction();

  const qty = Number(quantity) || 0;
  const usedUp = !!initial && !!onDelete && quantity.trim() !== "" && Number(quantity) === 0;

  const input = (): IngredientInput => ({
    name: name.trim(),
    quantity: qty,
    unit: unit.trim() || "개",
    purchased_on: unknownDate ? null : purchasedOn,
    expires_on: expiresOn || null,
    price: price === "" ? null : Number(price),
    location_id: locationId,
  });

  const priceTooHigh = price !== "" && Number(price) > MAX_PRICE;

  // 고치던 내용이 있으면 `장보기 보기`로 떠나기 전에 묻는다(RecipeForm과 같은 문구)
  const snapshot = JSON.stringify([name, quantity, unit, price, purchasedOn, unknownDate, expiresOn, locationId]);
  const [start] = useState(snapshot);
  const canLeave = () => snapshot === start || confirm("작성 중인 내용이 사라져요. 나갈까요?");

  const changeQuantity = (direction: 1 | -1) => {
    const min = initial ? 0 : 0.01;
    const next = Math.max(min, Math.round((qty + direction * stepFor(unit, qty)) * 100) / 100);
    setQuantity(String(next));
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (priceTooHigh) {
      setError("가격은 0~10,000,000원 사이 숫자로 입력해주세요.");
      return;
    }
    if (usedUp) setDeleting({ reason: "eaten" }); // 수량 0 = 다 먹었어요(usedUp이면 onDelete가 있다)
    else run(() => onSubmit(input(), false));
  };

  // 장 본 뒤 여러 개를 이어서 넣는 흐름: 이름·수량·유통기한만 비우고 단위·위치·구입일은 유지 (사용성 점검 C1)
  const saveAndContinue = async () => {
    if (nameRef.current?.form && !nameRef.current.form.reportValidity()) return;
    if (priceTooHigh) {
      setError("가격은 0~10,000,000원 사이 숫자로 입력해주세요.");
      return;
    }
    const added = name.trim();
    setLastAdded("");
    if (await run(() => onSubmit(input(), true))) {
      setName("");
      setQuantity("1");
      setExpiresOn("");
      setPrice("");
      setLastAdded(added);
      nameRef.current?.focus();
    }
  };

  const confirmDelete = async () => {
    if (!onDelete || !deleting) return;
    await run(() => onDelete(deleting.reason));
    setDeleting(null); // 실패하면 오류는 재료 수정 시트에 보인다(성공하면 시트가 통째로 닫힌다)
  };

  return (
    <>
      {/* 고치기(initial 있음)는 이름 칸이 첫 칸이라도 제목에 포커스한다 — 안 그러면 <dialog>가 autoFocus 없이도
          첫 포커스 가능 요소(이름 칸)로 포커스를 보내 열자마자 키보드가 올라온다(CookEditSheet와 같은 가드, 리뷰 발견) */}
      <Sheet title={initial ? "재료 수정" : "재료 추가"} focusTitle={!!initial} onClose={onClose}>
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

          <label className="field">
            <span className="field-label">
              가격 <span className="optional">(선택)</span>
            </span>
            <div className="input-suffix">
              <input
                className="input"
                id="ingredient-price"
                inputMode="numeric"
                value={price}
                placeholder="모르면 비워두세요"
                maxLength={8}
                onChange={(e) => setPrice(e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))}
              />
              <span className="suffix">원</span>
            </div>
          </label>

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
            <div className="field">
              <label className="field-label" htmlFor="ingredient-purchased">
                구입일
              </label>
              <input
                className="input"
                id="ingredient-purchased"
                type="date"
                value={unknownDate ? "" : purchasedOn}
                max={localToday()}
                disabled={unknownDate}
                onChange={(e) => setPurchasedOn(e.target.value)}
                required={!unknownDate}
              />
              <button type="button" className="choice" aria-pressed={unknownDate} onClick={() => setUnknownDate(!unknownDate)}>
                {unknownDate && <Icon name="check" size={16} />}
                기억 안 나요
              </button>
            </div>
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
                aria-pressed={!unknownDate && expiresOn === addDays(purchasedOn, days)}
                disabled={!purchasedOn || unknownDate}
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
              {busy ? "저장 중…" : usedUp ? "다 먹었어요 (삭제)" : "저장"}
            </button>
          </div>
          {initial && (
            <ShoppingAddButton
              source={initial.status === "urgent" || initial.status === "danger" ? "urgent" : "manual"}
              items={[
                { name: initial.name, quantity: initial.quantity > 0 ? initial.quantity : undefined, unit: cut(initial.unit, 10) },
              ]}
              label="장보기에 담기"
              canLeave={canLeave}
            />
          )}
          {onDelete && (
            <button type="button" className="btn danger-text" disabled={busy} onClick={() => setDeleting({ reason: null })}>
              이 재료 삭제
            </button>
          )}
        </form>
      </Sheet>
      {/* 시트 안이 아니라 옆에 둔다: React에서 안쪽 dialog의 close가 바깥 시트 onClose까지 올라가지 않게 */}
      {deleting && initial && (
        <Sheet
          title={`${initial.name} 지우기`}
          description={[
            initial.days_since_purchase !== null && `구입 ${initial.days_since_purchase}일째`,
            KIND_LABEL[initial.location_kind],
          ]
            .filter(Boolean)
            .join(" · ")}
          onClose={() => setDeleting(null)}
        >
          <div className="ck-reason" role="radiogroup" aria-label="지우는 이유" onKeyDown={onReasonKeyDown}>
            {DELETE_REASONS.map((r) => {
              const checked = deleting.reason === r.value;
              return (
                <button
                  key={r.label}
                  type="button"
                  className="ck-reason-opt"
                  role="radio"
                  aria-checked={checked}
                  tabIndex={checked ? 0 : -1}
                  onClick={() => setDeleting({ reason: r.value })}
                >
                  <span>{r.label}</span>
                  {r.note && <small>{r.note}</small>}
                </button>
              );
            })}
          </div>
          <div className="actions">
            <button type="button" className="btn outline" disabled={busy} onClick={() => setDeleting(null)}>
              취소
            </button>
            <button type="button" className="btn danger-text" disabled={busy} onClick={confirmDelete}>
              {busy ? "지우는 중…" : "지우기"}
            </button>
          </div>
        </Sheet>
      )}
    </>
  );
}
