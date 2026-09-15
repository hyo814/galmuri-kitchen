import { useCallback, useEffect, useState, type ReactNode } from "react";
import { localToday, type FoodLogMonth, type User } from "../api";
import Icon from "../components/Icon";
import LoadError from "../components/LoadError";
import { monthGrid } from "../meals/plan";
import { cellKcalText, cellLabel, monthLabel, monthOf, shiftMonth, summaryView } from "../foodlog/log";
import { goBack } from "../useHashRoute";
import { useResource } from "../useResource";

const DOW = ["월", "화", "수", "목", "금", "토", "일"];

// 탭·화면을 오가도 보던 달을 기억한다(결정 22). pendingOpen은 다른 화면(식단 칸 상세)에서 특정 날짜·기록을 열며
// 들어올 때 쓴다 — 이 화면이 마운트되면서 한 번 읽고 비운다(Task 8이 시트를 열고 Task 9가 기록을 연다).
let viewMonth: string | null = null;
let pendingOpen: { date: string; logId?: number } | null = null;

/** 다른 화면(식단 칸 상세)에서 먹은 기록으로 올 때 열 날짜·기록. 화면이 읽고 비운다 */
export function openFoodLog(target: { date: string; logId?: number }): void {
  pendingOpen = target;
}

/** 로그아웃: 보던 달·열 대상을 비운다 */
export function resetFoodLogView(): void {
  viewMonth = null;
  pendingOpen = null;
}

/** 한 달의 요약 카드·달 이동·달력(리뷰 fix round 1, I1 / fix round 2). `key={month}`로 달마다 새로 마운트해
 * - 늦게 도착한 옛 달 응답이 지금 보는 달을 덮지 않고(마운트 해제된 인스턴스의 setData는 아무 화면에도 안 붙는다),
 * - 그 달만 불러오기에 실패해도 자리에서 `LoadError`로 다시 시도할 수 있다.
 * 시안 순서(요약 → 달 이동 → 달력)를 지키려고 달 이동(`.fl-mnav`)은 `FoodLogPage`가 만들어 `nav`로 내려주고
 * 이 컴포넌트가 그 자리에 끼워 넣는다 — 그래서 불러오는 중·오류일 때도 달 이동은 그대로 보이고 눌린다. */
function MonthBody({
  month,
  selected,
  onSelect,
  onToday,
  nav,
}: {
  month: string;
  selected: string | null;
  onSelect: (date: string) => void;
  onToday: (today: string) => void;
  nav: ReactNode;
}) {
  const { data, error, reload } = useResource<FoodLogMonth>(`/api/food-logs/month?month=${month}`);

  useEffect(() => {
    if (data) onToday(data.today);
  }, [data, onToday]);

  if (!data)
    return (
      <>
        {nav}
        {error ? <LoadError error={error} onRetry={reload} /> : <p className="muted">불러오는 중…</p>}
      </>
    );

  const today = data.today;
  const days = new Map(data.days.map((d) => [d.date, d]));
  const summary = summaryView(data.summary);
  const label = monthLabel(month);
  const [year, monthNo] = month.split("-").map(Number);

  return (
    <>
      <section className="nt-card fl-summary" aria-label={`${label} 요약`}>
        <div className="fl-stats">
          <div>
            <b>{summary.days}</b>
            <span>기록한 날</span>
          </div>
          <div>
            <b>{summary.kcal}</b>
            <span>하루 평균 kcal</span>
          </div>
          <div>
            <b>{summary.home}</b>
            <span>집밥</span>
          </div>
        </div>
        {summary.split && (
          <div className="fl-split" role="img" aria-label={`집밥 ${summary.split[0]}%, 외식 ${summary.split[1]}%`}>
            {/* 100%/0%로 갈리면 0% 쪽은 그리지 않는다 — 폭 0인 칸도 flex gap 때문에 틈이 보여서 */}
            {summary.split[0] > 0 && <i className="fl-split-home" style={{ flex: summary.split[0] }} />}
            {summary.split[1] > 0 && <i className="fl-split-out" style={{ flex: summary.split[1] }} />}
          </div>
        )}
        <p className="muted">{summary.note}</p>
      </section>

      {nav}

      <div className="fl-cal">
        <div className="fl-dow" aria-hidden="true">
          {DOW.map((d) => (
            <span key={d}>{d}</span>
          ))}
        </div>
        {monthGrid(year, monthNo).map((row) => (
          <div key={row[0]} className="fl-wk">
            {row.map((date) => {
              const dayNum = Number(date.slice(8));
              if (monthOf(date) !== month)
                return (
                  <div key={date} className="fl-cell dim" aria-hidden="true">
                    <span className="fl-d">{dayNum}</span>
                  </div>
                );
              if (date > today)
                return (
                  <div key={date} className="fl-cell">
                    <span className="fl-d">{dayNum}</span>
                  </div>
                );
              const day = days.get(date);
              const isSel = date === selected;
              return (
                <button
                  key={date}
                  type="button"
                  className={["fl-cell", date === today && "today", isSel && "sel"].filter(Boolean).join(" ")}
                  aria-label={cellLabel(date, day, today)}
                  aria-pressed={isSel}
                  onClick={() => onSelect(date)}
                >
                  <span className="fl-d">{dayNum}</span>
                  {day?.photo_url ? (
                    <img className="fl-th" src={day.photo_url} alt="" loading="lazy" decoding="async" />
                  ) : (
                    <span className="fl-dots">
                      {Array.from({ length: day?.meals ?? 0 }, (_, i) => (
                        <i key={i} />
                      ))}
                    </span>
                  )}
                  <span className="fl-kc">{cellKcalText(day)}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <p className="fl-legend">
        <span aria-hidden="true">●</span> 끼니 기록 · 사진 = 첫 사진
      </p>
    </>
  );
}

/** 컴포넌트 이름은 FoodLogPage — 같은 파일이 `import type { FoodLog } from "../api"`를 쓰므로 `FoodLog`로 지으면 TS2440 이름 충돌(개정 1 D9) */
export default function FoodLogPage({ user }: { user: User }) {
  void user; // 카메라 버튼(Task 10)에서 쓴다
  const [month, setMonth] = useState(() => (pendingOpen ? monthOf(pendingOpen.date) : (viewMonth ?? monthOf(localToday()))));
  const [selected, setSelected] = useState<string | null>(() => pendingOpen?.date ?? null);
  // 서버 today(개정 1 P14) — 받기 전엔 기기 시계로 `다음 달` 막기를 어림하고, 어느 달이든 한 번 받으면 그 값으로 굳힌다
  const [today, setToday] = useState(() => localToday());

  useEffect(() => {
    pendingOpen = null;
  }, []);
  useEffect(() => {
    viewMonth = month;
  }, [month]);

  const onToday = useCallback((t: string) => setToday(t), []);

  // `MonthBody`가 요약과 달력 사이에 그대로 끼워 넣는다(시안 순서 유지) — 그래서 그 달이 불러오는 중·오류여도 이건 산다
  const nav = (
    <div className="fl-mnav">
      <button type="button" className="icon-btn" aria-label="지난달" onClick={() => setMonth((m) => shiftMonth(m, -1))}>
        <Icon name="back" />
      </button>
      <h2 aria-live="polite">{monthLabel(month)}</h2>
      <button
        type="button"
        className="icon-btn"
        aria-label="다음 달"
        disabled={month >= monthOf(today)}
        onClick={() => setMonth((m) => shiftMonth(m, 1))}
      >
        <Icon name="chevron" />
      </button>
    </div>
  );

  return (
    <main className="page">
      <header className="topbar fl-top">
        <button type="button" className="icon-btn" aria-label="더보기로 돌아가기" onClick={() => goBack("/more")}>
          <Icon name="back" />
        </button>
        <h1>먹은 기록</h1>
      </header>

      <MonthBody key={month} month={month} selected={selected} onSelect={setSelected} onToday={onToday} nav={nav} />
    </main>
  );
}
