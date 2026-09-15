import { Fragment, useEffect, useId, useRef, useState, type ChangeEvent, type MouseEvent } from "react";
import {
  ApiError,
  api,
  localToday,
  type CookDraft,
  type CookSaveResult,
  type CookUndoResult,
  type EatOutEstimate,
  type EatOutSource,
  type MealKind,
  type User,
} from "../api";
import {
  MAX_COOK_SERVINGS,
  cookMeal,
  dateChip,
  deductedText,
  defaultAmount,
  defaultChecked,
  foodLogLine,
  parseAmountInput,
  parseWon,
  savedText,
  seoulHour,
  stockText,
  undoneText,
  usesUp,
  wonFieldText,
} from "../cooklog/cook.ts";
import { addDays } from "../format.ts";
import { resizeImage } from "../image.ts";
import { useAsyncAction } from "../useAsyncAction";
import { forgetRecipeCaches, forgetResources, useResource } from "../useResource";
import Icon from "./Icon";
import Sheet from "./Sheet";
import StarPicker from "./StarPicker";
import { showUndoToast } from "./UndoToast";

export interface CookStart { servings: number; date: string; meal: MealKind; slotId: number; slotEaten: boolean }

interface Props {
  recipeId: number;
  user: User;
  /** 식단 칸에서 열 때(결정 16·28) */
  start?: CookStart;
  onSaved: (result: CookSaveResult) => void;
  onClose: () => void;
}

/** 자동 추정을 이미 부른 레시피 id — 실패·한도여도 시트를 열 때마다 AI를 다시 부르지 않게(개정 1 P16) */
const estimatedOnce = new Set<number>();

/** 저장·되돌리기 뒤 옛 재고·요리 표시를 보여주지 않게(Task 10 요리 일기 화면도 가져다 쓴다) */
export function forgetCookCaches() {
  forgetRecipeCaches(); // `/api/rec` 접두사가 `/api/recipes/:id`·cook-draft도 지운다(개정 1 T8④)
  forgetResources("/api/food-logs");
  forgetResources("/api/meal-plans");
  forgetResources("/api/cook-");
}

/** 요리 일기 저장·되돌리기 요청과 알림(RecipeDetail·MealSlotSheet 공통) */
export async function undoCook(logId: number): Promise<string> {
  const result = await api<CookUndoResult>(`/api/cook-logs/${logId}/undo`, { method: "POST" });
  forgetCookCaches();
  return undoneText(result);
}

/** onUndone: 되돌린 뒤 화면을 새로 받을 곳(레시피 상세 reload, 식단 onChanged) */
export function toastSaved(result: CookSaveResult, onUndone?: () => void): void {
  showUndoToast({
    message: deductedText(result.deducted_names),
    strong: result.log.saved === null ? undefined : savedText(result.log.saved),
    onUndo: async () => {
      const text = await undoCook(result.log.id);
      onUndone?.();
      return text;
    },
  });
}

/** 고치기 시트(Task 10)도 쓰는 조각 */
export function DateChips({ value, today, onChange }: { value: string; today: string; onChange: (date: string) => void }) {
  const yesterday = addDays(today, -1);
  const chip = dateChip(value, today, yesterday);
  const [picking, setPicking] = useState(false);
  const dateRef = useRef<HTMLInputElement>(null);
  const pick = (date: string) => {
    setPicking(false);
    onChange(date);
  };
  return (
    <div className="field">
      <span className="field-label" aria-hidden="true">
        언제
      </span>
      <div className="chips ck-dates" role="group" aria-label="언제">
        <button type="button" className="chip" aria-pressed={chip === "today"} onClick={() => pick(today)}>
          오늘
        </button>
        <button type="button" className="chip" aria-pressed={chip === "yesterday"} onClick={() => pick(yesterday)}>
          어제
        </button>
        <button
          type="button"
          className="chip"
          aria-pressed={chip === "pick"}
          onClick={() => {
            setPicking(true);
            requestAnimationFrame(() => {
              const input = dateRef.current;
              input?.focus();
              try {
                input?.showPicker(); // 폰은 포커스만으로 달력이 안 열린다
              } catch {
                // showPicker가 없는 브라우저는 보이는 날짜 칸을 직접 누른다
              }
            });
          }}
        >
          날짜 고르기
        </button>
        {(picking || chip === "pick") && (
          <input
            ref={dateRef}
            className="input"
            type="date"
            aria-label="요리한 날짜"
            max={today}
            value={value}
            onChange={(e) => {
              if (e.target.value && e.target.value <= today) onChange(e.target.value);
            }}
          />
        )}
      </div>
    </div>
  );
}

export function WonField({
  value,
  source,
  estimating,
  onChange,
  onEstimate,
}: {
  value: string;
  source: EatOutSource | null;
  estimating: boolean;
  onChange: (text: string) => void;
  /** 있으면 빈 칸일 때 작은 `추정해줘요` 버튼(체험 계정, 개정 1 P16) */
  onEstimate?: () => void;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const invalid = parseWon(value) === undefined;
  const note = estimating ? "추정하는 중…" : source === "ai" || source === "sample" ? "추정 · 고칠 수 있어요" : "";
  return (
    <div className="field">
      <label className="field-label" htmlFor={`${id}-input`}>
        사 먹으면 얼마 (1인분)
      </label>
      <div className="ck-won-row">
        {/* 칸 어디를 눌러도 입력으로(글자 폭만큼인 입력 칸 옆 빈자리) */}
        <span className="input-suffix ck-won" onClick={() => input.current?.focus()}>
          <input
            ref={input}
            id={`${id}-input`}
            className="input"
            inputMode="numeric"
            autoComplete="off"
            placeholder="예: 9,000"
            size={Math.max(7, value.length)}
            value={value}
            aria-invalid={invalid || undefined}
            aria-describedby={[note && `${id}-note`, invalid && `${id}-hint`].filter(Boolean).join(" ") || undefined}
            onChange={(e) => onChange(wonFieldText(parseWon(e.target.value), e.target.value))}
          />
          <span className="suffix" aria-hidden="true">
            원
          </span>
          <em id={`${id}-note`} className="ck-est" aria-live="polite">
            {note}
          </em>
        </span>
        {onEstimate && value === "" && !estimating && (
          <button type="button" className="nt-link" aria-label="사 먹으면 얼마 추정해줘요" onClick={onEstimate}>
            추정해줘요
          </button>
        )}
      </div>
      {invalid && (
        <p id={`${id}-hint`} className="hint ck-invalid">
          0~1,000,000원 사이로 입력해주세요
        </p>
      )}
    </div>
  );
}

export function PhotoPicker({
  file,
  currentUrl,
  onPick,
  onRemoveCurrent,
}: {
  file: Blob | null;
  currentUrl: string | null;
  onPick: (file: Blob | null) => void;
  onRemoveCurrent?: () => void;
}) {
  const cameraRef = useRef<HTMLInputElement>(null);
  const albumRef = useRef<HTMLInputElement>(null);
  const removeRef = useRef<HTMLButtonElement>(null);
  const takeRef = useRef<HTMLButtonElement>(null);
  const moveFocus = useRef(false);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) {
      setFileUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setFileUrl(url);
    return () => URL.revokeObjectURL(url); // 바꾸거나 닫힐 때
  }, [file]);
  const shown = file ? fileUrl : currentUrl;
  // 누른 버튼이 사라지므로(찍기·앨범 ↔ 사진 빼기) 포커스를 새 버튼으로 옮긴다
  useEffect(() => {
    if (!moveFocus.current) return;
    moveFocus.current = false;
    (shown ? removeRef : takeRef).current?.focus();
  }, [shown]);

  const picked = (e: ChangeEvent<HTMLInputElement>) => {
    const next = e.target.files?.[0];
    e.target.value = ""; // 같은 사진을 다시 골라도 change가 일어나게
    if (!next) return;
    moveFocus.current = true;
    onPick(next); // 한 장 — 새로 고르면 앞 사진을 바꾼다
  };

  return (
    <>
      {/* 안드로이드 14+는 capture 없이 열면 시스템 사진 선택기에 카메라가 없어 카메라용·앨범용 입력을 따로 둔다(ScanSheet·ShoppingMemo와 같게) */}
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={picked} />
      <input ref={albumRef} type="file" accept="image/*" hidden onChange={picked} />
      {shown ? (
        <>
          <span className="sh-photo ck-photo">
            <img src={shown} alt="요리 사진" />
          </span>
          <button
            ref={removeRef}
            type="button"
            className="icon-btn"
            aria-label="사진 빼기"
            onClick={() => {
              moveFocus.current = true;
              if (file) onPick(null);
              else onRemoveCurrent?.();
            }}
          >
            <Icon name="close" />
          </button>
        </>
      ) : (
        <>
          <button ref={takeRef} type="button" className="btn secondary" onClick={() => cameraRef.current?.click()}>
            <Icon name="camera" size={18} />
            찍기
          </button>
          <button type="button" className="btn secondary" onClick={() => albumRef.current?.click()}>
            <Icon name="file" size={18} />
            앨범
          </button>
        </>
      )}
    </>
  );
}

/** 시안 1 · COOKED: 요리했어요 시트. 초안을 받은 뒤에 폼을 그린다 */
export default function CookSheet({ recipeId, user, start, onSaved, onClose }: Props) {
  const url = `/api/recipes/${recipeId}/cook-draft`;
  const draft = useResource<CookDraft>(url);
  // ponytail: 초안은 지금 재고·사 먹으면 얼마라 닫으면 캐시를 버린다 — 다시 열 때 옛 값으로 폼을 채우지 않게
  useEffect(() => () => forgetResources(url), [url]);

  if (!draft.data) {
    return (
      <Sheet title="요리했어요" onClose={onClose}>
        {draft.error ? (
          <>
            <p className="error" role="alert">
              {draft.error}
            </p>
            <button type="button" className="btn secondary" onClick={draft.reload}>
              <Icon name="refresh" size={16} />
              다시 불러오기
            </button>
          </>
        ) : (
          <p className="muted" role="status">
            불러오는 중…
          </p>
        )}
      </Sheet>
    );
  }
  return <CookForm draft={draft.data} user={user} start={start} onSaved={onSaved} onClose={onClose} />;
}

function CookForm({ draft, user, start, onSaved, onClose }: Omit<Props, "recipeId"> & { draft: CookDraft }) {
  const today = localToday();
  const { rows } = draft;
  // 식단 칸에서 열면 칸 인분으로 시작하고 줄마다 기본 양도 그 인분으로(결정 3). 서버가 레시피·칸 인분을 1~20으로 막는다
  const [servings, setServings] = useState(start?.servings ?? draft.servings);
  const [amounts, setAmounts] = useState(() => rows.map((row) => String(defaultAmount(row, servings, draft.servings))));
  const [checked, setChecked] = useState(() => rows.map(defaultChecked));
  const touched = useRef(new Set<number>()); // 쓴 양을 직접 고친 줄은 인분을 바꿔도 그대로
  const [date, setDate] = useState(start?.date ?? today);
  const [priceText, setPriceText] = useState(() => wonFieldText(draft.eat_out_price, ""));
  const [source, setSource] = useState<EatOutSource | null>(draft.eat_out_source);
  const priceTouched = useRef(false);
  const [estimating, setEstimating] = useState(false);
  const [estimateError, setEstimateError] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [memoOpen, setMemoOpen] = useState(false);
  const [memo, setMemo] = useState("");
  const slotEaten = start?.slotEaten ?? false;
  const [foodLog, setFoodLog] = useState(!slotEaten);
  const save = useAsyncAction();
  const id = useId();
  const meal = cookMeal(date, today, seoulHour(new Date()), start?.meal);

  async function estimate() {
    setEstimating(true);
    setEstimateError("");
    try {
      const result = await api<EatOutEstimate>(`/api/recipes/${draft.recipe_id}/eat-out-estimate`, { method: "POST" });
      if (priceTouched.current) return; // 기다리는 사이 직접 넣은 값을 덮지 않는다
      setPriceText(wonFieldText(result.eat_out_price, ""));
      setSource(result.eat_out_source);
    } finally {
      setEstimating(false);
    }
  }

  // 자동 추정(개정 1 P16): 값이 없고 AI를 쓸 수 있고 체험 계정이 아니면 레시피마다 한 번. 실패·한도는 조용히 빈 칸
  useEffect(() => {
    if (draft.eat_out_price !== null || user.scan === "off" || user.provider === "demo" || estimatedOnce.has(draft.recipe_id)) return;
    estimatedOnce.add(draft.recipe_id);
    estimate().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 체험 계정은 시트만 열어 체험 AI를 쓰지 않게 누를 때만 부른다
  const demoEstimate =
    user.provider === "demo" && user.scan !== "off" && draft.eat_out_price === null
      ? () =>
          void estimate().catch((e: unknown) =>
            setEstimateError(e instanceof ApiError && typeof e.body?.error === "string" ? e.body.error : "추정하지 못했어요. 직접 입력해주세요"),
          )
      : undefined;

  function changeServings(next: number) {
    setServings(next);
    setAmounts((prev) => prev.map((text, i) => (touched.current.has(i) ? text : String(defaultAmount(rows[i], next, draft.servings)))));
  }

  const amountInvalid = (i: number) => checked[i] && parseAmountInput(amounts[i]) === null;
  const invalid = parseWon(priceText) === undefined || rows.some((_, i) => amountInvalid(i));
  const missing = rows.filter((row) => row.ingredient_id === null).map((row) => row.name);

  function submit(e: MouseEvent<HTMLButtonElement>) {
    if (invalid) {
      // 쓴 양 줄이 사 먹으면 얼마보다 위라 문서 순서의 첫 틀린 칸이 곧 화면 위 첫 칸
      e.currentTarget.closest("dialog")?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      return;
    }
    void save.run(async () => {
      const form = new FormData();
      form.append(
        "data",
        JSON.stringify({
          recipe_id: draft.recipe_id,
          servings,
          cooked_on: date,
          rating,
          memo: memo.trim() || null,
          eat_out_price: parseWon(priceText) ?? null,
          usages: rows.flatMap((row, i) =>
            checked[i] && row.ingredient_id !== null ? [{ ingredient_id: row.ingredient_id, amount: parseAmountInput(amounts[i]) }] : [],
          ),
          food_log: foodLog && !slotEaten,
          meal,
          meal_slot_id: start?.slotId,
        }),
      );
      if (photo) {
        const image = await resizeImage(photo);
        // 못 읽으면 resizeImage가 원본을 돌려주는데, 원본에는 위치 같은 사진 정보가 남아 있을 수 있어 올리지 않는다(uploadFoodPhoto와 같은 가드)
        if (image === photo) throw new Error("이 사진은 올릴 수 없어요. 다른 사진을 골라주세요.");
        form.append("image", image, "photo.jpg");
      }
      const result = await api<CookSaveResult>("/api/cook-logs", { method: "POST", body: form });
      forgetCookCaches();
      onSaved(result);
      onClose();
    });
  }

  return (
    <Sheet title={`${draft.title} 요리했어요`} description="쓴 재료는 재고에서 빼요" onClose={onClose}>
      <div className="ck-row">
        <span className="field-label">인분</span>
        <div className="stepper">
          <button type="button" className="icon-btn" aria-label="인분 줄이기" disabled={servings <= 1} onClick={() => changeServings(servings - 1)}>
            <Icon name="minus" />
          </button>
          <output className="input rc-count" aria-live="polite">
            {servings}인분
          </output>
          <button
            type="button"
            className="icon-btn"
            aria-label="인분 늘리기"
            disabled={servings >= MAX_COOK_SERVINGS}
            onClick={() => changeServings(servings + 1)}
          >
            <Icon name="plus" />
          </button>
        </div>
      </div>

      {rows.length > 0 && (
        <div className="field" role="group" aria-labelledby={`${id}-uses`}>
          <span className="field-label" id={`${id}-uses`}>
            쓴 재료
          </span>
          <div>
            {rows.map((row, i) => {
              if (row.ingredient_id === null) return null;
              const name = row.stock_name ?? row.name;
              const amount = parseAmountInput(amounts[i]);
              const bad = amountInvalid(i);
              return (
                <Fragment key={i}>
                  <div className="ck-use">
                    {/* 이름까지 누르면 체크(22px 상자만으로는 터치 영역이 작다) */}
                    <label className="ck-pick">
                      <input
                        type="checkbox"
                        className="ck-box"
                        aria-label={`${name} 재고에서 빼기`}
                        checked={checked[i]}
                        onChange={() => setChecked((prev) => prev.map((on, j) => (j === i ? !on : on)))}
                      />
                      <span>
                        {name}
                        {checked[i] && amount !== null && usesUp(amount, row.stock_quantity ?? 0) && <span className="badge old">마저 써요</span>}
                        <small>{row.seasoning ? "양념 · 기본으로 안 빼요" : stockText(row)}</small>
                      </span>
                    </label>
                    <span className="input-suffix ck-qty">
                      <input
                        className="input"
                        inputMode="decimal"
                        autoComplete="off"
                        aria-label={`${name} 쓴 양`}
                        aria-invalid={bad || undefined}
                        aria-describedby={bad ? `${id}-bad-${i}` : undefined}
                        disabled={!checked[i]}
                        value={amounts[i]}
                        onChange={(e) => {
                          const text = e.target.value;
                          touched.current.add(i);
                          setAmounts((prev) => prev.map((old, j) => (j === i ? text : old)));
                        }}
                      />
                      <span className="suffix" aria-hidden="true">
                        {row.stock_unit}
                      </span>
                    </span>
                  </div>
                  {bad && (
                    <p id={`${id}-bad-${i}`} className="hint ck-invalid">
                      쓴 양은 0보다 커야 해요
                    </p>
                  )}
                </Fragment>
              );
            })}
          </div>
          {missing.length > 0 && <p className="muted ck-missing">재고에 없는 재료: {missing.join(" · ")}</p>}
        </div>
      )}

      <DateChips value={date} today={today} onChange={setDate} />

      <div className="field">
        <WonField
          value={priceText}
          source={source}
          estimating={estimating}
          onEstimate={demoEstimate}
          onChange={(text) => {
            priceTouched.current = true;
            setSource(null);
            setEstimateError("");
            setPriceText(text);
          }}
        />
        {estimateError && (
          <p className="hint" role="alert">
            {estimateError}
          </p>
        )}
      </div>

      <div className="ck-row">
        <b>별점</b>
        <StarPicker value={rating} label="별점" onChange={setRating} />
      </div>

      <div className="ck-row">
        {user.photos && <PhotoPicker file={photo} currentUrl={null} onPick={setPhoto} />}
        {memoOpen ? (
          <div className="ck-memo">
            <textarea className="input" aria-label="메모" rows={3} maxLength={500} autoFocus value={memo} onChange={(e) => setMemo(e.target.value)} />
            <span className="muted" aria-hidden="true">
              {memo.length} / 500
            </span>
          </div>
        ) : (
          <button type="button" className="btn secondary ck-memo-btn" onClick={() => setMemoOpen(true)}>
            메모 (선택)
          </button>
        )}
      </div>

      <div className="ck-row">
        <span>
          <b>먹은 기록에도 남기기</b>
          <br />
          <span className="muted" id={`${id}-food`}>
            {slotEaten ? "이미 먹은 기록이 있어요" : foodLogLine(date, meal)}
          </span>
        </span>
        <button
          type="button"
          role="switch"
          className="r3-toggle"
          aria-checked={foodLog && !slotEaten}
          aria-label="먹은 기록에도 남기기"
          aria-describedby={`${id}-food`}
          disabled={slotEaten}
          onClick={() => setFoodLog((on) => !on)}
        />
      </div>

      {save.error && (
        <p className="error" role="alert">
          {save.error}
        </p>
      )}
      <button type="button" className="btn primary" disabled={save.busy} aria-disabled={invalid || undefined} onClick={submit}>
        {save.busy ? "저장하는 중…" : "저장하고 재고에서 빼기"}
      </button>
    </Sheet>
  );
}
