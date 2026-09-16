import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError, api, isMultiImport, type AiUsage, type MultiRecipeDraft, type RecipeDraft } from "../api";
import { remainingText } from "../format";
import { autoGrowTextarea, openDraft, openMultiPick } from "../pages/RecipeForm";
import { navigate } from "../useHashRoute";
import { useResource } from "../useResource";
import Icon, { type IconName } from "./Icon";
import { ImportPickSheet } from "./RecipePickSheet";
import { ScanWait, preparePhoto } from "./ScanSheet";
import Sheet from "./Sheet";

export type AddStep = "pick" | "link" | "text" | "photo";

const MAX_PHOTOS = 5;

const CHOICES: { step: AddStep | "manual"; icon: IconName; title: string; hint: string }[] = [
  { step: "link", icon: "link", title: "링크로 가져오기", hint: "유튜브·인스타그램·블로그 주소" },
  { step: "text", icon: "clipboard", title: "글 붙여넣기", hint: "메모나 게시물 설명을 복사해서" },
  { step: "photo", icon: "camera", title: "사진으로 가져오기", hint: "요리책·캡처·손글씨 레시피를 찍어서" },
  { step: "manual", icon: "pencil", title: "직접 쓰기", hint: "재료와 만드는 법을 하나씩" },
];

/** 못 읽은 유튜브·인스타그램 링크. 서버가 422 need_text에 읽은 출처·표준 주소를 함께 준다(화면은 주소를 다시 해석하지 않는다) */
export interface FailedLink {
  source: "youtube" | "instagram";
  source_url: string;
}

interface Props {
  /** 영상 보기처럼 글 붙여넣기·사진 단계부터 열 때 */
  initialStep?: AddStep;
  initialWarning?: string;
  /** 영상 보기에서 못 읽은 유튜브 링크: 처음부터 화면 캡처 흐름으로 연다 */
  failedLink?: FailedLink;
  onClose: () => void;
}

/** 유튜브·인스타그램 링크를 못 읽었을 때 경고(영상 보기는 가져오기 버튼) 아래에 두는 `화면 캡처로 가져오기` + 안내 한 줄.
 *  영상 보기처럼 회색 바탕(--bg) 위면 onPage — 회색 보조 버튼이 바탕에 묻혀 테두리 버튼으로 */
export function CaptureButton({ onClick, onPage = false }: { onClick: () => void; onPage?: boolean }) {
  const hintId = useId();
  return (
    <div className="r3-capture">
      <button type="button" className={onPage ? "btn outline" : "btn secondary"} aria-describedby={hintId} onClick={onClick}>
        <Icon name="file" />
        화면 캡처로 가져오기
      </button>
      <p className="hint r3-cta-note" id={hintId}>
        영상을 멈추고 재료와 만드는 법이 나온 화면을 캡처해 올려주세요 · 5장까지
      </p>
    </div>
  );
}

/** 레시피 추가: 방법 고르기 → 링크 / 글 붙여넣기(링크를 못 읽으면 경고 상자와 함께 이 단계로) / 사진 → 가져온 레시피 확인 폼 */
export default function AddRecipeSheet({ initialStep = "pick", initialWarning = "", failedLink, onClose }: Props) {
  const [step, setStep] = useState<AddStep>(initialStep);
  const [warning, setWarning] = useState(initialWarning);
  // 화면 캡처 흐름: 못 읽은 유튜브·인스타그램 링크와 그 경고. 링크는 이 흐름(글 ↔ 사진)에서 가져온 레시피의 출처로 남고(사진 단계는 앨범 먼저 + 취소),
  // 경고가 있으면 글 단계 경고 아래 `화면 캡처로 가져오기`. go()가 흐름 밖으로 옮기거나 시트를 닫으면 모두 지우고, 글을 다시 보내면 경고만 지운다
  const [capture, setCapture] = useState(failedLink ? { link: failedLink, warning: initialWarning } : null);
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [photoNote, setPhotoNote] = useState<{ count: number; trimmed: boolean }>({ count: 0, trimmed: false });
  // 여러 요리 가져오기(17절): 한 페이지에 요리가 여러 개면 저장 대신 고르기 화면을 보여준다
  const [multi, setMulti] = useState<MultiRecipeDraft | null>(null);
  const { data: usage, reload: reloadUsage } = useResource<AiUsage>("/api/ai-usage");
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const albumRef = useRef<HTMLInputElement>(null);
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

  // 사진을 읽는 동안에는 누른 버튼이 사라지므로 기다림 제목으로, 끝나면(실패·취소) 시트 제목으로 포커스
  const photoBusy = step === "photo" && busy;
  const prevPhotoBusy = useRef(photoBusy);
  useEffect(() => {
    if (prevPhotoBusy.current === photoBusy) return;
    prevPhotoBusy.current = photoBusy;
    const heading = rootRef.current?.querySelector<HTMLElement>(photoBusy ? ".scan-wait h2" : ".sheet-header h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [photoBusy]);

  // 단계를 바꾸면 요청·경고를 지우고 화면 캡처 흐름도 끝낸다. 흐름 안(글 ↔ 사진)에서만 keepCapture로 이어 가고, 글 단계로 돌아오면 그 경고를 다시 보여준다
  const go = (next: AddStep, keepCapture = false) => {
    abortRef.current?.abort();
    setBusy(false);
    setWarning(keepCapture && next === "text" ? (capture?.warning ?? "") : "");
    if (!keepCapture) setCapture(null);
    setStep(next);
  };

  // 취소: 화면 캡처 사진 단계는 글 단계로, 방법 고르기에서 왔으면 방법 고르기로, 영상 보기에서 바로 연 단계는 시트를 닫는다.
  // dialog.close()로 닫아야 여는 버튼으로 포커스가 돌아간다(close 이벤트가 onClose를 부른다)
  const cancel = () => {
    if (step === "photo" && initialStep !== "photo") return go("text", true);
    if (initialStep === "pick") return go("pick");
    abortRef.current?.abort();
    rootRef.current?.querySelector("dialog")?.close();
  };

  /** 초안을 받아 확인 폼으로 연다. makeBody는 사진 줄이기처럼 기다려야 할 수 있다(그동안도 취소할 수 있게 busy 뒤에 부른다) */
  const importDraft = async (makeBody: () => unknown) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setWarning("");
    try {
      const body = await makeBody();
      controller.signal.throwIfAborted();
      const result = await api<RecipeDraft | MultiRecipeDraft>("/api/recipes/import", { method: "POST", body, signal: controller.signal }).finally(
        () => void reloadUsage(), // 성공·실패 모두 AI 횟수를 셌을 수 있다
      );
      if (controller.signal.aborted) return;
      if (isMultiImport(result)) {
        // 여러 요리 가져오기(17절): 저장 폼 대신 고르기 화면. AddRecipeSheet의 나머지 단계는 그대로 두고(취소하면 되돌아온다) 위에 겹쳐 보여준다
        setBusy(false);
        setMulti(result);
        return;
      }
      // 못 읽은 영상 링크의 흐름에서 글·화면 캡처로 가져왔으면 출처는 그 링크(카드 없음)
      openDraft(capture ? { ...result, ...capture.link } : result);
    } catch (err) {
      if (controller.signal.aborted) return;
      setBusy(false);
      setWarning((err as Error).message);
      // 링크를 못 읽었으면 같은 시트를 글 붙여넣기로 바꾼다(포커스는 위 effect가 제목으로). 아니면 고칠 수 있게 입력 칸으로.
      // 유튜브·인스타그램(서버가 출처·표준 주소를 준다)은 레시피가 영상에만 있을 수 있어 화면 캡처로 가져오기도 보여준다.
      // 사진은 422(need_text)여도 사진 단계에 남아 경고로 보여준다(다시 찍을 수 있게)
      if (err instanceof ApiError && err.body?.need_text === true && step === "link") {
        setStep("text");
        const { source, source_url } = err.body;
        if ((source === "youtube" || source === "instagram") && typeof source_url === "string")
          setCapture({ link: { source, source_url }, warning: err.message });
      } else fieldRef.current?.focus();
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    // 글을 다시 보내면 경고 아래 캡처 버튼만 치운다(그 요청이 실패해도 다시 두지 않는다). 링크는 남겨 이 글로 가져온 레시피의 출처로 쓴다.
    // 링크 단계는 방법 고르기에서만 오므로(go가 흐름을 지웠다) 여기서는 늘 null이다
    setCapture((c) => c && { ...c, warning: "" });
    importDraft(() => (step === "link" ? { url: url.trim() } : { text: text.trim() }));
  };

  const readPhotos = (list: FileList | null) => {
    const picked = Array.from(list ?? []);
    if (!picked.length || busy) return;
    const files = picked.slice(0, MAX_PHOTOS);
    setPhotoNote({ count: files.length, trimmed: picked.length > MAX_PHOTOS });
    importDraft(async () => {
      const form = new FormData();
      for (const file of files) form.append("image", await preparePhoto(file), "photo.jpg");
      return form;
    });
  };

  const cancelPhotos = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  const title = { pick: "레시피 추가", link: "링크로 가져오기", text: "글 붙여넣기", photo: "사진으로 가져오기" }[step];
  const description = {
    pick: "어떻게 넣을지 골라주세요",
    link: "영상이나 글 주소를 붙여 넣으면 재료와 만드는 법을 정리해줘요",
    text: undefined,
    photo: "레시피 사진을 찍거나 고르면 재료와 만드는 법을 정리해줘요",
  }[step];
  const trimmedText = "사진은 5장까지 읽어요. 앞의 5장만 읽을게요";
  const value = step === "link" ? url : text;

  if (multi) {
    return <ImportPickSheet result={multi} onPick={(order) => openMultiPick(multi, order, capture?.link)} onClose={onClose} />;
  }

  return (
    <div ref={rootRef}>
      <Sheet title={title} description={description} hideHeader={photoBusy} onClose={onClose}>
        <p className="sr-only" role="status" aria-live="polite">
          {photoBusy
            ? `사진에서 레시피를 정리하고 있어요${photoNote.trimmed ? `. ${trimmedText}` : ""}`
            : busy
              ? "레시피를 정리하고 있어요"
              : ""}
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
        ) : step === "photo" ? (
          photoBusy ? (
            <ScanWait
              title="사진에서 레시피를 정리하고 있어요"
              photo={
                <>
                  {photoNote.trimmed ? trimmedText : `사진 ${photoNote.count}장`}
                  <br />
                  10초쯤 걸려요.
                </>
              }
              onCancel={cancelPhotos}
            />
          ) : (
            <div className="form">
              {warning && (
                <div className="r3-err-box" role="alert">
                  <Icon name="alert" size={16} />
                  <span>{warning}</span>
                </div>
              )}
              {/* 버튼 두 개로 나눈다: 안드로이드 14+의 시스템 사진 선택기(accept="image/*" multiple)에는 카메라가 없어서,
                  찍기는 capture 입력(1장)으로, 고르기는 여러 장 입력으로 따로 연다 */}
              <input
                ref={cameraRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={(e) => {
                  readPhotos(e.target.files);
                  e.target.value = ""; // 같은 사진을 다시 골라도 change가 일어나게
                }}
              />
              <input
                ref={albumRef}
                type="file"
                accept="image/*"
                multiple
                hidden
                onChange={(e) => {
                  readPhotos(e.target.files);
                  e.target.value = "";
                }}
              />
              <div className="r3-choices">
                {capture ? (
                  <>
                    {/* 화면 캡처로 왔다: 캡처한 화면은 앨범에 있어 앨범이 먼저 */}
                    <button type="button" className="btn primary" onClick={() => albumRef.current?.click()}>
                      <Icon name="file" />
                      앨범에서 고르기
                    </button>
                    <button type="button" className="btn secondary" onClick={() => cameraRef.current?.click()}>
                      <Icon name="camera" />
                      카메라로 찍기
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" className="btn primary" onClick={() => cameraRef.current?.click()}>
                      <Icon name="camera" />
                      카메라로 찍기
                    </button>
                    <button type="button" className="btn secondary" onClick={() => albumRef.current?.click()}>
                      <Icon name="file" />
                      앨범에서 고르기
                    </button>
                  </>
                )}
              </div>
              <p className="r3-quota">사진은 AI가 정리해요{remainingText(usage)}</p>
              {/* 화면 캡처로 왔으면 글 붙여넣기처럼 맨 아래에 취소(혼자라 가로 가득): 글 단계(쓰던 글·경고 그대로)나 영상 보기로 돌아간다 */}
              {capture && (
                <div className="actions actions-single">
                  <button type="button" className="btn outline" onClick={cancel}>
                    취소
                  </button>
                </div>
              )}
            </div>
          )
        ) : (
          <form className="form" onSubmit={submit} noValidate>
            {warning && (
              <div className="r3-err-box" role="alert">
                <Icon name="alert" size={16} />
                <span>{warning}</span>
              </div>
            )}
            {warning && capture?.warning && <CaptureButton onClick={() => go("photo", true)} />}
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
