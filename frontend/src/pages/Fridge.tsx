import { useEffect, useState } from "react";
import { api, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import Icon from "../components/Icon";
import IngredientForm from "../components/IngredientForm";
import LocationsSheet from "../components/LocationsSheet";
import SettingsSheet, { type SettingsTarget } from "../components/SettingsSheet";
import { formatDate, formatQuantity } from "../format";

function badge(item: Ingredient): string | null {
  const d = item.days_left;
  if (item.status === "old") return `구입 ${item.days_since_purchase}일째`;
  if (d !== null) return d > 0 ? `D-${d}` : d === 0 ? "D-day" : `${-d}일 지남`;
  return null;
}

export default function Fridge({ onLogout }: { onLogout: () => void }) {
  const [items, setItems] = useState<Ingredient[] | null>(null);
  const [locations, setLocations] = useState<StorageLocation[]>([]);
  const [filter, setFilter] = useState<number | "all">("all");
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [panel, setPanel] = useState<"settings" | SettingsTarget | null>(null);
  const [error, setError] = useState("");

  // 401은 api()의 전역 핸들러(App.tsx)가 처리한다.
  const load = () =>
    Promise.all([
      api<Ingredient[]>("/api/ingredients").then(setItems),
      api<StorageLocation[]>("/api/locations").then(setLocations),
    ]).catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  // 저장·삭제 오류는 던져서 시트 안에 표시한다.
  const save = async (input: IngredientInput) => {
    if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
    else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
    setEditing(null);
    await load();
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${editing.name}을(를) 삭제할까요?`)) return;
    await api(`/api/ingredients/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const logout = async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    onLogout();
  };

  const activeFilter = filter !== "all" && locations.some((l) => l.id === filter) ? filter : "all";
  const visible = items?.filter((i) => activeFilter === "all" || i.location_id === activeFilter) ?? null;
  const defaultLocationId =
    activeFilter !== "all" ? activeFilter : (locations.find((l) => l.kind === "fridge") ?? locations[0])?.id;
  const soon = items?.filter((i) => i.status === "urgent").length ?? 0;

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>내 냉장고</h1>
          {items && items.length > 0 && (
            <p className="summary">
              재료 {items.length}개{soon > 0 && ` · 곧 먹어야 할 재료 ${soon}개`}
            </p>
          )}
        </div>
        <button className="icon-btn" aria-label="설정" onClick={() => setPanel("settings")}>
          <Icon name="settings" size={22} />
        </button>
      </header>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {locations.length > 0 && (
        <div className="chip-row">
          <div className="chips" role="group" aria-label="보관 위치">
            <button className="chip" aria-pressed={activeFilter === "all"} onClick={() => setFilter("all")}>
              전체
            </button>
            {locations.map((location) => (
              <button
                key={location.id}
                className="chip"
                aria-pressed={activeFilter === location.id}
                onClick={() => setFilter(location.id)}
              >
                {location.name}
              </button>
            ))}
          </div>
          <div className="chip-row-end">
            <button className="icon-btn" aria-label="위치 관리" onClick={() => setPanel("locations")}>
              <Icon name="sliders" />
            </button>
          </div>
        </div>
      )}

      {visible === null ? (
        !error && <p className="center muted">불러오는 중…</p>
      ) : visible.length === 0 ? (
        <div className="empty">
          <p>{items && items.length > 0 ? "이 위치에는 재료가 없어요." : "냉장고가 비어 있어요."}</p>
          <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {visible.map((item) => {
            const label = badge(item);
            return (
              <li key={item.id}>
                <button className="row-btn" onClick={() => setEditing(item)}>
                  <span className="row-main">
                    <span className="row-title">{item.name}</span>
                    <span className="row-sub">
                      {formatQuantity(item.quantity)}
                      {item.unit} · {item.location_name} · {formatDate(item.purchased_on)} 구입
                    </span>
                  </span>
                  {label && <span className={`badge ${item.status}`}>{label}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="cta-bar">
        <button className="btn primary" disabled={defaultLocationId === undefined} onClick={() => setEditing("new")}>
          <Icon name="plus" />
          재료 추가
        </button>
      </div>

      {editing && defaultLocationId !== undefined && (
        <IngredientForm
          initial={editing === "new" ? null : editing}
          locations={locations}
          defaultLocationId={defaultLocationId}
          onSubmit={save}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}

      {panel === "settings" && <SettingsSheet onOpen={setPanel} onLogout={logout} onClose={() => setPanel(null)} />}
      {panel === "locations" && (
        <LocationsSheet locations={locations} onChanged={load} onClose={() => setPanel(null)} />
      )}
    </div>
  );
}
