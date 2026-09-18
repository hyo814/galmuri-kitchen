import { useId, useRef, useState, type FormEvent } from "react";
import { api, type Activity, type BodyGoal, type BodyProfile, type BodyProfileResponse, type Sex } from "../api";
import { ACTIVITIES, GOALS, SEXES, ageOf, dailyTarget, goalLabel, kcalNumber, parseProfileInput, targetNote } from "../nutrition/body";
import { useAsyncAction } from "../useAsyncAction";
import Sheet from "./Sheet";

interface Props {
  today: string;
  profile: BodyProfile | null;
  /** PUT 성공: 응답을 그대로 넘긴다(호출한 쪽이 다시 받지 않고 바로 반영) */
  onSaved: (res: BodyProfileResponse) => void;
  /** DELETE 성공 */
  onDeleted: () => void;
  /** 취소(Esc·배경 탭·저장/삭제 없이 닫기) */
  onClose: () => void;
}

type NumberField = "birthYear" | "height" | "weight";

/** 시안 BODY SHEET: 하루 칼로리 목표 정하기(성별·태어난 해·키·몸무게·활동량·목표) — 더보기에서도 그대로 쓴다 */
export default function BodyGoalSheet({ today, profile, onSaved, onDeleted, onClose }: Props) {
  const [sex, setSex] = useState<Sex | null>(profile?.sex ?? null);
  const [birthYear, setBirthYear] = useState(profile ? String(profile.birth_year) : "");
  const [height, setHeight] = useState(profile ? String(profile.height_cm) : "");
  const [weight, setWeight] = useState(profile ? String(profile.weight_kg) : "");
  const [activity, setActivity] = useState<Activity | null>(profile?.activity ?? null);
  const [goal, setGoal] = useState<BodyGoal>(profile?.goal ?? "maintain");
  const { busy, error, run } = useAsyncAction();

  // 건강 관련 정보(개인정보 보호법 제23조)라 처음 저장할 때 따로 동의를 받는다. 동의해야 행이 생기므로 저장 시각이 곧 동의 시각이다.
  // 이미 저장한 분은 처음 저장할 때 동의했으니 고칠 때 다시 묻지 않는다.
  const [agreed, setAgreed] = useState(false);
  const [agreeError, setAgreeError] = useState(false);
  const needAgree = !profile;
  const agreeRef = useRef<HTMLInputElement>(null);
  const agreeErrId = useId();

  // 칸을 떠났거나 저장을 눌렀을 때만 틀렸다고 보여준다(시안 ShoppingItemSheet 패턴)
  const [touched, setTouched] = useState<Set<NumberField>>(() => new Set());
  const touch = (f: NumberField) => setTouched((prev) => (prev.has(f) ? prev : new Set(prev).add(f)));

  const sexRef = useRef<HTMLDivElement>(null);
  const birthRef = useRef<HTMLInputElement>(null);
  const heightRef = useRef<HTMLInputElement>(null);
  const weightRef = useRef<HTMLInputElement>(null);
  const activityRef = useRef<HTMLDivElement>(null);

  const birthInputId = useId();
  const heightInputId = useId();
  const weightInputId = useId();
  const birthErrId = useId();
  const heightErrId = useId();
  const weightErrId = useId();

  const { value, errors } = parseProfileInput({ sex, birthYear, height, weight, activity, goal }, today);
  const target = value ? dailyTarget(value, today) : null;
  const ageSuffix = birthYear.trim() !== "" && !errors.birthYear ? `${ageOf(Number(birthYear), today)}세` : "";
  const showBirthErr = touched.has("birthYear") && !!errors.birthYear;
  const showHeightErr = touched.has("height") && !!errors.height;
  const showWeightErr = touched.has("weight") && !!errors.weight;

  const focusFirstEmpty = () => {
    if (!sex) return sexRef.current?.querySelector<HTMLElement>("button")?.focus();
    if (!birthYear.trim() || errors.birthYear) return birthRef.current?.focus();
    if (!height.trim() || errors.height) return heightRef.current?.focus();
    if (!weight.trim() || errors.weight) return weightRef.current?.focus();
    if (!activity) return activityRef.current?.querySelector<HTMLElement>("button")?.focus();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!value) {
      setTouched(new Set(["birthYear", "height", "weight"]));
      return focusFirstEmpty();
    }
    if (needAgree && !agreed) {
      setAgreeError(true);
      return agreeRef.current?.focus();
    }
    run(async () => {
      const res = await api<BodyProfileResponse>("/api/body-profile", { method: "PUT", body: value });
      onSaved(res);
    });
  };

  const remove = () => {
    if (!confirm("입력한 정보를 지울까요? 하루 칼로리 목표도 함께 사라져요.")) return;
    run(async () => {
      await api("/api/body-profile", { method: "DELETE" });
      onDeleted();
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
          <div className="field">
            <label className="field-label" htmlFor={birthInputId}>
              태어난 해
            </label>
            <div className="input-suffix">
              <input
                id={birthInputId}
                ref={birthRef}
                className={showBirthErr ? "input invalid" : "input"}
                inputMode="numeric"
                maxLength={4}
                value={birthYear}
                aria-invalid={showBirthErr || undefined}
                aria-describedby={showBirthErr ? birthErrId : undefined}
                onChange={(e) => setBirthYear(e.target.value.replace(/\D/g, "").slice(0, 4))}
                onBlur={() => touch("birthYear")}
              />
              <span className="suffix" aria-hidden="true">
                {ageSuffix}
              </span>
            </div>
            {showBirthErr && (
              <p className="hint nt-invalid" id={birthErrId}>
                {errors.birthYear}
              </p>
            )}
          </div>
          <div className="field">
            <label className="field-label" htmlFor={heightInputId}>
              키
            </label>
            <div className="input-suffix">
              <input
                id={heightInputId}
                ref={heightRef}
                className={showHeightErr ? "input invalid" : "input"}
                inputMode="decimal"
                value={height}
                aria-invalid={showHeightErr || undefined}
                aria-describedby={showHeightErr ? heightErrId : undefined}
                onChange={(e) => setHeight(e.target.value.replace(/[^0-9.,]/g, ""))}
                onBlur={() => touch("height")}
              />
              <span className="suffix" aria-hidden="true">
                cm
              </span>
            </div>
            {showHeightErr && (
              <p className="hint nt-invalid" id={heightErrId}>
                {errors.height}
              </p>
            )}
          </div>
          <div className="field">
            <label className="field-label" htmlFor={weightInputId}>
              몸무게
            </label>
            <div className="input-suffix">
              <input
                id={weightInputId}
                ref={weightRef}
                className={showWeightErr ? "input invalid" : "input"}
                inputMode="decimal"
                value={weight}
                aria-invalid={showWeightErr || undefined}
                aria-describedby={showWeightErr ? weightErrId : undefined}
                onChange={(e) => setWeight(e.target.value.replace(/[^0-9.,]/g, ""))}
                onBlur={() => touch("weight")}
              />
              <span className="suffix" aria-hidden="true">
                kg
              </span>
            </div>
            {showWeightErr && (
              <p className="hint nt-invalid" id={weightErrId}>
                {errors.weight}
              </p>
            )}
          </div>
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

        {needAgree && (
          <div className="field">
            <label className="nt-agree">
              <input
                ref={agreeRef}
                type="checkbox"
                checked={agreed}
                aria-invalid={agreeError || undefined}
                aria-describedby={agreeError ? agreeErrId : undefined}
                onChange={(e) => {
                  setAgreed(e.target.checked);
                  if (e.target.checked) setAgreeError(false);
                }}
              />
              <span>키·몸무게 같은 건강 관련 정보를 하루 칼로리 목표 계산에 쓰는 데 동의해요</span>
            </label>
            {agreeError && (
              <p id={agreeErrId} className="hint nt-invalid" role="alert">
                동의해야 저장할 수 있어요
              </p>
            )}
          </div>
        )}

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
