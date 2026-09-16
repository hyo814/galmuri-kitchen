import { useCallback, useEffect, useRef, useState } from "react";
import { api, localToday, type CookLogDetail, type CookLogListItem, type CookLogPage, type CookReport, type User } from "../api";
import CookLogSheet from "../components/CookLogSheet";
import Icon from "../components/Icon";
import InfiniteSentinel from "../components/InfiniteSentinel";
import { diaryDateText, diaryHeader, firstLine, savedRowText } from "../cooklog/cook.ts";
import { monthOf, starsText } from "../foodlog/log";
import { goBack, navigate } from "../useHashRoute";
import { useInfiniteList } from "../useInfiniteList";
import { useResource } from "../useResource";
import { resetCookReportView } from "./CookReport";

// 다른 화면(먹은 기록 날짜 상세, Task 13)에서 특정 일기를 열며 들어올 때 쓴다 — 이 화면이 마운트되면서 한 번 읽고 비운다
let pendingOpen: number | null = null;

/** 다른 화면(먹은 기록 날짜 상세)에서 올 때 열 일기. 화면이 읽고 비운다 */
export function openCookLog(id: number): void {
  pendingOpen = id;
}

/** 로그아웃: 열 대상을 비운다 */
export function resetCookDiaryView(): void {
  pendingOpen = null;
}

/** 시안 3 · DIARY: 이번 달 카드 + 날짜 역순 무한 스크롤(결정 20). 누르면 상세 시트(시안 4) */
export default function CookDiary({ user }: { user: User }) {
  const today = localToday();
  const report = useResource<CookReport>(`/api/cook-report?month=${monthOf(today)}`);
  const { items, loading, error, hasMore, multiPage, loadMore, reload, patch } = useInfiniteList<CookLogListItem>(
    (cursor) =>
      api<CookLogPage>(`/api/cook-logs?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`).then((p) => ({ items: p.items, next: p.next_cursor })),
    ["cook-logs"],
  );
  const [openId, setOpenId] = useState(() => pendingOpen);
  const heading = useRef<HTMLHeadingElement>(null);
  // 먹은 기록 날짜 상세 `보기`로 들어왔으면 뒤로가 먹은 기록으로 간다(history.back) — 들어올 때 한 번 읽어 이름을 맞춘다(CookReport와 같게)
  const [fromFoodLog] = useState(() => (history.state as { from?: string } | null)?.from === "/food-log");

  useEffect(() => {
    pendingOpen = null;
  }, []);

  // 상세를 닫을 때 포커스 갈 곳: undefined면 Sheet가 여는 줄로 돌려준다, id면 그 줄, null이면 제목
  const focusOnClose = useRef<number | null | undefined>(undefined);

  // 고치기(새 일기)·지우기(지운 id) 뒤: 받아 둔 줄만 고쳐 보던 자리·포커스를 지킨다(R10-F3)
  const onChanged = useCallback(
    (change: CookLogDetail | number) => {
      void report.reload();
      if (typeof change === "number") {
        const i = items.findIndex((log) => log.id === change);
        // 지우기 전에 옆 줄을 기억한다 — 받아 둔 목록에 없는 일기(다른 화면에서 연 것)면 제목으로
        focusOnClose.current = i === -1 ? null : ((items[i + 1] ?? items[i - 1])?.id ?? null);
        patch((logs) => logs.filter((log) => log.id !== change));
        return;
      }
      if (items.find((log) => log.id === change.id)?.cooked_on === change.cooked_on) {
        focusOnClose.current = change.id; // 앞서 날짜를 바꿔 다시 받았으면 여는 줄이 새 버튼이라 직접 돌린다
        patch((logs) => logs.map((log) => (log.id === change.id ? change : log)));
        return;
      }
      // ponytail: 날짜가 바뀌면 줄 자리가 달라져(받아 둔 페이지 밖으로 갈 수도) 처음부터 다시 받는다 — 옛 줄은 사라지므로 제목으로
      focusOnClose.current = null;
      reload();
    },
    [items, patch, reload, report.reload],
  );

  const closeSheet = () => {
    const target = focusOnClose.current;
    focusOnClose.current = undefined;
    setOpenId(null);
    requestAnimationFrame(() => {
      if (target === undefined && document.activeElement !== document.body) return; // Sheet가 여는 줄로 돌려놨다
      const row = target ? document.querySelector<HTMLElement>(`[data-cook-log="${target}"]`) : null;
      if (row) row.focus();
      else heading.current?.focus({ preventScroll: true });
    });
  };

  return (
    <main className="page">
      <header className="topbar fl-top">
        <button type="button" className="icon-btn" aria-label={fromFoodLog ? "먹은 기록으로 돌아가기" : "더보기로 돌아가기"} onClick={() => goBack("/more")}>
          <Icon name="back" />
        </button>
        <h1 ref={heading} tabIndex={-1}>
          요리 일기
        </h1>
      </header>

      {/* 받기 전에도 늘 그린다 — 뒤늦게 끼어들며 목록을 밀지 않게, 이번 달 0번이어도 리포트로 가게(R11-5) */}
      <button
        type="button"
        className="nt-card ck-month"
        onClick={() => {
          resetCookReportView(); // 카드가 이번 달이라 이번 달로 연다(R11-9)
          navigate("/cook-report");
        }}
      >
        <span>
          <b>{report.data ? diaryHeader(report.data) : "\u00a0"}</b>
          <br />
          <span className="muted">집밥 리포트 보기</span>
        </span>
        <Icon name="chevron" />
      </button>

      {items.length > 0 && (
        <ul className="nt-card ck-list">
          {items.map((log) => {
            const saved = savedRowText(log);
            const memo = firstLine(log.memo);
            return (
              <li key={log.id}>
                {/* aria-label 없이 내용이 이름(별점·아낀 돈·메모까지 읽힌다, R10-9) */}
                <button type="button" className="ck-diary" data-cook-log={log.id} aria-haspopup="dialog" onClick={() => setOpenId(log.id)}>
                  {log.photo_url ? (
                    <img className="ck-ph" src={log.photo_url} alt="" loading="lazy" decoding="async" />
                  ) : (
                    <span className="ck-noph">
                      <Icon name="pan" />
                    </span>
                  )}
                  <span>
                    <b>{log.title}</b>
                    {log.rating !== null && (
                      <>
                        {" "}
                        <span className="fl-stars" role="img" aria-label={`별점 ${log.rating}점`}>
                          {starsText(log.rating)}
                        </span>
                      </>
                    )}
                    <small>
                      {diaryDateText(log)} · <span className={saved.good ? "ck-save" : undefined}>{saved.text}</span>
                    </small>
                    {memo && <small className="ck-memo-line">{memo}</small>}
                  </span>
                  <span className="sr-only"> 일기 보기</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {!loading && !hasMore && items.length === 0 ? (
        <div className="empty">
          <p>아직 요리 일기가 없어요</p>
          <p className="hint">레시피 상세의 요리했어요로 남겨요</p>
        </div>
      ) : (
        <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} multiPage={multiPage} loading={loading} error={error} onRetry={loadMore} />
      )}

      {openId !== null && <CookLogSheet id={openId} today={today} user={user} onChanged={onChanged} onClose={closeSheet} />}
    </main>
  );
}
