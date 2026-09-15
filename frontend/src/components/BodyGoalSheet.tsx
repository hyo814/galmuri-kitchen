import { useId, useRef, useState, type FormEvent } from "react";
import { api, type Activity, type BodyGoal, type BodyProfile, type BodyProfileResponse, type Sex } from "../api";
import { ACTIVITIES, GOALS, SEXES, ageOf, dailyTarget, goalLabel, kcalNumber, parseProfileInput, targetNote } from "../nutrition/body";
import { useAsyncAction } from "../useAsyncAction";
import { cache } from "../useResource";
import Sheet from "./Sheet";

interface Props {
  today: string;
  profile: BodyProfile | null;
  onClose: () => void;
}

/** 시안 BODY SHEET: 하루 칼로리 목표 정하기(성별·태어난 해·키·몸무게·활동량·목표) — 더보기에서도 그대로 쓴다 */
export default function BodyGoalSheet({ today, profile, onClose }: Props) {
  const [sex, setSex] = useState<Sex | null>(profile?.sex ?? null);
  const [birthYear, setBirthYear] = useState(profile ? String(profile.birth_year) : "");
  const [height, setHeight] = useState(profile ? String(profile.height_cm) : "");
  const [weight, setWeight] = useState(profile ? String(profile.weight_kg) : "");
  const [activity, setActivity] = useState<Activity | null>(profile?.activity ?? null);
  const [goal, setGoal] = useState<BodyGoal>(profile?.goal ?? "maintain");
  const { busy, error, run } = useAsyncAction();

  const sexRef = useRef<HTMLDivElement>(null);
  const birthRef = useRef<HTMLInputElement>(null);
  const heightRef = useRef<HTMLInputElement>(null);
  const weightRef = useRef<HTMLInputElement>(null);
  const activityRef = useRef<HTMLDivElement>(null);

  const birthErrId = useId();
  const heightErrId = useId();
  const weightErrId = useId();

  const { value, errors } = parseProfileInput({ sex, birthYear, height, weight, activity, goal }, today);
  const target = value ? dailyTarget(value, today) : null;
  const ageSuffix = birthYear.trim() !== "" && !errors.birthYear ? `${ageOf(Number(birthYear), today)}세` : "";

  const focusFirstEmpty = () => {
    if (!sex) return sexRef.current?.querySelector<HTMLElement>("button")?.focus();
    if (!birthYear.trim() || errors.birthYear) return birthRef.current?.focus();
    if (!height.trim() || errors.height) return heightRef.current?.focus();
    if (!weight.trim() || errors.weight) return weightRef.current?.focus();
    if (!activity) return activityRef.current?.querySelector<HTMLElement>("button")?.focus();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!value) return focusFirstEmpty();
    run(async () => {
      const res = await api<BodyProfileResponse>("/api/body-profile", { method: "PUT", body: value });
      cache.set("/api/body-profile", res);
      onClose();
    });
  };

  const remove = () => {
    if (!confirm("입력한 정보를 지울까요? 하루 칼로리 목표도 함께 사라져요.")) return;
    run(async () => {
      await api("/api/body-profile", { method: "DELETE" });
      cache.set("/api/body-profile", { profile: null });
      onClose();
    });
  };

  return (
    <Sheet title="하루 칼로리 목표 정하기" description="나만 볼 수 있고 언제든 지울 수 있어요" focusTitle onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <div className="nt-grid2">
          <div className="field">
            <span className="field-label">성별</span>
            <div ref={sexRef} className="segmented" role="group" aria-label="성별" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              {SEXES.map(([sexValue, label]) => (
                <button key={sexValue} type="button" aria-pressed={sex === sexValue} onClick={() => setSex(sexValue)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <label className="field">
            <span className="field-label">태어난 해</span>
            <div className="input-suffix">
              <input
                ref={birthRef}
                className="input"
                inputMode="numeric"
                maxLength={4}
                value={birthYear}
                aria-invalid={!!errors.birthYear}
                aria-describedby={errors.birthYear ? birthErrId : undefined}
                onChange={(e) => setBirthYear(e.target.value.replace(/\D/g, "").slice(0, 4))}
              />
              <span className="suffix" aria-hidden="true">
                {ageSuffix}
              </span>
            </div>
            {errors.birthYear && (
              <p className="hint nt-invalid" id={birthErrId}>
                {errors.birthYear}
              </p>
            )}
          </label>
          <label className="field">
            <span className="field-label">키</span>
            <div className="input-suffix">
              <input
                ref={heightRef}
                className="input"
                inputMode="decimal"
                value={height}
                aria-invalid={!!errors.height}
                aria-describedby={errors.height ? heightErrId : undefined}
                onChange={(e) => setHeight(e.target.value.replace(/[^0-9.,]/g, ""))}
              />
              <span className="suffix" aria-hidden="true">
                cm
              </span>
            </div>
            {errors.height && (
              <p className="hint nt-invalid" id={heightErrId}>
                {errors.height}
              </p>
            )}
          </label>
          <label className="field">
            <span className="field-label">몸무게</span>
            <div className="input-suffix">
              <input
                ref={weightRef}
                className="input"
                inputMode="decimal"
                value={weight}
                aria-invalid={!!errors.weight}
                aria-describedby={errors.weight ? weightErrId : undefined}
                onChange={(e) => setWeight(e.target.value.replace(/[^0-9.,]/g, ""))}
              />
              <span className="suffix" aria-hidden="true">
                kg
              </span>
            </div>
            {errors.weight && (
              <p className="hint nt-invalid" id={weightErrId}>
                {errors.weight}
              </p>
            )}
          </label>
        </div>

        <div className="field" role="group" aria-label="활동량">
          <span className="field-label">활동량</span>
          <div ref={activityRef} className="choices">
            {ACTIVITIES.map((a) => (
              <button key={a.value} type="button" className="choice" aria-pressed={activity === a.value} onClick={() => setActivity(a.value)}>
                {a.label}
              </button>
            ))}
          </div>
          <p className="hint">{activity ? ACTIVITIES.find((a) => a.value === activity)!.hint : ""}</p>
        </div>

        <div className="field" role="group" aria-label="목표">
          <span className="field-label">목표</span>
          <div className="choices">
            {GOALS.map(([goalValue, label]) => (
              <button key={goalValue} type="button" className="choice" aria-pressed={goal === goalValue} onClick={() => setGoal(goalValue)}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="nt-card field-bg">
          {value && target ? (
            <>
              <div className="nt-kv">
                <span>기초대사량</span>
                <b>{kcalNumber(target.bmr)}kcal</b>
                <span>하루 필요량</span>
                <b>{kcalNumber(target.tdee)}kcal</b>
                <span>{goalLabel(goal)} 목표</span>
                <b style={{ color: "var(--accent-strong)" }}>{kcalNumber(target.target)}kcal</b>
              </div>
              <p className="nt-src">{targetNote(target, goal)}</p>
            </>
          ) : (
            <p className="muted">정보를 모두 넣으면 계산해 보여줘요</p>
          )}
        </div>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="ml-stack">
          <button type="submit" className="btn primary" disabled={busy} aria-disabled={!value || undefined}>
            {busy ? "저장하는 중…" : "저장"}
          </button>
          {profile && (
            <button type="button" className="btn danger-text" disabled={busy} onClick={remove}>
              입력한 정보 지우기
            </button>
          )}
        </div>
      </form>
    </Sheet>
  );
}
