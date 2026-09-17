import { useState, type ReactNode } from "react";
import { api, type MyRecipe, type RecipeDetail as Detail, type RecipeIngredientStatus, type User } from "../api";
import { cookedLine, savedRecipeNote } from "../cooklog/cook.ts";
import CookSheet, { toastSaved } from "../components/CookSheet";
import Icon from "../components/Icon";
import RecipeNutrition from "../components/RecipeNutrition";
import ShoppingAddButton from "../components/ShoppingAddButton";
import { starsText } from "../foodlog/log.ts";
import { SOURCE_LABEL, imageSrc, scaleAmount, withJosa } from "../format";
import { spoonHint } from "../seasoning";
import { quantityText, recipeQuantity } from "../shopping/sync";
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

/** 재료(인분 조절·있어요 표시)와 만드는 법. 내 레시피·공공 레시피·AI 레시피 상세가 같이 쓴다 */
export function RecipeBody({
  title,
  servings: rawBase,
  ingredients,
  steps,
  afterIngredients,
  justCooked,
}: {
  title: string;
  servings: number;
  ingredients: RecipeIngredientStatus[];
  steps: string[];
  /** 재료 아래, 만드는 법 위에 그릴 내용(레시피 상세 영양 칸) */
  afterIngredients?: ReactNode;
  /** 방금 요리했어요로 재고에서 다 빠진 재료 줄 이름(item.name) — 그 줄만 "다 썼어요"(29절, 되돌리기·화면을 나가면 사라짐) */
  justCooked?: Set<string>;
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
          {ingredients.map((item, index) => {
            const amount = scaleAmount(item.amount, ratio);
            // 인분을 바꿔 양이 달라진 큰술·작은술만 아래 회색 줄(레시피 인분이면 지금과 같다)
            const hint = amount !== item.amount ? spoonHint(recipeQuantity(amount)) : null;
            return (
              <li key={index} className="plain-row">
                <span className="staple-name">
                  {item.name}
                  {item.amount && (
                    <span className={hint ? "rc-amt rc-spoon" : "rc-amt"}>
                      {amount}
                      {hint && (
                        <small>
                          <span className="sr-only">, </span>
                          {hint}
                        </small>
                      )}
                    </span>
                  )}
                </span>
                {justCooked?.has(item.name) ? (
                  <span className="stock-warn">다 썼어요</span>
                ) : item.have ? (
                  <span className="stock-col">
                    <span className="stock-ok">
                      <Icon name="check" size={16} />
                      있어요
                      {item.stock_quantity != null && item.stock_unit && ` ${quantityText(item.stock_quantity, item.stock_unit)}`}
                    </span>
                    {/* 매칭된 재고 이름이 다르면 둘째 줄에 작게(길면 말줄임) — 첫 줄과 합치면 재료 이름 칸이 꺾인다(리뷰) */}
                    {item.matched_name && item.matched_name !== item.name && <small className="stock-alt">{item.matched_name}</small>}
                  </span>
                ) : (
                  <span className="badge">없어요</span>
                )}
              </li>
            );
          })}
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

export default function RecipeDetail({ kind, id, user }: { kind: "mine" | "public"; id: string; user: User }) {
  const {
    data: recipe,
    error,
    status,
    reload,
  } = useResource<Detail>(kind === "mine" ? `/api/recipes/${id}` : `/api/public-recipes/${id}`);
  const { busy, error: actionError, run } = useAsyncAction();
  // 추천 레시피 요리했어요가 저장 중인지(저장만과 잠금은 run 하나 — 한 번에 둘 다 눌러도 요청 하나, 리뷰 F6)
  const [opening, setOpening] = useState(false);
  // 요리했어요 시트: 내 레시피 id(추천 레시피는 저장한 복사본)와 맨 위 한 줄
  const [cooking, setCooking] = useState<{ recipeId: number; note?: string } | null>(null);
  // 방금 요리했어요로 다 쓴 재고 이름(matched_name) — 되돌리거나 화면을 나가면 App이 새로 만들어 사라진다(29절)
  const [justCooked, setJustCooked] = useState<Set<string>>(() => new Set());

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

  // 결정 C(29절 추가 2026-09-16): 추천 레시피의 요리했어요는 내 레시피로 저장(이미 저장했으면 그 복사본)한 뒤 같은 시트를 연다.
  // 이 화면에 남는다 — 되돌려도 저장한 레시피는 그대로(되돌리기는 요리 일기만)
  const cookPublic = () => {
    if (busy) return;
    // opening은 run이 실제로 시작할 때만 켜고 끈다(run의 inFlight 가드가 두 번째 탭에서 action을 아예 안 부르므로,
    // 여기 안에 두면 먼저 시작한 요청이 남아있는데 두 번째 탭 때문에 opening이 꺼지지 않는다 — 리뷰 발견)
    void run(async () => {
      setOpening(true);
      try {
        const res = await api<Response>(`/api/public-recipes/${recipe.id}/save`, { method: "POST", raw: true });
        // 응답 본문을 못 읽으면 영어 SyntaxError 대신 공통 문구(api의 기본 오류와 같게, 리뷰 FYI3)
        const saved: MyRecipe = await res.json().catch(() => {
          throw new Error("문제가 생겼어요. 잠시 후 다시 시도해주세요.");
        });
        forgetRecipeCaches();
        setCooking({ recipeId: saved.id, note: savedRecipeNote(saved.title, res.status === 201) });
      } finally {
        setOpening(false);
      }
    });
  };

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
        justCooked={justCooked}
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
          {/* 알림이 떠 있으면 styles.css가 버튼을 알림 위로 올린다(시안 2). data-cook-button: 되돌린 뒤 포커스가 돌아올 자리 */}
          <div className="cta-bar">
            <button className="btn primary" aria-haspopup="dialog" data-cook-button disabled={busy} onClick={() => setCooking({ recipeId: recipe.id })}>
              <Icon name="pan" />
              요리했어요
            </button>
          </div>
        </>
      ) : (
        <div className="cta-bar">
          {/* 시안 ⑤: 저장만(작게) + 요리했어요(크게). 요리했어요는 저장하는 동안에도 disabled 대신 aria-disabled — 포커스가 남아 시트를 닫으면 돌아온다 */}
          <div className="actions">
            <button className="btn outline ck-save-only" aria-label={busy && !opening ? undefined : "내 레시피로 저장만 하기"} disabled={busy} onClick={save}>
              <Icon name="bookmark" size={18} />
              {busy && !opening ? "저장 중…" : "저장만"}
            </button>
            <button className="btn primary" aria-haspopup="dialog" aria-disabled={busy || undefined} data-cook-button onClick={cookPublic}>
              <Icon name="pan" />
              {opening ? "저장 중…" : "요리했어요"}
            </button>
          </div>
        </div>
      )}
      {cooking && (
        <CookSheet
          recipeId={cooking.recipeId}
          user={user}
          note={cooking.note}
          onSaved={(result) => {
            toastSaved(result); // 되돌리면 App이 지금 화면을 새로 만든다(justCooked도 이때 사라진다)
            // 다 쓴 재고 이름(log.items[].name)을 지금 화면의 재료 줄 이름으로 바꿔 둔다 — reload 뒤엔 매칭이 끊겨 matched_name이 없어진다
            const usedUpStock = new Set(result.log.items.filter((item) => item.removed).map((item) => item.name));
            setJustCooked(new Set(recipe.ingredients.filter((item) => item.matched_name && usedUpStock.has(item.matched_name)).map((item) => item.name)));
            void reload(); // 재고 표시·요리 표시를 새로
          }}
          onClose={() => setCooking(null)}
        />
      )}
    </main>
  );
}
