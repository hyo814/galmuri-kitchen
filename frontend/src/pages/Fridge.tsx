import { useCallback, useEffect, useState } from "react";
import { api, type DeleteReason, type Ingredient, type IngredientInput, type Staple, type StorageLocation, type User } from "../api";
import Icon from "../components/Icon";
import InfiniteSentinel from "../components/InfiniteSentinel";
import IngredientForm from "../components/IngredientForm";
import LocationsSheet from "../components/LocationsSheet";
import Mascot from "../components/Mascot";
import ScanSheet from "../components/ScanSheet";
import SettingsSheet, { type SettingsTarget } from "../components/SettingsSheet";
import StaplesSheet from "../components/StaplesSheet";
import { guideText, urgentItems } from "../demoGuide";
import { formatDate, formatQuantity, withJosa } from "../format";
import { forgetScroll } from "../useHashRoute";
import { forgetRecipeCaches } from "../useResource";
import { spotlightAiEntry } from "./Recipes";

// 떨어진 필수품이 많아도 배너가 화면을 차지하지 않도록 앞의 몇 개만 이름을 보여 준다 (전체는 필수품 시트)
const BANNER_NAMES = 3;

// 체험 계정 안내 카드는 계정마다 한 번만(닫거나 버튼을 누르면 이 기기에 기억한다)
const guideKey = (user: User) => `demoGuideDone:${user.id}`;

function guideDone(user: User): boolean {
  try {
    return localStorage.getItem(guideKey(user)) !== null;
  } catch {
    return false; // 저장소를 못 쓰면 이번 화면에서만 닫힌다
  }
}

function badge(item: Ingredient): string | null {
  if (item.status === "danger") return "섭취 주의";
  const d = item.days_left;
  if (item.status === "old") return `구입 ${item.days_since_purchase}일째`;
  if (d !== null) return d > 0 ? `D-${d}` : d === 0 ? "D-day" : `${-d}일 지남`;
  return null;
}

export default function Fridge({ user }: { user: User }) {
  const [items, setItems] = useState<Ingredient[] | null>(null);
  const [locations, setLocations] = useState<StorageLocation[]>([]);
  const [staples, setStaples] = useState<Staple[]>([]);
  const [filter, setFilter] = useState<number | "all">("all");
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [prefillName, setPrefillName] = useState("");
  const [panel, setPanel] = useState<"settings" | SettingsTarget | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [staplesMissingOnly, setStaplesMissingOnly] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [notice, setNotice] = useState("");
  const [guide, setGuide] = useState(() => user.provider === "demo" && !guideDone(user));
  const [shown, setShown] = useState(50); // 재고는 서버가 전체를 주고 화면에서 50개씩 점진 렌더 (2,000개까지 대비)

  // 필터·검색이 바뀌면 처음 50개부터 다시 보여 준다
  useEffect(() => {
    setShown(50);
  }, [filter, query]);
  const showMore = useCallback(() => setShown((s) => s + 50), []);

  // 401은 api()의 전역 핸들러(App.tsx)가 처리한다.
  const load = () => {
    setError("");
    return Promise.all([
      api<Ingredient[]>("/api/ingredients").then(setItems),
      api<StorageLocation[]>("/api/locations").then(setLocations),
      api<Staple[]>("/api/staples").then(setStaples),
    ]).catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  // I1: 재고가 실제로 바뀐 뒤(저장·삭제·스캔·필수품/위치/규칙 변경)에만 추천·레시피 캐시를 지운다.
  // 처음 화면을 열 때(load) 지우면 안 되므로 mount용 load()와 분리해 둔다.
  const changed = () => {
    forgetRecipeCaches();
    return load();
  };

  // 사진으로 넣은 뒤 안내는 잠깐만 보여 준다
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  // 저장·삭제 오류는 던져서 시트 안에 표시한다. keepOpen이면 시트를 닫지 않는다(연속 추가).
  const save = async (input: IngredientInput, keepOpen: boolean) => {
    if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
    else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
    if (!keepOpen) setEditing(null);
    await changed();
  };

  // 지우는 이유(선택)는 IngredientForm의 삭제 확인 시트에서 고른다 — 월간 리포트의 버린 재료 수 (스펙 27절)
  const remove = async (reason: DeleteReason | null) => {
    if (!editing || editing === "new") return;
    await api(`/api/ingredients/${editing.id}${reason ? `?reason=${reason}` : ""}`, { method: "DELETE" });
    setEditing(null);
    await changed();
  };

  const openNew = (name = "") => {
    setPanel(null);
    setScanning(false);
    setStaplesMissingOnly(false);
    setPrefillName(name);
    setEditing("new");
  };

  const scanned = async (count: number) => {
    setScanning(false);
    setNotice(`${count}개를 재고에 넣었어요`);
    await changed();
  };

  const activeFilter = filter !== "all" && locations.some((l) => l.id === filter) ? filter : "all";
  const q = query.replace(/\s+/g, "").toLowerCase();
  const visible =
    items?.filter(
      (i) =>
        (activeFilter === "all" || i.location_id === activeFilter) &&
        (!q || i.name.replace(/\s+/g, "").toLowerCase().includes(q)),
    ) ?? null;
  const defaultLocationId =
    activeFilter !== "all" ? activeFilter : (locations.find((l) => l.kind === "fridge") ?? locations[0])?.id;
  const soon = items?.filter((i) => i.status === "urgent" || i.status === "danger").length ?? 0;
  const missing = staples.filter((s) => !s.in_stock);

  const closeGuide = () => {
    setGuide(false);
    try {
      localStorage.setItem(guideKey(user), "1");
    } catch {
      // 저장소를 못 쓰는 브라우저는 이번 화면에서만 닫는다
    }
  };
  const [guideBefore, guideStrong, guideAfter] = items ? guideText(items) : ["", "", ""];

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <h1>내 재고</h1>
          {items && items.length > 0 && (
            <p className="summary">
              재료 {items.length}개{soon > 0 && ` · 빨리 먹어야 할 재료 ${soon}개`}
            </p>
          )}
        </div>
        <button className="icon-btn" aria-label="설정" onClick={() => setPanel("settings")}>
          <Icon name="settings" size={22} />
        </button>
      </header>

      {guide && items && (
        <section className="demo-guide" aria-label="체험 안내">
          <div className="demo-guide-head">
            <Mascot size={40} />
            <p>
              {guideBefore}
              {guideStrong && <b>{guideStrong}</b>}
              {guideAfter}
            </p>
            <button className="icon-btn" aria-label="안내 닫기" onClick={closeGuide}>
              <Icon name="close" size={20} />
            </button>
          </div>
          <div className="demo-guide-acts">
            <button
              className="btn primary"
              onClick={() => {
                closeGuide();
                spotlightAiEntry(urgentItems(items).map((i) => i.name));
                forgetScroll("/recipes"); // 추천 칸 맨 위 AI 카드가 보이게 맨 위에서 연다
                location.replace("#/recipes"); // 탭 전환과 같게 히스토리를 쌓지 않는다
              }}
            >
              요리 찾아보기
            </button>
            {user.scan !== "off" && (
              <button
                className="btn secondary"
                disabled={defaultLocationId === undefined}
                onClick={() => {
                  closeGuide();
                  setScanning(true);
                }}
              >
                사진 찍어보기
              </button>
            )}
          </div>
        </section>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      {/* 체험 안내 카드가 떠 있는 동안은 필수품 배너를 숨긴다(카드 두 장이 겹쳐 보이지 않게). 닫으면 다시 보인다 */}
      {missing.length > 0 && !(guide && items) && (
        <button className="banner" onClick={() => { setStaplesMissingOnly(true); setPanel("staples"); }}>
          <span className="banner-icon">
            <Icon name="alert" size={22} />
          </span>
          <span className="row-main">
            <span className="banner-title">필수품 {missing.length}개가 떨어졌어요</span>
            <span className="banner-sub">
              {missing.slice(0, BANNER_NAMES).map((s) => s.name).join(", ")}
              {missing.length > BANNER_NAMES && ` 외 ${missing.length - BANNER_NAMES}개`}
            </span>
          </span>
          <Icon name="chevron" />
        </button>
      )}

      {items && (items.length >= 10 || query) && (
        <div className="search">
          <Icon name="search" />
          <input
            className="input"
            id="inventory-search"
            type="search"
            aria-label="재고 검색"
            placeholder="재고에서 찾기"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
            enterKeyHint="search"
          />
        </div>
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
          {query ? (
            activeFilter !== "all" ? (
              <>
                <p>이 위치에는 ‘{query.trim()}’ 재료가 없어요.</p>
                <button className="btn secondary inline" onClick={() => setFilter("all")}>
                  전체 위치에서 찾기
                </button>
              </>
            ) : (
              <>
                <p>‘{query.trim()}’ 재료가 없어요.</p>
                <button className="btn secondary inline" onClick={() => openNew(query.trim())}>
                  {withJosa(query.trim(), "을", "를")} 재고에 추가
                </button>
              </>
            )
          ) : (
            <>
              <p>{items && items.length > 0 ? "이 위치에는 재료가 없어요." : "재고가 비어 있어요."}</p>
              <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
            </>
          )}
        </div>
      ) : (
        <>
          <ul className="list">
            {visible.slice(0, shown).map((item) => {
              const label = badge(item);
              return (
                <li key={item.id}>
                  <button className="row-btn" onClick={() => setEditing(item)}>
                    <span className="row-main">
                      <span className="row-title">{item.name}</span>
                      <span className="row-sub">
                        {formatQuantity(item.quantity)}
                        {item.unit} · {item.location_name}
                        {item.purchased_on && ` · ${formatDate(item.purchased_on)} 구입`}
                        {item.status === "danger" && item.days_since_purchase !== null && ` · 구입 ${item.days_since_purchase}일째`}
                      </span>
                    </span>
                    {label && <span className={`badge ${item.status}`}>{label}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
          {visible.length > 50 && <InfiniteSentinel onVisible={showMore} hasMore={shown < visible.length} />}
        </>
      )}

      <div className="cta-bar">
        <div className="cta-2">
          {user.scan !== "off" && (
            <button className="btn outline" disabled={defaultLocationId === undefined} onClick={() => setScanning(true)}>
              <Icon name="camera" />
              사진으로 추가
            </button>
          )}
          <button className="btn primary" disabled={defaultLocationId === undefined} onClick={() => openNew()}>
            <Icon name="plus" />
            재료 추가
          </button>
        </div>
      </div>

      {editing && defaultLocationId !== undefined && (
        <IngredientForm
          initial={editing === "new" ? null : editing}
          initialName={editing === "new" ? prefillName : undefined}
          locations={locations}
          defaultLocationId={defaultLocationId}
          onSubmit={save}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}

      {scanning && user.scan !== "off" && (
        <ScanSheet
          mode={user.scan}
          limit={user.scan_limit}
          locations={locations}
          onAdded={scanned}
          onManual={() => openNew()}
          onClose={() => setScanning(false)}
          onLocationsStale={load}
        />
      )}
      {panel === "settings" && <SettingsSheet onOpen={setPanel} onClose={() => setPanel(null)} />}
      {panel === "locations" && (
        <LocationsSheet locations={locations} onChanged={changed} onClose={() => setPanel(null)} />
      )}
      {panel === "staples" && (
        <StaplesSheet
          staples={staples}
          initialMissingOnly={staplesMissingOnly}
          onChanged={changed}
          onAddIngredient={openNew}
          onClose={() => {
            setPanel(null);
            setStaplesMissingOnly(false);
          }}
        />
      )}
    </main>
  );
}
