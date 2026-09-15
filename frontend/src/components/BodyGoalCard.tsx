import { useState } from "react";
import type { BodyProfileResponse } from "../api";
import { dailyTarget, goalLabel, kcalNumber } from "../nutrition/body";
import { useResource } from "../useResource";
import BodyGoalSheet from "./BodyGoalSheet";

export interface TodayTotal {
  text: string;
  percent: number;
  over: boolean;
}

/** 시안 BODY CARD EMPTY / WEEK WITH KCAL: 식단 탭 맨 위 하루 칼로리 목표 카드 + 시트 */
export default function BodyGoalCard({ today, todayTotal }: { today: string; todayTotal?: TodayTotal | null }) {
  const { data, reload } = useResource<BodyProfileResponse>("/api/body-profile");
  const [open, setOpen] = useState(false);

  if (!data) return null; // 아직 못 받았거나 오류면 아무것도 그리지 않는다(자리 튐 없음)
  const profile = data.profile;

  return (
    <>
      <section className="nt-card">
        {profile ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className="muted">하루 목표 · {goalLabel(profile.goal)}</span>
              <br />
              <span className="nt-big">{kcalNumber(dailyTarget(profile, today).target)}</span>
              <span className="muted"> kcal</span>
            </span>
            <button type="button" className="nt-link" aria-label="하루 칼로리 목표 고치기" aria-haspopup="dialog" onClick={() => setOpen(true)}>
              고치기
            </button>
          </div>
        ) : (
          <div>
            <b style={{ fontSize: 16 }}>하루에 얼마나 먹으면 될까요?</b>
            <br />
            <span className="muted">키·몸무게·활동량을 넣으면 하루 필요 칼로리와 목표를 알려줘요</span>
          </div>
        )}
        {profile && todayTotal && (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="muted" style={{ whiteSpace: "nowrap" }}>
              오늘 식단
            </span>
            <span className="rc-bar" style={{ flex: 1, height: 8 }} aria-hidden="true">
              <i style={{ width: `${Math.min(todayTotal.percent, 100)}%`, background: todayTotal.over ? "var(--warn)" : undefined }} />
            </span>
            <span style={{ fontSize: 14, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{todayTotal.text}</span>
          </div>
        )}
        {!profile && (
          <button type="button" className="btn secondary" aria-haspopup="dialog" onClick={() => setOpen(true)}>
            목표 정하기
          </button>
        )}
      </section>
      {open && (
        <BodyGoalSheet
          today={today}
          profile={profile}
          onClose={() => {
            setOpen(false);
            void reload();
          }}
        />
      )}
    </>
  );
}
