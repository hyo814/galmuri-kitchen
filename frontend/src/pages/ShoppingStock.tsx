import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api, type StorageLocation } from "../api";
import Icon from "../components/Icon";
import { formatDate, formatQuantity } from "../format";
import { stockButtonText, stockSummaryText } from "../shopping/sync";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate, setLeaveGuard } from "../useHashRoute";
import { forgetRecipeCaches } from "../useResource";
import { refresh } from "../shopping/useShopping";

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
  household: boolean;
  location_id: number | null;
  location_reason: Reason;
}

interface Draft {
  purchased_on: string;
  items: DraftItem[];
}

interface StockBody {
  purchased_on: string;
  items: ({ id: number; name: string; quantity: number; unit: string; location_id: number } | { id: number; skip: true })[];
}

interface Row extends DraftItem {
  /** 고른 위치 id, 아직 안 골랐거나 사라진 위치면 "" */
  chosen: string;
  /** 재고에 넣기(끄면 재료를 만들지 않고 산 것으로만 옮김). 생활용품은 기본 끔 */
  stock: boolean;
}

/** 고정 CTA 바의 실제 높이(안내 줄·큰 글씨로 줄바꿈 포함)만큼 화면 아래 여백을 잡아 마지막 항목이 가려지지 않게 한다 */
function reserveCtaSpace(bar: HTMLDivElement | null) {
  const page = bar?.closest<HTMLElement>(".page");
  if (!bar || !page) return;
  const observer = new ResizeObserver(() => page.style.setProperty("--sh-cta-h", `${bar.offsetHeight}px`));
  observer.observe(bar);
  return () => {
    observer.disconnect();
    page.style.removeProperty("--sh-cta-h");
  };
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
  // 응답을 못 받은 채 끊긴 요청. 연결되면 같은 내용으로 다시 보낸다(이미 넣었으면 서버가 200 created 0)
  const pending = useRef<StockBody | null>(null);

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
          const old = prev.find((r) => r.id === item.id);
          const kept = old?.chosen ?? String(item.location_id ?? "");
          return { ...item, chosen: locs.some((l) => String(l.id) === kept) ? kept : "", stock: old?.stock ?? !item.household };
        }),
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) setOffline(true);
      else setLoadError((e as Error).message);
    }
  };

  useEffect(() => {
    if (navigator.onLine) load();
    const onOnline = () => (pending.current ? send(pending.current) : load());
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dirty =
    !!draft &&
    (purchasedOn !== draft.purchased_on || rows.some((r) => r.chosen !== String(r.location_id ?? "") || r.stock === r.household));
  const canLeave = () => !dirty || confirm(LEAVE_CONFIRM);
  useEffect(() => {
    setLeaveGuard(canLeave);
    return () => setLeaveGuard(null);
  });
  const leave = () => {
    if (canLeave()) goBack("/shopping");
  };

  const change = (id: number, patch: Partial<Row>) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
    setRowErrors(({ [id]: _, ...rest }) => rest);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    const unset = rows.filter((r) => r.stock && !r.chosen);
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
    send({
      purchased_on: purchasedOn,
      items: rows.map((r) =>
        r.stock
          ? { id: r.id, name: r.name, quantity: r.quantity, unit: r.unit, location_id: Number(r.chosen) }
          : { id: r.id, skip: true as const },
      ),
    });
  };

  // online 이벤트에서도 불리므로 상태(rows)가 아니라 보낸 body로 행을 찾는다
  const send = (body: StockBody) =>
    run(async () => {
      pending.current = null;
      try {
        await api("/api/shopping/items/stock", { method: "POST", body });
      } catch (e) {
        if (!(e instanceof ApiError)) throw e;
        if (e.status === 0) {
          pending.current = body;
          throw new Error(OFFLINE);
        }
        if (e.status === 400) {
          const errors = Object.fromEntries((e.errors ?? []).map((x) => [body.items[x.index]?.id, x.error]));
          setRowErrors(errors);
          await load(); // 목록·위치가 바뀌었을 수 있다. 고른 위치는 load가 지킨다
          const first = Object.keys(errors)[0];
          if (first) document.getElementById(`stock-loc-${first}`)?.focus();
        }
        throw e;
      }
      setLeaveGuard(null);
      void refresh(); // 장보기 목록은 useShopping 기기 상태라 새로 받는다
      forgetRecipeCaches(); // 재고가 바뀌었으니 추천·보유 표시도 새로
      navigate("/shopping", { replace: true });
    });

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

  const stockCount = rows.filter((r) => r.stock).length;
  const skipCount = rows.length - stockCount;
  return (
    <main className="page sh-in-page">
      <BackLink onClick={leave} />
      <header className="topbar">
        <div>
          <h1>재고에 넣기</h1>
          <p className="summary">{stockSummaryText(stockCount, skipCount)}</p>
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

        <section className="rc-sec sh-in-list" aria-label={`체크한 항목 · 재고로 ${stockCount}개 · 산 것으로만 ${skipCount}개`}>
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
                    {row.household && <span className="badge sh-in-tag">생활용품</span>}
                    {!row.stock ? (
                      <span className="row-sub">산 것으로만 옮겨요</span>
                    ) : (
                      prefilled &&
                      REASON_LABEL[row.location_reason] && <span className="row-sub">{REASON_LABEL[row.location_reason]}</span>
                    )}
                  </span>
                  {row.stock && (
                    <span className="sh-in-sel">
                      <select
                        id={`stock-loc-${row.id}`}
                        className={err ? "input invalid" : "input"}
                        aria-label={`${row.name} 보관 위치`}
                        aria-invalid={!!err}
                        aria-describedby={err ? `stock-err-${row.id}` : undefined}
                        value={row.chosen}
                        onChange={(e) => change(row.id, { chosen: e.target.value })}
                      >
                        {row.chosen === "" && (
                          <option value="" disabled>
                            골라주세요
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
                  )}
                  <span className="sh-in-toggle">
                    <span aria-hidden="true">재고에 넣기</span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={row.stock}
                      aria-label={`${row.name} 재고에 넣기`}
                      className="r3-toggle"
                      disabled={busy}
                      onClick={() => change(row.id, { stock: !row.stock })}
                    />
                  </span>
                  {err && (
                    <p className="rc-err" id={`stock-err-${row.id}`}>
                      <Icon name="alert" size={16} />
                      {err}
                    </p>
                  )}
              </div>
            );
          })}
        </section>

        {locations.length === 0 && (
          <a
            className="btn secondary sh-in-make"
            href="#/more"
            onClick={(e) => {
              e.preventDefault();
              if (canLeave()) navigate("/more"); // 더보기 → 보관 위치
            }}
          >
            <Icon name="plus" />
            보관 위치 만들기
          </a>
        )}

        <p className="mo-note sh-in-note">
          <Icon name="info" size={16} />
          <span>재고에 넣으면 장보기 목록에서 빠져요. 유통기한은 재고에서 고칠 수 있어요.</span>
        </p>

        {error && (
          <p className="error sh-in-error" role="alert">
            {error}
          </p>
        )}

        <div className="cta-bar" ref={reserveCtaSpace}>
          {skipCount > 0 && stockCount > 0 && (
            <p className="sh-in-hint">
              {rows.every((r) => r.stock || r.household) ? "생활용품 " : ""}
              {skipCount}개는 재고에 넣지 않고 산 것으로만 옮겨요
            </p>
          )}
          <div className="actions">
            <button type="button" className="btn outline" disabled={busy} aria-disabled={busy} onClick={leave}>
              취소
            </button>
            <button className="btn primary sh-in-submit" disabled={busy}>
              {busy ? "넣는 중…" : stockButtonText(stockCount, skipCount)}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
