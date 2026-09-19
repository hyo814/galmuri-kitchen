import { Fragment, useEffect, useRef, useState } from "react";
import type { ShoppingItem, User } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import MemoPhotoScan, { type ScanState } from "../components/MemoPhotoScan";
import Sheet from "../components/Sheet";
import ShoppingMemoCard from "../components/ShoppingMemoCard";
import ShoppingItemSheet, { type ItemInput } from "../components/ShoppingItemSheet";
import StoreFindAllSheet from "../components/StoreFindAllSheet";
import StoreLinksSheet from "../components/StoreLinksSheet";
import { pickFor } from "../data/picks";
import { formatDate, withJosa } from "../format";
import { groupItems, nameKey, newClientId, quantityText, sourceTag, type EditFields, type Op, type Ref, type ViewItem } from "../shopping/sync";
import { useShopping } from "../shopping/useShopping";
import { navigate } from "../useHashRoute";
import { forgetResources } from "../useResource";

const refOf = (item: ViewItem): Ref => (item.id !== undefined ? { id: item.id } : { client_id: item.client_id! });
/** 행 key: 기기에서 만든 항목은 보낸 뒤에도 client_id가 같아 자리·포커스가 유지된다 */
const keyOf = (item: { id?: number; client_id: string | null }) => item.client_id ?? `id:${item.id}`;
const sameName = (a: string, b: string) => nameKey(a) === nameKey(b);
const now = () => new Date().toISOString();
const seoulDate = (iso: string) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });

/** 저장하지 못한 변경 한 줄 설명 */
function failedLabel(op: Op, items: { id?: number; client_id: string | null; name: string }[]): string {
  const nameOf = (ref: Ref) => items.find((i) => ("id" in ref ? i.id === ref.id : i.client_id === ref.client_id))?.name ?? "살 것";
  switch (op.op) {
    case "add": return `${op.fields.name} 추가`;
    case "edit": return `${nameOf(op.ref)} 고치기`;
    case "check": return `${nameOf(op.ref)} ${op.done ? "체크" : "체크 해제"}`;
    case "delete": return `${nameOf(op.ref)} 빼기`;
    case "photo_add": case "photo_delete": return "메모 사진";
    default: return "장보기 메모";
  }
}

let pendingNotice: string | null = null;
/** 다른 화면(메모 사진에서 담기)에서 장보기로 올 때 목록 위에 한 번 보여줄 알림 */
export const showShoppingNotice = (text: string) => {
  pendingNotice = text;
};

/** 시안 ShoppingList·ShoppingOffline·ShoppingDark: 장보기 탭 */
export default function Shopping({ user }: { user: User }) {
  const shopping = useShopping();
  const { view, offline, pending, failed, act, dismissFailed } = shopping;
  const [editing, setEditing] = useState<ViewItem | "new" | null>(null);
  /** 살 것 추가 시트의 "사진에서 뽑기": 메모 없이 바로 카메라·앨범 → MemoScanReview */
  const [scan, setScan] = useState<ScanState>(null);
  const [store, setStore] = useState<string | null>(null);
  const [findAll, setFindAll] = useState(false);
  const [showFailed, setShowFailed] = useState(false);
  const [stockedOpen, setStockedOpen] = useState(false);
  const [notice, setNotice] = useState<{ text: string; near: "stock" | "bought" } | null>(() =>
    pendingNotice ? { text: pendingNotice, near: "stock" } : null,
  );
  useEffect(() => {
    pendingNotice = null; // 초기값에서 지우지 않는다(StrictMode가 초기값 함수를 두 번 부른다)
  }, []);
  /** 빼기 뒤 포커스: 뺀 행이 화면에서 사라지면 next 행 이름(없으면 머리 + 버튼)으로 */
  const [focusAfterDelete, setFocusAfterDelete] = useState<{ deleted: string; next: string | null } | null>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  // 오프라인에서 쌓인 변경은 연결된 뒤 다 보낼 때까지 띠를 남긴다(온라인에서 체크할 때마다 띠가 깜빡이지 않게)
  const [draining, setDraining] = useState(false);
  useEffect(() => {
    if (offline) setDraining(true);
    else if (pending === 0) setDraining(false);
  }, [offline, pending]);

  useEffect(() => {
    if (!focusAfterDelete || view?.items.some((i) => keyOf(i) === focusAfterDelete.deleted)) return;
    const next = focusAfterDelete.next && document.querySelector<HTMLElement>(`[data-row="${CSS.escape(focusAfterDelete.next)}"]`);
    (next || addButton.current)?.focus();
    setFocusAfterDelete(null);
  }, [focusAfterDelete, view]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  if (!view)
    return (
      <main className="page">
        <header className="topbar">
          <h1>장보기</h1>
        </header>
        <p className="center muted">불러오는 중…</p>
      </main>
    );

  const { items, stocked, today } = view;
  const checked = items.filter((i) => i.done_at).length;
  const band = offline || (draining && pending > 0);
  const groups = groupItems(items, today);
  const unchecked = groups.flatMap((g) => g.items).filter((i) => !i.done_at);

  const save = (fields: ItemInput | EditFields, keepOpen: boolean) => {
    if (editing === "new") {
      const f = fields as ItemInput;
      act({ op: "add", client_id: newClientId(), fields: { ...f, source: "manual" }, at: now() });
    } else if (editing && Object.keys(fields).length) {
      act({ op: "edit", ref: refOf(editing), fields, at: now() });
    }
    if (!keepOpen) setEditing(null);
  };

  const addAgain = (item: ShoppingItem) => {
    if (items.some((i) => sameName(i.name, item.name))) return;
    setNotice({ text: `${withJosa(item.name, "을", "를")} 오늘 살 것에 담았어요`, near: "bought" });
    act({
      op: "add",
      client_id: newClientId(),
      fields: { name: item.name, quantity: item.quantity, unit: item.unit, planned_on: today, source: "manual" },
      at: now(),
    });
  };

  const remove = (item: ViewItem) => {
    const order = groups.flatMap((g) => g.items);
    const at = order.findIndex((i) => keyOf(i) === keyOf(item));
    const next = at >= 0 ? order[at + 1] : undefined;
    setFocusAfterDelete({ deleted: keyOf(item), next: next ? keyOf(next) : null });
    act({ op: "delete", ref: refOf(item), at: now() });
    setEditing(null);
  };

  const noticeAt = (near: "stock" | "bought") =>
    notice?.near === near && (
      <p className="notice" role="status">
        {notice.text}
      </p>
    );

  return (
    <main className="page">
      <header className="topbar">
        <h1>장보기</h1>
        <button ref={addButton} className="icon-btn" aria-label="항목 추가" onClick={() => setEditing("new")}>
          <Icon name="plus" size={24} />
        </button>
      </header>
      {items.length > 0 && (
        <div className="sh-summary-row">
          <p className="sh-summary">
            살 것 {items.length}개{checked > 0 && ` · 체크한 ${checked}개`}
          </p>
          {unchecked.length >= 2 && (
            <button type="button" className="sh-findall" onClick={() => setFindAll(true)}>
              <Icon name="search" size={16} />
              쇼핑몰에서 한꺼번에 찾기
            </button>
          )}
        </div>
      )}

      {/* 띠가 나타날 때 문장만 한 번 읽는다(건수는 바뀔 때마다 읽지 않게 aria-hidden) */}
      <div role="status">
        {band && (
          <div className="sh-offline">
            <Icon name={offline ? "offline" : "refresh"} size={18} />
            {offline ? "오프라인 · 연결되면 저장돼요" : "저장하고 있어요"}
            {pending > 0 && <b aria-hidden="true">기다리는 중 {pending}건</b>}
          </div>
        )}
      </div>
      <div role="status">
        {failed.length > 0 && (
          <button className="sh-offline" onClick={() => setShowFailed(true)}>
            <Icon name="alert" size={18} />
            저장하지 못한 변경 {failed.length}건
            <Icon name="chevron" size={18} />
          </button>
        )}
      </div>

      <ShoppingMemoCard shopping={shopping} />

      {checked > 0 && (
        <div className="sh-stock">
          <span>체크한 {checked}개를 재고에 넣을까요?</span>
          <button
            className="btn primary"
            onClick={() => {
              // 재고에 넣기 화면은 서버의 체크 상태를 읽으므로, 아직 못 보낸 체크가 있으면 기다린다
              if (offline) setNotice({ text: "인터넷이 연결되면 넣을 수 있어요", near: "stock" });
              else if (pending > 0) setNotice({ text: "체크한 걸 저장하고 있어요. 잠깐 뒤에 눌러주세요", near: "stock" });
              else navigate("/shopping/stock");
            }}
          >
            재고에 넣기
          </button>
        </div>
      )}
      {noticeAt("stock")}

      {items.length === 0 && (
        <section className="empty rc-empty">
          <Mascot size={64} />
          <p className="muted">살 것을 담아두면 마트에서 체크만 하면 돼요</p>
          <button className="btn secondary inline" onClick={() => setEditing("new")}>
            <Icon name="plus" />
            살 것 추가
          </button>
        </section>
      )}

      {groups.map((group) => (
        <section key={group.key} aria-labelledby={`sh-group-${group.key}`}>
          <h2 className="sh-group" id={`sh-group-${group.key}`}>
            {group.title}
          </h2>
          <ul className="list">
            {group.items.map((item) => {
              const tag = sourceTag(item);
              const done = !!item.done_at;
              const pick = done ? null : pickFor(item.name); // 산 줄에는 안 보여준다
              return (
                <Fragment key={keyOf(item)}>
                <li className={done ? "sh-row done" : "sh-row"}>
                  <button
                    className="sh-check"
                    role="checkbox"
                    aria-checked={done}
                    aria-label={`${item.name} 샀어요`}
                    onClick={() => act({ op: "check", ref: refOf(item), done: !done, at: now() })}
                  >
                    <i>{done && <Icon name="check" size={16} />}</i>
                  </button>
                  <button className="sh-main" data-row={keyOf(item)} onClick={() => setEditing(item)}>
                    <span className="sh-name">
                      {item.name}
                      <span>{quantityText(item.quantity, item.unit)}</span>
                    </span>
                    {(tag || item.pending) && (
                      <span className="sh-meta">
                        {tag && <span className={`sh-tag ${tag.tone}`}>{tag.text}</span>}
                        {item.pending && <span className="sh-pending">저장 전</span>}
                      </span>
                    )}
                  </button>
                  <button className="icon-btn" aria-label={`${item.name} 쇼핑몰에서 찾기`} onClick={() => setStore(item.name)}>
                    <Icon name="store" size={22} />
                  </button>
                </li>
                {pick && (
                  <li className="sh-rec">
                    <span className="sh-tag info">{pick.note ? "기억할 것" : "추천"}</span>
                    {pick.note ? (
                      <p>{pick.note}</p>
                    ) : (
                      <ul>
                        {pick.products!.map((product) => (
                          <li key={product}>
                            <button type="button" aria-label={`${product} 쇼핑몰에서 찾기`} onClick={() => setStore(product)}>
                              {product}
                              <Icon name="search" size={14} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                )}
                </Fragment>
              );
            })}
          </ul>
        </section>
      ))}

      {stocked.length > 0 && (
        <>
          <button className="sh-fold" aria-expanded={stockedOpen} onClick={() => setStockedOpen((o) => !o)}>
            <span>산 것 {stocked.length}개</span>
            <Icon name={stockedOpen ? "down" : "chevron"} />
          </button>
          {stockedOpen && (
            <ul className="list">
              {stocked.map((item) => (
                <li key={item.id} className="sh-bought">
                  <span className="row-main">
                    <span className="sh-name">
                      {item.name}
                      <span>{quantityText(item.quantity, item.unit)}</span>
                    </span>
                    {item.stocked_at && (
                      // ponytail: 스냅숏에 넣음·건너뜀 구분이 없어 생활용품만 `샀어요`. 일반 재료를 끄고 옮긴 것도 구분하려면 서버가 skip 여부를 준다
                      <span className="row-sub">{formatDate(seoulDate(item.stocked_at))} {item.household ? "샀어요" : "재고에 넣었어요"}</span>
                    )}
                  </span>
                  {/* 같은 버튼을 유지해야 누른 뒤 포커스가 사라지지 않는다 */}
                  <button
                    className="btn outline"
                    aria-disabled={items.some((i) => sameName(i.name, item.name)) || undefined}
                    onClick={() => addAgain(item)}
                  >
                    <span className="sr-only">{item.name} </span>
                    {items.some((i) => sameName(i.name, item.name)) ? "담았어요" : "다시 담기"}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {noticeAt("bought")}
        </>
      )}

      {editing && (
        <ShoppingItemSheet
          item={editing === "new" ? undefined : editing}
          today={today}
          onSave={save}
          listedNames={items.map((i) => i.name)}
          onDelete={editing === "new" ? undefined : () => remove(editing)}
          onClose={() => setEditing(null)}
          user={user}
          offline={offline}
          onScanPhoto={() => {
            setEditing(null);
            setScan("source");
          }}
        />
      )}
      <MemoPhotoScan
        scan={scan}
        onScanChange={setScan}
        sourceLabel="장보기 메모"
        listed={items.map((i) => i.name)}
        today={today}
        onScanned={() => forgetResources("/api/ai-usage")} // 다른 화면이 남은 AI 횟수를 옛 값으로 먼저 보이지 않게
        onDone={(text) => {
          setScan(null);
          setNotice({ text, near: "stock" });
        }}
      />
      {store !== null && <StoreLinksSheet name={store} affiliates={user.shop_affiliates} onClose={() => setStore(null)} />}
      {findAll && unchecked.length > 0 && (
        <StoreFindAllSheet
          items={unchecked.map((i) => ({ key: keyOf(i), name: i.name, quantity: i.quantity, unit: i.unit }))}
          affiliates={user.shop_affiliates}
          onClose={() => setFindAll(false)}
        />
      )}
      {showFailed && (
        <Sheet title="저장하지 못한 변경" description="이 변경은 저장하지 못했어요. 확인했으면 지워주세요." onClose={() => setShowFailed(false)}>
          <ul className="sh-failed">
            {failed.map((f, i) => (
              <li key={i}>
                <span className="row-title">{failedLabel(f.op, [...items, ...stocked])}</span>
                <span className="row-sub">{f.error}</span>
              </li>
            ))}
          </ul>
          <button
            className="btn secondary"
            onClick={() => {
              dismissFailed();
              setShowFailed(false);
            }}
          >
            지우기
          </button>
        </Sheet>
      )}
    </main>
  );
}
