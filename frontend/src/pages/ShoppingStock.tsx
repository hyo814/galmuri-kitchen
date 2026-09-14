import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, type StorageLocation } from "../api";
import Icon from "../components/Icon";
import { formatDate, formatQuantity } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate, setLeaveGuard } from "../useHashRoute";
import { forgetRecipeCaches, forgetResources } from "../useResource";

// backend/app/shopping.py — 이 문구면 초안·보관 위치를 다시 받는다
const LIST_CHANGED = "목록이 방금 바뀌었어요. 다시 불러와주세요.";
const LOCATION_ERRORS = ["선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요.", "보관 위치를 다시 선택해주세요."];
const OFFLINE = "인터넷이 연결되면 넣을 수 있어요";
const LEAVE_CONFIRM = "작성 중인 내용이 사라져요. 나갈까요?";

type Reason = "item" | "same_name" | "default" | "none";
const REASON_LABEL: Record<Reason, string> = {
  item: "장보기에 적어 둔 곳",
  same_name: "같은 이름 재료가 있던 곳",
  default: "기본 위치",
  none: "",
};

interface DraftItem {
  id: number;
  name: string;
  quantity: number;
  unit: string;
  location_id: number | null;
  location_reason: Reason;
}

interface Draft {
  purchased_on: string;
  items: DraftItem[];
}

interface Row extends DraftItem {
  /** 고른 위치 id, 아직 안 골랐거나 사라진 위치면 "" */
  chosen: string;
}

function BackLink({ onClick }: { onClick: () => void }) {
  return (
    <a
      className="back-link"
      href="#/shopping"
      onClick={(e) => {
        e.preventDefault();
        onClick();
      }}
    >
      <Icon name="back" size={18} />
      장보기
    </a>
  );
}

/** #/shopping/stock — 체크한 장보기 항목을 산 날 하나·항목별 보관 위치로 재고에 넣는다(시안 StockIn) */
export default function ShoppingStock() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [locations, setLocations] = useState<StorageLocation[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [purchasedOn, setPurchasedOn] = useState("");
  const [offline, setOffline] = useState(() => !navigator.onLine);
  const [loadError, setLoadError] = useState("");
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const { busy, error, setError, run } = useAsyncAction();

  // 다시 받을 때(목록이 바뀜·위치가 바뀜) 남아 있는 항목은 사용자가 고른 위치를 지킨다
  const load = async () => {
    setLoadError("");
    try {
      const [next, locs] = await Promise.all([
        api<Draft>("/api/shopping/stock-draft"),
        api<StorageLocation[]>("/api/locations"),
      ]);
      setOffline(false);
      setLocations(locs);
      setDraft(next);
      setPurchasedOn((prev) => prev || next.purchased_on);
      setRows((prev) =>
        next.items.map((item) => {
          const kept = prev.find((r) => r.id === item.id)?.chosen ?? String(item.location_id ?? "");
          return { ...item, chosen: locs.some((l) => String(l.id) === kept) ? kept : "" };
        }),
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) setOffline(true);
      else setLoadError((e as Error).message);
    }
  };

  useEffect(() => {
    if (navigator.onLine) load();
    const onOnline = () => load();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dirty =
    !!draft && (purchasedOn !== draft.purchased_on || rows.some((r) => r.chosen !== String(r.location_id ?? "")));
  const canLeave = () => !dirty || confirm(LEAVE_CONFIRM);
  useEffect(() => {
    setLeaveGuard(canLeave);
    return () => setLeaveGuard(null);
  });
  const leave = () => {
    if (canLeave()) goBack("/shopping");
  };

  const choose = (id: number, chosen: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, chosen } : r)));
    setRowErrors(({ [id]: _, ...rest }) => rest);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    const unset = rows.filter((r) => !r.chosen);
    setRowErrors(Object.fromEntries(unset.map((r) => [r.id, "보관 위치를 골라주세요"])));
    if (unset.length) {
      setError(locations.length ? "" : "보관 위치를 먼저 만들어주세요.");
      document.getElementById(`stock-loc-${unset[0].id}`)?.focus();
      return;
    }
    if (!purchasedOn || purchasedOn > draft.purchased_on) {
      setError("산 날은 오늘이나 그 전 날짜로 골라주세요.");
      return;
    }
    run(async () => {
      const items = rows.map((r) => ({ id: r.id, name: r.name, quantity: r.quantity, unit: r.unit, location_id: Number(r.chosen) }));
      try {
        await api("/api/shopping/items/stock", { method: "POST", body: { purchased_on: purchasedOn, items } });
      } catch (e) {
        if (!(e instanceof ApiError)) throw e;
        if (e.status === 0) throw new Error(OFFLINE);
        const first = e.errors?.[0];
        const row = first && rows[first.index];
        if (row) {
          setRowErrors({ [row.id]: first.error });
          document.getElementById(`stock-loc-${row.id}`)?.focus();
        }
        // 위치가 사라진 건 항목별 오류(`N번째 재료: 보관 위치를 다시 선택해주세요.`)로도 온다
        if ([e.message, first?.error].some((m) => m === LIST_CHANGED || LOCATION_ERRORS.includes(m ?? ""))) {
          await load();
          throw new Error("목록이 바뀌어서 다시 불러왔어요. 확인하고 다시 넣어주세요.");
        }
        throw e;
      }
      setLeaveGuard(null);
      forgetResources("/api/shopping");
      forgetRecipeCaches(); // 재고가 바뀌었으니 추천·보유 표시도 새로
      navigate("/shopping", { replace: true });
    });
  };

  if (offline && !draft)
    return (
      <main className="page">
        <BackLink onClick={() => goBack("/shopping")} />
        <div className="center">
          <p>{OFFLINE}</p>
          <button type="button" className="btn primary inline" onClick={() => goBack("/shopping")}>
            장보기로
          </button>
        </div>
      </main>
    );

  if (!draft)
    return (
      <main className="page">
        <BackLink onClick={() => goBack("/shopping")} />
        {loadError ? (
          <div className="list-end">
            <p className="error" role="alert">
              {loadError}
            </p>
            <button type="button" className="btn secondary inline" onClick={load}>
              <Icon name="refresh" size={16} />
              다시 불러오기
            </button>
          </div>
        ) : (
          <p className="center muted">불러오는 중…</p>
        )}
      </main>
    );

  if (rows.length === 0)
    return (
      <main className="page">
        <BackLink onClick={() => goBack("/shopping")} />
        <header className="topbar">
          <h1>재고에 넣기</h1>
        </header>
        <div className="center">
          <p className="muted">체크한 항목이 없어요. 장보기에서 산 것을 체크해주세요.</p>
          <button type="button" className="btn primary inline" onClick={() => goBack("/shopping")}>
            장보기로
          </button>
        </div>
      </main>
    );

  return (
    <main className="page">
      <BackLink onClick={leave} />
      <header className="topbar">
        <div>
          <h1>재고에 넣기</h1>
          <p className="summary">체크한 {rows.length}개를 재고로 옮겨요</p>
        </div>
      </header>

      <form onSubmit={submit} noValidate>
        <section className="rc-sec">
          <label className="field">
            <span className="field-label">산 날</span>
            <span className="input sh-date">
              {purchasedOn === draft.purchased_on ? `오늘 · ${formatDate(purchasedOn)}` : purchasedOn && formatDate(purchasedOn)}
              <input
                type="date"
                value={purchasedOn}
                max={draft.purchased_on}
                required
                onClick={(e) => e.currentTarget.showPicker?.()}
                onChange={(e) => setPurchasedOn(e.target.value)}
              />
            </span>
          </label>
        </section>

        <section className="rc-sec sh-in-list" aria-label="넣을 재료">
          {rows.map((row) => {
            const err = rowErrors[row.id];
            const prefilled = row.chosen !== "" && row.chosen === String(row.location_id ?? "");
            return (
              <div key={row.id} className="sh-in-row">
                  <span className="row-main">
                    <span className="sh-name">
                      {row.name}
                      <span>
                        {formatQuantity(row.quantity)}
                        {row.unit}
                      </span>
                    </span>
                    {prefilled && REASON_LABEL[row.location_reason] && (
                      <span className="row-sub">{REASON_LABEL[row.location_reason]}</span>
                    )}
                  </span>
                  <span className="sh-in-sel">
                    <select
                      id={`stock-loc-${row.id}`}
                      className={err ? "input invalid" : "input"}
                      aria-label={`${row.name} 보관 위치`}
                      aria-invalid={!!err}
                      aria-describedby={err ? `stock-err-${row.id}` : undefined}
                      value={row.chosen}
                      onChange={(e) => choose(row.id, e.target.value)}
                    >
                      {row.chosen === "" && (
                        <option value="" disabled>
                          보관 위치를 골라주세요
                        </option>
                      )}
                      {locations.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name}
                        </option>
                      ))}
                    </select>
                    <Icon name="chevron" size={16} />
                  </span>
                  {err && (
                    <p className="rc-err" id={`stock-err-${row.id}`} role="alert">
                      <Icon name="alert" size={16} />
                      {err}
                    </p>
                  )}
              </div>
            );
          })}
        </section>

        <p className="mo-note sh-in-note">
          <Icon name="info" size={16} />
          <span>재고에 넣으면 장보기 목록에서 빠져요. 유통기한은 재고에서 고칠 수 있어요.</span>
        </p>

        {error && (
          <p className="error sh-in-error" role="alert">
            {error}
          </p>
        )}

        <div className="cta-bar">
          <div className="actions">
            <button type="button" className="btn outline" onClick={leave}>
              취소
            </button>
            <button className="btn primary" disabled={busy}>
              {busy ? "넣는 중…" : `${rows.length}개 넣기`}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
