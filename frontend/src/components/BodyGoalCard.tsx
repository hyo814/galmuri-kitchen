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

/** 저장·삭제 뒤 열던 버튼(목표 정하기 ↔ 고치기)이 다른 자리로 바뀌어 시트의 자동 포커스 복원이 못 찾을 때 새 버튼으로 옮긴다 */
function focusAfterClose(selector: string) {
  setTimeout(() => {
    if (document.activeElement !== document.body) return; // 복원이 이미 됐으면 그대로 둔다
    document.querySelector<HTMLElement>(selector)?.focus();
  });
}

interface Props {
  today: string;
  todayTotal?: TodayTotal | null;
  /** 몸 정보를 저장·삭제했다: 이 화면 말고 몸 정보를 따로 불러 쓰는 곳(주 보기 목표 막대)도 다시 받게 알린다 */
  onProfileChanged?: () => void;
}

/** 시안 BODY CARD EMPTY / WEEK WITH KCAL: 식단 탭 맨 위 하루 칼로리 목표 카드 + 시트 */
export default function BodyGoalCard({ today, todayTotal, onProfileChanged }: Props) {
  const { data, set } = useResource<BodyProfileResponse>("/api/body-profile");
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
            <div className={todayTotal.over ? "nt-meter grow warn" : "nt-meter grow"} style={{ height: 10 }} aria-hidden="true">
              <i style={{ width: `${Math.min(todayTotal.percent, 100)}%` }} />
            </div>
            <span className="nt-num">{todayTotal.text}</span>
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
          onSaved={(res) => {
            set(res);
            onProfileChanged?.();
            setOpen(false);
            // 없음 → 있음으로 바뀌면 열었던 "목표 정하기" 버튼이 사라져 포커스를 잃는다 → 새로 생긴 "고치기"로
            if (!profile) focusAfterClose('[aria-label="하루 칼로리 목표 고치기"]');
          }}
          onDeleted={() => {
            set({ profile: null });
            onProfileChanged?.();
            setOpen(false);
            // 있음 → 없음으로 바뀌면 열었던 "고치기" 버튼이 사라져 포커스를 잃는다 → 새로 생긴 "목표 정하기"로
            focusAfterClose(".nt-card .btn.secondary");
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
