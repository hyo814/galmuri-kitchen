import { useEffect, useRef, useState, type RefObject } from "react";
import { localToday, type CookReport as CookReportData } from "../api";
import Icon from "../components/Icon";
import LoadError from "../components/LoadError";
import { aboutWon, barSavedText, barWidths, compareLine, overSpent, reportLead, reportNote, reportTitle } from "../cooklog/cook.ts";
import { monthOf, shiftMonth } from "../foodlog/log";
import { goBack } from "../useHashRoute";
import { useFocusOnRecover, useResource } from "../useResource";

// 뒤로 가기로 돌아오면 보던 달을 연다. 이번 달을 말하는 입구(더보기 줄·요리 일기 카드)는 resetCookReportView 뒤에 연다(R11-9)
let viewMonth: string | null = null;

/** 이번 달로 열기·로그아웃: 보던 달을 비운다 */
export function resetCookReportView(): void {
  viewMonth = null;
}

/** 한 달 카드 넷. `key={month}`로 달마다 새로 마운트해 늦게 온 옛 달 응답이 지금 달을 덮지 않는다(FoodLog.tsx MonthBody와 같게, R11-3) */
function ReportBody({
  month,
  onToday,
  titleRef,
}: {
  month: string;
  onToday: (today: string) => void;
  /** 다시 불러오기 성공 시 사라진 버튼 대신 이 heading으로 포커스를 옮긴다 */
  titleRef: RefObject<HTMLHeadingElement | null>;
}) {
  const { data, error, reload } = useResource<CookReportData>(`/api/cook-report?month=${month}`);
  useFocusOnRecover(titleRef, error, data);

  useEffect(() => {
    if (data) onToday(data.today);
  }, [data, onToday]);

  if (!data) return error ? <LoadError error={error} onRetry={reload} /> : <p className="center muted">불러오는 중…</p>;

  const compare = compareLine(data);
  const widths = barWidths(data.top_saved);
  const home = data.home_percent;

  return (
    <>
      <section className="nt-card ck-hero-card" aria-labelledby="ck-hero-lead">
        <span id="ck-hero-lead" className="muted">
          {reportLead(month, data.today)}
        </span>
        {data.cooked === 0 ? (
          <>
            <b className="ck-hero-empty">요리 일기가 없어요</b>
            <p className="nt-src">레시피나 식단 칸에서 ‘요리했어요’를 누르면 아낀 돈을 계산해요</p>
          </>
        ) : data.counted === 0 ? (
          <>
            <b className="ck-hero-empty">계산한 요리가 없어요</b>
            <p className="nt-src">요리 일기에 사 먹으면 얼마와 재료 가격이 있어야 계산해요</p>
          </>
        ) : (
          <>
            <span className={overSpent(data.saved_total) ? "ck-hero-big ck-warn" : "ck-hero-big"}>{aboutWon(data.saved_total)}</span>
            <span className="ck-hero-sub">{overSpent(data.saved_total) ? "더 들었어요" : "아꼈어요"}</span>
            <p className="nt-src">{reportNote(data)}</p>
          </>
        )}
      </section>

      <section className="nt-card">
        <div className="fl-stats ck-stats4">
          <div>
            <b>{data.cooked}번</b>
            <span>요리</span>
          </div>
          <div>
            <b>{data.logged_days}일</b>
            <span>기록한 날</span>
          </div>
          <div>
            <b>{home === null ? <span aria-label="계산할 수 없어요">—</span> : `${home}%`}</b>
            <span>집밥</span>
          </div>
          <div>
            <b className={data.discarded > 0 ? "ck-warn" : undefined}>{data.discarded}개</b>
            <span>버린 재료</span>
          </div>
        </div>
        {data.cooked > 0 && home === null && <p className="muted">먹은 기록이 있어야 집밥 비율을 보여줘요</p>}
        {home !== null && (
          <div className="fl-split" role="img" aria-label={`집밥 ${home}%, 외식 ${100 - home}%`}>
            {/* 0%인 쪽은 그리지 않는다(FoodLog.tsx와 같게) */}
            {home > 0 && <i className="fl-split-home" style={{ flex: home }} />}
            {home < 100 && <i className="fl-split-out" style={{ flex: 100 - home }} />}
          </div>
        )}
        {compare && <p className="muted">{compare}</p>}
      </section>

      {data.top_saved.length > 0 && (
        <section className="nt-card">
          <h2>많이 아낀 요리</h2>
          <ul className="ck-bars">
            {data.top_saved.map((row, i) => (
              <li key={row.title} className="ck-bar">
                <span>{row.title}</span>
                {/* 막대는 숨기고 보이는 제목·금액을 읽는다(BodyGoalCard와 같게) */}
                <div className="nt-meter" aria-hidden="true">
                  <i style={{ width: `${widths[i]}%` }} />
                </div>
                <span>{barSavedText(row.saved)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.discarded > 0 && (
        <section className="nt-card">
          <h2>버린 재료</h2>
          <ul className="ck-chips">
            {data.discarded_names.map((name) => (
              <li key={name} className="badge old">
                {name}
              </li>
            ))}
            {data.discarded_more > 0 && <li className="badge">외 {data.discarded_more}개</li>}
          </ul>
          <p className="muted">빨리 먹어야 할 재료는 추천에서 먼저 보여줘요</p>
        </section>
      )}
    </>
  );
}

/** 시안 5 · REPORT: 달 이동 + 아낀 돈 합계·요리·기록한 날·집밥 비율·버린 재료·지난달 대비·많이 아낀 요리(스펙 27·29절) */
export default function CookReport() {
  const [month, setMonth] = useState(() => viewMonth ?? monthOf(localToday()));
  // `다음 달` 막기용 오늘 — 받기 전엔 기기 시계, 받으면 서버 today(FoodLog.tsx와 같게)
  const [today, setToday] = useState(() => localToday());
  // 요리 일기 카드로 들어왔으면 뒤로가 요리 일기로 간다(history.back) — 들어올 때 한 번 읽어 이름을 맞춘다(R11-F2)
  const [fromDiary] = useState(() => (history.state as { from?: string } | null)?.from === "/cook-logs");
  const title = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    viewMonth = month;
  }, [month]);

  return (
    <main className="page ck-report">
      <a
        className="back-link"
        href={fromDiary ? "#/cook-logs" : "#/more"}
        aria-label={fromDiary ? "요리 일기로 돌아가기" : "더보기로 돌아가기"}
        onClick={(e) => {
          e.preventDefault();
          goBack("/more");
        }}
      >
        <Icon name="back" size={18} />
        {fromDiary ? "요리 일기" : "더보기"}
      </a>
      <div className="fl-mnav">
        <button type="button" className="icon-btn" aria-label="지난달" onClick={() => setMonth((m) => shiftMonth(m, -1))}>
          <Icon name="back" />
        </button>
        <h1 ref={title} tabIndex={-1} aria-live="polite">
          {reportTitle(month)}
        </h1>
        <button
          type="button"
          className="icon-btn"
          aria-label="다음 달"
          disabled={month >= monthOf(today)}
          onClick={() => {
            const next = shiftMonth(month, 1);
            setMonth(next);
            if (next >= monthOf(today)) title.current?.focus(); // 이번 달이면 이 버튼이 막혀 포커스가 사라지니 새 제목으로
          }}
        >
          <Icon name="chevron" />
        </button>
      </div>
      <ReportBody key={month} month={month} onToday={setToday} titleRef={title} />
    </main>
  );
}
