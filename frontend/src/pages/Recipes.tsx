import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type AiUsage, type RecipeSummary, type RecommendationCard, type Recommendations, type User } from "../api";
import AddRecipeSheet from "../components/AddRecipeSheet";
import Icon from "../components/Icon";
import InfiniteSentinel from "../components/InfiniteSentinel";
import { SOURCE_LABEL, imageSrc, namesLabel, remainingText, withJosa } from "../format";
import { navigate } from "../useHashRoute";
import { useInfiniteList, type Page } from "../useInfiniteList";
import { cache, useResource } from "../useResource";
import { hasAiState, startAiRecipes, useAiStatus } from "./RecipeAi";
import Seasonings from "./Seasonings";
import Videos, { resetVideoFilter } from "./Videos";

export type Segment = "recommend" | "mine" | "video" | "seasoning";

const SEGMENTS: [Segment, string][] = [
  ["recommend", "추천"],
  ["mine", "내 레시피"],
  ["video", "영상"],
  ["seasoning", "양념 비율"],
];

// ponytail: 상세에서 돌아와도 보던 칸을 유지한다(모듈 변수, 새로고침하면 추천). 칸을 공유 링크로 열 일이 생기면 경로로 옮긴다.
let lastSegment: Segment = "recommend";
let lastPublicQuery = ""; // 식약처 레시피 검색어도 같은 이유로 유지한다

/** 로그아웃 때 다른 계정에서 이전 탭이 그대로 보이지 않게 (M9) */
export function resetRecipesSegment() {
  lastSegment = "recommend";
  lastPublicQuery = "";
  resetVideoFilter();
}

/** 레시피 삭제 뒤 뒤로가기하면 내 레시피 탭에 있게 (E1) */
export function setRecipesSegment(segment: Segment) {
  lastSegment = segment;
}

/** ["두부"] → "두부 마저 써요", ["두부", "대파"] → "두부·대파 마저 써요", 3개 이상 → "두부 외 2개 마저 써요" */
export function urgentLabel(names: string[]): string {
  return names.length === 0 ? "" : `${namesLabel(names)} 마저 써요`;
}

/** "재료 7개 중 5개 있어요" + 막대 (추천 카드·상세 공통) */
export function MatchLine({ have, total }: { have: number; total: number }) {
  const percent = total ? Math.round((have / total) * 100) : 0;
  return (
    <span className="rc-match">
      {have === total ? (
        <span className="done">
          <Icon name="check" size={16} />
          재료 {total}개 다 있어요
        </span>
      ) : (
        <>
          재료 {total}개 중 <b>{have}개</b> 있어요
        </>
      )}
      <span className="rc-bar" aria-hidden="true">
        <i style={{ width: `${percent}%` }} />
      </span>
    </span>
  );
}

function RecipeLink({ path, className, children }: { path: string; className: string; children: ReactNode }) {
  return (
    <a
      className={className}
      href={`#${path}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(path);
      }}
    >
      {children}
    </a>
  );
}

function RecommendCardView({ card }: { card: RecommendationCard }) {
  const missing = card.total_count - card.have_count;
  const src = imageSrc(card.image_url);
  const urgent = urgentLabel(card.urgent_names);
  return (
    <RecipeLink path={`/recipes/${card.kind}/${card.id}`} className="rc-card">
      <span className={src ? "rc-thumb" : "rc-thumb rc-ph"}>
        {src ? <img src={src} alt="" loading="lazy" /> : <Icon name="bowl" size={28} />}
      </span>
      <span className="rc-body">
        {urgent && <span className="badge old">{urgent}</span>}
        <span className="row-title">{card.title}</span>
        {card.total_count > 0 && <MatchLine have={card.have_count} total={card.total_count} />}
      </span>
      {missing > 0 && (
        <span className="rc-missing">
          <span className="label">없는 재료</span>
          {card.missing.slice(0, 3).map((name, index) => (
            // M10: 이름이 겹칠 수 있어(같은 재료가 다른 레시피에도) index 기반 key
            <span key={index} className="rc-chip">
              {name}
            </span>
          ))}
          {missing > 3 && <span className="rc-chip more">+{missing - 3}</span>}
        </span>
      )}
    </RecipeLink>
  );
}

// addendum: 추천은 페이지가 있다. section=all(첫 페이지)이 내 레시피 상위 10개 + 공공 레시피 1페이지를 주고,
// 더 받을 공공 레시피는 section=public&offset=<next_offset>로 받는다. 내 레시피 top 10 밖은 "내 레시피" 탭으로 보낸다.
interface RecsMeta {
  mine: RecommendationCard[];
  mineTotal: number;
  sample: boolean;
  inventoryCount: number;
  publicCount: number; // M11: 재고와 안 겹쳐도 세는 전체 공공 레시피 수
}

const RECS_META_KEY = "list:recs-meta"; // "list:" 접두사라 forgetResources("list:")로 함께 지워진다

function useRecommendations() {
  const [meta, setMeta] = useState<RecsMeta | undefined>(() => cache.get(RECS_META_KEY) as RecsMeta | undefined);

  const fetchPage = useCallback(async (cursor: string | null): Promise<Page<RecommendationCard>> => {
    const path = cursor ? `/api/recommendations?section=public&offset=${encodeURIComponent(cursor)}&limit=20` : "/api/recommendations";
    const data = await api<Recommendations>(path);
    if (!cursor) {
      const next: RecsMeta = {
        mine: data.mine ?? [],
        mineTotal: data.mine_total ?? 0,
        sample: data.sample,
        inventoryCount: data.inventory_count,
        publicCount: data.public_count,
      };
      cache.set(RECS_META_KEY, next);
      setMeta(next);
    }
    return { items: data.public, next: data.next_offset !== null ? String(data.next_offset) : null };
  }, []);

  const list = useInfiniteList<RecommendationCard>(fetchPage, ["recs"]);
  return { meta, ...list };
}

/** 추천 칸 맨 위 한 줄 카드: 지금 재고로 AI 레시피 3개 만들기 */
function AiEntry() {
  const { data: usage } = useResource<AiUsage>("/api/ai-usage");
  const usedUp = !!usage && usage.recipe.used >= usage.recipe.limit;
  const status = useAiStatus();
  // 이미 만든 결과·만드는 중이면 새로 부르지 않고 그 화면을 연다(횟수를 아낀다. 새로 만들기는 `다시 만들기`)
  const open = () => {
    if (!status || (status === "error" && !usedUp)) startAiRecipes();
    navigate("/recipes/ai");
  };
  return (
    <section className="r3-ai" aria-labelledby="ai-entry-title">
      <span className="r3-ai-mark">
        <Icon name="sparkle" size={26} />
      </span>
      <span className="row-main">
        <span className="row-title" id="ai-entry-title">
          내 재고로 새 레시피
        </span>
        <span className="row-sub">{status === "done" ? "만든 레시피 3개가 있어요" : `AI가 3개 만들어줘요${remainingText(usage)}`}</span>
      </span>
      <button type="button" className="btn primary inline" disabled={usedUp && !hasAiState()} onClick={open}>
        {status === "done" ? "결과 보기" : status === "loading" ? "만드는 중…" : "만들기"}
      </button>
    </section>
  );
}

/** 식약처 레시피 제목 검색 결과: 재고와 안 겹치는 레시피도 일치 점수 순으로 보여 준다 */
function PublicSearchResults({ q }: { q: string }) {
  const fetchPage = useCallback(
    async (cursor: string | null): Promise<Page<RecommendationCard>> => {
      const params = new URLSearchParams({ section: "public", q, offset: cursor ?? "0", limit: "20" });
      const data = await api<Recommendations>(`/api/recommendations?${params}`);
      return { items: data.public, next: data.next_offset !== null ? String(data.next_offset) : null };
    },
    [q],
  );
  const { items, loading, error, hasMore, multiPage, loadMore, reload } = useInfiniteList<RecommendationCard>(fetchPage, ["recs-search", q]);
  const noMatch = `'${q}'${withJosa(q, "이", "가").slice(q.length)} 들어간 레시피가 없어요.`;
  let status = "";
  if (!loading && !error) status = items.length ? "레시피를 찾았어요" : noMatch;

  return (
    <>
      <p className="sr-only" role="status" aria-live="polite">
        {status}
      </p>
      {items.length === 0 ? (
        error ? (
          <div className="list-end">
            <p className="error" role="alert">
              {error}
            </p>
            <button className="btn secondary inline" onClick={reload}>
              <Icon name="refresh" size={16} />
              다시 불러오기
            </button>
          </div>
        ) : loading || hasMore ? (
          <p className="center muted">찾는 중…</p>
        ) : (
          <div className="empty">
            <p>{noMatch}</p>
          </div>
        )
      ) : (
        <>
          <ul className="rc-cards">
            {items.map((card) => (
              <li key={`search-${card.id}`}>
                <RecommendCardView card={card} />
              </li>
            ))}
          </ul>
          <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} multiPage={multiPage} loading={loading} error={error} onRetry={loadMore} />
        </>
      )}
    </>
  );
}

function RecommendList({ onShowMine, showAi }: { onShowMine: () => void; showAi: boolean }) {
  const { meta, items, loading, error, hasMore, multiPage, loadMore, reload } = useRecommendations();
  const [input, setInput] = useState(lastPublicQuery);
  const [q, setQ] = useState(lastPublicQuery);
  const inputRef = useRef<HTMLInputElement>(null);

  // 입력을 멈추고 300ms 뒤에 찾는다(영상 칸과 같게)
  useEffect(() => {
    const timer = setTimeout(() => setQ(input.trim()), 300);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    lastPublicQuery = q;
  }, [q]);
  // 재고 수를 알기 전에는 그리지 않고, 재고가 비었으면 숨긴다(만들 재료가 없다. 깜빡임 방지)
  const ai = showAi && meta !== undefined && meta.inventoryCount > 0 && <AiEntry />;

  // C-L2: 첫 페이지가 실패하면(메타가 없음) 다시 불러오기 버튼을 보여 준다
  if (!meta)
    return error ? (
      <>
        {ai}
        <div className="list-end">
          <p className="error" role="alert">
            {error}
          </p>
          <button className="btn secondary inline" onClick={reload}>
            <Icon name="refresh" size={16} />
            다시 불러오기
          </button>
        </div>
      </>
    ) : (
      <>
        {ai}
        <p className="center muted">불러오는 중…</p>
      </>
    );

  if (meta.inventoryCount === 0)
    return (
      <section className="empty rc-empty">
        <img className="rc-empty-mark" src="/mark.svg" width="64" height="64" alt="" />
        <p className="soon-title">재고가 비어 있어요</p>
        <p className="muted">재고에 재료를 넣으면 만들 수 있는 요리를 찾아줘요</p>
        <button className="btn primary inline" onClick={() => location.replace("#/")}>
          <Icon name="fridge" />
          재고로 가기
        </button>
      </section>
    );

  const publicLabel = meta.sample ? "예시 레시피" : "식약처 레시피";
  const noneFound = meta.mine.length === 0 && items.length === 0 && !loading && !hasMore;
  if (noneFound)
    // M11: 카탈로그 자체가 비었을 때(재고와 안 겹치는 것까지 다 세도 공공 레시피가 0)는 "재료를 더 넣어보라"는
    // 안내가 맞지 않는다 — 아직 채우는 중이라는 걸 알려준다.
    return (
      <>
        {ai}
        {meta.inventoryCount > 0 && meta.publicCount === 0 ? (
          <section className="empty">
            <p>추천할 레시피가 아직 없어요. 곧 채워둘게요.</p>
          </section>
        ) : (
          <section className="empty">
            <p>지금 재고로 만들 수 있는 요리를 찾지 못했어요.</p>
            <p className="muted">재료를 더 넣거나 내 레시피를 추가해보세요.</p>
          </section>
        )}
      </>
    );

  return (
    <>
      {ai}
      {meta.sample && (meta.mine.length > 0 || items.length > 0) && (
        <p className="rc-sample">
          <Icon name="info" size={16} />
          예시 레시피로 보여줘요
        </p>
      )}
      {meta.mine.length > 0 && (
        <section aria-label="내 레시피">
          <h2 className="section-label rc-group">내 레시피</h2>
          <ul className="rc-cards">
            {meta.mine.map((card) => (
              <li key={`mine-${card.id}`}>
                <RecommendCardView card={card} />
              </li>
            ))}
          </ul>
          {meta.mineTotal > meta.mine.length && (
            <button type="button" className="rc-more" onClick={onShowMine}>
              내 레시피에서 더 보기
              <Icon name="chevron" size={16} />
            </button>
          )}
        </section>
      )}
      {/* M6: 공공 레시피가 하나도 없으면(내 레시피만 있을 때) 빈 섹션 자체를 그리지 않는다 */}
      {items.length > 0 && (
        <section aria-label={publicLabel}>
          {/* 식약처 레시피 위 제목 검색 칸(2026-09-15 사용자 요청). 검색어가 있으면 아래 목록이 검색 결과로 바뀐다 */}
          <form
            role="search"
            className="rc-search"
            onSubmit={(e) => {
              e.preventDefault();
              setQ(input.trim());
              inputRef.current?.blur(); // 키보드를 닫아 결과가 보이게
            }}
          >
            <div className="r3-search">
              <label>
                <Icon name="search" size={20} />
                <span className="sr-only">{publicLabel}에서 찾기</span>
                <input
                  ref={inputRef}
                  type="search"
                  placeholder={`${publicLabel}에서 찾기`}
                  maxLength={50}
                  enterKeyHint="search"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                />
              </label>
              {input && (
                <button
                  type="button"
                  className="r3-search-clear"
                  aria-label="검색어 지우기"
                  onClick={() => {
                    setInput("");
                    setQ("");
                    inputRef.current?.focus();
                  }}
                >
                  <Icon name="close" size={18} />
                </button>
              )}
            </div>
          </form>
          <h2 className="section-label rc-group">{publicLabel}</h2>
          {q ? (
            <PublicSearchResults q={q} />
          ) : (
            <>
              <ul className="rc-cards">
                {items.map((card) => (
                  <li key={`public-${card.id}`}>
                    <RecommendCardView card={card} />
                  </li>
                ))}
              </ul>
              <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} multiPage={multiPage} loading={loading} error={error} onRetry={loadMore} />
            </>
          )}
        </section>
      )}
    </>
  );
}

interface RecipeListPage {
  items: RecipeSummary[];
  next_cursor: string | null;
}

function MyRecipeList({ canImport }: { canImport: boolean }) {
  const [adding, setAdding] = useState(false);
  const fetchPage = useCallback(async (cursor: string | null): Promise<Page<RecipeSummary>> => {
    const path = cursor ? `/api/recipes?limit=30&cursor=${encodeURIComponent(cursor)}` : "/api/recipes?limit=30";
    const data = await api<RecipeListPage>(path);
    return { items: data.items, next: data.next_cursor };
  }, []);
  const { items, loading, error, hasMore, multiPage, loadMore, reload } = useInfiniteList<RecipeSummary>(fetchPage, ["my-recipes"]);

  return (
    <>
      {items.length === 0 ? (
        // C-L2: 첫 페이지가 실패하면 다시 불러오기 버튼을 보여 준다(로딩·빈 상태보다 먼저 확인)
        error ? (
          <div className="list-end">
            <p className="error" role="alert">
              {error}
            </p>
            <button className="btn secondary inline" onClick={reload}>
              <Icon name="refresh" size={16} />
              다시 불러오기
            </button>
          </div>
        ) : loading || hasMore ? (
          <p className="center muted">불러오는 중…</p>
        ) : (
          <section className="empty">
            <p>저장한 레시피가 없어요.</p>
            <p className="muted">
              추천에서 마음에 드는 레시피를 저장하거나
              <br />
              아래 버튼으로 직접 추가해보세요.
            </p>
          </section>
        )
      ) : (
        <>
          <ul className="list">
            {items.map((recipe) => (
              <li key={recipe.id}>
                <RecipeLink path={`/recipes/mine/${recipe.id}`} className="row-btn">
                  <span className="row-main">
                    <span className="row-title">{recipe.title}</span>
                    <span className="row-sub">
                      {recipe.servings}인분 · 재료 {recipe.ingredient_count}개{SOURCE_LABEL[recipe.source] && ` · ${SOURCE_LABEL[recipe.source]}`}
                    </span>
                  </span>
                  <Icon name="chevron" />
                </RecipeLink>
              </li>
            ))}
          </ul>
          <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} multiPage={multiPage} loading={loading} error={error} onRetry={loadMore} />
        </>
      )}
      <div className="cta-bar">
        {/* 사진 인식과 같은 키가 없으면(scan off) 링크·글 가져오기도 못 하므로 바로 폼으로 */}
        <button className="btn primary" onClick={() => (canImport ? setAdding(true) : navigate("/recipes/new"))}>
          <Icon name="plus" />
          레시피 추가
        </button>
      </div>
      {adding && <AddRecipeSheet onClose={() => setAdding(false)} />}
    </>
  );
}

export default function Recipes({ user }: { user: User }) {
  // 영상을 쓸 수 없으면(운영에서 키 없음) 영상 칸을 숨긴다
  const segments = user.videos === "off" ? SEGMENTS.filter(([key]) => key !== "video") : SEGMENTS;
  const [segment, setSegment] = useState<Segment>(segments.some(([key]) => key === lastSegment) ? lastSegment : "recommend");
  const choose = useCallback((next: Segment) => {
    lastSegment = next;
    setSegment(next);
  }, []);

  return (
    <main className="page">
      <header className="topbar">
        <h1>레시피</h1>
      </header>
      <div className="segmented rc-seg" role="group" aria-label="레시피 보기" style={{ gridTemplateColumns: `repeat(${segments.length}, minmax(0, 1fr))` }}>
        {segments.map(([key, label]) => (
          <button key={key} aria-pressed={segment === key} onClick={() => choose(key)}>
            {label}
          </button>
        ))}
      </div>
      {segment === "recommend" && <RecommendList onShowMine={() => choose("mine")} showAi={user.scan !== "off"} />}
      {segment === "mine" && <MyRecipeList canImport={user.scan !== "off"} />}
      {segment === "video" && <Videos sample={user.videos === "sample"} />}
      {segment === "seasoning" && <Seasonings />}
    </main>
  );
}
