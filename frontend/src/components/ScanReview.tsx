import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  localToday,
  type LocationKind,
  type ScanKind,
  type ScanResult,
  type StorageLocation,
} from "../api";
import { formatQuantity, formatWon, namesLabel } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import { forgetResources } from "../useResource";
import Icon from "./Icon";
import Sheet from "./Sheet";

// backend/app/locations.py INVALID_LOCATION, backend/app/ingredients.py의 커밋 시 위치 사라짐 오류.
// 둘 중 하나면 부모가 들고 있는 locations 목록이 낡았다는 뜻이라 다시 불러와야 한다.
const INVALID_LOCATION = "보관 위치를 다시 선택해주세요.";
const LOCATION_CHANGED = "선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요.";
const MAX_PRICE = 10_000_000;
const MATCH_MAX = 50; // backend/app/shopping.py BULK_MAX

/** 영수증·주문으로 넣은 재료와 이름이 맞는 장보기 항목. on: `장보기에서 빼기`에 넣을지(짧은 이름은 잘못 맞을 수 있어 하나씩 끈다) */
interface Matched {
  count: number;
  items: { id: number; name: string; on: boolean }[];
}

interface Row {
  key: number;
  checked: boolean;
  name: string;
  quantity: string;
  unit: string;
  price: string;
  locationId: number;
  locationKind: LocationKind;
}

interface Props {
  kind: ScanKind;
  result: ScanResult;
  locations: StorageLocation[];
  onRetake: () => void;
  onAdded: (count: number) => Promise<void>;
  onLocationsStale?: () => void;
}

const DATE_SOURCE: Partial<Record<ScanKind, string>> = {
  receipt: "영수증 날짜로 채웠어요",
  order: "주문 날짜로 채웠어요",
};

export default function ScanReview({ kind, result, locations, onRetake, onAdded, onLocationsStale }: Props) {
  const today = localToday();
  const [rows, setRows] = useState<Row[]>(() =>
    result.items.map((item, key) => ({
      key,
      checked: true,
      name: item.name,
      quantity: String(item.quantity),
      unit: item.unit,
      price: item.price != null ? String(item.price) : "",
      // AI가 추정한 보관 종류의 첫 위치, 그런 위치가 없으면 첫 위치 (스펙 15절)
      locationId: (locations.find((l) => l.kind === item.location_kind) ?? locations[0]).id,
      locationKind: item.location_kind,
    })),
  );
  const [openKey, setOpenKey] = useState<number | null>(null);

  // 보관 위치가 새로 로드된 뒤(onLocationsStale), 사라진 위치를 고르고 있던 행은 같은 종류의
  // 첫 위치로, 그런 위치도 없으면 첫 위치로 되돌린다(위 초기값과 같은 규칙, 스펙 15절).
  useEffect(() => {
    setRows((prev) =>
      prev.map((r) =>
        locations.some((l) => l.id === r.locationId)
          ? r
          : { ...r, locationId: (locations.find((l) => l.kind === r.locationKind) ?? locations[0]).id },
      ),
    );
  }, [locations]);
  const [purchasedOn, setPurchasedOn] = useState(result.purchased_on ?? today);
  const { busy, error, setError, run } = useAsyncAction();
  const [matched, setMatched] = useState<Matched | null>(null);
  const follow = useAsyncAction();
  // 제안 시트는 어떻게 닫혀도(버튼·Esc·배경, 빼는 중·실패 뒤 포함) 한 번만 onAdded로 이어 간다
  const finished = useRef(false);
  const finish = (count: number) => {
    if (finished.current) return;
    finished.current = true;
    setMatched(null);
    return onAdded(count);
  };

  const chosen = rows.filter((r) => r.checked);
  const update = (key: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const locationName = (id: number) => locations.find((l) => l.id === id)?.name ?? "";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bad = chosen.find((r) => !r.name.trim() || !(Number(r.quantity) > 0));
    if (bad) {
      setOpenKey(bad.key);
      setError("이름을 채우고 수량은 0보다 큰 숫자로 입력해주세요.");
      return;
    }
    if (!purchasedOn || purchasedOn > today) {
      setError("구입일은 오늘이나 그 전 날짜로 골라주세요.");
      return;
    }
    const badPrice = chosen.find((r) => r.price !== "" && Number(r.price) > MAX_PRICE);
    if (badPrice) {
      setOpenKey(badPrice.key);
      setError("가격은 0~10,000,000원 사이 숫자로 입력해주세요.");
      return;
    }
    run(async () => {
      const items = chosen.map((r) => ({
        name: r.name.trim(),
        quantity: Number(r.quantity),
        unit: r.unit.trim() || "개",
        purchased_on: purchasedOn,
        price: r.price === "" ? null : Number(r.price),
        location_id: r.locationId,
      }));
      try {
        await api("/api/ingredients/bulk", { method: "POST", body: { items } });
      } catch (e) {
        // errors[]가 있으면(항목별 오류) 그 행을 펼치고 그 항목의 오류만 보여 준다.
        // 없으면(상한·위치 변경처럼 항목과 무관한 오류) 서버가 준 top-level error를 그대로 보여 준다.
        const first = e instanceof ApiError ? e.errors?.[0] : undefined;
        const row = first && chosen[first.index];
        const message = row ? first.error : e instanceof ApiError ? e.message : undefined;
        if (message === INVALID_LOCATION || message === LOCATION_CHANGED) onLocationsStale?.();
        if (row) {
          setOpenKey(row.key);
          throw new Error(first.error);
        }
        throw e;
      }
      if (kind !== "fridge") {
        // 스펙 16절: 체크해서 또 넣지 않게 목록에 있던 걸 산 것으로 옮길지 묻는다. 찾기가 실패해도 재고 등록은 끝났다.
        // ponytail: 이름은 앞의 50개만 맞춰 본다(match 상한). 한 장에 50개 넘는 영수증이 흔해지면 나눠 보낸다.
        const found = await api<{ items: { id: number; name: string }[] }>("/api/shopping/items/match", {
          method: "POST",
          body: { names: items.slice(0, MATCH_MAX).map((i) => i.name) },
        }).catch(() => null);
        if (found?.items.length) {
          setMatched({ count: items.length, items: found.items.map((i) => ({ ...i, on: true })) });
          return;
        }
      }
      await onAdded(items.length);
    });
  };

  const keep = () => matched && finish(matched.count);
  const markStocked = () =>
    matched &&
    follow.run(async () => {
      const ids = matched.items.filter((i) => i.on).map((i) => i.id);
      await api("/api/shopping/items/mark-stocked", { method: "POST", body: { ids } });
      forgetResources("/api/shopping");
      await finish(matched.count);
    });

  return (
    <>
      <form className="form scan-review" onSubmit={submit}>
        {result.sample && (
          <span className="badge info scan-sample">
            <Icon name="info" size={16} />
            예시 결과예요 · 사진을 읽지 않았어요
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
            const editId = `scan-edit-${row.key}`;
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
                  <button
                    type="button"
                    className="row-main scan-item-main"
                    aria-expanded={open}
                    aria-controls={editId}
                    onClick={toggle}
                  >
                    <span className="row-title">{row.name}</span>
                    <span className="row-sub">
                      {formatQuantity(Number(row.quantity) || 0)}
                      {row.unit} · {locationName(row.locationId)}
                      {row.price !== "" && ` · ${formatWon(Number(row.price))}`}
                    </span>
                  </button>
                )}
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={open ? "접기" : `${row.name} 고치기`}
                  aria-expanded={open}
                  aria-controls={editId}
                  onClick={toggle}
                >
                  <Icon name={open ? "up" : "down"} />
                </button>
                {open && (
                  <div className="scan-edit" id={editId}>
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
                    <label className="field scan-edit-price">
                      <span className="field-label">
                        가격 <span className="optional">(선택)</span>
                      </span>
                      <div className="input-suffix">
                        <input
                          className="input"
                          aria-label="가격"
                          inputMode="numeric"
                          value={row.price}
                          placeholder="모르면 비워두세요"
                          maxLength={8}
                          onChange={(e) => update(row.key, { price: e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "") })}
                        />
                        <span className="suffix">원</span>
                      </div>
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
            <button className="btn primary" disabled={busy || chosen.length === 0 || !!matched}>
              {busy ? "넣는 중…" : `${chosen.length}개 재고에 넣기`}
            </button>
          </div>
        </div>
      </form>

      {matched && (
        <Sheet
          title={`장보기 목록에 있던 ${namesLabel(matched.items.map((i) => i.name))}도 샀나요?`}
          description="재고에 넣은 걸로 장보기에서 뺄게요"
          className="sh-match-sheet"
          onClose={keep}
        >
          <ul className="sh-match">
            {matched.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={item.on}
                  onClick={() =>
                    setMatched({ ...matched, items: matched.items.map((i) => (i.id === item.id ? { ...i, on: !i.on } : i)) })
                  }
                >
                  <span className={`checkbox${item.on ? "" : " off"}`} aria-hidden="true">
                    <span>{item.on && <Icon name="check" size={16} />}</span>
                  </span>
                  {item.name}
                </button>
              </li>
            ))}
          </ul>
          {follow.error && (
            <p className="error" role="alert">
              {follow.error}
            </p>
          )}
          <div className="actions">
            <button type="button" className="btn outline" disabled={follow.busy} onClick={keep}>
              그대로 두기
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={follow.busy || !matched.items.some((i) => i.on)}
              onClick={markStocked}
            >
              {follow.busy ? "빼는 중…" : "장보기에서 빼기"}
            </button>
          </div>
        </Sheet>
      )}
    </>
  );
}
