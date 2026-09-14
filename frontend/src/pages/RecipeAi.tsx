import { useEffect, useState } from "react";
import { api, type AiSuggestions, type AiUsage, type Ingredient, type MyRecipe } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import { imageSrc, namesLabel, remainingText, withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetRecipeCaches, useResource } from "../useResource";
import { BackLink, RecipeBody } from "./RecipeDetail";
import { MatchLine, urgentLabel } from "./Recipes";

type AiState = { status: "loading"; urgent: string[] } | { status: "error"; message: string } | { status: "done"; data: AiSuggestions };

// ponytail: 결과·저장 상태는 모듈 변수(뒤로 갔다 와도 다시 부르지 않음, 새로고침하면 사라짐)
let state: AiState | null = null;
let controller: AbortController | null = null;
let listener: ((next: AiState | null) => void) | null = null;
const savedIndexes = new Set<number>();

const set = (next: AiState | null) => {
  state = next;
  listener?.(next);
};

/** 로그아웃 때 이전 사용자의 AI 결과가 남지 않게 */
export function resetAiRecipes() {
  controller?.abort();
  state = null;
  savedIndexes.clear();
}

function generate() {
  controller?.abort();
  const own = new AbortController();
  controller = own;
  savedIndexes.clear();
  set({ status: "loading", urgent: [] });
  // 만드는 중 문구의 `빨리 먹어야 할 두부·대파`: 재고 중 임박·지남 이름(실패해도 문구만 빠진다)
  api<Ingredient[]>("/api/ingredients", { signal: own.signal })
    .then((items) => {
      if (state?.status !== "loading" || controller !== own) return;
      const urgent = items.filter((item) => item.status === "urgent" || item.status === "danger").map((item) => item.name);
      set({ status: "loading", urgent: [...new Set(urgent)] });
    })
    .catch(() => {});
  api<AiSuggestions>("/api/recommendations/ai", { method: "POST", signal: own.signal })
    .then((data) => set({ status: "done", data }))
    .catch((e: unknown) => {
      if (own.signal.aborted) return;
      set({ status: "error", message: (e as Error).message });
    });
}

/** 화면이 떠 있는 동안 상태를 받는다. 결과가 없으면 만들기 시작, 만드는 중에 화면을 떠나면 요청을 끊는다. */
function useAiState(start: boolean) {
  const [view, setView] = useState(state);
  useEffect(() => {
    listener = setView;
    if (start && (state === null || state.status === "error")) generate();
    else setView(state);
    return () => {
      listener = null;
      // StrictMode는 마운트 → 정리 → 마운트를 바로 이어서 한다. 정말 떠났을 때만(다시 붙지 않았을 때) 끊는다.
      queueMicrotask(() => {
        if (listener || state?.status === "done") return;
        controller?.abort();
        state = null;
      });
    };
  }, [start]);
  return view;
}

async function saveSuggestion(data: AiSuggestions, index: number) {
  const recipe = data.recipes[index];
  await api<MyRecipe>("/api/recipes", {
    method: "POST",
    body: {
      title: recipe.title,
      servings: recipe.servings,
      ingredients: recipe.ingredients.map(({ name, amount }) => ({ name, amount })),
      steps: recipe.steps,
      source: "ai",
      ...(recipe.image_url ? { image_url: recipe.image_url } : {}),
    },
  });
  savedIndexes.add(index);
  forgetRecipeCaches();
}

function SaveButton({ data, index }: { data: AiSuggestions; index: number }) {
  const [saved, setSaved] = useState(() => savedIndexes.has(index));
  const { busy, error, run } = useAsyncAction();
  return (
    <>
      {saved ? (
        <button type="button" className="btn saved" disabled>
          <Icon name="check" size={18} />
          저장했어요
        </button>
      ) : (
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={() => run(async () => (await saveSuggestion(data, index), setSaved(true)))}
        >
          <Icon name="bookmark" size={18} />
          {busy ? "저장 중…" : "저장"}
        </button>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

function Loading({ urgent }: { urgent: string[] }) {
  return (
    <>
      <section className="r3-loading" role="status">
        <Mascot />
        <p className="r3-loading-title">재고를 보고 레시피를 고르고 있어요</p>
        <p className="muted r3-loading-sub">
          {urgent.length > 0 && (
            <>
              빨리 먹어야 할 {withJosa(namesLabel(urgent), "을", "를")} 먼저 넣어볼게요.
              <br />
            </>
          )}
          10초쯤 걸려요.
        </p>
        <div className="r3-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </section>
      <div className="r3-skel" aria-hidden="true">
        <div />
        <div />
      </div>
    </>
  );
}

function Results({ data }: { data: AiSuggestions }) {
  const { data: usage, reload } = useResource<AiUsage>("/api/ai-usage");
  // 방금 만든 1번이 반영된 남은 횟수를 받는다(useResource는 캐시를 먼저 보여 준다)
  useEffect(() => {
    reload();
  }, [data, reload]);
  // 만드는 중 화면의 h1이 사라져 포커스가 body로 떨어졌으면 결과 제목으로 옮긴다
  useEffect(() => {
    const heading = document.querySelector<HTMLElement>("main.page h1");
    if (!heading || (document.activeElement && document.activeElement !== document.body)) return;
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }, []);
  const usedUp = !!usage && usage.recipe.used >= usage.recipe.limit;
  const first = data.urgent_first;
  return (
    <>
      <header className="topbar">
        <div>
          <h1>AI 레시피</h1>
          <p className="summary">
            {first.length > 0
              ? `${withJosa(namesLabel(first), "을", "를")} 먼저 넣어 ${data.recipes.length}개 만들었어요`
              : `재고로 ${data.recipes.length}개 만들었어요`}
          </p>
        </div>
      </header>
      {data.sample && (
        <p className="rc-sample">
          <Icon name="info" size={16} />
          예시 레시피로 보여줘요
        </p>
      )}
      <p className="r3-note">
        <Icon name="info" size={16} />
        <span>AI가 만든 레시피예요. 간과 익힘은 맛보면서 조절해주세요.</span>
      </p>
      <ul className="rc-cards">
        {data.recipes.map((recipe, index) => {
          const src = imageSrc(recipe.image_url);
          const have = recipe.ingredients.filter((item) => item.have).length;
          const missing = recipe.ingredients.filter((item) => !item.have).map((item) => item.name);
          const urgent = urgentLabel(recipe.urgent_names);
          return (
            <li key={index} className="rc-card">
              <span className={src ? "rc-thumb" : "rc-thumb rc-ph"}>
                {src ? <img src={src} alt="비슷한 요리 사진" loading="lazy" /> : <Icon name="sparkle" size={28} />}
              </span>
              <span className="rc-body">
                {urgent && <span className="badge old">{urgent}</span>}
                <span className="row-title">{recipe.title}</span>
                <span className="r3-meta">
                  {recipe.servings}인분{recipe.minutes ? ` · ${recipe.minutes}분` : ""}
                </span>
                <MatchLine have={have} total={recipe.ingredients.length} />
              </span>
              {missing.length > 0 && (
                <span className="rc-missing">
                  <span className="label">없는 재료</span>
                  {missing.slice(0, 3).map((name, i) => (
                    <span key={i} className="rc-chip">
                      {name}
                    </span>
                  ))}
                  {missing.length > 3 && <span className="rc-chip more">+{missing.length - 3}</span>}
                </span>
              )}
              <div className="r3-card-actions">
                <button
                  type="button"
                  className="btn secondary"
                  aria-label={`${recipe.title} 자세히`}
                  onClick={() => navigate(`/recipes/ai/${index}`)}
                >
                  자세히
                </button>
                <SaveButton data={data} index={index} />
              </div>
            </li>
          );
        })}
      </ul>
      <div className="rc-actions r3-again">
        <button type="button" className="btn outline" disabled={usedUp} onClick={generate}>
          <Icon name="sparkle" />
          다시 만들기{remainingText(usage)}
        </button>
      </div>
    </>
  );
}

/** #/recipes/ai — 만드는 중 → 결과 3개 */
export default function RecipeAi() {
  const view = useAiState(true);
  return (
    <main className="page">
      <BackLink />
      {view?.status === "done" ? (
        <Results data={view.data} />
      ) : (
        <>
          <header className="topbar">
            <h1>AI 레시피</h1>
          </header>
          {view?.status === "error" ? (
            <section className="r3-loading">
              <span className="scan-fail-icon">
                <Icon name="alert" size={28} />
              </span>
              <p className="r3-loading-title" role="alert">
                {view.message}
              </p>
              <button type="button" className="btn secondary inline r3-back" onClick={() => goBack("/recipes")}>
                돌아가기
              </button>
            </section>
          ) : (
            <Loading urgent={view?.status === "loading" ? view.urgent : []} />
          )}
        </>
      )}
    </main>
  );
}

/** #/recipes/ai/:n — 결과 한 개 자세히(3a 상세 모양). 결과가 없으면(새로고침) 레시피 탭으로 */
export function RecipeAiDetail({ index }: { index: number }) {
  const view = useAiState(false);
  const recipe = view?.status === "done" ? view.data.recipes[index] : undefined;
  useEffect(() => {
    if (!recipe) navigate("/recipes", { replace: true });
  }, [recipe]);
  if (!recipe || view?.status !== "done") return null;
  const src = imageSrc(recipe.image_url);
  return (
    <main className="page">
      <BackLink to="/recipes/ai" label="AI 레시피" />
      {src && <img className="rc-hero" src={src} alt="비슷한 요리 사진" />}
      {src && <p className="hint r3-photo-note">비슷한 요리 사진이에요</p>}
      <header className="rc-head">
        <h1>{recipe.title}</h1>
        <p className="summary">
          {recipe.servings}인분{recipe.minutes ? ` · ${recipe.minutes}분` : ""} · AI가 만든 레시피
        </p>
      </header>
      <RecipeBody servings={recipe.servings} ingredients={recipe.ingredients} steps={recipe.steps} />
      <div className="cta-bar">
        <div className="r3-detail-save">
          <SaveButton data={view.data} index={index} />
        </div>
      </div>
    </main>
  );
}
