import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { flushSync } from "react-dom";
import { api, type MyRecipe, type RecipeDraft, type RecipeInput } from "../api";
import Icon from "../components/Icon";
import { forgetRecipeNutritionFill } from "../components/RecipeNutrition";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate, setLeaveGuard } from "../useHashRoute";
import { forgetRecipeCaches, useResource } from "../useResource";
import { forgetMealNutritionFill } from "./Meals";

const MAX_INGREDIENTS = 50;
const MAX_STEPS = 30;
const LEAVE_CONFIRM = "작성 중인 내용이 사라져요. 나갈까요?";
const LEAVE_DRAFT_CONFIRM = "가져온 레시피가 사라져요. 나갈까요?";

interface IngredientRow {
  key: number;
  name: string;
  amount: string;
}

interface StepRow {
  key: number;
  text: string;
}

let lastKey = 0;
const newKey = () => ++lastKey;

// U-B1: 만드는 법 textarea가 내용만큼 자란다. field-sizing: content(styles.css)가 안 먹는 브라우저를 위한 JS 보강 —
// ref(마운트 시)와 onChange(입력마다) 양쪽에서 부른다.
export function autoGrowTextarea(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

// 가져온 초안은 모듈 변수로 폼에 넘기고, 폼에 있는 동안 고친 내용까지 sessionStorage에 한 벌 둔다.
// 폰 뒤로가기로 나갔다가 앞으로 가기(또는 새로고침)로 돌아오면 그 히스토리 칸(state.draft)에서만 되살린다.
// 저장·나가기 확인·로그아웃 때 지운다.
let pendingDraft: RecipeDraft | null = null;
const DRAFT_KEY = "recipe-draft";

function storeDraft(draft: RecipeDraft | null) {
  try {
    if (draft) sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    else sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // 저장소를 못 쓰면(사생활 보호 모드 등) 되살리기만 안 된다
  }
}

function storedDraft(): RecipeDraft | null {
  try {
    const draft = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "null") as RecipeDraft | null;
    return Array.isArray(draft?.ingredients) && Array.isArray(draft.steps) ? draft : null;
  } catch {
    return null;
  }
}

/** 로그아웃 때 이전 사용자의 가져온 초안이 남지 않게 */
export function resetRecipeDraft() {
  pendingDraft = null;
  storeDraft(null);
}

/** 링크·글·사진에서 가져온 초안을 `가져온 레시피 확인` 폼으로 연다 */
export function openDraft(draft: RecipeDraft, { replace = false } = {}) {
  pendingDraft = draft;
  navigate("/recipes/new", { replace });
  history.replaceState({ ...(history.state as object | null), draft: true }, ""); // 이 칸으로 돌아오면 되살린다
}

const SOURCE_NAME: Record<RecipeDraft["source"], string> = { youtube: "유튜브", instagram: "인스타그램", blog: "블로그", text: "", photo: "" };

/** 가져온 링크의 출처 카드: 썸네일(외부 사진이라 리퍼러 없이, 저장하지 않음) · 제목 · `유튜브 · 채널명` · 원본 */
function SourceCardView({ draft }: { draft: RecipeDraft }) {
  const card = draft.source_card;
  if (!card) return null;
  const sub = [SOURCE_NAME[draft.source], card.author].filter(Boolean).join(" · ");
  const url = /^https?:\/\//i.test(draft.source_url ?? "") ? draft.source_url : null;
  return (
    <div className="r3-source">
      <span className="r3-source-thumb">
        {card.thumbnail_url ? (
          <img src={card.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <Icon name={draft.source === "youtube" ? "play" : "link"} size={16} />
        )}
      </span>
      <span className="row-main">
        <span className="row-title">{card.title}</span>
        {sub && <span className="row-sub">{sub}</span>}
      </span>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer">
          <Icon name="external" size={16} />
          원본
          <span className="sr-only"> (새 창에서 열려요)</span>
        </a>
      )}
    </div>
  );
}

function BackLink({ onClick, label = "레시피" }: { onClick: () => void; label?: string }) {
  return (
    <a
      className="back-link"
      href="#/recipes"
      onClick={(e) => {
        e.preventDefault();
        onClick();
      }}
    >
      <Icon name="back" size={18} />
      {label}
    </a>
  );
}

function RecipeEditor({ initial, draft = null }: { initial: MyRecipe | null; draft?: RecipeDraft | null }) {
  const start = initial ?? draft;
  const [title, setTitle] = useState(start?.title ?? "");
  const [servings, setServings] = useState(start?.servings ?? 2);
  const [rows, setRows] = useState<IngredientRow[]>(() =>
    (start?.ingredients.length ? start.ingredients : [{ name: "", amount: "" }]).map((item) => ({
      key: newKey(),
      name: item.name,
      amount: item.amount,
    })),
  );
  const [steps, setSteps] = useState<StepRow[]>(() =>
    (start?.steps.length ? start.steps : [""]).map((text) => ({ key: newKey(), text })),
  );
  const [invalidKey, setInvalidKey] = useState<number | null>(null); // 양만 있고 이름이 빈 재료 줄
  const [focusKey, setFocusKey] = useState<number | null>(null); // 방금 추가한 줄에 커서
  const addRowRef = useRef<HTMLButtonElement>(null);
  // 영상 보기에서 가져왔으면 뒤로 링크가 `영상`
  const [fromVideo] = useState(() => !!(history.state as { from?: string } | null)?.from?.startsWith("/recipes/videos/"));
  const { busy, error, setError, run } = useAsyncAction();

  const input = (): RecipeInput => ({
    title: title.trim(),
    servings,
    ingredients: rows
      .filter((row) => row.name.trim() || row.amount.trim())
      .map((row) => ({ name: row.name.trim(), amount: row.amount.trim() })),
    steps: steps.map((step) => step.text.trim()).filter(Boolean),
  });
  const json = JSON.stringify(input());
  const [startJson] = useState(json);
  // 가져온 초안은 고치지 않았어도 나가면 사라지므로(AI 횟수도 이미 썼다) 늘 확인한다
  const dirty = !!draft || json !== startJson;

  useEffect(() => {
    if (draft) storeDraft({ ...draft, ...(JSON.parse(json) as RecipeInput) });
  }, [draft, json]);

  // 앱 안의 뒤로·취소·탭 바가 같은 확인을 쓴다. 폰의 뒤로가기 버튼은 막을 수 없어(popstate는 취소 불가) 초안을 되살리는 것으로 대신한다.
  const canLeave = () => {
    if (dirty && !confirm(draft ? LEAVE_DRAFT_CONFIRM : LEAVE_CONFIRM)) return false;
    if (draft) resetRecipeDraft();
    return true;
  };
  useEffect(() => {
    setLeaveGuard(canLeave);
    return () => setLeaveGuard(null);
  });

  const leave = () => {
    if (canLeave()) goBack(initial ? `/recipes/mine/${initial.id}` : "/recipes");
  };

  const updateRow = (key: number, patch: Partial<IngredientRow>) =>
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));

  const addRow = () => {
    const key = newKey();
    setRows((prev) => [...prev, { key, name: "", amount: "" }]);
    setFocusKey(key);
  };

  const addStep = () => {
    const key = newKey();
    setSteps((prev) => [...prev, { key, text: "" }]);
    setFocusKey(key);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const nameless = rows.find((row) => !row.name.trim() && row.amount.trim());
    setInvalidKey(nameless?.key ?? null);
    if (nameless) {
      // U-S4: 잘못된 줄을 화면 가운데로 가져오고 이름 입력으로 포커스를 옮긴다
      const invalidInput = document.getElementById(`ingredient-name-${nameless.key}`);
      invalidInput?.scrollIntoView({ block: "center" });
      (invalidInput as HTMLInputElement | null)?.focus();
      return;
    }
    const body = draft ? { ...input(), source: draft.source, source_url: draft.source_url } : input();
    if (body.ingredients.length === 0) {
      setError("재료를 하나 이상 입력해주세요.");
      return;
    }
    run(async () => {
      const saved = await api<MyRecipe>(initial ? `/api/recipes/${initial.id}` : "/api/recipes", {
        method: initial ? "PUT" : "POST",
        body,
      });
      forgetRecipeCaches();
      forgetRecipeNutritionFill(saved.id); // 재료가 바뀌었을 수 있다 — 영양 채우기를 다시 부르게
      forgetMealNutritionFill(saved.id);
      if (draft) resetRecipeDraft();
      if (initial) goBack(`/recipes/mine/${saved.id}`);
      else navigate(`/recipes/mine/${saved.id}`, { replace: true }); // 뒤로가기하면 목록으로
    });
  };

  return (
    <main className="page">
      <BackLink onClick={leave} label={draft ? (fromVideo ? "영상" : "내 레시피") : "레시피"} />
      <header className="topbar">
        {draft ? (
          <div>
            <h1>가져온 레시피 확인</h1>
            <p className="summary">
              AI가 정리했어요. 틀린 곳을 고친 뒤 저장해주세요{draft.sample && " · 예시 초안이에요"}
            </p>
          </div>
        ) : (
          <h1>{initial ? "레시피 수정" : "레시피 추가"}</h1>
        )}
      </header>
      {draft && <SourceCardView draft={draft} />}

      <form className="rc-page-form" onSubmit={submit}>
        <section className="rc-sec rc-form">
          <label className="field">
            <span className="field-label">이름</span>
            <input
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={60}
              placeholder="예: 애호박볶음"
              autoFocus={!start}
            />
          </label>
          <div className="field">
            <span className="field-label" id="recipe-servings">
              인분
            </span>
            <div className="stepper">
              <button
                type="button"
                className="icon-btn"
                aria-label="인분 줄이기"
                disabled={servings <= 1}
                onClick={() => setServings(servings - 1)}
              >
                <Icon name="minus" />
              </button>
              <output className="input rc-count" aria-labelledby="recipe-servings" aria-live="polite">
                {servings}
              </output>
              <button
                type="button"
                className="icon-btn"
                aria-label="인분 늘리기"
                disabled={servings >= 20}
                onClick={() => setServings(servings + 1)}
              >
                <Icon name="plus" />
              </button>
            </div>
          </div>
        </section>

        <section className="rc-sec" aria-labelledby="recipe-ingredients">
          <div className="rc-sec-head">
            <h2 id="recipe-ingredients">
              재료
              {draft && <span className="r3-count">{rows.filter((row) => row.name.trim()).length}개</span>}
            </h2>
            <span className="hint">양은 비워도 괜찮아요</span>
          </div>
          <div className="rc-rows">
            {rows.map((row, index) => {
              const invalid = invalidKey === row.key;
              return (
                <Fragment key={row.key}>
                  <div className="rc-ing-row">
                    <input
                      id={`ingredient-name-${row.key}`}
                      className={invalid ? "input invalid" : "input"}
                      aria-label={`${index + 1}번째 재료 이름`}
                      aria-invalid={invalid}
                      aria-describedby={invalid ? `recipe-error-${row.key}` : undefined}
                      placeholder="재료 이름"
                      maxLength={50}
                      value={row.name}
                      autoFocus={focusKey === row.key}
                      onChange={(e) => {
                        if (invalid) setInvalidKey(null);
                        updateRow(row.key, { name: e.target.value });
                      }}
                    />
                    <input
                      className="input"
                      aria-label={`${index + 1}번째 재료 양`}
                      placeholder="양"
                      maxLength={30}
                      value={row.amount}
                      onChange={(e) => updateRow(row.key, { amount: e.target.value })}
                    />
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`${row.name.trim() || "빈 재료"} 빼기`}
                      onClick={() => {
                        // 뺀 뒤 다음 줄 이름 칸(마지막 줄이었으면 `재료 추가`)으로 포커스
                        const next = rows[index + 1];
                        flushSync(() => setRows((prev) => prev.filter((r) => r.key !== row.key)));
                        (next ? document.getElementById(`ingredient-name-${next.key}`) : addRowRef.current)?.focus();
                      }}
                    >
                      <Icon name="trash" />
                    </button>
                  </div>
                  {invalid && (
                    <p className="rc-err" id={`recipe-error-${row.key}`} role="alert">
                      <Icon name="alert" size={16} />
                      재료 이름을 입력해주세요
                    </p>
                  )}
                </Fragment>
              );
            })}
          </div>
          <button ref={addRowRef} type="button" className="btn secondary rc-add" disabled={rows.length >= MAX_INGREDIENTS} onClick={addRow}>
            <Icon name="plus" />
            재료 추가
          </button>
        </section>

        <section className="rc-sec" aria-labelledby="recipe-steps">
          <h2 id="recipe-steps">만드는 법</h2>
          <div className="rc-rows">
            {steps.map((step, index) => (
              <div key={step.key} className="rc-step-row">
                <span className="rc-num" aria-hidden="true">
                  {index + 1}
                </span>
                <textarea
                  ref={autoGrowTextarea}
                  className="input rc-area"
                  aria-label={`${index + 1}단계`}
                  rows={2}
                  maxLength={500}
                  value={step.text}
                  autoFocus={focusKey === step.key}
                  onChange={(e) => {
                    autoGrowTextarea(e.currentTarget);
                    setSteps((prev) => prev.map((s) => (s.key === step.key ? { ...s, text: e.target.value } : s)));
                  }}
                />
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={`${index + 1}단계 빼기`}
                  onClick={() => setSteps((prev) => prev.filter((s) => s.key !== step.key))}
                >
                  <Icon name="trash" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="btn secondary rc-add" disabled={steps.length >= MAX_STEPS} onClick={addStep}>
            <Icon name="plus" />
            단계 추가
          </button>
        </section>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <div className="cta-bar">
          <div className="actions">
            <button type="button" className="btn outline" onClick={leave}>
              취소
            </button>
            <button className="btn primary" disabled={busy}>
              {busy ? "저장 중…" : "저장"}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}

function EditRecipe({ id }: { id: string }) {
  const { data, error, status, reload } = useResource<MyRecipe>(`/api/recipes/${id}`);
  if (data) return <RecipeEditor initial={data} />;
  return (
    <main className="page">
      <BackLink onClick={() => goBack(`/recipes/mine/${id}`)} />
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
}

/** /recipes/new (id 없음) · /recipes/mine/:id/edit */
function NewRecipe() {
  // StrictMode가 초기화 함수를 두 번 불러도 같은 초안을 받게, 비우는 건 effect에서 한다.
  // 넘겨받은 초안이 없어도 가져온 초안의 히스토리 칸이면(뒤로 → 앞으로·새로고침) 고치던 내용을 되살린다.
  const [draft] = useState(() => pendingDraft ?? ((history.state as { draft?: boolean } | null)?.draft ? storedDraft() : null));
  useEffect(() => {
    pendingDraft = null;
  }, []);
  return <RecipeEditor initial={null} draft={draft} />;
}

export default function RecipeForm({ id }: { id?: string }) {
  return id ? <EditRecipe id={id} /> : <NewRecipe />;
}
