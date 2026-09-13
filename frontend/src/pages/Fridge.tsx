import { useEffect, useState } from "react";
import { api, ApiError, type Ingredient, type IngredientInput } from "../api";
import IngredientForm from "../components/IngredientForm";

function badge(item: Ingredient): string | null {
  const d = item.days_left;
  if (d !== null) return d > 0 ? `D-${d}` : d === 0 ? "D-day" : `${-d}일 지남`;
  if (item.status === "old") return `구입 ${item.days_since_purchase}일째`;
  return null;
}

const formatQuantity = (q: number) => (Number.isInteger(q) ? String(q) : q.toFixed(1));

export default function Fridge({ onLogout }: { onLogout: () => void }) {
  const [items, setItems] = useState<Ingredient[] | null>(null);
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [error, setError] = useState("");

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) onLogout();
    else setError((e as Error).message);
  };

  const load = () => api<Ingredient[]>("/api/ingredients").then(setItems, fail);

  useEffect(() => {
    load();
  }, []);

  const save = async (input: IngredientInput) => {
    try {
      if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
      else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
      setEditing(null);
      setError("");
      await load();
    } catch (e) {
      fail(e);
    }
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${editing.name}을(를) 삭제할까요?`)) return;
    try {
      await api(`/api/ingredients/${editing.id}`, { method: "DELETE" });
      setEditing(null);
      await load();
    } catch (e) {
      fail(e);
    }
  };

  const logout = async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    onLogout();
  };

  return (
    <div className="page">
      <header className="topbar">
        <h1>내 냉장고</h1>
        <button className="link" onClick={logout}>
          로그아웃
        </button>
      </header>

      {error && (
        <p className="error" role="alert" onClick={() => setError("")}>
          {error}
        </p>
      )}

      {items === null ? (
        <p className="center muted">불러오는 중…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          <p>냉장고가 비어 있어요.</p>
          <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {items.map((item) => {
            const label = badge(item);
            return (
              <li key={item.id}>
                <button className="item" onClick={() => setEditing(item)}>
                  <span className="item-name">{item.name}</span>
                  <span className="item-meta">
                    {formatQuantity(item.quantity)}
                    {item.unit} · {item.purchased_on} 구입
                  </span>
                  {label && <span className={`badge ${item.status}`}>{label}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <button className="btn primary fab" onClick={() => setEditing("new")}>
        + 재료 추가
      </button>

      {editing && (
        <IngredientForm
          initial={editing === "new" ? null : editing}
          onSubmit={save}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
