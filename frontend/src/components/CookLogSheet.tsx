import { Fragment, useId, useState } from "react";
import { api, type CookLogDetail, type User } from "../api";
import { aboutWon, costLine, eatOutLine, excludedNote, savedText } from "../cooklog/cook.ts";
import { starsText } from "../foodlog/log.ts";
import { formatWon } from "../format.ts";
import { slotDateText } from "../meals/plan.ts";
import { useAsyncAction } from "../useAsyncAction";
import { useResource } from "../useResource";
import { forgetCookCaches } from "./CookSheet";
import CookEditSheet from "./CookEditSheet";
import Icon from "./Icon";
import LoadError from "./LoadError";
import Sheet from "./Sheet";

interface Props {
  id: number;
  today: string;
  user: User;
  /** 고치기·지우기 뒤 목록·이번 달 카드를 다시 받는다 */
  onChanged: () => void;
  onClose: () => void;
}

/** 시안 4 · DETAIL: 사진·별점·메모와 아낀 돈 계산표(결정 13~15), 고치기·일기 지우기(결정 17·18) */
export default function CookLogSheet({ id, today, user, onChanged, onClose }: Props) {
  const detail = useResource<CookLogDetail>(`/api/cook-logs/${id}`);
  const [editing, setEditing] = useState(false);
  const remove = useAsyncAction();
  const uid = useId();
  const log = detail.data;

  function removeLog() {
    if (!confirm("이 일기를 지울까요? 재고는 되돌리지 않아요.")) return;
    void remove.run(async () => {
      await api(`/api/cook-logs/${id}`, { method: "DELETE" });
      forgetCookCaches();
      onChanged();
      onClose();
    });
  }

  if (!log) {
    return (
      <>
        <Sheet title="요리 일기" onClose={onClose}>
          {detail.status === 404 ? (
            <p className="muted">지운 일기예요</p>
          ) : detail.error ? (
            <LoadError error={detail.error} onRetry={detail.reload} />
          ) : (
            <p className="muted" role="status">
              불러오는 중…
            </p>
          )}
        </Sheet>
      </>
    );
  }

  const priced = log.items.some((i) => i.cost !== null);
  // 계산표 합계 줄(R10-10): 음수는 위 큰 글자와 같은 `더 들었어요`, 계산 못 했으면 무엇이 모자란지
  const total =
    log.saved !== null
      ? log.saved < 0
        ? savedText(log.saved)
        : `아낀 돈 ${aboutWon(log.saved)}`
      : priced
        ? "사 먹으면 얼마를 넣으면 계산해요"
        : "재료 가격을 몰라 계산하지 못했어요";

  return (
    <>
      <Sheet title={log.title} description={`${slotDateText(log.cooked_on, "")} · ${log.servings}인분`} locked={remove.busy} onClose={onClose}>
        {log.rating !== null && (
          <p className="ck-sd">
            <span className="fl-stars" role="img" aria-label={`별점 ${log.rating}점`}>
              {starsText(log.rating)}
            </span>
          </p>
        )}
        {log.photo_url && <img className="ck-hero" src={log.photo_url} alt={`${log.title} 사진`} />}
        {log.memo && <p className="ck-memo-text">{log.memo}</p>}

        <section className="nt-card field-bg ck-calc" aria-labelledby={`${uid}-calc`}>
          <div className="ck-sum">
            <span id={`${uid}-calc`} className="muted">
              아낀 돈
            </span>
            {log.saved === null ? (
              <span className="ck-big ck-none">계산하지 못했어요</span>
            ) : (
              <span className={log.saved < 0 ? "ck-big ck-over" : "ck-big"}>{aboutWon(log.saved)}</span>
            )}
            {log.saved !== null && log.saved < 0 && <span>더 들었어요</span>}
          </div>
          <dl className="ck-table">
            {log.eat_out_price !== null && (
              <>
                <dt>
                  {eatOutLine(log.eat_out_price, log.servings)}
                  {(log.eat_out_source === "ai" || log.eat_out_source === "sample") && (
                    <>
                      {" "}
                      <span className="badge">추정</span>
                    </>
                  )}
                </dt>
                <dd>{formatWon(log.eat_out_price * log.servings)}</dd>
              </>
            )}
            {log.items.map(
              (item, i) =>
                item.cost !== null && (
                  <Fragment key={i}>
                    <dt>{costLine(item)}</dt>
                    <dd>− {formatWon(item.cost)}</dd>
                  </Fragment>
                ),
            )}
            {/* 재료비는 저장값 그대로 — 바로 위 줄 값의 합과 같게(R10-14) */}
            <dt className="ck-tot">재료비 {formatWon(log.ingredient_cost)}</dt>
            <dd className="ck-tot">{total}</dd>
          </dl>
          <p className="nt-src">{excludedNote(log.items)}</p>
        </section>

        {remove.error && (
          <p className="error" role="alert">
            {remove.error}
          </p>
        )}
        <div className="actions actions-even">
          <button type="button" className="btn secondary" disabled={remove.busy} aria-haspopup="dialog" onClick={() => setEditing(true)}>
            <Icon name="pencil" size={18} />
            고치기
          </button>
          <button type="button" className="btn danger-text" disabled={remove.busy} onClick={removeLog}>
            일기 지우기
          </button>
        </div>
        <p className="nt-src">일기를 지워도 재고는 되돌리지 않아요.</p>
      </Sheet>
      {/* 상세 시트 안이 아니라 옆에 둔다: 안쪽 dialog의 close가 바깥 시트 onClose까지 올라가지 않게(R10-8) */}
      {editing && (
        <CookEditSheet
          log={log}
          today={today}
          photos={user.photos}
          onSaved={(next) => {
            detail.set(next);
            setEditing(false);
            onChanged();
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  );
}
