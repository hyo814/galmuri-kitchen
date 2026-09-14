import { useEffect, useState, useSyncExternalStore } from "react";
import { api, type AiRecipe, type AiSuggestions, type AiUsage, type Ingredient, type MyRecipe } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import { imageSrc, namesLabel, remainingText, withJosa } from "../format";
import { goBack, navigate } from "../useHashRoute";
import { forgetRecipeCaches, useResource } from "../useResource";
import { BackLink, RecipeBody } from "./RecipeDetail";
import { MatchLine, urgentLabel } from "./Recipes";

type AiState = { status: "loading"; urgent: string[] } | { status: "error"; message: string } | { status: "done"; data: AiSuggestions };

// ponytail: 결과·저장 상태는 모듈 변수(뒤로 갔다 와도 다시 부르지 않음, 새로고침하면 사라짐).
// 만드는 중에 화면을 떠나도 요청은 끊지 않는다(서버는 이미 횟수를 셌다) — 돌아오면 만드는 중이거나 결과가 보인다.
let state: AiState | null = null;
let generation = 0; // 다시 만들기·로그아웃 뒤에 도착한 옛 응답을 버리는 번호
// 저장 상태는 레시피 객체에 붙인다: 다시 만들기 뒤에 끝난 옛 저장이 새 카드에 표시되지 않는다
let saved = new WeakSet<AiRecipe>();
let pending = new WeakSet<AiRecipe>();
let version = 0;
const listeners = new Set<() => void>();

const emit = () => {
  version++;
  listeners.forEach((listener) => listener());
};
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** 모듈 상태가 바뀌면 다시 그린다 */
function useAiStore() {
  useSyncExternalStore(subscribe, () => version);
  return state;
}

/** 로그아웃 때 이전 사용자의 AI 결과가 남지 않게(진행 중인 응답도 버린다) */
export function resetAiRecipes() {
  generation++;
  state = null;
  saved = new WeakSet();
  pending = new WeakSet();
  emit();
}

/** 만드는 중·결과·오류 중 하나라도 있으면 true — 한도를 다 써도 추천 칸 카드로 그 화면을 다시 열 수 있다 */
export function hasAiState() {
  return state !== null;
}

/** 추천 칸 카드가 상태 변화(만드는 중 → 결과)를 따라 다시 그려지게 */
export function useAiStatus() {
  return useAiStore()?.status;
}

/** `만들기`(추천 칸 카드)·`다시 만들기`만 부른다. 이미 만드는 중이면 새로 부르지 않는다. */
export function startAiRecipes() {
  if (state?.status === "loading") return;
  const id = ++generation;
  state = { status: "loading", urgent: [] };
  emit();
  // 만드는 중 문구의 `빨리 먹어야 할 두부·대파`: 재고 중 임박·지남 이름(실패해도 문구만 빠진다)
  api<Ingredient[]>("/api/ingredients")
    .then((items) => {
      if (id !== generation || state?.status !== "loading") return;
      const urgent = items.filter((item) => item.status === "urgent" || item.status === "danger").map((item) => item.name);
      state = { status: "loading", urgent: [...new Set(urgent)] };
      emit();
    })
    .catch(() => {});
  api<AiSuggestions>("/api/recommendations/ai", { method: "POST" }).then(
    (data) => {
      if (id !== generation) return;
      state = { status: "done", data };
      emit();
    },
    (e: unknown) => {
      if (id !== generation) return;
      state = { status: "error", message: (e as Error).message };
      emit();
    },
  );
}

async function saveRecipe(recipe: AiRecipe) {
  if (pending.has(recipe) || saved.has(recipe)) return;
  pending.add(recipe);
  emit();
  try {
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
    saved.add(recipe);
    forgetRecipeCaches();
  } finally {
    pending.delete(recipe);
    emit();
  }
}

/** 저장 → 저장했어요. 버튼 요소를 바꾸지 않아 포커스가 그대로 남는다. 목록과 자세히가 같은 진행 상태를 본다. */
function SaveButton({ recipe }: { recipe: AiRecipe }) {
  useAiStore();
  const [error, setError] = useState("");
  const done = saved.has(recipe);
  const busy = pending.has(recipe);
  const save = async () => {
    if (done || busy) return;
    setError("");
    try {
      await saveRecipe(recipe);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <button
        type="button"
        className={done ? "btn saved" : "btn primary"}
        aria-disabled={done || busy || undefined}
        aria-label={`${recipe.title} ${done ? "저장했어요" : "저장"}`}
        onClick={save}
      >
        <Icon name={done ? "check" : "bookmark"} size={18} />
        {done ? "저장했어요" : busy ? "저장 중…" : "저장"}
      </button>
      <span className="sr-only" role="status">
        {done ? "저장했어요" : ""}
      </span>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

function Loading({ urgent }: { urgent: string[] }) {
  // 알림 영역을 먼저 그려 두고 문구를 나중에 넣어야 스크린리더가 읽는다
  const [announce, setAnnounce] = useState(false);
  useEffect(() => setAnnounce(true), []);
  return (
    <>
      <p className="sr-only" role="status">
        {announce ? "재고를 보고 레시피를 고르고 있어요" : ""}
      </p>
      <section className="r3-loading">
        <Mascot />
        <p className="r3-loading-title" aria-hidden="true">
          재고를 보고 레시피를 고르고 있어요
        </p>
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
  // 결과 화면은 결과가 나온 뒤에만 마운트되므로 첫 요청이 곧 방금 쓴 횟수를 반영한 값이다(따로 다시 부르지 않는다)
  const { data: usage } = useResource<AiUsage>("/api/ai-usage");
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
                <SaveButton recipe={recipe} />
              </div>
            </li>
          );
        })}
      </ul>
      <div className="rc-actions r3-again">
        <button type="button" className="btn outline" disabled={usedUp} onClick={startAiRecipes}>
          <Icon name="sparkle" />
          다시 만들기{remainingText(usage)}
        </button>
      </div>
    </>
  );
}

/** #/recipes/ai — 만드는 중 → 결과 3개. 요청은 `만들기`가 시작한다. 상태가 없으면(새로고침·주소로 열기) 레시피 탭으로 */
export default function RecipeAi() {
  const view = useAiStore();
  useEffect(() => {
    if (!view) navigate("/recipes", { replace: true });
  }, [view]);
  if (!view) return null;
  return (
    <main className="page">
      <BackLink />
      {view.status === "done" ? (
        <Results data={view.data} />
      ) : (
        <>
          <header className="topbar">
            <h1>AI 레시피</h1>
          </header>
          {view.status === "error" ? (
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
            <Loading urgent={view.urgent} />
          )}
        </>
      )}
    </main>
  );
}

/** #/recipes/ai/:n — 결과 한 개 자세히(3a 상세 모양). 결과가 없으면(새로고침) 레시피 탭으로 */
export function RecipeAiDetail({ index }: { index: number }) {
  const view = useAiStore();
  const recipe = view?.status === "done" ? view.data.recipes[index] : undefined;
  useEffect(() => {
    if (!recipe) navigate("/recipes", { replace: true });
  }, [recipe]);
  if (!recipe) return null;
  const src = imageSrc(recipe.image_url);
  return (
    <main className="page">
      <BackLink to="/recipes/ai" label="AI 레시피" />
      {/* 사진 아래 글자가 같은 뜻을 알려주므로 대체 텍스트는 비운다 */}
      {src && <img className="rc-hero" src={src} alt="" />}
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
          <SaveButton recipe={recipe} />
        </div>
      </div>
    </main>
  );
}
