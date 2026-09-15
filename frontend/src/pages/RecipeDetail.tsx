import { useEffect, useState, type ReactNode } from "react";
import { api, type MyRecipe, type RecipeDetail as Detail, type RecipeIngredientStatus, type User } from "../api";
import { cookedLine } from "../cooklog/cook.ts";
import CookSheet, { toastSaved } from "../components/CookSheet";
import Icon from "../components/Icon";
import RecipeNutrition from "../components/RecipeNutrition";
import ShoppingAddButton from "../components/ShoppingAddButton";
import { useUndoToastVisible } from "../components/UndoToast";
import { starsText } from "../foodlog/log.ts";
import { SOURCE_LABEL, imageSrc, scaleAmount, withJosa } from "../format";
import { recipeQuantity } from "../shopping/sync";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetRecipeCaches, useResource } from "../useResource";
import { MatchLine, setRecipesSegment } from "./Recipes";

export function BackLink({ to = "/recipes", label = "레시피" }: { to?: string; label?: string }) {
  return (
    <a
      className="back-link"
      href={`#${to}`}
      onClick={(e) => {
        e.preventDefault();
        goBack(to);
      }}
    >
      <Icon name="back" size={18} />
      {label}
    </a>
  );
}

/** 재료(인분 조절·있음 표시)와 만드는 법. 내 레시피·공공 레시피·AI 레시피 상세가 같이 쓴다 */
export function RecipeBody({
  title,
  servings: rawBase,
  ingredients,
  steps,
  afterIngredients,
}: {
  title: string;
  servings: number;
  ingredients: RecipeIngredientStatus[];
  steps: string[];
  /** 재료 아래, 만드는 법 위에 그릴 내용(레시피 상세 영양 칸) */
  afterIngredients?: ReactNode;
}) {
  const base = Math.max(1, rawBase || 1); // 인분이 0·빈 값이면 비율이 NaN이 되지 않게
  const [servings, setServings] = useState<number | null>(null); // null이면 레시피 기준 인분
  const shown = servings ?? base;
  const ratio = shown / base;
  const have = ingredients.filter((item) => item.have).length;
  // 보이는 양(인분 조절 반영)을 수량·단위로 읽어 담는다. 못 읽는 양("약간")은 1 약간 — 23절 D4 합산은 4b
  const missing = ingredients
    .filter((item) => !item.have)
    .map((item) => ({ name: item.name, ...recipeQuantity(scaleAmount(item.amount, ratio)) }));
  return (
    <>
      <section className="rc-sec" aria-labelledby="rc-ingredients">
        <div className="rc-sec-head">
          <h2 id="rc-ingredients">재료</h2>
          <div className="rc-serv" role="group" aria-label="인분 조절">
            <button
              type="button"
              className="icon-btn"
              aria-label="인분 줄이기"
              disabled={shown <= 1}
              onClick={() => setServings(shown - 1)}
            >
              <Icon name="minus" />
            </button>
            <b aria-live="polite">{shown}인분</b>
            <button
              type="button"
              className="icon-btn"
              aria-label="인분 늘리기"
              disabled={shown >= 20}
              onClick={() => setServings(shown + 1)}
            >
              <Icon name="plus" />
            </button>
          </div>
        </div>
        {ingredients.length > 0 && (
          <div className="rc-have">
            <MatchLine have={have} total={ingredients.length} />
          </div>
        )}
        <ul className="rc-ings">
          {ingredients.map((item, index) => (
            <li key={index} className="plain-row">
              <span className="staple-name">
                {item.name}
                {item.amount && <span className="rc-amt">{scaleAmount(item.amount, ratio)}</span>}
              </span>
              {item.have ? (
                <span className="stock-ok">
                  <Icon name="check" size={16} />
                  {item.matched_name ? `있음 · ${item.matched_name}` : "있음"}
                </span>
              ) : (
                <span className="badge">없음</span>
              )}
            </li>
          ))}
        </ul>
        {missing.length > 0 && (
          <ShoppingAddButton
            className="sh-missing-cta"
            source="recipe"
            sourceLabel={title}
            items={missing}
            label={`없는 재료 ${missing.length}개 장보기에 담기`}
          />
        )}
      </section>

      {afterIngredients}

      {steps.length > 0 && (
        <section className="rc-sec" aria-labelledby="rc-steps">
          <h2 id="rc-steps">만드는 법</h2>
          <ol className="rc-steps">
            {steps.map((step, index) => (
              <li key={index}>
                <span className="rc-num" aria-hidden="true">
                  {index + 1}
                </span>
                <p>{step}</p>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

/** 지금 떠 있는 레시피 상세의 다시 받기. 알림의 되돌리기는 화면을 떠난 뒤에도 누를 수 있어, 떠난 화면은 빠지고
 * 같은 레시피를 다시 연 새 화면은 들어 있게 인스턴스가 아니라 여기서 부른다(떠났다 돌아온 화면이 옛 `요리 1번`을 보이지 않게) */
const shownDetails = new Set<() => void>();

export default function RecipeDetail({ kind, id, user }: { kind: "mine" | "public"; id: string; user: User }) {
  const {
    data: recipe,
    error,
    status,
    reload,
  } = useResource<Detail>(kind === "mine" ? `/api/recipes/${id}` : `/api/public-recipes/${id}`);
  const { busy, error: actionError, run } = useAsyncAction();
  const [cooking, setCooking] = useState(false);
  const toastVisible = useUndoToastVisible();
  useEffect(() => {
    shownDetails.add(reload);
    return () => {
      shownDetails.delete(reload);
    };
  }, [reload]);

  if (!recipe)
    return (
      <main className="page">
        <BackLink />
        {status === 404 ? (
          // M8: 지워진 레시피는 다시 불러와도 또 404라 재시도 버튼을 주지 않는다
          <p className="center muted">레시피를 찾을 수 없어요.</p>
        ) : error ? (
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
        )}
      </main>
    );

  const src = imageSrc(recipe.image_url);
  const meta = [
    `${recipe.servings}인분`,
    recipe.category,
    recipe.kind === "public" && recipe.is_sample ? "예시 레시피" : null,
    recipe.kind === "mine" ? SOURCE_LABEL[recipe.source] : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const similarPhoto = recipe.kind === "mine" && recipe.source === "ai";
  const sourceUrl = recipe.kind === "mine" && /^https?:\/\//i.test(recipe.source_url ?? "") ? recipe.source_url : null;

  const save = () =>
    run(async () => {
      const saved = await api<MyRecipe>(`/api/public-recipes/${recipe.id}/save`, { method: "POST" });
      forgetRecipeCaches();
      navigate(`/recipes/mine/${saved.id}`, { replace: true });
    });

  const remove = () => {
    if (!confirm(`${withJosa(recipe.title, "을", "를")} 삭제할까요?`)) return;
    run(async () => {
      await api(`/api/recipes/${recipe.id}`, { method: "DELETE" });
      forgetRecipeCaches();
      setRecipesSegment("mine"); // E1: 삭제 뒤 뒤로가기하면 내 레시피 탭에 있게
      goBack("/recipes");
    });
  };

  return (
    <main className="page">
      <BackLink />
      {src && <img className="rc-hero" src={src} alt="" />}
      {src && similarPhoto && <p className="hint r3-photo-note">비슷한 요리 사진이에요 · 사진: 식품안전나라</p>}
      <header className="rc-head">
        <h1>{recipe.title}</h1>
        <p className="summary r3-summary">
          <span>{meta}</span>
          {sourceUrl && (
            <>
              <span aria-hidden="true">·</span>
              <a className="r3-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">
                원본 보기
                <Icon name="external" size={16} />
                <span className="sr-only"> (새 창에서 열려요)</span>
              </a>
            </>
          )}
        </p>
      </header>
      {recipe.kind === "mine" && recipe.cooked && (
        <p className="ck-cooked">
          <span className="badge info">요리 {recipe.cooked.count}번</span>
          <span className="muted" aria-hidden="true">
            {cookedLine(recipe.cooked, starsText)}
          </span>
          <span className="sr-only">{cookedLine(recipe.cooked, (n) => `별점 ${n}점`)}</span>
        </p>
      )}

      <RecipeBody
        title={recipe.title}
        servings={recipe.servings}
        ingredients={recipe.ingredients}
        steps={recipe.steps}
        afterIngredients={
          recipe.kind === "mine" && user.nutrition !== "off" && <RecipeNutrition recipeId={recipe.id} user={user} />
        }
      />

      {recipe.kind === "public" && !recipe.is_sample && (
        <p className="hint rc-source">
          출처:{" "}
          <a href="https://www.foodsafetykorea.go.kr" target="_blank" rel="noopener noreferrer">
            식품의약품안전처 식품안전나라 조리식품 레시피 DB
            <span className="sr-only"> (새 창에서 열려요)</span>
          </a>
        </p>
      )}

      {actionError && (
        <p className="error" role="alert">
          {actionError}
        </p>
      )}

      {recipe.kind === "mine" ? (
        <>
          <div className="rc-actions">
            <button className="btn outline" onClick={() => navigate(`/recipes/mine/${recipe.id}/edit`)}>
              <Icon name="pencil" />
              수정
            </button>
            <button className="btn danger-text" disabled={busy} onClick={remove}>
              이 레시피 삭제
            </button>
          </div>
          {/* 알림이 떠 있으면 버튼을 알림 위로 올린다(시안 2) */}
          <div className={toastVisible ? "cta-bar ck-lift" : "cta-bar"}>
            <button className="btn primary" aria-haspopup="dialog" disabled={busy} onClick={() => setCooking(true)}>
              <Icon name="pan" />
              요리했어요
            </button>
          </div>
          {cooking && (
            <CookSheet
              recipeId={recipe.id}
              user={user}
              onSaved={(result) => {
                toastSaved(result, () => shownDetails.forEach((reloadShown) => reloadShown())); // 되돌린 뒤에도 재고 표시·요리 표시를 새로
                void reload();
              }}
              onClose={() => setCooking(false)}
            />
          )}
        </>
      ) : (
        <div className="cta-bar">
          <button className="btn primary" disabled={busy} onClick={save}>
            <Icon name="bookmark" />
            {busy ? "저장 중…" : "내 레시피로 저장"}
          </button>
        </div>
      )}
    </main>
  );
}
