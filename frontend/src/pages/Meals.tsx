import { useEffect, useRef, useState } from "react";
import {
  api, localToday, type AiUsage, type BodyProfileResponse, type MealKind, type MealPlan, type MealPlanList, type MealPlanSummary, type MealSlot, type User,
} from "../api";
import BodyGoalCard, { type TodayTotal } from "../components/BodyGoalCard";
import DayNutritionSheet from "../components/DayNutritionSheet";
import Icon from "../components/Icon";
import LoadError from "../components/LoadError";
import Mascot from "../components/Mascot";
import MealCopySheet, { type CopyResult } from "../components/MealCopySheet";
import MealFillSheet from "../components/MealFillSheet";
import MealPickerSheet from "../components/MealPickerSheet";
import MealPlanSheet from "../components/MealPlanSheet";
import MealSlotSheet from "../components/MealSlotSheet";
import Sheet from "../components/Sheet";
import { addDays, remainingText, withJosa } from "../format";
import {
  dayHead, defaultPlanName, initialWeek, MEALS, monthGrid, pickPlan, rangeText, slotDateText, weekDates, weekOf, weekStarts,
} from "../meals/plan";
import { dailyTarget, kcalNumber } from "../nutrition/body";
import { daySum, dayHeadText, fillTargets, goalFor, meterPercent, slotKcalText } from "../nutrition/day";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import { cache, forgetResources, useResource } from "../useResource";
import { forgetMealDraft } from "../meals/draftStore";
import { urgentLabel } from "./Recipes";

/** 채우기를 이미 부른 레시피 `${planId}|${recipe_id}`(결정 13). pending 목록이 나중에 줄어도(다른 레시피가 먼저 풀려도)
 * 이미 부른 레시피는 다시 넣지 않는다 — 레시피별로 한 번만 시도한다(합쳐 부른 목록으로 판단하면 pending이 줄 때마다
 * 새 조합으로 보여 계속 다시 불렀다). resetMealsView가 비운다 */
const attempted = new Set<string>();

// 탭을 오가도 보던 식단·보기·주를 기억한다(로그아웃 때 resetMealsView)
let lastPlanId: number | null = null;
let lastView: "week" | "month" = "week";
let lastWeek: Record<number, string> = {};
/** AI 초안을 넣은 뒤 식단 머리에 한 번 보여줄 한 줄 */
let notice: { planId: number; text: string } | null = null;

export function resetMealsView() {
  lastPlanId = null;
  lastView = "week";
  lastWeek = {};
  notice = null;
  attempted.clear();
  forgetMealDraft();
}

/** AI 초안 넣기 뒤: 그 식단을 열고 머리에 결과 한 줄을 한 번 보여준다 */
export function showMealsNotice(planId: number, text: string) {
  lastPlanId = planId;
  notice = { planId, text };
}

/** 식단별로 보고 있던 주 시작일(AI 초안 화면이 이 주를 채운다) */
export function currentWeekOf(planId: number): string | undefined {
  return lastWeek[planId];
}

export { LoadError };

export default function Meals({ user }: { user: User }) {
  const today = localToday();
  const list = useResource<MealPlanList>("/api/meal-plans");
  const [planId, setPlanId] = useState(lastPlanId);
  /** create-ai: `AI로 초안 만들기` — 만든 뒤 바로 AI 초안 화면으로 */
  const [sheet, setSheet] = useState<"create" | "create-ai" | "pick" | null>(null);
  /** 방금 만든 식단: 목록을 다시 받지 못해도(연결 끊김) 옛 식단 대신 이것을 보여준다 — 또 만들어 겹치지 않게 */
  const [justCreated, setJustCreated] = useState<MealPlanSummary | null>(null);

  const choose = (id: number) => {
    lastPlanId = id;
    setPlanId(id);
  };
  const created = async (plan: MealPlan) => {
    forgetResources("/api/meal-plans");
    cache.set(`/api/meal-plans/${plan.id}`, plan); // 새 식단은 받은 그대로 바로 보여준다
    setJustCreated(plan);
    await list.reload(); // 목록에 새 식단이 들어온 뒤에 바꿔야 이전 식단이 잠깐 보이지 않는다
    choose(plan.id);
    setSheet(null);
    if (sheet === "create-ai") navigate(`/meals/${plan.id}/ai`);
  };

  const items = list.data?.items;
  // 기억한 식단이 목록에 없으면(지워짐) 오늘이 든 식단부터
  const current =
    items && (items.find((p) => p.id === planId) ?? (justCreated?.id === planId ? justCreated : undefined) ?? pickPlan(items, today));

  const createSheet = (sheet === "create" || sheet === "create-ai") && list.data && (
    <MealPlanSheet today={today} defaultServings={list.data.default_servings} onSaved={created} onClose={() => setSheet(null)} />
  );

  if (!items || !current)
    return (
      <main className="page">
        <header className="topbar">
          <h1>식단</h1>
        </header>
        <BodyGoalCard today={today} />
        {!items ? (
          list.error ? (
            <LoadError error={list.status === 0 ? "인터넷이 연결되면 식단을 볼 수 있어요" : list.error} onRetry={list.reload} />
          ) : (
            <p className="center muted">불러오는 중…</p>
          )
        ) : (
          <section className="empty rc-empty ml-empty">
            <Mascot size={72} />
            <p className="soon-title">아직 식단이 없어요</p>
            <p className="muted">한 주 끼니를 미리 정해두면 장보기가 쉬워져요</p>
            <ul className="plain-list ml-steps">
              {["끼니마다 먹을 요리를 칸에 채워요", "재고에서 곧 먹어야 할 재료를 먼저 써요", "모자란 재료만 장보기에 담아줘요"].map((step) => (
                <li key={step}>
                  <Icon name="check" size={18} />
                  <span>{step}</span>
                </li>
              ))}
            </ul>
            <div className="ml-stack ml-empty-actions">
              <button type="button" className="btn primary" onClick={() => setSheet("create")}>
                <Icon name="plus" />
                식단 만들기
              </button>
              {user.scan !== "off" && (
                <button type="button" className="btn outline" aria-haspopup="dialog" onClick={() => setSheet("create-ai")}>
                  <Icon name="sparkle" />
                  AI로 초안 만들기
                </button>
              )}
            </div>
            {user.scan !== "off" && <AiQuota />}
          </section>
        )}
        {createSheet}
      </main>
    );

  return (
    <>
      <PlanWeek
        key={current.id}
        summary={current}
        today={today}
        user={user}
        onPick={() => setSheet("pick")}
        onChanged={list.reload}
        onDeleted={async () => {
          forgetResources("/api/meal-plans");
          await list.reload(); // created와 같은 순서: 목록을 받은 뒤에 바꾼다
          setJustCreated(null);
          lastPlanId = null;
          setPlanId(null);
          // 지운 식단 화면의 메뉴 버튼이 사라져 포커스를 잃는다 → 제목으로
          setTimeout(() => {
            const h1 = document.querySelector<HTMLElement>(".topbar h1");
            if (!h1 || document.activeElement !== document.body) return;
            h1.tabIndex = -1;
            h1.focus();
          });
        }}
      />
      {sheet === "pick" && (
        <MealPickerSheet
          items={items}
          currentId={current.id}
          onPick={(id) => {
            choose(id);
            setSheet(null);
          }}
          onCreate={() => setSheet("create")}
          onClose={() => setSheet(null)}
        />
      )}
      {createSheet}
    </>
  );
}

/** 빈 화면 `AI로 초안 만들기` 아래 횟수 줄 */
function AiQuota() {
  const { data } = useResource<AiUsage>("/api/ai-usage");
  return <p className="r3-quota ml-empty-quota">AI 레시피와 같은 횟수를 써요{remainingText(data)}</p>;
}

interface PlanWeekProps {
  summary: MealPlanSummary;
  today: string;
  /** 채우기 시트의 영상 칸(user.videos) */
  user: User;
  onPick: () => void;
  /** 칸을 바꿨다: 목록(식단 고르기의 채운 칸 수)도 다시 받는다 */
  onChanged: () => void;
  onDeleted: () => Promise<void>;
}

const DOW_HEAD = ["월", "화", "수", "목", "금", "토", "일"];

/** 시안 WeekView·MonthView: 머리·식단 고르기·주|월·주(달) 이동·하루 카드(달력) */
function PlanWeek({ summary, today, user, onPick, onChanged, onDeleted }: PlanWeekProps) {
  const url = `/api/meal-plans/${summary.id}`;
  const { data: plan, error, reload } = useResource<MealPlan>(url);
  const shown = plan ?? summary;
  const weeks = weekStarts(shown);
  const [picked, setPicked] = useState(() => lastWeek[summary.id]);
  const week = picked && weeks.includes(picked) ? picked : initialWeek(shown, today);
  const index = weeks.indexOf(week);
  const [view, setView] = useState(lastView);
  /** 월 보기에서 보고 있는 달 "2026-09"(null이면 보고 있는 주의 달) */
  const [month, setMonth] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"menu" | "copy" | "edit" | null>(null);
  /** 이번 주 복사·AI 초안 넣기 결과 한 줄 */
  const [copied, setCopied] = useState("");
  const [openSlot, setOpenSlot] = useState<MealSlot | null>(null);
  const [fill, setFill] = useState<{ date: string; meal: MealKind; current?: MealSlot } | null>(null);
  /** 하루 머리를 눌러 연 하루 영양 시트의 날짜 */
  const [nutritionDate, setNutritionDate] = useState<string | null>(null);
  /** 시트가 열려 있는 동안 바뀐 칸은 닫을 때 한 번에 다시 받는다. 닫은 뒤 늦게 끝난 저장은 바로 다시 받는다 */
  const dirty = useRef(false);
  const sheetOpen = useRef(false);

  const { data: bodyProfile, set: setBodyProfile } = useResource<BodyProfileResponse>("/api/body-profile");
  const profileTarget = bodyProfile?.profile ? dailyTarget(bodyProfile.profile, today).target : null;
  const goal = goalFor(profileTarget, plan?.goal_kcal ?? null);

  useEffect(() => {
    lastWeek[summary.id] = week;
  }, [summary.id, week]);

  // 채우기(결정 13): 주 보기에서 보이는 주의 pending 레시피 중 아직 안 시도한 것만, 레시피마다 한 번
  useEffect(() => {
    if (!plan || view !== "week" || user.nutrition === "off") return;
    const attemptedIds = new Set(plan.nutrition_pending_recipe_ids.filter((id) => attempted.has(`${plan.id}|${id}`)));
    const ids = fillTargets(plan.slots, weekDates(week, plan), plan.nutrition_pending_recipe_ids, attemptedIds);
    if (!ids.length) return;
    for (const id of ids) attempted.add(`${plan.id}|${id}`); // 요청 전에 표시(pending이 줄어도 같은 레시피를 다시 부르지 않게)
    (async () => {
      try {
        await api("/api/nutrition/fill", { method: "POST", body: { recipe_ids: ids } });
      } catch {
        // 조용히 실패: 다음에 다시 보면 그때 채운다(레시피는 그대로 시도한 것으로 남는다)
      }
      await reload();
    })();
  }, [plan, view, week, user.nutrition, reload]);

  // 복사 결과 한 줄은 주·보기가 바뀌면 지운다(식단이 바뀌면 key로 새로 그린다). 처음 그릴 때는 지우지 않는다(AI 초안 결과)
  const shownFor = useRef(`${week}|${view}`);
  useEffect(() => {
    if (shownFor.current === `${week}|${view}`) return;
    shownFor.current = `${week}|${view}`;
    setCopied("");
  }, [week, view]);
  // AI 초안 넣기 결과: 알림 영역을 먼저 그린 뒤 문구를 넣어야 스크린리더가 읽는다. 한 번 보여주고 지운다
  useEffect(() => {
    if (notice?.planId === summary.id) setCopied(notice.text);
    notice = null;
  }, [summary.id]);

  const switchView = (next: "week" | "month") => {
    lastView = next;
    setView(next);
    setMonth(null);
  };

  /** 달력 날짜·카드: 그 날이 든 주 보기로 가고, 누른 버튼이 사라지니 그날 카드로 포커스 */
  const openDay = (date: string) => {
    setPicked(weekOf(shown, date) ?? week);
    switchView("week");
    setTimeout(() => {
      const day = document.querySelector<HTMLElement>(`.ml-day[data-date="${date}"]`);
      if (!day) return;
      day.tabIndex = -1;
      day.focus();
    });
  };

  const closeSlot = async (slot: MealSlot) => {
    sheetOpen.current = false;
    setOpenSlot(null);
    if (!dirty.current) return;
    dirty.current = false;
    setCopied("");
    onChanged();
    await reload();
    // 칸을 비우면 시트를 연 줄 버튼이 사라져 포커스를 잃는다 → 그날 카드로 옮긴다
    setTimeout(() => {
      if (document.activeElement !== document.body) return;
      const day = document.querySelector<HTMLElement>(`.ml-day[data-date="${slot.date}"]`);
      if (!day) return;
      day.tabIndex = -1;
      day.focus();
    });
  };

  /** 칸·기간을 바꿨다: 식단과 목록(채운 칸 수)을 다시 받는다 */
  const replacePlan = async () => {
    setCopied(""); // 다음 변경에서 지난 복사 결과는 지운다(복사는 끝난 뒤 다시 적는다)
    forgetResources("/api/meal-plans"); // 목록·장보기 미리보기 캐시도 옛 칸을 보여주지 않게
    onChanged();
    await reload();
  };

  /** 채우기 시트에서 넣었다: 식단을 다시 받은 뒤 닫는다(닫자마자 빈 칸이 잠깐 보이지 않게) */
  const saved = async (slot: MealSlot) => {
    await replacePlan();
    setFill(null);
    // 빈 끼니 칩은 채운 칸 줄로 바뀌어 사라진다 → 그 줄로 포커스
    setTimeout(() => {
      if (document.activeElement !== document.body) return;
      document.querySelector<HTMLElement>(`.ml-day[data-date="${slot.date}"] [data-meal="${slot.meal}"]`)?.focus();
    });
  };

  const copiedWeek = async ({ copied: count, kept }: CopyResult) => {
    await replacePlan();
    setSheet(null);
    // 모두 이미 채운 칸이면 "0칸을 복사했어요"는 빼고 그대로 둔 칸만 알린다
    const keptText = kept ? `이미 채운 ${kept}칸은 그대로 뒀어요` : "";
    setCopied(count ? `${count}칸을 복사했어요${keptText && ` · ${keptText}`}` : keptText);
  };

  // 고친 기간 밖으로 나간 주는 week 계산이 initialWeek로 돌린다
  const edited = async () => {
    await replacePlan();
    setSheet(null);
  };

  const move = (step: number) => setPicked(weeks[index + step]);
  /** 끝 주·끝 달에 닿아 누른 화살표가 disabled가 되면 포커스를 잃는다 → 반대쪽 화살표로 */
  const keepNavFocus = (button: HTMLElement) =>
    setTimeout(() => {
      if ((button as HTMLButtonElement).disabled) button.parentElement?.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
    });
  const dates = weekDates(week, shown);
  const slots = new Map((plan?.slots ?? []).map((s) => [`${s.date}|${s.meal}`, s]));

  // 카드 둘째 줄 "오늘 식단": 오늘이 식단 기간 안이고 그날 채운 칸이 있으면(보고 있는 주와 무관하게 오늘 칸으로)
  const todaySlots = plan ? MEALS.map(([meal]) => plan.slots.find((s) => s.date === today && s.meal === meal)).filter((s): s is MealSlot => !!s) : [];
  const todaySum = plan && shown.start_on <= today && today <= shown.end_on ? daySum(todaySlots) : null;
  const todayTotal: TodayTotal | null = todaySum
    ? {
        text: `${todaySum.approx ? "약 " : ""}${kcalNumber(todaySum.kcal)}`,
        percent: meterPercent(todaySum.kcal, profileTarget ?? todaySum.kcal),
        over: profileTarget !== null && todaySum.kcal > profileTarget,
      }
    : null;

  // 월 보기: 식단 기간과 겹치는 달만
  const firstMonth = shown.start_on.slice(0, 7);
  const lastMonth = addDays(shown.start_on, shown.days - 1).slice(0, 7);
  const shownMonth = month && month >= firstMonth && month <= lastMonth ? month : week.slice(0, 7);
  const [year, monthNo] = shownMonth.split("-").map(Number);
  const weekFilled = (plan?.slots ?? []).filter((s) => dates.includes(s.date)).length;

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <h1>식단</h1>
          <p className="summary">
            {shown.total}칸 중 {shown.filled}칸 채웠어요
          </p>
        </div>
        <div className="ml-head-actions">
          {user.scan !== "off" && (
            <button type="button" className="ml-ai-pill" onClick={() => navigate(`/meals/${summary.id}/ai`)}>
              <Icon name="sparkle" size={18} />
              AI 초안
            </button>
          )}
          <button
            type="button"
            className="icon-btn"
            aria-label="식단 메뉴"
            aria-haspopup="dialog"
            disabled={!plan}
            onClick={() => {
              setCopied("");
              setSheet("menu");
            }}
          >
            <Icon name="more" />
          </button>
        </div>
      </header>
      <p className="ml-copied" role="status">
        {copied}
      </p>
      <BodyGoalCard today={today} todayTotal={todayTotal} onProfileChanged={setBodyProfile} />
      <div className="ml-row2">
        <button type="button" className="ml-plan" aria-haspopup="dialog" aria-label={`${shown.name}, 다른 식단 고르기`} onClick={onPick}>
          <span>{shown.name}</span>
          <Icon name="down" size={18} />
        </button>
        <div className="segmented ml-seg" role="group" aria-label="보기">
          <button type="button" aria-pressed={view === "week"} onClick={() => switchView("week")}>
            주
          </button>
          <button type="button" aria-pressed={view === "month"} onClick={() => switchView("month")}>
            월
          </button>
        </div>
      </div>
      {view === "week" ? (
        <div className="ml-nav">
          <button
            type="button"
            className="icon-btn"
            aria-label="이전 주"
            disabled={index <= 0}
            onClick={(e) => {
              move(-1);
              keepNavFocus(e.currentTarget);
            }}
          >
            <Icon name="back" size={22} />
          </button>
          <b aria-live="polite">{rangeText(dates[0], dates[dates.length - 1])}</b>
          <button
            type="button"
            className="icon-btn"
            aria-label="다음 주"
            disabled={index >= weeks.length - 1}
            onClick={(e) => {
              move(1);
              keepNavFocus(e.currentTarget);
            }}
          >
            <Icon name="chevron" size={22} />
          </button>
        </div>
      ) : (
        <div className="ml-nav">
          <button
            type="button"
            className="icon-btn"
            aria-label="지난달"
            disabled={shownMonth <= firstMonth}
            onClick={(e) => {
              setMonth(addDays(`${shownMonth}-01`, -1).slice(0, 7));
              keepNavFocus(e.currentTarget);
            }}
          >
            <Icon name="back" size={22} />
          </button>
          <b aria-live="polite">
            {year}년 {monthNo}월
          </b>
          <button
            type="button"
            className="icon-btn"
            aria-label="다음 달"
            disabled={shownMonth >= lastMonth}
            onClick={(e) => {
              setMonth(addDays(`${shownMonth}-01`, 31).slice(0, 7));
              keepNavFocus(e.currentTarget);
            }}
          >
            <Icon name="chevron" size={22} />
          </button>
        </div>
      )}

      {!plan ? (
        error ? (
          <LoadError
            error={error}
            onRetry={() => {
              void reload();
              onChanged();
            }}
          />
        ) : (
          <p className="center muted">불러오는 중…</p>
        )
      ) : view === "month" ? (
        <>
          <div className="ml-cal">
            <div className="ml-wk" aria-hidden="true">
              {DOW_HEAD.map((d) => (
                <span key={d}>{d}</span>
              ))}
            </div>
            {monthGrid(year, monthNo).map((row) => (
              <div key={row[0]} className="ml-wrow">
                {row.map((date) => {
                  const inPlan = weekOf(shown, date) !== null;
                  const cls = ["ml-cell", date.slice(0, 7) !== shownMonth && "dim", inPlan && "in", date === today && "today"]
                    .filter(Boolean)
                    .join(" ");
                  const num = <b>{Number(date.slice(8))}</b>;
                  // 기간 밖 날짜는 누를 곳이 없어 스크린리더에서도 건너뛴다
                  if (!inPlan)
                    return (
                      <span key={date} className={cls} aria-hidden="true">
                        {num}
                        <span className="ml-dots" />
                      </span>
                    );
                  const filled = MEALS.map(([meal]) => slots.has(`${date}|${meal}`));
                  const head = dayHead(date);
                  // 흐린 칸(앞뒤 달)은 날짜만으로는 어느 달인지 모른다
                  const monthText = date.slice(0, 7) !== shownMonth ? `${Number(date.slice(5, 7))}월 ` : "";
                  return (
                    <button
                      key={date}
                      type="button"
                      className={cls}
                      aria-current={date === today ? "date" : undefined}
                      aria-label={`${monthText}${head.day} ${head.dow} · 4끼 중 ${filled.filter(Boolean).length}끼 채움`}
                      onClick={() => openDay(date)}
                    >
                      {num}
                      <span className="ml-dots">
                        {filled.map((on, i) => (
                          <i key={i} className={on ? undefined : "no"} />
                        ))}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="ml-legend">
            <span>
              <span className="ml-dots">
                <i />
              </span>
              채운 끼니
            </span>
            <span>
              <span className="ml-dots">
                <i className="no" />
              </span>
              빈 끼니
            </span>
            <span>초록 줄 = 이 식단 기간</span>
          </div>
          <button type="button" className="ml-plan-card" onClick={() => openDay(week)}>
            <span className="row-main">
              <span className="row-title">날짜를 누르면 그 주로 가요</span>
              <span className="row-sub">
                {/* 수요일 시작처럼 주 중간에 시작하는 식단은 가운데 날로 부른다(다음 달이 대부분인 주를 앞 달 주로 부르지 않게). 월요일 시작은 식단 이름과 같게 */}
                {defaultPlanName(dayHead(week).dow === "월요일" ? week : dates[Math.floor((dates.length - 1) / 2)], 7)} · {rangeText(dates[0], dates[dates.length - 1]).replace(/^\d+월 /, "")} ·{" "}
                {dates.length * 4}칸 중 {weekFilled}칸
              </span>
            </span>
            <Icon name="chevron" size={20} />
          </button>
        </>
      ) : (
        <div className="ml-days">
          {dates.map((date) => {
            const head = dayHead(date);
            const daySlots = MEALS.map(([meal]) => slots.get(`${date}|${meal}`)).filter((s): s is MealSlot => !!s);
            const filled = daySlots.length;
            const sum = daySum(daySlots);
            const over = goal !== null && !!sum && sum.kcal > goal;
            return (
              <section key={date} className={date === today ? "ml-day today" : "ml-day"} data-date={date} aria-label={slotDateText(date, today)}>
                {sum ? (
                  <button
                    type="button"
                    className="ml-day-head nt-head-btn"
                    aria-haspopup="dialog"
                    aria-label={`${head.day} ${head.dow}${date === today ? " · 오늘" : ""} 식단 영양 보기, ${dayHeadText(sum, goal)}`}
                    onClick={() => setNutritionDate(date)}
                  >
                    <span className="ml-date">{head.day}</span>
                    <span className="ml-dow">{head.dow}</span>
                    {date === today && <span className="badge info">오늘</span>}
                    <span className={over ? "ml-count nt-kcal warn" : "ml-count nt-kcal"}>{dayHeadText(sum, goal)}</span>
                  </button>
                ) : (
                  <div className="ml-day-head">
                    <span className="ml-date">{head.day}</span>
                    <span className="ml-dow">{head.dow}</span>
                    {date === today && <span className="badge info">오늘</span>}
                    <span className="ml-count">{filled} / 4</span>
                  </div>
                )}
                {goal !== null && sum && (
                  <div
                    className={over ? "nt-meter nt-dmeter warn" : "nt-meter nt-dmeter"}
                    role="img"
                    aria-label={`목표의 ${Math.round((sum.kcal / goal) * 100)}%`}
                  >
                    <i style={{ width: `${meterPercent(sum.kcal, goal)}%` }} />
                  </div>
                )}
                {MEALS.map(([meal, label]) => {
                  const slot = slots.get(`${date}|${meal}`);
                  if (!slot) return null;
                  const urgent = slot.recipe_id !== null ? urgentLabel(slot.urgent_names) : "";
                  const kcalText = slotKcalText(slot.nutrition);
                  return (
                    <button
                      key={meal}
                      type="button"
                      className="ml-slot"
                      data-meal={meal}
                      aria-haspopup="dialog"
                      aria-label={`${head.day} ${label} ${slot.title}, ${slot.servings}인분${urgent && `, ${urgent}`}${kcalText && `, 1인분 ${kcalText}`}`}
                      onClick={() => {
                        sheetOpen.current = true;
                        setOpenSlot(slot);
                      }}
                    >
                      <span className="ml-meal">{label}</span>
                      <span className="row-main">
                        <span className="ml-title">{slot.title}</span>
                        <span className="ml-sub">
                          {slot.servings}인분
                          {urgent && (
                            <>
                              {" · "}
                              <span className="ml-use">{urgent}</span>
                            </>
                          )}
                        </span>
                      </span>
                      <span className="nt-slot-kcal">{kcalText}</span>
                    </button>
                  );
                })}
                {/* 시안 B: 빈 끼니는 카드 맨 아래 칩 한 줄 */}
                {filled < 4 && (
                  <div className="ml-add-chips">
                    {MEALS.filter(([meal]) => !slots.has(`${date}|${meal}`)).map(([meal, label]) => (
                      <button
                        key={meal}
                        type="button"
                        className="ml-add-chip"
                        aria-label={`${head.day} ${label} 채우기`}
                        aria-haspopup="dialog"
                        onClick={() => setFill({ date, meal })}
                      >
                        <Icon name="plus" size={16} />
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      {plan && (
        <div className="cta-bar">
          <button type="button" className="btn primary" onClick={() => navigate(`/meals/${plan.id}/shopping`)}>
            <Icon name="cart" size={20} />
            장보기 목록 만들기
          </button>
        </div>
      )}

      {openSlot && (
        <MealSlotSheet
          slot={openSlot}
          today={today}
          onChanged={() => {
            if (sheetOpen.current) dirty.current = true;
            else {
              setCopied("");
              void reload();
              onChanged();
            }
          }}
          onClose={() => closeSlot(openSlot)}
          onReplace={(slot) => {
            void closeSlot(slot);
            setFill({ date: slot.date, meal: slot.meal, current: slot });
          }}
        />
      )}
      {sheet === "menu" && plan && (
        <PlanMenuSheet plan={plan} onCopy={() => setSheet("copy")} onEdit={() => setSheet("edit")} onDeleted={onDeleted} onClose={() => setSheet(null)} />
      )}
      {sheet === "copy" && plan && <MealCopySheet plan={plan} week={week} onCopied={copiedWeek} onClose={() => setSheet(null)} />}
      {sheet === "edit" && plan && (
        <MealPlanSheet today={today} defaultServings={plan.default_servings} plan={plan} onSaved={edited} onClose={() => setSheet(null)} />
      )}
      {fill && plan && (
        <MealFillSheet
          plan={plan}
          date={fill.date}
          meal={fill.meal}
          current={fill.current}
          user={user}
          onSaved={saved}
          onInterrupted={() => void replacePlan()}
          onClose={() => setFill(null)}
        />
      )}
      {nutritionDate && plan && (
        <DayNutritionSheet
          date={nutritionDate}
          slots={plan.slots.filter((s) => s.date === nutritionDate)}
          goal={goal}
          onClose={() => setNutritionDate(null)}
        />
      )}
    </main>
  );
}

interface PlanMenuProps {
  plan: MealPlan;
  onCopy: () => void;
  onEdit: () => void;
  onDeleted: () => Promise<void>;
  onClose: () => void;
}

/** 시안 WeekMenu: 식단 메뉴(이번 주 복사·이름·기간 고치기·식단 지우기) */
function PlanMenuSheet({ plan, onCopy, onEdit, onDeleted, onClose }: PlanMenuProps) {
  const { busy, error, run } = useAsyncAction();
  const remove = () => {
    if (!confirm(`${withJosa(plan.name, "을", "를")} 지울까요? 채운 칸도 함께 지워져요.`)) return;
    void run(async () => {
      await api(`/api/meal-plans/${plan.id}`, { method: "DELETE" });
      forgetMealDraft(plan.id);
      await onDeleted();
    });
  };
  return (
    <Sheet title={plan.name} description={`${rangeText(plan.start_on, plan.end_on)} · 기본 ${plan.default_servings}인분`} onClose={onClose}>
      <ul className="plain-list mo-menu ml-menu">
        {(
          [
            ["clipboard", "이번 주 복사", onCopy],
            ["pencil", "식단 이름·기간 고치기", onEdit],
          ] as const
        ).map(([icon, label, onClick]) => (
          <li key={label}>
            <button type="button" className="plain-row menu-row" aria-haspopup="dialog" onClick={onClick}>
              <span className="row-title">
                <Icon name={icon} size={22} />
                {label}
              </span>
              <Icon name="chevron" size={20} />
            </button>
          </li>
        ))}
      </ul>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="button" className="btn danger-text" disabled={busy} onClick={remove}>
        {busy ? "지우는 중…" : "식단 지우기"}
      </button>
    </Sheet>
  );
}
