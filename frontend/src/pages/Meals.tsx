import { useEffect, useRef, useState } from "react";
import { localToday, type MealPlan, type MealPlanList, type MealPlanSummary, type MealSlot, type User } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import MealPickerSheet from "../components/MealPickerSheet";
import MealPlanSheet from "../components/MealPlanSheet";
import MealSlotSheet from "../components/MealSlotSheet";
import { dayHead, initialWeek, MEALS, pickPlan, rangeText, slotDateText, weekDates, weekStarts } from "../meals/plan";
import { cache, forgetResources, useResource } from "../useResource";
import { urgentLabel } from "./Recipes";

// 탭을 오가도 보던 식단·보기·주를 기억한다(로그아웃 때 resetMealsView)
let lastPlanId: number | null = null;
let lastView: "week" | "month" = "week";
let lastWeek: Record<number, string> = {};

export function resetMealsView() {
  lastPlanId = null;
  lastView = "week";
  lastWeek = {};
}

/** 식단별로 보고 있던 주 시작일(AI 초안 화면이 이 주를 채운다) */
export function currentWeekOf(planId: number): string | undefined {
  return lastWeek[planId];
}

function LoadError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="list-end">
      <p className="error" role="alert">
        {error}
      </p>
      <button type="button" className="btn secondary inline" onClick={onRetry}>
        <Icon name="refresh" size={16} />
        다시 불러오기
      </button>
    </div>
  );
}

// user: AI 초안 버튼(scan off면 숨김)을 켜는 Task 8에서 쓴다
export default function Meals(_: { user: User }) {
  const today = localToday();
  const list = useResource<MealPlanList>("/api/meal-plans");
  const [planId, setPlanId] = useState(lastPlanId);
  const [sheet, setSheet] = useState<"create" | "pick" | null>(null);

  const choose = (id: number) => {
    lastPlanId = id;
    setPlanId(id);
  };
  const created = async (plan: MealPlan) => {
    forgetResources("/api/meal-plans");
    cache.set(`/api/meal-plans/${plan.id}`, plan); // 새 식단은 받은 그대로 바로 보여준다
    await list.reload(); // 목록에 새 식단이 들어온 뒤에 바꿔야 이전 식단이 잠깐 보이지 않는다
    choose(plan.id);
    setSheet(null);
  };

  const items = list.data?.items;
  // 기억한 식단이 목록에 없으면(지워짐) 오늘이 든 식단부터
  const current = items && (items.find((p) => p.id === planId) ?? pickPlan(items, today));

  const createSheet = sheet === "create" && list.data && (
    <MealPlanSheet today={today} defaultServings={list.data.default_servings} onCreated={created} onClose={() => setSheet(null)} />
  );

  if (!items || !current)
    return (
      <main className="page">
        <header className="topbar">
          <h1>식단</h1>
        </header>
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
            <div className="ml-stack" style={{ marginTop: 24 }}>
              <button type="button" className="btn primary" onClick={() => setSheet("create")}>
                <Icon name="plus" />
                식단 만들기
              </button>
            </div>
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
        onPick={() => setSheet("pick")}
        onChanged={list.reload}
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

interface PlanWeekProps {
  summary: MealPlanSummary;
  today: string;
  onPick: () => void;
  /** 칸을 바꿨다: 목록(식단 고르기의 채운 칸 수)도 다시 받는다 */
  onChanged: () => void;
}

/** 시안 WeekView: 머리·식단 고르기·주 이동·하루 카드 */
function PlanWeek({ summary, today, onPick, onChanged }: PlanWeekProps) {
  const { data: plan, error, reload } = useResource<MealPlan>(`/api/meal-plans/${summary.id}`);
  const shown = plan ?? summary;
  const weeks = weekStarts(shown);
  const [picked, setPicked] = useState(() => lastWeek[summary.id]);
  const week = picked && weeks.includes(picked) ? picked : initialWeek(shown, today);
  const index = weeks.indexOf(week);
  const [openSlot, setOpenSlot] = useState<MealSlot | null>(null);
  /** 시트가 열려 있는 동안 바뀐 칸은 닫을 때 한 번에 다시 받는다. 닫은 뒤 늦게 끝난 저장은 바로 다시 받는다 */
  const dirty = useRef(false);
  const sheetOpen = useRef(false);

  useEffect(() => {
    lastWeek[summary.id] = week;
  }, [summary.id, week]);

  const move = (step: number) => setPicked(weeks[index + step]);
  const dates = weekDates(week, shown);
  const slots = new Map((plan?.slots ?? []).map((s) => [`${s.date}|${s.meal}`, s]));

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <h1>식단</h1>
          <p className="summary">
            {shown.total}칸 중 {shown.filled}칸 채웠어요
          </p>
        </div>
      </header>
      <div className="ml-row2">
        <button type="button" className="ml-plan" aria-haspopup="dialog" onClick={onPick}>
          <span>{shown.name}</span>
          <Icon name="down" size={18} />
        </button>
      </div>
      <div className="ml-nav">
        <button type="button" className="icon-btn" aria-label="이전 주" disabled={index <= 0} onClick={() => move(-1)}>
          <Icon name="back" size={22} />
        </button>
        <b aria-live="polite">{rangeText(dates[0], dates[dates.length - 1])}</b>
        <button type="button" className="icon-btn" aria-label="다음 주" disabled={index >= weeks.length - 1} onClick={() => move(1)}>
          <Icon name="chevron" size={22} />
        </button>
      </div>

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
      ) : (
        <div className="ml-days">
          {dates.map((date) => {
            const head = dayHead(date);
            const filled = MEALS.filter(([meal]) => slots.has(`${date}|${meal}`)).length;
            return (
              <section key={date} className={date === today ? "ml-day today" : "ml-day"} data-date={date} aria-label={slotDateText(date, today)}>
                <div className="ml-day-head">
                  <span className="ml-date">{head.day}</span>
                  <span className="ml-dow">{head.dow}</span>
                  {date === today && <span className="badge info">오늘</span>}
                  <span className="ml-count">{filled} / 4</span>
                </div>
                {MEALS.map(([meal, label]) => {
                  const slot = slots.get(`${date}|${meal}`);
                  if (!slot)
                    return (
                      <div key={meal} className="ml-slot">
                        <span className="ml-meal">{label}</span>
                        {/* 채우기 시트는 Task 6 */}
                        <button type="button" className="ml-plus" aria-label={`${head.day} ${label} 채우기`} disabled>
                          <Icon name="plus" />
                        </button>
                      </div>
                    );
                  const urgent = slot.recipe_id !== null ? urgentLabel(slot.urgent_names) : "";
                  return (
                    <button key={meal} type="button" className="ml-slot" aria-haspopup="dialog" onClick={() => {
                        sheetOpen.current = true;
                        setOpenSlot(slot);
                      }}>
                      <span className="ml-meal">{label}</span>
                      <span className="row-main">
                        <span className="ml-title">{slot.title}</span>
                        {urgent && (
                          <span className="sh-meta">
                            <span className="sh-tag warn">{urgent}</span>
                          </span>
                        )}
                      </span>
                      <span className="ml-serv">{slot.servings}인분</span>
                    </button>
                  );
                })}
              </section>
            );
          })}
        </div>
      )}

      {openSlot && (
        <MealSlotSheet
          slot={openSlot}
          today={today}
          onChanged={() => {
            if (sheetOpen.current) dirty.current = true;
            else {
              void reload();
              onChanged();
            }
          }}
          onClose={async () => {
            sheetOpen.current = false;
            setOpenSlot(null);
            if (!dirty.current) return;
            dirty.current = false;
            onChanged();
            await reload();
            // 칸을 비우면 시트를 연 줄 버튼이 사라져 포커스를 잃는다 → 그날 카드로 옮긴다
            setTimeout(() => {
              if (document.activeElement !== document.body) return;
              const day = document.querySelector<HTMLElement>(`.ml-day[data-date="${openSlot.date}"]`);
              if (!day) return;
              day.tabIndex = -1;
              day.focus();
            });
          }}
        />
      )}
    </main>
  );
}
