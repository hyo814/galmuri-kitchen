import { useCallback, useState, type ReactNode } from "react";
import { api, type RecipeSummary, type RecommendationCard, type Recommendations } from "../api";
import Icon from "../components/Icon";
import InfiniteSentinel from "../components/InfiniteSentinel";
import { imageSrc } from "../format";
import { navigate } from "../useHashRoute";
import { useInfiniteList, type Page } from "../useInfiniteList";
import { cache } from "../useResource";

type Segment = "recommend" | "mine" | "video" | "seasoning";

const SEGMENTS: [Segment, string][] = [
  ["recommend", "추천"],
  ["mine", "내 레시피"],
  ["video", "영상"],
  ["seasoning", "양념 비율"],
];

// ponytail: 상세에서 돌아와도 보던 칸을 유지한다(모듈 변수, 새로고침하면 추천). 칸을 공유 링크로 열 일이 생기면 경로로 옮긴다.
let lastSegment: Segment = "recommend";

/** ["두부"] → "두부 마저 써요", ["두부", "대파"] → "두부·대파 마저 써요", 3개 이상 → "두부 외 2개 마저 써요" */
export function urgentLabel(names: string[]): string {
  if (names.length === 0) return "";
  const who = names.length <= 2 ? names.join("·") : `${names[0]} 외 ${names.length - 1}개`;
  return `${who} 마저 써요`;
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
        <MatchLine have={card.have_count} total={card.total_count} />
      </span>
      {missing > 0 && (
        <span className="rc-missing">
          <span className="label">없는 재료</span>
          {card.missing.slice(0, 3).map((name) => (
            <span key={name} className="rc-chip">
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
      };
      cache.set(RECS_META_KEY, next);
      setMeta(next);
    }
    return { items: data.public, next: data.next_offset !== null ? String(data.next_offset) : null };
  }, []);

  const list = useInfiniteList<RecommendationCard>(fetchPage, ["recs"]);
  return { meta, ...list };
}

function RecommendList({ onShowMine }: { onShowMine: () => void }) {
  const { meta, items, loading, error, hasMore, loadMore, reload } = useRecommendations();

  // C-L2: 첫 페이지가 실패하면(메타가 없음) 다시 불러오기 버튼을 보여 준다
  if (!meta)
    return error ? (
      <div className="list-end">
        <p className="error" role="alert">
          {error}
        </p>
        <button className="btn secondary inline" onClick={reload}>
          <Icon name="refresh" size={16} />
          다시 불러오기
        </button>
      </div>
    ) : (
      <p className="center muted">불러오는 중…</p>
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

  const noneFound = meta.mine.length === 0 && items.length === 0 && !loading && !hasMore;
  if (noneFound)
    return (
      <section className="empty">
        <p>지금 재고로 만들 수 있는 요리를 찾지 못했어요.</p>
        <p className="muted">재료를 더 넣거나 내 레시피를 추가해보세요.</p>
      </section>
    );

  return (
    <>
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
      {(meta.mine.length > 0 || items.length > 0) && (
        <section aria-label={meta.sample ? "예시 레시피" : "식약처 레시피"}>
          <h2 className="section-label rc-group">{meta.sample ? "예시 레시피" : "식약처 레시피"}</h2>
          <ul className="rc-cards">
            {items.map((card) => (
              <li key={`public-${card.id}`}>
                <RecommendCardView card={card} />
              </li>
            ))}
          </ul>
          {items.length > 0 && <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} loading={loading} error={error} onRetry={loadMore} />}
        </section>
      )}
    </>
  );
}

interface RecipeListPage {
  items: RecipeSummary[];
  next_cursor: string | null;
}

function MyRecipeList() {
  const fetchPage = useCallback(async (cursor: string | null): Promise<Page<RecipeSummary>> => {
    const path = cursor ? `/api/recipes?limit=30&cursor=${encodeURIComponent(cursor)}` : "/api/recipes?limit=30";
    const data = await api<RecipeListPage>(path);
    return { items: data.items, next: data.next_cursor };
  }, []);
  const { items, loading, error, hasMore, loadMore, reload } = useInfiniteList<RecipeSummary>(fetchPage, ["my-recipes"]);

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
                      {recipe.servings}인분 · 재료 {recipe.ingredient_count}개{recipe.source === "public" && " · 추천에서 저장"}
                    </span>
                  </span>
                  <Icon name="chevron" />
                </RecipeLink>
              </li>
            ))}
          </ul>
          <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} loading={loading} error={error} onRetry={loadMore} />
        </>
      )}
      <div className="cta-bar">
        <button className="btn primary" onClick={() => navigate("/recipes/new")}>
          <Icon name="plus" />
          레시피 추가
        </button>
      </div>
    </>
  );
}

// addendum: 요리 채널 영상 가져오기는 3b에서 한다
function VideoSoon() {
  return (
    <section className="empty">
      <Icon name="camera" size={32} color="var(--accent-strong)" />
      <p className="soon-title">요리 채널 영상은 준비 중이에요.</p>
      <p className="muted">고른 요리 채널의 새 영상을 보고 바로 레시피로 가져올 수 있게 할게요.</p>
    </section>
  );
}

// 3c단계(양념 비율 계산기) 전까지 자리만 잡는다
function SeasoningSoon() {
  return (
    <section className="empty">
      <Icon name="book" size={32} color="var(--accent-strong)" />
      <p className="soon-title">준비 중이에요</p>
      <p className="muted">곧 이런 걸 할 수 있어요.</p>
      <ul className="soon-list">
        {["불고기·제육볶음 같은 기본 양념 비율", "고기 양·인분에 맞춰 숟가락 단위로 계산", "내 입맛에 맞춘 비율 저장"].map((item) => (
          <li key={item}>
            <Icon name="check" size={16} color="var(--accent-strong)" />
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Recipes() {
  const [segment, setSegment] = useState<Segment>(lastSegment);
  const choose = useCallback((next: Segment) => {
    lastSegment = next;
    setSegment(next);
  }, []);

  return (
    <main className="page">
      <header className="topbar">
        <h1>레시피</h1>
      </header>
      <div className="segmented rc-seg" role="group" aria-label="레시피 보기">
        {SEGMENTS.map(([key, label]) => (
          <button key={key} aria-pressed={segment === key} onClick={() => choose(key)}>
            {label}
          </button>
        ))}
      </div>
      {segment === "recommend" && <RecommendList onShowMine={() => choose("mine")} />}
      {segment === "mine" && <MyRecipeList />}
      {segment === "video" && <VideoSoon />}
      {segment === "seasoning" && <SeasoningSoon />}
    </main>
  );
}
