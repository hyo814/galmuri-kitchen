import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api, type AiUsage, type RecipeDraft } from "../api";
import { remainingText } from "../format";
import { autoGrowTextarea, openDraft } from "../pages/RecipeForm";
import { navigate } from "../useHashRoute";
import { useResource } from "../useResource";
import Icon, { type IconName } from "./Icon";
import Sheet from "./Sheet";

export type AddStep = "pick" | "link" | "text";

const CHOICES: { step: AddStep | "manual"; icon: IconName; title: string; hint: string }[] = [
  { step: "link", icon: "link", title: "링크로 가져오기", hint: "유튜브·인스타그램·블로그 주소" },
  { step: "text", icon: "clipboard", title: "글 붙여넣기", hint: "메모나 게시물 설명을 복사해서" },
  { step: "manual", icon: "pencil", title: "직접 쓰기", hint: "재료와 만드는 법을 하나씩" },
];

interface Props {
  /** 영상 보기처럼 글 붙여넣기 단계부터 열 때 */
  initialStep?: AddStep;
  initialWarning?: string;
  onClose: () => void;
}

/** 레시피 추가: 방법 고르기 → 링크 / 글 붙여넣기(링크를 못 읽으면 경고 상자와 함께 이 단계로) → 가져온 레시피 확인 폼 */
export default function AddRecipeSheet({ initialStep = "pick", initialWarning = "", onClose }: Props) {
  const [step, setStep] = useState<AddStep>(initialStep);
  const [warning, setWarning] = useState(initialWarning);
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: usage } = useResource<AiUsage>("/api/ai-usage");
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  // 경고와 함께 열었으면(영상 보기에서 링크를 못 읽음) 처음 열 때도 아래 effect가 제목으로 포커스하게 null로 시작
  const prevStep = useRef<AddStep | null>(initialWarning ? null : step);

  // 시트를 닫으면(뒤로가기·배경 탭 포함) 진행 중인 요청도 멈춘다
  useEffect(() => () => abortRef.current?.abort(), []);

  // 단계가 바뀌면: 방법 고르기로 돌아왔거나 경고와 함께 글 붙여넣기로 바뀌었으면 시트 제목으로 포커스
  // (그 밖의 링크·글 단계는 입력 칸이 autoFocus). 이전 단계와 비교하므로 StrictMode의 두 번 실행에도 튀지 않는다.
  useEffect(() => {
    if (prevStep.current === step) return;
    prevStep.current = step;
    if (step === "link" || (step === "text" && !warning)) return;
    const heading = rootRef.current?.querySelector<HTMLElement>(".sheet-header h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [step, warning]);

  const go = (next: AddStep) => {
    abortRef.current?.abort();
    setBusy(false);
    setWarning("");
    setStep(next);
  };

  // 영상 보기에서 바로 글 단계로 열었으면 취소는 시트를 닫는다. dialog.close()로 닫아야 여는 버튼으로 포커스가 돌아간다(close 이벤트가 onClose를 부른다)
  const cancel = () => {
    if (initialStep === "pick") return go("pick");
    abortRef.current?.abort();
    rootRef.current?.querySelector("dialog")?.close();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const body = step === "link" ? { url: url.trim() } : { text: text.trim() };
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setWarning("");
    try {
      const draft = await api<RecipeDraft>("/api/recipes/import", { method: "POST", body, signal: controller.signal });
      if (controller.signal.aborted) return;
      openDraft(draft);
    } catch (err) {
      if (controller.signal.aborted) return;
      setBusy(false);
      setWarning((err as Error).message);
      // 링크를 못 읽었으면 같은 시트를 글 붙여넣기로 바꾼다(포커스는 위 effect가 제목으로). 아니면 고칠 수 있게 입력 칸으로
      if (err instanceof ApiError && err.body?.need_text === true && step === "link") setStep("text");
      else fieldRef.current?.focus();
    }
  };

  const title = step === "pick" ? "레시피 추가" : step === "link" ? "링크로 가져오기" : "글 붙여넣기";
  const description =
    step === "pick"
      ? "어떻게 넣을지 골라주세요"
      : step === "link"
        ? "영상이나 글 주소를 붙여 넣으면 재료와 만드는 법을 정리해줘요"
        : undefined;
  const value = step === "link" ? url : text;

  return (
    <div ref={rootRef}>
      <Sheet title={title} description={description} onClose={onClose}>
        <p className="sr-only" role="status" aria-live="polite">
          {busy ? "레시피를 정리하고 있어요" : ""}
        </p>

        {step === "pick" ? (
          <>
            <div className="r3-choices">
              {CHOICES.map((choice) => (
                <button
                  key={choice.step}
                  type="button"
                  className="r3-choice"
                  onClick={() => (choice.step === "manual" ? navigate("/recipes/new") : go(choice.step))}
                >
                  <span className="r3-choice-icon">
                    <Icon name={choice.icon} size={22} />
                  </span>
                  <span className="row-main">
                    <span className="row-title">{choice.title}</span>
                    <span className="row-sub">{choice.hint}</span>
                  </span>
                  <Icon name="chevron" />
                </button>
              ))}
            </div>
            <p className="r3-quota">링크·글은 AI가 정리해요{remainingText(usage)}</p>
          </>
        ) : (
          <form className="form" onSubmit={submit} noValidate>
            {warning && (
              <div className="r3-err-box" role="alert">
                <Icon name="alert" size={16} />
                <span>{warning}</span>
              </div>
            )}
            {step === "link" ? (
              <label className="field">
                <span className="field-label">링크</span>
                <input
                  ref={(el) => {
                    fieldRef.current = el;
                  }}
                  className="input"
                  type="url"
                  inputMode="url"
                  autoComplete="off"
                  placeholder="https://"
                  maxLength={2000}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  autoFocus
                />
              </label>
            ) : (
              <label className="field">
                <span className="field-label">레시피 글</span>
                <textarea
                  ref={(el) => {
                    fieldRef.current = el;
                    autoGrowTextarea(el);
                  }}
                  className="input r3-area"
                  rows={5}
                  maxLength={10000}
                  value={text}
                  onChange={(e) => {
                    autoGrowTextarea(e.currentTarget);
                    setText(e.target.value);
                  }}
                  autoFocus={!warning}
                />
              </label>
            )}
            <div className="actions">
              <button type="button" className="btn outline" onClick={cancel}>
                취소
              </button>
              {/* 정리하는 동안에도 같은 버튼(disabled 대신 aria-disabled)이라 포커스가 사라지지 않는다 */}
              <button className="btn primary" disabled={!busy && !value.trim()} aria-disabled={busy || undefined} aria-busy={busy || undefined}>
                {busy ? "정리하는 중…" : step === "link" ? "가져오기" : "정리하기"}
              </button>
            </div>
          </form>
        )}
      </Sheet>
    </div>
  );
}
