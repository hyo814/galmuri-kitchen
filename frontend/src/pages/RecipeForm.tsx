import { Fragment, useState, type FormEvent } from "react";
import { api, type MyRecipe, type RecipeInput } from "../api";
import Icon from "../components/Icon";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetRecipeCaches, useResource } from "../useResource";

const MAX_INGREDIENTS = 50;
const MAX_STEPS = 30;
const LEAVE_CONFIRM = "작성 중인 내용이 사라져요. 나갈까요?";

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
function autoGrowTextarea(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

function BackLink({ onClick }: { onClick: () => void }) {
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
      레시피
    </a>
  );
}

function RecipeEditor({ initial }: { initial: MyRecipe | null }) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [servings, setServings] = useState(initial?.servings ?? 2);
  const [rows, setRows] = useState<IngredientRow[]>(() =>
    (initial?.ingredients ?? [{ name: "", amount: "" }]).map((item) => ({ key: newKey(), name: item.name, amount: item.amount })),
  );
  const [steps, setSteps] = useState<StepRow[]>(() =>
    (initial?.steps.length ? initial.steps : [""]).map((text) => ({ key: newKey(), text })),
  );
  const [invalidKey, setInvalidKey] = useState<number | null>(null); // 양만 있고 이름이 빈 재료 줄
  const [focusKey, setFocusKey] = useState<number | null>(null); // 방금 추가한 줄에 커서
  const { busy, error, setError, run } = useAsyncAction();

  const input = (): RecipeInput => ({
    title: title.trim(),
    servings,
    ingredients: rows
      .filter((row) => row.name.trim() || row.amount.trim())
      .map((row) => ({ name: row.name.trim(), amount: row.amount.trim() })),
    steps: steps.map((step) => step.text.trim()).filter(Boolean),
  });
  const [startJson] = useState(() => JSON.stringify(input()));
  const dirty = JSON.stringify(input()) !== startJson;

  // ponytail: 앱 안의 뒤로·취소만 확인한다. 폰의 뒤로가기 버튼은 막을 수 없어(popstate는 취소 불가) 그대로 나간다.
  const leave = () => {
    if (dirty && !confirm(LEAVE_CONFIRM)) return;
    goBack(initial ? `/recipes/mine/${initial.id}` : "/recipes");
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
    const body = input();
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
      if (initial) goBack(`/recipes/mine/${saved.id}`);
      else navigate(`/recipes/mine/${saved.id}`, { replace: true }); // 뒤로가기하면 목록으로
    });
  };

  return (
    <main className="page">
      <BackLink onClick={leave} />
      <header className="topbar">
        <h1>{initial ? "레시피 수정" : "레시피 추가"}</h1>
      </header>

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
              autoFocus={!initial}
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
            <h2 id="recipe-ingredients">재료</h2>
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
                      onClick={() => setRows((prev) => prev.filter((r) => r.key !== row.key))}
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
          <button type="button" className="btn secondary rc-add" disabled={rows.length >= MAX_INGREDIENTS} onClick={addRow}>
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
export default function RecipeForm({ id }: { id?: string }) {
  return id ? <EditRecipe id={id} /> : <RecipeEditor initial={null} />;
}
