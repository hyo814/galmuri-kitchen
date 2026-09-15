import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, api, localToday, type AiUsage, type BodyProfileResponse, type Ingredient, type MealKind, type MealPlan, type User } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import { namesLabel, remainingText, withJosa } from "../format";
import {
  cancelDraft, discardDraft, drafts, emit, errors, getVersion, keyOf, running, startDraft, subscribe, type DraftStore,
} from "../meals/draftStore";
import { dateWithDow, dayHead, emptySlotCount, initialWeek, kcalText, MEALS, urgentChip, weekDates, weekStarts } from "../meals/plan";
import { dailyTarget } from "../nutrition/body";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import { forgetRecipeCaches, forgetResources, useResource } from "../useResource";
import { currentWeekOf, LoadError, showMealsNotice } from "./Meals";
import { BackLink } from "./RecipeDetail";
import { urgentLabel } from "./Recipes";

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
        <Draft key={plan.id} plan={plan} reloadPlan={reload} />
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

function Draft({ plan, reloadPlan }: { plan: MealPlan; reloadPlan: () => Promise<void> }) {
  const today = localToday();
  useSyncExternalStore(subscribe, getVersion);
  const viewed = currentWeekOf(plan.id);
  const viewedWeek = viewed && weekStarts(plan).includes(viewed) ? viewed : initialWeek(plan, today);
  // 들어올 때 한 번: 다 만든 초안·오류가 식단에서 보고 있던 주와 다르면 옛 것이라 버리고 그 주 입력을 보여준다.
  // 만드는 중인 요청은 횟수를 이미 썼으니 주가 달라도 그대로 기다린다. 읽기 전에 지워 emit 없이 이번 렌더에 반영된다(두 번 불려도 같다)
  useState(() => {
    if (running.has(plan.id)) return;
    if (drafts.get(plan.id) && drafts.get(plan.id)!.weekStart !== viewedWeek) drafts.delete(plan.id);
    if (errors.get(plan.id) && errors.get(plan.id)!.weekStart !== viewedWeek) errors.delete(plan.id);
  });
  const store = drafts.get(plan.id) ?? null;
  const loading = running.get(plan.id);
  const error = errors.get(plan.id)?.message ?? "";
  const week = loading?.weekStart ?? store?.weekStart ?? viewedWeek;
  const dates = weekDates(week, plan);
  const [meals, setMeals] = useState<MealKind[]>(loading?.meals ?? store?.meals ?? ["lunch", "dinner"]);
  const [kcal, setKcal] = useState(plan.goal_kcal?.toString() ?? "");
  const touchedKcal = useRef(false);
  const [note, setNote] = useState(plan.goal_note ?? "");
  const usage = useResource<AiUsage>("/api/ai-usage");
  const stock = useResource<Ingredient[]>("/api/ingredients");
  const bodyProfile = useResource<BodyProfileResponse>("/api/body-profile");
  const ids = { meals: useId(), kcal: useId(), kcalErr: useId() };

  // 목표 칸이 비어 있으면 몸 정보 목표로 채운다(결정 4). 이미 만졌으면 덮어쓰지 않는다
  useEffect(() => {
    if (plan.goal_kcal !== null || touchedKcal.current) return;
    const profile = bodyProfile.data?.profile;
    if (profile) setKcal(String(dailyTarget(profile, today).target));
  }, [bodyProfile.data, plan.goal_kcal, today]);

  const phase = loading ? "loading" : store ? "review" : "input";
  // 단계가 바뀌면 누른 버튼이 사라져 포커스를 잃는다 → 맨 위 제목으로
  const shownPhase = useRef(phase);
  const reloadUsage = usage.reload;
  useEffect(() => {
    if (shownPhase.current === phase) return;
    if (shownPhase.current === "loading") void reloadUsage(); // 만들기가 끝나거나 취소하면 남은 횟수를 다시 받는다
    shownPhase.current = phase;
    window.scrollTo(0, 0);
    const h1 = document.querySelector<HTMLElement>("main.page h1");
    if (!h1 || (document.activeElement && document.activeElement !== document.body)) return;
    h1.tabIndex = -1;
    h1.focus({ preventScroll: true });
  }, [phase, reloadUsage]);

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

  const generate = () =>
    startDraft(plan.id, week, meals, { start_on: dates[0], days: dates.length, meals, goal_kcal: kcal ? kcalNum : null, goal_note: note.trim() || null });

  if (phase === "loading")
    return (
      <>
        <header className="topbar">
          <h1>{TITLE}</h1>
        </header>
        <Loading urgent={urgent.map((i) => i.name)} onCancel={() => cancelDraft(plan.id)} />
      </>
    );

  if (store)
    return (
      <Review
        plan={plan}
        today={today}
        store={store}
        regenerateError={error}
        onChange={(next) => {
          drafts.set(plan.id, next);
          emit();
        }}
        onRegenerate={generate}
        onDiscard={(message) => {
          discardDraft(plan.id, message);
          if (message) void reloadPlan(); // 넣기 4xx: 기간·칸이 바뀌었을 수 있다
        }}
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
              onChange={(e) => {
                touchedKcal.current = true;
                setKcal(e.target.value.replace(/\D/g, "").slice(0, 4));
              }}
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
          {/* 처음부터 붙어 있는 영역에 글자만 넣어야 스크린리더가 읽는다 */}
          <p className="sr-only" aria-live="polite">
            {kcalBad ? "500~5000 사이로 입력해주세요" : ""}
          </p>
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
          1분쯤 걸려요.
          <br />
          다른 화면에 다녀와도 계속 만들어요.
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
  /** 다시 만들기 실패: 이전 초안은 그대로 두고 CTA 위에 알린다 */
  regenerateError: string;
  onChange: (next: DraftStore) => void;
  onRegenerate: () => void;
  /** 초안 버리기·넣기 4xx: 입력 화면으로(message는 입력 화면 오류 자리에) */
  onDiscard: (message?: string) => void;
}

function Review({ plan, today, store, regenerateError, onChange, onRegenerate, onDiscard }: ReviewProps) {
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
      let res: { filled: number; kept: number; created_recipes: number };
      try {
        res = await api(`/api/meal-plans/${plan.id}/ai-draft/apply`, { method: "POST", body: { dishes, slots } });
      } catch (e) {
        // 레시피가 바뀌었거나 식단 기간이 줄었으면 같은 초안으로는 넣을 수 없다 → 버리고 입력 화면에서 다시 만들게
        if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 401) {
          forgetResources("/api/meal-plans");
          return onDiscard(e.message);
        }
        throw e;
      }
      forgetRecipeCaches();
      forgetResources("/api/meal-plans");
      const kept = res.kept ? `그사이 채운 ${res.kept}칸은 그대로 뒀어요` : "";
      const created = res.created_recipes ? `새 레시피 ${res.created_recipes}개를 내 레시피에 저장했어요` : "";
      showMealsNotice(plan.id, [res.filled ? `${res.filled}칸을 넣었어요` : "", kept, created].filter(Boolean).join(" · "));
      navigate("/meals", { replace: true });
      drafts.delete(plan.id); // 화면을 옮긴 뒤에 비워야 입력 화면이 잠깐 보이지 않는다(다른 식단 초안·요청은 그대로)
      errors.delete(plan.id);
      emit();
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
          <div key={date}>
            <h2 className="ml-daygroup">
              {head.day} {head.dow}
              {date === today && " · 오늘"}
              {sum && (
                <>
                  {/* 스크린리더가 `오늘1인분`처럼 붙여 읽지 않게 */}
                  <span className="sr-only">, </span>
                  <span>1인분 {sum}</span>
                </>
              )}
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
                        aria-label={`${head.day} ${label} 다른 걸로`}
                        onClick={() => {
                          const next = slot.options[(slot.options.indexOf(choice[k]) + 1) % slot.options.length];
                          onChange({ ...store, choice: { ...choice, [k]: next } });
                          // 같은 글자를 다시 넣으면 읽지 않는다 → 끝에 공백을 번갈아 붙인다
                          const text = `${toward(draft.dishes[next].title)} 바꿨어요`;
                          setSwapped((prev) => (prev === text ? `${text}\u00a0` : text));
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
          </div>
        );
      })}
      <div className="ml-discard">
        <button
          type="button"
          className="btn outline inline"
          disabled={busy}
          onClick={() => {
            if (confirm("초안을 버릴까요? 다시 만들면 AI 사용 횟수를 한 번 더 써요.")) onDiscard();
          }}
        >
          초안 버리기
        </button>
      </div>
      <div className="cta-bar">
        {(error || regenerateError) && (
          <p className="error ml-cta-error" role="alert">
            {error || regenerateError}
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

