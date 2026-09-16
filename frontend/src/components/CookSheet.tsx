import { Fragment, useEffect, useId, useRef, useState, type ChangeEvent, type MouseEvent, type ReactNode } from "react";
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
  amountHint,
  cookMeal,
  dateChip,
  deductedText,
  defaultAmount,
  defaultChecked,
  foodLogLine,
  overSpent,
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
import { forgetRecipeCaches, forgetResources } from "../useResource";
import Icon from "./Icon";
import Sheet from "./Sheet";
import StarPicker from "./StarPicker";
import { showUndoToast, undoToastSession } from "./UndoToast";

export interface CookStart { servings: number; date: string; meal: MealKind; slotId: number; slotEaten: boolean }

interface Props {
  recipeId: number;
  user: User;
  /** 식단 칸에서 열 때(결정 16·28) */
  start?: CookStart;
  /** 시트 맨 위 한 줄(추천 레시피를 내 레시피에 저장한 뒤 열 때, 29절 추가 2026-09-16) */
  note?: string;
  onSaved: (result: CookSaveResult) => void;
  onClose: () => void;
}

/** 저장·되돌리기 뒤 옛 재고·요리 표시를 보여주지 않게(Task 10 요리 일기 화면도 가져다 쓴다) */
export function forgetCookCaches() {
  forgetRecipeCaches(); // `/api/rec` 접두사가 `/api/recipes/:id`·cook-draft도 지운다(개정 1 T8④)
  forgetResources("/api/food-logs");
  forgetResources("/api/meal-plans");
  forgetResources("/api/cook-");
  forgetResources("/api/ingredients"); // 식단 AI 초안의 재고
  forgetResources("/api/export"); // 내보내기 시트의 요리 일기 수
}

/** 앱 세션 동안 사 먹으면 얼마를 자동 추정한 레시피 id. 로그아웃(App resetScreens)이 비운다.
 *  ponytail: 시트 안 ref는 열 때마다 초기화돼 서버 거절(502)·요청 중 닫고 다시 열기마다 AI 하루 횟수를 조용히 썼다 — 레시피마다 한 번만 자동, 그 뒤는 `추정해줘요`.
 *  새로고침하면 다시 한 번 부른다(성공하면 레시피에 저장돼 초안에 값이 있어 부르지 않는다) */
export const autoEstimateTried = new Set<number>();

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
    over: result.log.saved !== null && overSpent(result.log.saved),
    // 서버가 되돌리기를 받는 길이(undo_until − created_at, 120초)를 응답을 받은 순간부터 잰다 — 기기 시계가 서버와 달라도 같은 길이
    undoUntil: Date.now() + (Date.parse(result.log.undo_until) - Date.parse(result.log.created_at)),
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
  label = "사 먹으면 얼마 (1인분)",
  placeholder = "예: 9,000",
  help,
  value,
  source,
  estimating,
  onChange,
  onEstimate,
}: {
  /** 직접 쓴 일기의 `재료비 (선택)`도 같은 칸(0~1,000,000원) */
  label?: ReactNode;
  placeholder?: string;
  /** 칸 아래 늘 보이는 도움말(재료비가 몇 인분을 합친 값인지) */
  help?: string;
  value: string;
  source: EatOutSource | null;
  estimating: boolean;
  onChange: (text: string) => void;
  /** 있으면 빈 칸일 때 작은 `추정해줘요` 버튼(체험 계정, 개정 1 P16 · 자동 추정을 한 번 해 본 레시피) */
  onEstimate?: () => void;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const invalid = parseWon(value) === undefined;
  const note = estimating ? "추정하는 중…" : source === "ai" || source === "sample" ? "추정 · 고칠 수 있어요" : "";
  return (
    <div className="field">
      <label className="field-label" htmlFor={`${id}-input`}>
        {label}
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
            placeholder={placeholder}
            size={Math.max(7, value.length)}
            value={value}
            aria-invalid={invalid || undefined}
            aria-describedby={[note && `${id}-note`, help && `${id}-help`, invalid && `${id}-hint`].filter(Boolean).join(" ") || undefined}
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
      {help && (
        <p id={`${id}-help`} className="hint">
          {help}
        </p>
      )}
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

/** 직접 쓴 일기의 재료비 칸(선택, 0~1,000,000원). 옆 칸이 1인분이라 인분을 합친 값이라고 늘 알린다(리뷰 W3) */
export const CostField = ({ value, servings, onChange }: { value: string; servings: number; onChange: (text: string) => void }) => (
  <WonField
    label={
      <>
        재료비 <span className="optional">(선택)</span>
      </>
    }
    placeholder="예: 6,500"
    help={`${servings}인분을 합친 값이에요`}
    value={value}
    source={null}
    estimating={false}
    onChange={onChange}
  />
);

/** 인분 −/+ 1~20(결정 3) — 요리했어요·일기 쓰기 시트 공용 */
export function ServingsStepper({ value, onChange }: { value: number; onChange: (servings: number) => void }) {
  return (
    <div className="ck-row">
      <span className="field-label">인분</span>
      <div className="stepper">
        <button type="button" className="icon-btn" aria-label="인분 줄이기" disabled={value <= 1} onClick={() => onChange(value - 1)}>
          <Icon name="minus" />
        </button>
        <output className="input rc-count" aria-live="polite">
          {value}인분
        </output>
        <button type="button" className="icon-btn" aria-label="인분 늘리기" disabled={value >= MAX_COOK_SERVINGS} onClick={() => onChange(value + 1)}>
          <Icon name="plus" />
        </button>
      </div>
    </div>
  );
}

/** 사진 한 장(저장소가 꺼져 있으면 없음) + 누르면 펼치는 메모 500자 */
export function PhotoMemoRow({
  photos,
  photo,
  onPhoto,
  memo,
  onMemo,
}: {
  photos: boolean;
  photo: Blob | null;
  onPhoto: (file: Blob | null) => void;
  memo: string;
  onMemo: (memo: string) => void;
}) {
  const [memoOpen, setMemoOpen] = useState(false);
  return (
    <div className="ck-row">
      {photos && <PhotoPicker file={photo} currentUrl={null} onPick={onPhoto} />}
      {memoOpen ? (
        <div className="ck-memo">
          <textarea className="input" aria-label="메모" rows={3} maxLength={500} autoFocus value={memo} onChange={(e) => onMemo(e.target.value)} />
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
  );
}

/** `먹은 기록에도 남기기`(결정 16). 이미 먹은 식단 칸이면 꺼진 채 막힌다 */
export function FoodLogSwitch({ on, onChange, line, blocked = false }: { on: boolean; onChange: (on: boolean) => void; line: string; blocked?: boolean }) {
  const id = useId();
  return (
    <div className="ck-row">
      <span>
        <b>먹은 기록에도 남기기</b>
        <br />
        <span className="muted" id={id}>
          {blocked ? "이미 먹은 기록이 있어요" : line}
        </span>
      </span>
      <button
        type="button"
        role="switch"
        className="r3-toggle"
        aria-checked={on && !blocked}
        aria-label="먹은 기록에도 남기기"
        aria-describedby={id}
        disabled={blocked}
        onClick={() => onChange(!on)}
      />
    </div>
  );
}

/** POST /api/cook-logs(요리했어요·일기 쓰기 공통): 사진은 줄여서 함께 보내고, 저장하면 캐시를 지운 뒤 done */
export function saveCook(save: ReturnType<typeof useAsyncAction>, data: Record<string, unknown>, photo: Blob | null, done: (result: CookSaveResult) => void) {
  const session = undoToastSession();
  void save.run(async () => {
    const form = new FormData();
    form.append("data", JSON.stringify(data));
    if (photo) {
      const image = await resizeImage(photo);
      // 못 읽으면 resizeImage가 원본을 돌려주는데, 원본에는 위치 같은 사진 정보가 남아 있을 수 있어 올리지 않는다(uploadFoodPhoto와 같은 가드)
      if (image === photo) throw new Error("이 사진은 올릴 수 없어요. 다른 사진을 골라주세요.");
      form.append("image", image, "photo.jpg");
    }
    const result = await api<CookSaveResult>("/api/cook-logs", { method: "POST", body: form });
    if (undoToastSession() !== session) return; // 그사이 로그아웃 — 다음 계정 화면에 앞 사용자 알림·캐시 지우기를 하지 않는다
    forgetCookCaches();
    done(result);
  });
}

/** 추천 레시피를 저장한 뒤 연 시트 맨 위 한 줄(시안 ⑥) */
export function SavedNote({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <p className="ck-note">
      <Icon name="check" size={16} />
      {text}
    </p>
  );
}

/** 시안 1 · COOKED: 요리했어요 시트. 초안을 받은 뒤에 폼을 그린다 */
export default function CookSheet({ recipeId, user, start, note, onSaved, onClose }: Props) {
  const [draft, setDraft] = useState<CookDraft>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  // 초안은 지금 재고·사 먹으면 얼마라 캐시에 두지 않고 열 때마다 받는다. 닫히면 요청을 끊어 닫힌 시트에 쓰지 않는다
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<CookDraft>(`/api/recipes/${recipeId}/cook-draft`, { signal: controller.signal }).then(setDraft, (e: Error) => {
      if (!controller.signal.aborted) setError(e.message);
    });
    return () => controller.abort();
  }, [recipeId, attempt]);

  if (!draft) {
    return (
      <Sheet title="요리했어요" onClose={onClose}>
        <SavedNote text={note} />
        {error ? (
          <>
            <p className="error" role="alert">
              {error}
            </p>
            <button type="button" className="btn secondary" onClick={() => setAttempt((n) => n + 1)}>
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
  return <CookForm draft={draft} user={user} start={start} note={note} onSaved={onSaved} onClose={onClose} />;
}

function CookForm({ draft, user, start, note, onSaved, onClose }: Omit<Props, "recipeId"> & { draft: CookDraft }) {
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
  const [memo, setMemo] = useState("");
  const slotEaten = start?.slotEaten ?? false;
  const [foodLog, setFoodLog] = useState(!slotEaten);
  const [submitted, setSubmitted] = useState(false); // 쓴 양 안내는 저장을 누른 뒤부터
  const save = useAsyncAction();
  const id = useId();
  const meal = cookMeal(date, today, seoulHour(new Date()), start?.meal);
  // 열려 있는 동안만 true(effect 안에서 켜야 StrictMode 다시 마운트에도 true) — 닫힌 뒤 도착한 추정은 쓰지 않는다
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  async function estimate() {
    setEstimating(true);
    setEstimateError("");
    try {
      const result = await api<EatOutEstimate>(`/api/recipes/${draft.recipe_id}/eat-out-estimate`, { method: "POST" });
      if (!alive.current || priceTouched.current) return; // 닫힌 시트, 기다리는 사이 직접 넣은 값에는 쓰지 않는다
      setPriceText(wonFieldText(result.eat_out_price, ""));
      setSource(result.eat_out_source);
    } finally {
      forgetResources("/api/ai-usage"); // 다른 화면이 남은 AI 횟수를 옛 값으로 먼저 보이지 않게(Shopping.tsx와 같게)
      if (alive.current) setEstimating(false);
    }
  }

  // 자동 추정(개정 1 P16): 값이 없고 AI를 쓸 수 있고 체험 계정이 아니면 앱 세션 동안 레시피마다 한 번(autoEstimateTried), 실패·한도는 조용히 빈 칸
  useEffect(() => {
    if (autoEstimateTried.has(draft.recipe_id) || draft.eat_out_price !== null || user.scan === "off" || user.provider === "demo") return;
    autoEstimateTried.add(draft.recipe_id);
    estimate().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 누를 때만 부르는 `추정해줘요`: 체험 계정은 시트만 열어 체험 AI를 쓰지 않게 늘, 로그인 사용자는 자동 추정을 한 번 해 본 뒤에
  const manualEstimate =
    user.scan !== "off" && draft.eat_out_price === null && (user.provider === "demo" || autoEstimateTried.has(draft.recipe_id))
      ? () => {
          priceTouched.current = false; // 칸을 만졌다 비운 뒤 눌러도 받은 값으로 채운다
          estimate().catch((e: unknown) => {
            if (alive.current)
              setEstimateError(e instanceof ApiError && typeof e.body?.error === "string" ? e.body.error : "추정하지 못했어요. 직접 입력해주세요");
          });
        }
      : undefined;

  function changeServings(next: number) {
    setServings(next);
    setAmounts((prev) => prev.map((text, i) => (touched.current.has(i) ? text : String(defaultAmount(rows[i], next, draft.servings)))));
  }

  const amountInvalid = (i: number) => checked[i] && parseAmountInput(amounts[i]) === null;
  const invalid = parseWon(priceText) === undefined || rows.some((_, i) => amountInvalid(i));
  const missing = rows.filter((row) => row.ingredient_id === null).map((row) => row.name);

  function submit(e: MouseEvent<HTMLButtonElement>) {
    setSubmitted(true);
    if (invalid) {
      // 쓴 양 줄이 사 먹으면 얼마보다 위라 문서 순서의 첫 틀린 칸이 곧 화면 위 첫 칸(쓴 양은 안내가 뜨기 전이라 data-bad로 찾는다)
      e.currentTarget.closest("dialog")?.querySelector<HTMLElement>('[data-bad], [aria-invalid="true"]')?.focus();
      return;
    }
    const data = {
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
    };
    saveCook(save, data, photo, (result) => {
      onSaved(result);
      onClose();
    });
  }

  return (
    <Sheet title={`${draft.title} 요리했어요`} description="쓴 재료는 재고에서 빼요" locked={save.busy} onClose={onClose}>
      <SavedNote text={note} />
      <ServingsStepper value={servings} onChange={changeServings} />

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
              const hint = submitted && bad ? amountHint(amounts[i]) : null;
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
                        data-bad={bad || undefined}
                        aria-invalid={hint ? true : undefined}
                        aria-describedby={hint ? `${id}-bad-${i}` : undefined}
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
                  {hint && (
                    <p id={`${id}-bad-${i}`} className="hint ck-invalid">
                      {hint}
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
          onEstimate={manualEstimate}
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

      <PhotoMemoRow photos={user.photos} photo={photo} onPhoto={setPhoto} memo={memo} onMemo={setMemo} />

      <FoodLogSwitch on={foodLog} onChange={setFoodLog} line={foodLogLine(date, meal)} blocked={slotEaten} />

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
