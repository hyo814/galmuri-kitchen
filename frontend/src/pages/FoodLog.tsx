import { useEffect, useState } from "react";
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

/** 컴포넌트 이름은 FoodLogPage — 같은 파일이 `import type { FoodLog } from "../api"`를 쓰므로 `FoodLog`로 지으면 TS2440 이름 충돌(개정 1 D9) */
export default function FoodLogPage({ user }: { user: User }) {
  void user; // 카메라 버튼(Task 10)에서 쓴다
  const [month, setMonth] = useState(() => (pendingOpen ? monthOf(pendingOpen.date) : (viewMonth ?? monthOf(localToday()))));
  const [selected, setSelected] = useState<string | null>(() => pendingOpen?.date ?? null);

  useEffect(() => {
    pendingOpen = null;
  }, []);
  useEffect(() => {
    viewMonth = month;
  }, [month]);

  const { data, error, reload } = useResource<FoodLogMonth>(`/api/food-logs/month?month=${month}`);

  const header = (
    <header className="topbar fl-top">
      <button type="button" className="icon-btn" aria-label="더보기로 돌아가기" onClick={() => goBack("/more")}>
        <Icon name="back" />
      </button>
      <h1>먹은 기록</h1>
    </header>
  );

  if (!data)
    return (
      <main className="page">
        {header}
        {error ? <LoadError error={error} onRetry={reload} /> : <p className="muted">불러오는 중…</p>}
      </main>
    );

  const today = data.today;
  const days = new Map(data.days.map((d) => [d.date, d]));
  const summary = summaryView(data.summary);
  const label = monthLabel(month);
  const [year, monthNo] = month.split("-").map(Number);

  return (
    <main className="page">
      {header}

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
            <i style={{ flex: summary.split[0] }} />
            <i style={{ flex: summary.split[1] }} />
          </div>
        )}
        <p className="muted">{summary.note}</p>
      </section>

      <div className="fl-mnav">
        <button type="button" className="icon-btn" aria-label="지난달" onClick={() => setMonth((m) => shiftMonth(m, -1))}>
          <Icon name="back" />
        </button>
        <h2 aria-live="polite">{label}</h2>
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
                  onClick={() => setSelected(date)}
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
      <p className="fl-legend">● 끼니 기록 · 사진 = 첫 사진</p>
    </main>
  );
}
