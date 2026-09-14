import { Fragment, useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import Icon from "../components/Icon";
import {
  BASIS_UNITS,
  amountInputText,
  parseAmountInput,
  type Basis,
  type BasisUnit,
  type Seasoning,
  type SeasoningUnit,
} from "../seasoning";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetResources, useResource } from "../useResource";

const MAX_ITEMS = 30;
const UNITS: SeasoningUnit[] = ["큰술", "작은술", "컵", "ml", "g", "개", "꼬집"];
const BASES: [Basis, string][] = [
  ["main_weight", "주재료 무게"],
  ["servings", "인분"],
  ["yield", "완성량"],
];
const LEAVE_CONFIRM = "작성 중인 내용이 사라져요. 나갈까요?";
const AMOUNT_ERROR = "양을 숫자나 ½처럼 입력해주세요";

interface ItemRow {
  key: number;
  name: string;
  amount: string;
  unit: SeasoningUnit;
}

type RowField = "name" | "amount" | "unit";
interface Errors {
  name?: string;
  basis?: string;
  row?: { key: number; field: RowField; message: string };
}

let lastKey = 0;
const newKey = () => ++lastKey;

// 기본 양념의 `이 비율 고쳐서 내 비율로`: 폼으로 넘길 내용. 폼이 열리면 비운다(새로 만들기가 옛 내용으로 열리지 않게).
// ponytail: 모듈 변수라 새로고침하면 빈 폼. 링크로 공유할 일이 생기면 경로(#/recipes/seasonings/new?preset=1)로 옮긴다.
let draft: Seasoning | null = null;

export function openSeasoningDraft(seasoning: Seasoning) {
  draft = seasoning;
  navigate("/recipes/seasonings/new");
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
      양념 비율
    </a>
  );
}

function focusField(id: string) {
  const el = document.getElementById(id);
  el?.scrollIntoView({ block: "center" });
  el?.focus();
}

function SeasoningEditor({ initial, editId }: { initial: Seasoning | null; editId: number | null }) {
  const [name, setName] = useState(initial?.name ?? "");
  const [basis, setBasis] = useState<Basis>(initial?.basis ?? "main_weight");
  const [mainIngredient, setMainIngredient] = useState(initial?.main_ingredient ?? "");
  const [basisText, setBasisText] = useState(initial ? amountInputText(initial.basis_amount) : "");
  const [basisUnit, setBasisUnit] = useState<BasisUnit>(initial?.basis_unit ?? "g");
  const [rows, setRows] = useState<ItemRow[]>(() =>
    (initial?.items ?? [{ name: "", amount: 0, unit: "큰술" as const }]).map((item) => ({
      key: newKey(),
      name: item.name,
      amount: item.amount ? amountInputText(item.amount) : "",
      unit: item.unit,
    })),
  );
  const [errors, setErrors] = useState<Errors>({});
  const [focusKey, setFocusKey] = useState<number | null>(null);
  const { busy, error, setError, run } = useAsyncAction();

  const snapshot = JSON.stringify([name, basis, mainIngredient, basisText, basisUnit, rows.map(({ key: _, ...row }) => row)]);
  const [start] = useState(snapshot);
  const dirty = snapshot !== start;

  // ponytail: 앱 안의 뒤로·취소만 확인한다(RecipeForm과 같음). 폰 뒤로가기는 막을 수 없다.
  const leave = () => {
    if (dirty && !confirm(LEAVE_CONFIRM)) return;
    goBack(editId ? `/recipes/seasonings/${editId}` : "/recipes");
  };

  const updateRow = (key: number, patch: Partial<ItemRow>) => {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
    if (errors.row?.key === key) setErrors({ ...errors, row: undefined });
  };

  const addRow = () => {
    const key = newKey();
    setRows((prev) => [...prev, { key, name: "", amount: "", unit: "큰술" }]);
    setFocusKey(key);
  };

  const chooseBasis = (next: Basis) => {
    setBasis(next);
    setBasisUnit(BASIS_UNITS[next][0]);
    setErrors({ ...errors, basis: undefined });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const filled = rows.filter((row) => row.name.trim() || row.amount.trim());
    const bad = filled.find((row) => !row.name.trim() || parseAmountInput(row.amount) === null);
    const basisAmount = parseAmountInput(basisText);
    const next: Errors = {};
    if (basisAmount === null || (basis === "servings" && !(Number.isInteger(basisAmount) && basisAmount <= 20)))
      next.basis = "기준 양을 다시 확인해주세요.";
    if (bad)
      next.row = bad.name.trim()
        ? { key: bad.key, field: "amount", message: AMOUNT_ERROR }
        : { key: bad.key, field: "name", message: "양념 이름을 입력해주세요" };
    setErrors(next);
    if (next.basis) return focusField("seasoning-basis-amount");
    if (next.row) return focusField(`seasoning-${next.row.field}-${next.row.key}`);
    if (filled.length === 0) return setError("양념 재료를 하나 이상 입력해주세요.");

    run(async () => {
      const body = {
        name: name.trim(),
        basis,
        basis_amount: basisAmount,
        basis_unit: basisUnit,
        main_ingredient: basis === "main_weight" ? mainIngredient.trim() || null : null,
        items: filled.map((row) => ({ name: row.name.trim(), amount: parseAmountInput(row.amount), unit: row.unit })),
      };
      try {
        const saved = await api<Seasoning>(editId ? `/api/seasonings/${editId}` : "/api/seasonings", {
          method: editId ? "PUT" : "POST",
          body,
        });
        forgetResources("/api/seasonings");
        if (editId) goBack(`/recipes/seasonings/${saved.id}`);
        else navigate(`/recipes/seasonings/${saved.id}`, { replace: true }); // 뒤로가기하면 목록(또는 기본 양념)으로
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 400)) throw err;
        // 서버 문구를 해당 칸 아래에: "N번째 양념 …"은 그 줄, 이름(중복 포함)은 이름 칸, 기준·주재료는 기준 칸
        const message = err.message;
        const rowMatch = message.match(/^(\d+)번째 양념 (이름|양|단위)/);
        const row = rowMatch && filled[Number(rowMatch[1]) - 1];
        if (row) {
          const field: RowField = rowMatch[2] === "이름" ? "name" : rowMatch[2] === "양" ? "amount" : "unit";
          setErrors({ row: { key: row.key, field, message } });
          focusField(`seasoning-${field}-${row.key}`);
        } else if (message.startsWith("이름") || message.startsWith("같은 이름")) {
          setErrors({ name: message });
          focusField("seasoning-name");
        } else if (message.startsWith("기준") || message.startsWith("주재료")) {
          setErrors({ basis: message });
          focusField("seasoning-basis-amount");
        } else throw err;
      }
    });
  };

  const basisAmountInput = (
    <input
      id="seasoning-basis-amount"
      className={errors.basis ? "input invalid" : "input"}
      inputMode={basis === "servings" ? "numeric" : "decimal"}
      aria-label={`기준 양 (${basisUnit})`}
      aria-invalid={!!errors.basis}
      aria-describedby={errors.basis ? "seasoning-basis-error" : undefined}
      placeholder={basis === "main_weight" ? "600" : basis === "servings" ? "2" : "½"}
      maxLength={8}
      value={basisText}
      onChange={(e) => {
        setBasisText(e.target.value);
        if (errors.basis) setErrors({ ...errors, basis: undefined });
      }}
    />
  );

  return (
    <main className="page">
      <BackLink onClick={leave} />
      <header className="topbar">
        <h1>{editId ? "내 비율 고치기" : "내 비율 만들기"}</h1>
      </header>

      <form className="rc-page-form" onSubmit={submit}>
        <section className="rc-sec rc-form">
          <div className="field">
            <label className="field-label" htmlFor="seasoning-name">
              이름
            </label>
            <input
              id="seasoning-name"
              className={errors.name ? "input invalid" : "input"}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (errors.name) setErrors({ ...errors, name: undefined });
              }}
              required
              maxLength={30}
              placeholder="예: 우리집 제육 (덜 달게)"
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? "seasoning-name-error" : undefined}
              autoFocus={!initial}
            />
            {errors.name && (
              <p className="rc-err" id="seasoning-name-error" role="alert">
                <Icon name="alert" size={16} />
                {errors.name}
              </p>
            )}
          </div>

          <div className="field">
            <span className="field-label" id="seasoning-basis-label">
              무엇을 기준으로 할까요?
            </span>
            <div className="segmented" role="group" aria-labelledby="seasoning-basis-label">
              {BASES.map(([key, label]) => (
                <button key={key} type="button" aria-pressed={basis === key} onClick={() => chooseBasis(key)}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <span className="field-label">기준</span>
            <div className="r3-basis-row">
              {basis === "main_weight" && (
                <input
                  className="input"
                  aria-label="주재료 이름"
                  placeholder="돼지고기"
                  maxLength={50}
                  value={mainIngredient}
                  onChange={(e) => setMainIngredient(e.target.value)}
                />
              )}
              {basis === "yield" ? (
                basisAmountInput
              ) : (
                <div className="input-suffix">
                  {basisAmountInput}
                  <span className="suffix" aria-hidden="true">
                    {basisUnit}
                  </span>
                </div>
              )}
              {basis === "yield" && (
                <span className="r3-sel">
                  <select
                    className="input"
                    aria-label="완성량 단위"
                    value={basisUnit}
                    onChange={(e) => setBasisUnit(e.target.value as BasisUnit)}
                  >
                    {BASIS_UNITS.yield.map((unit) => (
                      <option key={unit}>{unit}</option>
                    ))}
                  </select>
                  <Icon name="chevron" size={16} />
                </span>
              )}
            </div>
            {errors.basis && (
              <p className="rc-err" id="seasoning-basis-error" role="alert">
                <Icon name="alert" size={16} />
                {errors.basis}
              </p>
            )}
          </div>
        </section>

        <section className="rc-sec" aria-labelledby="seasoning-items-title">
          <div className="rc-sec-head">
            <h2 id="seasoning-items-title">양념 재료</h2>
          </div>
          <div className="rc-rows">
            {rows.map((row, index) => {
              const rowError = errors.row?.key === row.key ? errors.row : null;
              const errorId = `seasoning-row-error-${row.key}`;
              const invalid = (field: RowField) => ({
                className: rowError?.field === field ? "input invalid" : "input",
                "aria-invalid": rowError?.field === field,
                "aria-describedby": rowError?.field === field ? errorId : undefined,
              });
              return (
                <Fragment key={row.key}>
                  <div className="r3-unit-row">
                    <input
                      id={`seasoning-name-${row.key}`}
                      {...invalid("name")}
                      aria-label={`${index + 1}번째 양념 이름`}
                      placeholder="양념"
                      maxLength={30}
                      value={row.name}
                      autoFocus={focusKey === row.key}
                      onChange={(e) => updateRow(row.key, { name: e.target.value })}
                    />
                    <input
                      id={`seasoning-amount-${row.key}`}
                      {...invalid("amount")}
                      aria-label={`${index + 1}번째 양념 양`}
                      placeholder="양"
                      maxLength={8}
                      value={row.amount}
                      onChange={(e) => updateRow(row.key, { amount: e.target.value })}
                      onBlur={() => {
                        if (row.amount.trim() && parseAmountInput(row.amount) === null)
                          setErrors({ ...errors, row: { key: row.key, field: "amount", message: AMOUNT_ERROR } });
                      }}
                    />
                    <span className="r3-sel">
                      <select
                        id={`seasoning-unit-${row.key}`}
                        {...invalid("unit")}
                        aria-label={`${index + 1}번째 양념 단위`}
                        value={row.unit}
                        onChange={(e) => updateRow(row.key, { unit: e.target.value as SeasoningUnit })}
                      >
                        {UNITS.map((unit) => (
                          <option key={unit}>{unit}</option>
                        ))}
                      </select>
                      <Icon name="chevron" size={16} />
                    </span>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`${row.name.trim() || "빈 양념"} 빼기`}
                      onClick={() => {
                        setRows((prev) => prev.filter((r) => r.key !== row.key));
                        if (rowError) setErrors({ ...errors, row: undefined });
                      }}
                    >
                      <Icon name="trash" />
                    </button>
                  </div>
                  {rowError && (
                    <p className="rc-err" id={errorId} role="alert">
                      <Icon name="alert" size={16} />
                      {rowError.message}
                    </p>
                  )}
                </Fragment>
              );
            })}
          </div>
          <button type="button" className="btn secondary rc-add" disabled={rows.length >= MAX_ITEMS} onClick={addRow}>
            <Icon name="plus" />
            재료 추가
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

function NewSeasoning() {
  const [initial] = useState(() => draft);
  useEffect(() => {
    draft = null;
  }, []);
  return <SeasoningEditor initial={initial} editId={null} />;
}

function EditSeasoning({ id }: { id: string }) {
  const { data, error, status, reload } = useResource<Seasoning>(`/api/seasonings/${id}`);
  if (data) return <SeasoningEditor initial={data} editId={data.id} />;
  return (
    <main className="page">
      <BackLink onClick={() => goBack(`/recipes/seasonings/${id}`)} />
      {status === 404 ? (
        <p className="center muted">비율을 찾을 수 없어요.</p>
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

/** #/recipes/seasonings/new · #/recipes/seasonings/:id/edit — 시안 SeasoningForm */
export default function SeasoningForm({ id }: { id?: string }) {
  return id ? <EditSeasoning id={id} /> : <NewSeasoning />;
}
