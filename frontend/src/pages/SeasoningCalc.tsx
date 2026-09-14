import { useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { SEASONING_PRESETS } from "../data/seasoningPresets";
import { formatAmountNumber } from "../format";
import {
  amountInputText,
  basisLabel,
  parseAmountInput,
  ratioLabel,
  scaleFactor,
  scaleItem,
  type BasisUnit,
  type Seasoning,
} from "../seasoning";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetResources, useResource } from "../useResource";
import { openSeasoningDraft } from "./SeasoningForm";

// 기준 양 −/+ 한 칸과 최대(최소는 한 칸), 빠른 칩 (계획 3c 태스크 3)
const STEP: Record<BasisUnit, number> = { g: 100, 인분: 1, 컵: 0.25, ml: 50 };
const MAX: Record<BasisUnit, number> = { g: 10000, 인분: 20, 컵: 20, ml: 4000 };
const QUICK: Record<BasisUnit, number[]> = { g: [300, 600, 900, 1000, 1200], 인분: [1, 2, 3, 4], 컵: [0.5, 1, 2], ml: [100, 200, 400] };
const quickLabel = (value: number, unit: BasisUnit) =>
  unit === "g" && value >= 1000 ? `${value / 1000}kg` : `${formatAmountNumber(value)}${unit}`;

function BackLink() {
  return (
    <a
      className="back-link"
      href="#/recipes"
      onClick={(e) => {
        e.preventDefault();
        goBack("/recipes");
      }}
    >
      <Icon name="back" size={18} />
      레시피
    </a>
  );
}

function Calculator({ seasoning: s }: { seasoning: Seasoning }) {
  const unit = s.basis_unit;
  // ponytail: 입력값은 저장하지 않는다(화면을 나가면 기준량으로 돌아감). 자주 바꾸면 localStorage.
  const [text, setText] = useState(() => amountInputText(s.basis_amount));
  const { busy, error, run } = useAsyncAction();
  const amount = parseAmountInput(text);
  const factor = amount === null ? null : scaleFactor(s, amount, unit);
  const question =
    s.basis === "main_weight" ? `${s.main_ingredient || "주재료"} 얼마나 써요?` : s.basis === "servings" ? "몇 인분 만들어요?" : "얼마나 만들어요?";

  const set = (value: number) => setText(amountInputText(Number(value.toFixed(2))));

  const remove = () => {
    if (!confirm("이 비율을 삭제할까요?")) return;
    run(async () => {
      await api(`/api/seasonings/${s.id}`, { method: "DELETE" });
      forgetResources("/api/seasonings");
      goBack("/recipes");
    });
  };

  return (
    <main className="page">
      <BackLink />
      <header className="rc-head r3-calc-head">
        <h1>{s.name}</h1>
        <p className="summary">
          {s.source === "default" ? "기본 비율" : "내 비율"} · {basisLabel(s)}
        </p>
      </header>

      <section className="rc-sec" aria-labelledby="seasoning-basis">
        <div className="rc-sec-head">
          <h2 id="seasoning-basis">{question}</h2>
          {/* 결과 목록 전체 대신 배율만 읽어 준다(입력할 때마다 목록을 다 읽으면 시끄럽다) */}
          <span aria-live="polite">{factor !== null && <span className="r3-ratio">{ratioLabel(factor)}</span>}</span>
        </div>
        <div className="r3-basis">
          <div className="stepper">
            <button
              type="button"
              className="icon-btn"
              aria-label="양 줄이기"
              disabled={amount === null || amount <= STEP[unit]}
              onClick={() => amount !== null && set(Math.max(STEP[unit], amount - STEP[unit]))}
            >
              <Icon name="minus" />
            </button>
            <label className="input r3-amount">
              <input
                inputMode="decimal"
                aria-label={`${question} (${unit})`}
                size={Math.max(2, text.length)}
                maxLength={8}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <span aria-hidden="true">{unit}</span>
            </label>
            <button
              type="button"
              className="icon-btn"
              aria-label="양 늘리기"
              disabled={amount !== null && amount >= MAX[unit]}
              onClick={() => set(amount === null ? STEP[unit] : Math.min(MAX[unit], amount + STEP[unit]))}
            >
              <Icon name="plus" />
            </button>
          </div>
          <div className="r3-quick" role="group" aria-label="자주 쓰는 양">
            {QUICK[unit].map((value) => (
              <button key={value} type="button" aria-pressed={amount === value} onClick={() => set(value)}>
                {quickLabel(value, unit)}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rc-sec" aria-labelledby="seasoning-items">
        <div className="rc-sec-head">
          <h2 id="seasoning-items">양념</h2>
          <span className="hint">계량스푼 기준</span>
        </div>
        {factor === null ? (
          <p className="r3-sec-msg">기준 양을 입력해주세요.</p>
        ) : (
          <ul className="r3-sitems">
            {s.items.map((item, index) => {
              const { text: shown, sub } = scaleItem(item, factor);
              return (
                <li key={index}>
                  <span className="r3-sname">{item.name}</span>
                  <span className="r3-samt">
                    <b>{shown}</b>
                    {sub && <span>{sub}</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="r3-note">
        <Icon name="spoon" size={16} />
        <span>1큰술은 15ml예요. 밥숟가락은 집마다 달라서 대략으로 보여줘요. 입맛에 맞게 조절해주세요.</span>
      </div>
      {s.source === "default" && s.source_note && <p className="hint r3-cite">출처: {s.source_note}</p>}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="rc-actions">
        {s.source === "default" ? (
          <button className="btn outline" onClick={() => openSeasoningDraft(s)}>
            <Icon name="pencil" />이 비율 고쳐서 내 비율로
          </button>
        ) : (
          <>
            <button className="btn outline" onClick={() => navigate(`/recipes/seasonings/${s.id}/edit`)}>
              <Icon name="pencil" />
              수정
            </button>
            <button className="btn danger-text" disabled={busy} onClick={remove}>
              이 비율 삭제
            </button>
          </>
        )}
      </div>
    </main>
  );
}

function MineCalc({ id }: { id: string }) {
  const { data, error, status, reload } = useResource<Seasoning>(`/api/seasonings/${id}`);
  if (data) return <Calculator seasoning={data} />;
  return (
    <main className="page">
      <BackLink />
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

/** #/recipes/seasonings/preset/:id (기본 양념) · #/recipes/seasonings/:id (내 비율) — 시안 SeasoningCalc */
export default function SeasoningCalc({ kind, id }: { kind: "preset" | "mine"; id: string }) {
  if (kind === "mine") return <MineCalc id={id} />;
  const preset = SEASONING_PRESETS.find((p) => p.id === Number(id));
  if (preset) return <Calculator seasoning={preset} />;
  return (
    <main className="page">
      <BackLink />
      <p className="center muted">비율을 찾을 수 없어요.</p>
    </main>
  );
}
