import { useEffect, useId, useRef, useState } from "react";
import { api, localToday, type AiUsage, type Ingredient, type MealDraft, type MealKind, type MealPlan, type User } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import { namesLabel, remainingText, withJosa } from "../format";
import { dateWithDow, dayHead, emptySlotCount, initialWeek, kcalText, MEALS, urgentChip, weekDates, weekStarts } from "../meals/plan";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import { forgetRecipeCaches, forgetResources, useResource } from "../useResource";
import { currentWeekOf, LoadError, showMealsNotice } from "./Meals";
import { BackLink } from "./RecipeDetail";
import { urgentLabel } from "./Recipes";

interface DraftStore {
  planId: number;
  weekStart: string;
  meals: MealKind[];
  draft: MealDraft;
  /** 칸 "날짜|끼니" → 지금 고른 요리 번호 */
  choice: Record<string, number>;
  checked: Record<string, boolean>;
}

// ponytail: 확인 화면은 모듈 변수(뒤로가기·탭 이동 뒤에도 그대로, 새로고침하면 사라짐). 다른 식단을 열면 버린다.
let draftStore: DraftStore | null = null;

/** 로그아웃 때 resetMealsView가 부른다 */
export function forgetMealDraft() {
  draftStore = null;
}

const keyOf = (s: { date: string; meal: MealKind }) => `${s.date}|${s.meal}`;
/** "두부달걀찜으로", "불고기로", ㄹ 받침은 "로"(물로) */
const toward = (word: string) => ((word.charCodeAt(word.length - 1) - 0xac00) % 28 === 8 ? `${word}로` : withJosa(word, "으로", "로"));
const TITLE = "AI 식단 초안";

/** #/meals/:id/ai — 입력 → 만드는 중 → 확인 → 넣기 */
export default function MealAiDraft({ id, user }: { id: string; user: User }) {
  const { data: plan, error, status, reload } = useResource<MealPlan>(`/api/meal-plans/${id}`);
  useEffect(() => {
    if (user.scan === "off") navigate("/meals", { replace: true });
  }, [user.scan]);
  return (
    <main className="page">
      <BackLink to="/meals" label="식단" />
      {plan ? (
        <Draft key={plan.id} plan={plan} />
      ) : (
        <>
          <header className="topbar">
            <h1>{TITLE}</h1>
          </header>
          {status === 404 ? (
            <p className="center muted">식단을 찾을 수 없어요.</p>
          ) : error ? (
            <LoadError error={error} onRetry={reload} />
          ) : (
            <p className="center muted">불러오는 중…</p>
          )}
        </>
      )}
    </main>
  );
}

function Draft({ plan }: { plan: MealPlan }) {
  const today = localToday();
  const [store, setStore] = useState(() => (draftStore?.planId === plan.id ? draftStore : null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const viewed = currentWeekOf(plan.id);
  const week = store?.weekStart ?? (viewed && weekStarts(plan).includes(viewed) ? viewed : initialWeek(plan, today));
  const dates = weekDates(week, plan);
  const [meals, setMeals] = useState<MealKind[]>(store?.meals ?? ["lunch", "dinner"]);
  const [kcal, setKcal] = useState(plan.goal_kcal?.toString() ?? "");
  const [note, setNote] = useState(plan.goal_note ?? "");
  const usage = useResource<AiUsage>("/api/ai-usage");
  const stock = useResource<Ingredient[]>("/api/ingredients");
  const abort = useRef<AbortController | null>(null);
  const ids = { meals: useId(), kcal: useId(), kcalErr: useId() };

  // 다른 식단의 초안은 버린다
  useEffect(() => {
    if (draftStore && draftStore.planId !== plan.id) draftStore = null;
  }, [plan.id]);
  // 화면을 떠나면 만드는 중인 요청을 끊는다(서버가 이미 센 횟수는 돌아오지 않는다)
  useEffect(() => () => abort.current?.abort(), []);

  const phase = loading ? "loading" : store ? "review" : "input";
  // 단계가 바뀌면 누른 버튼이 사라져 포커스를 잃는다 → 맨 위 제목으로
  const shownPhase = useRef(phase);
  useEffect(() => {
    if (shownPhase.current === phase) return;
    shownPhase.current = phase;
    window.scrollTo(0, 0);
    const h1 = document.querySelector<HTMLElement>("main.page h1");
    if (!h1 || (document.activeElement && document.activeElement !== document.body)) return;
    h1.tabIndex = -1;
    h1.focus({ preventScroll: true });
  }, [phase]);

  // 곧 먹어야 할 재료: 임박·지남, 유통기한 빠른 순 4개(같은 이름은 하나)
  const urgent: Ingredient[] = [];
  for (const item of [...(stock.data ?? [])]
    .filter((i) => i.status === "danger" || i.status === "urgent")
    .sort((a, b) => (a.expires_on ?? "9999").localeCompare(b.expires_on ?? "9999")))
    if (urgent.length < 4 && !urgent.some((u) => u.name === item.name)) urgent.push(item);

  const empty = emptySlotCount(dates, meals, plan.slots);
  const kcalNum = Number(kcal);
  const kcalBad = kcal !== "" && (kcalNum < 500 || kcalNum > 5000);
  const usedUp = !!usage.data && usage.data.recipe.used >= usage.data.recipe.limit;

  const generate = async () => {
    setError("");
    setLoading(true);
    setStore(null);
    draftStore = null;
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      const draft = await api<MealDraft>(`/api/meal-plans/${plan.id}/ai-draft`, {
        method: "POST",
        body: { start_on: dates[0], days: dates.length, meals, goal_kcal: kcal ? kcalNum : null, goal_note: note.trim() || null },
        signal: ctrl.signal,
      });
      draftStore = {
        planId: plan.id,
        weekStart: week,
        meals,
        draft,
        choice: Object.fromEntries(draft.slots.map((s) => [keyOf(s), s.options[0]])),
        checked: Object.fromEntries(draft.slots.map((s) => [keyOf(s), true])),
      };
      setStore(draftStore);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError((e as Error).message);
    } finally {
      if (!ctrl.signal.aborted) {
        setLoading(false);
        forgetResources("/api/meal-plans"); // 목표 두 칸은 서버가 식단에 저장했다
        void usage.reload();
      }
    }
  };

  const cancel = () => {
    abort.current?.abort();
    setLoading(false);
    void usage.reload();
  };

  if (phase === "loading")
    return (
      <>
        <header className="topbar">
          <h1>{TITLE}</h1>
        </header>
        <Loading urgent={urgent.map((i) => i.name)} onCancel={cancel} />
      </>
    );

  if (store)
    return (
      <Review
        plan={plan}
        today={today}
        store={store}
        onChange={(next) => {
          draftStore = next;
          setStore(next);
        }}
        onRegenerate={generate}
      />
    );

  const end = dates[dates.length - 1];
  return (
    <>
      <header className="topbar">
        <div>
          <h1>{TITLE}</h1>
          <p className="summary">빈 칸에 넣을 요리를 골라줘요</p>
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <section className="rc-sec rc-form ml-ai-form">
        <div className="ml-preview-line">
          <span>{dates.includes(today) ? "기간 · 이번 주" : "기간"}</span>
          <b>
            {dateWithDow(dates[0])} – {end.slice(0, 7) === dates[0].slice(0, 7) ? dateWithDow(end).replace(/^\d+월 /, "") : dateWithDow(end)}
          </b>
        </div>
        <div className="field" role="group" aria-labelledby={ids.meals}>
          <span className="field-label" id={ids.meals}>
            끼니 고르기
          </span>
          <div className="sh-when ml-when">
            {MEALS.map(([meal, label]) => {
              const on = meals.includes(meal);
              return (
                <button
                  key={meal}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setMeals(MEALS.map(([k]) => k).filter((k) => (k === meal ? !on : meals.includes(k))))}
                >
                  {on && <Icon name="check" size={18} />}
                  {label}
                </button>
              );
            })}
          </div>
          <p className="ml-hint" aria-live="polite">
            {empty > 0 ? `고른 끼니의 빈 칸 ${empty}개만 채워요. 채운 칸은 그대로 둬요` : "고른 끼니에 빈 칸이 없어요"}
          </p>
        </div>
        <div className="field">
          <label className="field-label" htmlFor={ids.kcal}>
            하루 목표 칼로리 (선택)
          </label>
          <div className="input-suffix ml-goal">
            <input
              id={ids.kcal}
              className={kcalBad ? "input invalid" : "input"}
              inputMode="numeric"
              autoComplete="off"
              placeholder="예: 1800"
              value={kcal}
              aria-invalid={kcalBad || undefined}
              aria-describedby={kcalBad ? ids.kcalErr : undefined}
              onChange={(e) => setKcal(e.target.value.replace(/\D/g, "").slice(0, 4))}
            />
            <span className="suffix" aria-hidden="true">
              kcal
            </span>
          </div>
          {kcalBad && (
            <p className="rc-err" id={ids.kcalErr}>
              500~5000 사이로 입력해주세요
            </p>
          )}
        </div>
        <label className="field">
          <span className="field-label">메모 (선택)</span>
          <textarea
            className="input rc-area ml-note"
            rows={2}
            maxLength={100}
            placeholder="단백질 위주로, 저녁은 가볍게"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <span className="hint ml-counter" aria-hidden="true">
            {note.length} / 100
          </span>
        </label>
      </section>
      {urgent.length > 0 && (
        <div className="ml-use-box">
          <span>
            <Icon name="fridge" size={20} />
            재고에서 곧 먹어야 할 재료를 먼저 써요
          </span>
          <span className="rc-chips">
            {urgent.map((item) => (
              <span key={item.id} className="badge old">
                {urgentChip(item.name, item.expires_on, today)}
              </span>
            ))}
          </span>
        </div>
      )}
      <div className="cta-bar">
        <button type="button" className="btn primary" disabled={empty === 0 || kcalBad || usedUp} onClick={generate}>
          <Icon name="sparkle" />
          초안 만들기{remainingText(usage.data)}
        </button>
        {usedUp && <p className="r3-quota ml-cta-note">오늘 AI 레시피는 {usage.data!.recipe.limit}번까지 쓸 수 있어요. 내일 다시 써주세요.</p>}
      </div>
    </>
  );
}

/** RecipeAi Loading과 같은 모양 + 취소 */
function Loading({ urgent, onCancel }: { urgent: string[]; onCancel: () => void }) {
  // 알림 영역을 먼저 그려 두고 문구를 나중에 넣어야 스크린리더가 읽는다
  const [announce, setAnnounce] = useState(false);
  useEffect(() => setAnnounce(true), []);
  return (
    <>
      <p className="sr-only" role="status">
        {announce ? "빈 칸에 넣을 요리를 고르고 있어요" : ""}
      </p>
      <section className="r3-loading">
        <Mascot />
        <p className="r3-loading-title" aria-hidden="true">
          빈 칸에 넣을 요리를 고르고 있어요
        </p>
        <p className="muted r3-loading-sub">
          {urgent.length > 0 && (
            <>
              빨리 먹어야 할 {withJosa(namesLabel(urgent), "을", "를")} 먼저 넣어볼게요.
              <br />
            </>
          )}
          20초쯤 걸려요.
        </p>
        <div className="r3-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <button type="button" className="btn outline inline r3-back" onClick={onCancel}>
          취소
        </button>
      </section>
    </>
  );
}

interface ReviewProps {
  plan: MealPlan;
  today: string;
  store: DraftStore;
  onChange: (next: DraftStore) => void;
  onRegenerate: () => void;
}

function Review({ plan, today, store, onChange, onRegenerate }: ReviewProps) {
  const { draft, choice, checked } = store;
  const [swapped, setSwapped] = useState("");
  const { busy, error, run } = useAsyncAction();
  const dates = [...new Set([...draft.slots.map((s) => s.date), ...draft.kept.map((k) => k.date)])].sort();
  const slotAt = new Map(draft.slots.map((s) => [keyOf(s), s]));
  const keptAt = new Map(draft.kept.map((k) => [keyOf(k), k]));
  const count = draft.slots.filter((s) => checked[keyOf(s)]).length;
  // `새 레시피예요` 긴 안내는 화면 순서로 첫 새 요리 줄에만
  const firstNew = dates
    .flatMap((date) => MEALS.map(([meal]) => `${date}|${meal}`))
    .find((k) => slotAt.has(k) && draft.dishes[choice[k]].recipe_id === null);

  const apply = () =>
    run(async () => {
      const index = new Map<number, number>();
      const dishes: object[] = [];
      const slots = draft.slots
        .filter((s) => checked[keyOf(s)])
        .map((s) => {
          const n = choice[keyOf(s)];
          const dish = draft.dishes[n];
          if (!index.has(n)) {
            index.set(n, dishes.length);
            dishes.push(
              dish.recipe_id !== null
                ? { recipe_id: dish.recipe_id }
                : { title: dish.title, servings: dish.servings, ingredients: dish.ingredients.map(({ name, amount }) => ({ name, amount })), steps: dish.steps },
            );
          }
          return { date: s.date, meal: s.meal, dish: index.get(n), est_kcal: dish.est_kcal };
        });
      const res = await api<{ filled: number; kept: number; created_recipes: number }>(`/api/meal-plans/${plan.id}/ai-draft/apply`, {
        method: "POST",
        body: { dishes, slots },
      });
      forgetRecipeCaches();
      forgetResources("/api/meal-plans");
      forgetMealDraft();
      const kept = res.kept ? `그사이 채운 ${res.kept}칸은 그대로 뒀어요` : "";
      const created = res.created_recipes ? `새 레시피 ${res.created_recipes}개를 내 레시피에 저장했어요` : "";
      showMealsNotice(plan.id, [res.filled ? `${res.filled}칸을 넣었어요` : "", kept, created].filter(Boolean).join(" · "));
      navigate("/meals", { replace: true });
    });

  return (
    <>
      <header className="topbar">
        <div>
          <h1>{TITLE}</h1>
          <p className="summary">빈 칸 {draft.slots.length}개에 넣을 요리를 골랐어요</p>
        </div>
      </header>
      {draft.sample && (
        <p className="rc-sample">
          <Icon name="info" size={16} />
          예시 초안이에요
        </p>
      )}
      <p className="r3-note">
        <Icon name="info" size={16} />
        <span>kcal은 1인분 기준 AI 추정치예요. 정확한 영양 성분이 아니에요.</span>
      </p>
      <p className="sr-only" role="status">
        {swapped}
      </p>
      {dates.map((date) => {
        const head = dayHead(date);
        const sum = kcalText(draft.slots.filter((s) => s.date === date && checked[keyOf(s)]).map((s) => draft.dishes[choice[keyOf(s)]].est_kcal));
        return (
          <section key={date} aria-label={`${head.day} ${head.dow}`}>
            <h2 className="ml-daygroup">
              {head.day} {head.dow}
              {date === today && " · 오늘"}
              {sum && <span>1인분 {sum}</span>}
            </h2>
            <div className="list">
              {MEALS.map(([meal, label]) => {
                const k = `${date}|${meal}`;
                const slot = slotAt.get(k);
                const kept = keptAt.get(k);
                if (kept)
                  return (
                    <div key={meal} className="ml-kept">
                      <Icon name="check" size={18} />
                      <span>
                        <b>
                          {label} · {kept.title}
                        </b>{" "}
                        이미 채운 칸이라 그대로 둬요
                      </span>
                    </div>
                  );
                if (!slot) return null;
                const on = !!checked[k];
                const dish = draft.dishes[choice[k]];
                const urgent = urgentLabel(dish.urgent_names);
                const isNew = dish.recipe_id === null;
                const kcal = kcalText([dish.est_kcal]);
                return (
                  <div key={meal} className={on ? "ml-ai-row" : "ml-ai-row off"}>
                    <button
                      type="button"
                      className="sh-check"
                      role="checkbox"
                      aria-checked={on}
                      aria-label={`${head.day} ${label} 넣기`}
                      onClick={() => onChange({ ...store, checked: { ...checked, [k]: !on } })}
                    >
                      <i>{on && <Icon name="check" size={18} />}</i>
                    </button>
                    <span className="row-main">
                      <span className="ml-meal">{label}</span>
                      <span className="ml-title">{dish.title}</span>
                      <span className="row-sub">
                        {plan.default_servings}인분{kcal && ` · 1인분 ${kcal}`}
                      </span>
                      {(urgent || (isNew && k !== firstNew)) && (
                        <span className="sh-meta">
                          {urgent && <span className="sh-tag warn">{urgent}</span>}
                          {isNew && k !== firstNew && <span className="sh-tag">새 레시피</span>}
                        </span>
                      )}
                      {k === firstNew && <span className="ml-new">새 레시피예요 · 넣으면 내 레시피에도 저장해요</span>}
                    </span>
                    {slot.options.length > 1 && (
                      <button
                        type="button"
                        className="btn outline ml-swap"
                        aria-label={`${head.day} ${label} 다른 요리로 바꾸기`}
                        onClick={() => {
                          const next = slot.options[(slot.options.indexOf(choice[k]) + 1) % slot.options.length];
                          onChange({ ...store, choice: { ...choice, [k]: next } });
                          setSwapped(`${toward(draft.dishes[next].title)} 바꿨어요`);
                        }}
                      >
                        <Icon name="refresh" size={16} />
                        다른 걸로
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
      <div className="cta-bar">
        {error && (
          <p className="error ml-cta-error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button
            type="button"
            className="btn outline ml-regen"
            disabled={busy}
            onClick={() => {
              if (confirm("초안을 다시 만들까요? AI 사용 횟수를 한 번 더 써요.")) onRegenerate();
            }}
          >
            다시 만들기
          </button>
          <button type="button" className="btn primary" disabled={count === 0 || busy} onClick={apply}>
            {busy ? "넣는 중…" : `${count}칸 식단에 넣기`}
          </button>
        </div>
      </div>
    </>
  );
}

