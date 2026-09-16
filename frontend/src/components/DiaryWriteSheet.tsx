import { useId, useRef, useState, type MouseEvent } from "react";
import { localToday, type CookSaveResult, type RecipeChoice, type User } from "../api";
import { cookMeal, cookedChoiceText, foodLogLine, parseWon, seoulHour } from "../cooklog/cook.ts";
import { useAsyncAction } from "../useAsyncAction";
import CookSheet, { CostField, DateChips, DishNameField, FoodLogSwitch, PhotoMemoRow, ServingsStepper, WonField, saveCook } from "./CookSheet";
import { ListState, SearchBox, useSearch } from "./MealFillSheet";
import Sheet from "./Sheet";
import StarPicker from "./StarPicker";

type Step = { kind: "pick" } | { kind: "recipe"; recipeId: number } | { kind: "manual"; title: string };

interface Props {
  user: User;
  onSaved: (result: CookSaveResult) => void;
  onClose: () => void;
}

/** 요리 일기의 `일기 쓰기`(29절 추가 2026-09-16, 시안 diary-write ②③): 내 레시피를 고르면 요리했어요 시트, 이름만 적으면 레시피 없는 일기.
 *  다음 시트는 고르기 시트를 닫으며 같은 순간에 연다 — Sheet가 여는 버튼(일기 쓰기)을 물려받아 끝에 포커스를 돌려준다 */
export default function DiaryWriteSheet({ user, onSaved, onClose }: Props) {
  const [step, setStep] = useState<Step>({ kind: "pick" });
  if (step.kind === "recipe") return <CookSheet recipeId={step.recipeId} user={user} onSaved={onSaved} onClose={onClose} />;
  if (step.kind === "manual") return <ManualSheet title={step.title} user={user} onSaved={onSaved} onClose={onClose} />;
  return <PickSheet onNext={setStep} onClose={onClose} />;
}

/** 시안 ② WHAT: 내 레시피(식단 칸 채우기와 같은 목록 API) 하나를 고르거나 요리 이름을 적는다 — 한쪽을 하면 다른 쪽은 비운다 */
function PickSheet({ onNext, onClose }: { onNext: (step: Step) => void; onClose: () => void }) {
  const [input, setInput] = useState("");
  const [recipeId, setRecipeId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [tried, setTried] = useState(false);
  const recipes = useSearch<RecipeChoice>("/api/recipes/choices", input);
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();
  // 검색으로 목록에서 빠진 것은 고른 것으로 치지 않는다(MealFillSheet와 같게)
  const picked = recipes.result?.items.find((r) => r.id === recipeId);
  const title = name.trim();
  const missing = tried && !picked && !title;

  const next = () => {
    setTried(true);
    if (picked) onNext({ kind: "recipe", recipeId: picked.id });
    else if (title) onNext({ kind: "manual", title });
  };
  // dialog.close()로 닫아야 여는 버튼으로 포커스가 돌아간다(close 이벤트가 onClose를 부른다)
  const close = () => rootRef.current?.querySelector("dialog")?.close();

  return (
    <div ref={rootRef}>
      {/* focusTitle: 첫 칸이 검색 칸이라 열자마자 키보드가 목록을 가리지 않게 */}
      <Sheet title="무엇을 요리했나요?" description="내 레시피에서 고르면 쓴 재료를 재고에서 빼요" focusTitle onClose={onClose}>
        <SearchBox label="내 레시피에서 찾기" value={input} onChange={setInput} />
        {recipes.result?.items.length ? (
          <>
            {recipes.error && <ListState error={recipes.error} loading={false} empty="" onRetry={recipes.retry} compact />}
            <div className="ml-picks" role="radiogroup" aria-label="내 레시피">
              {recipes.result.items.map((recipe) => (
                <label key={recipe.id} className="mo-radio">
                  <input
                    className="sr-only"
                    type="radio"
                    name={`${id}-recipe`}
                    checked={recipe.id === recipeId}
                    aria-label={recipe.title}
                    aria-describedby={`${id}-r${recipe.id}`}
                    onChange={() => {
                      setRecipeId(recipe.id);
                      setName("");
                    }}
                  />
                  <span className="mo-dot" aria-hidden="true" />
                  <span className="row-main">
                    <span className="row-title">{recipe.title}</span>
                    <span className="row-sub" id={`${id}-r${recipe.id}`}>
                      {cookedChoiceText(recipe.cooked)}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </>
        ) : (
          <ListState
            error={recipes.error}
            loading={!recipes.result}
            empty={recipes.result?.q ? "찾는 레시피가 없어요" : "아직 내 레시피가 없어요. 아래에 요리 이름을 적어주세요"}
            onRetry={recipes.retry}
          />
        )}

        <p className="ck-or">레시피가 없으면</p>
        <DishNameField
          value={name}
          onChange={(text) => {
            setName(text);
            if (text.trim()) setRecipeId(null);
          }}
          onEnter={next}
        />

        {missing && (
          <p id={`${id}-missing`} className="hint ck-invalid" role="alert">
            레시피를 고르거나 요리 이름을 적어주세요
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn outline" onClick={close}>
            취소
          </button>
          {/* 고른 게 없어도 disabled 대신 aria-disabled — 누르면 무엇이 모자란지 알린다 */}
          <button
            type="button"
            className="btn primary"
            aria-disabled={(!picked && !title) || undefined}
            aria-describedby={missing ? `${id}-missing` : undefined}
            onClick={next}
          >
            다음
          </button>
        </div>
      </Sheet>
    </div>
  );
}

/** 시안 ③ WRITE: 요리했어요 시트에서 쓴 재료 줄만 빠진 모양. 재고는 그대로, 사 먹으면 얼마는 AI 추정 없이, 재료비(선택)를 더 받는다 */
function ManualSheet({ title, user, onSaved, onClose }: Props & { title: string }) {
  const today = localToday();
  const [servings, setServings] = useState(2); // 레시피 인분 기본값과 같게
  const [date, setDate] = useState(today);
  const [priceText, setPriceText] = useState("");
  const [costText, setCostText] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [memo, setMemo] = useState("");
  const [foodLog, setFoodLog] = useState(true);
  const save = useAsyncAction();
  const meal = cookMeal(date, today, seoulHour(new Date()));
  const invalid = parseWon(priceText) === undefined || parseWon(costText) === undefined;

  function submit(e: MouseEvent<HTMLButtonElement>) {
    if (invalid) {
      e.currentTarget.closest("dialog")?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      return;
    }
    const data = {
      manual: true,
      title,
      servings,
      cooked_on: date,
      rating,
      memo: memo.trim() || null,
      eat_out_price: parseWon(priceText) ?? null,
      ingredient_cost: parseWon(costText) ?? null,
      food_log: foodLog,
      meal,
    };
    saveCook(save, data, photo, (result) => {
      onSaved(result);
      onClose();
    });
  }

  return (
    <Sheet title={`${title} 요리했어요`} description="레시피가 없어 재고는 그대로예요" locked={save.busy} onClose={onClose}>
      <ServingsStepper value={servings} onChange={setServings} />
      <DateChips value={date} today={today} onChange={setDate} />
      <div className="ck-wons">
        <WonField value={priceText} source={null} estimating={false} onChange={setPriceText} />
        <CostField value={costText} servings={servings} onChange={setCostText} />
      </div>
      <div className="ck-row">
        <b>별점</b>
        <StarPicker value={rating} label="별점" onChange={setRating} />
      </div>
      <PhotoMemoRow photos={user.photos} photo={photo} onPhoto={setPhoto} memo={memo} onMemo={setMemo} />
      <FoodLogSwitch on={foodLog} onChange={setFoodLog} line={foodLogLine(date, meal)} />

      {save.error && (
        <p className="error" role="alert">
          {save.error}
        </p>
      )}
      <button type="button" className="btn primary" disabled={save.busy} aria-disabled={invalid || undefined} onClick={submit}>
        {save.busy ? "저장하는 중…" : "일기 저장"}
      </button>
    </Sheet>
  );
}
