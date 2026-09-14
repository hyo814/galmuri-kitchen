import { useEffect, useState } from "react";
import type { ShoppingItem, User } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import Sheet from "../components/Sheet";
import ShoppingItemSheet, { type ItemInput } from "../components/ShoppingItemSheet";
import StoreLinksSheet from "../components/StoreLinksSheet";
import { formatDate } from "../format";
import { groupItems, newClientId, quantityText, sourceTag, type EditFields, type Op, type Ref, type ViewItem } from "../shopping/sync";
import { useShopping } from "../shopping/useShopping";
import { navigate } from "../useHashRoute";

const refOf = (item: ViewItem): Ref => (item.id !== undefined ? { id: item.id } : { client_id: item.client_id! });
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

/** 시안 ShoppingList·ShoppingOffline·ShoppingDark: 장보기 탭 */
export default function Shopping({ user }: { user: User }) {
  const { view, offline, pending, failed, act, dismissFailed } = useShopping();
  const [editing, setEditing] = useState<ViewItem | "new" | null>(null);
  const [store, setStore] = useState<string | null>(null);
  const [showFailed, setShowFailed] = useState(false);
  const [stockedOpen, setStockedOpen] = useState(false);
  const [notice, setNotice] = useState("");
  // 오프라인에서 쌓인 변경은 연결된 뒤 다 보낼 때까지 띠를 남긴다(온라인에서 체크할 때마다 띠가 깜빡이지 않게)
  const [draining, setDraining] = useState(false);
  useEffect(() => {
    if (offline) setDraining(true);
    else if (pending === 0) setDraining(false);
  }, [offline, pending]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4000);
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

  const save = (fields: ItemInput | EditFields, keepOpen: boolean) => {
    if (editing === "new") {
      const f = fields as ItemInput;
      act({ op: "add", client_id: newClientId(), fields: { ...f, source: "manual" }, at: now() });
    } else if (editing && Object.keys(fields).length) {
      act({ op: "edit", ref: refOf(editing), fields, at: now() });
    }
    if (!keepOpen) setEditing(null);
  };

  const addAgain = (item: ShoppingItem) =>
    act({
      op: "add",
      client_id: newClientId(),
      fields: { name: item.name, quantity: item.quantity, unit: item.unit, planned_on: today, source: "manual" },
      at: now(),
    });

  return (
    <main className="page">
      <header className="topbar">
        <h1>장보기</h1>
        <button className="icon-btn" aria-label="항목 추가" onClick={() => setEditing("new")}>
          <Icon name="plus" size={24} />
        </button>
      </header>
      {items.length > 0 && (
        <p className="sh-summary">
          살 것 {items.length}개{checked > 0 && ` · 체크한 ${checked}개`}
        </p>
      )}

      <div role="status">
        {band && (
          <div className="sh-offline">
            <Icon name="offline" size={18} />
            {offline ? "오프라인 · 연결되면 저장돼요" : "저장하고 있어요"}
            {pending > 0 && <b>기다리는 중 {pending}건</b>}
          </div>
        )}
      </div>
      {failed.length > 0 && (
        <button className="sh-offline" onClick={() => setShowFailed(true)}>
          <Icon name="alert" size={18} />
          저장하지 못한 변경 {failed.length}건
          <Icon name="chevron" size={18} />
        </button>
      )}

      {/* 메모 카드 자리(sh-memo): Task 10의 ShoppingMemoCard가 여기, 재고에 넣기 막대 위에 들어간다 */}

      {checked > 0 && (
        <div className="sh-stock">
          <span>체크한 {checked}개를 재고에 넣을까요?</span>
          <button
            className="btn primary"
            onClick={() => (offline ? setNotice("인터넷이 연결되면 넣을 수 있어요") : navigate("/shopping/stock"))}
          >
            재고에 넣기
          </button>
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      {items.length === 0 && stocked.length === 0 && (
        <section className="empty rc-empty">
          <Mascot size={64} />
          <p className="muted">살 것을 담아두면 마트에서 체크만 하면 돼요</p>
        </section>
      )}

      {groupItems(items, today).map((group) => (
        <section key={group.key} aria-labelledby={`sh-group-${group.key}`}>
          <h2 className="sh-group" id={`sh-group-${group.key}`}>
            {group.title}
          </h2>
          <ul className="list">
            {group.items.map((item) => {
              const tag = sourceTag(item);
              const done = !!item.done_at;
              return (
                <li key={item.id ?? item.client_id} className={done ? "sh-row done" : "sh-row"}>
                  <button
                    className="sh-check"
                    role="checkbox"
                    aria-checked={done}
                    aria-label={`${item.name} 샀어요`}
                    onClick={() => act({ op: "check", ref: refOf(item), done: !done, at: now() })}
                  >
                    <i>{done && <Icon name="check" size={16} />}</i>
                  </button>
                  <button className="sh-main" onClick={() => setEditing(item)}>
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
                    {item.stocked_at && <span className="row-sub">{formatDate(seoulDate(item.stocked_at))} 재고에 넣었어요</span>}
                  </span>
                  <button className="btn outline" aria-label={`${item.name} 다시 담기`} onClick={() => addAgain(item)}>
                    다시 담기
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {editing && (
        <ShoppingItemSheet
          item={editing === "new" ? undefined : editing}
          today={today}
          onSave={save}
          onDelete={
            editing === "new"
              ? undefined
              : () => {
                  act({ op: "delete", ref: refOf(editing), at: now() });
                  setEditing(null);
                }
          }
          onClose={() => setEditing(null)}
        />
      )}
      {store !== null && <StoreLinksSheet name={store} affiliates={user.shop_affiliates} onClose={() => setStore(null)} />}
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
