import { useEffect, useRef, useState } from "react";
import { ApiError, api, type ScanKind, type ScanResult, type StorageLocation } from "../api";
import { resizeImage } from "../image";
import Icon, { type IconName } from "./Icon";
import ScanReview from "./ScanReview";
import Sheet from "./Sheet";

export const SCAN_CHOICES: { kind: ScanKind; icon: IconName; title: string; hint: string; photo: string }[] = [
  { kind: "fridge", icon: "fridge", title: "냉장고 사진", hint: "냉장고 안을 찍으면 보이는 재료를 찾아요", photo: "냉장고 사진" },
  { kind: "receipt", icon: "receipt", title: "영수증", hint: "마트 영수증에서 식재료만 골라요", photo: "영수증 사진" },
  { kind: "order", icon: "phone", title: "온라인 주문 캡처", hint: "쿠팡·컬리·네이버 등 주문 완료 화면", photo: "주문 캡처" },
];

const NOT_FOUND = "사진에서 재료를 찾지 못했어요.";
const TOO_BIG = "사진이 너무 커요. 10MB 이하로 올려주세요.";
const UNREADABLE_FORMAT = "이 사진 형식은 읽을 수 없어요. 카메라 설정에서 HEIF를 끄거나 스크린샷으로 올려주세요.";
const HEIF_HINT = "카메라 설정에서 HEIF를 끄거나 스크린샷으로 올려주세요.";
const READABLE_TYPES = ["image/jpeg", "image/png", "image/webp"];

type Step =
  | { name: "pick" }
  | { name: "loading" }
  | { name: "review"; result: ScanResult }
  // status: 실제 HTTP 상태가 없을 때(찾은 재료 0개)는 0("상태 없음", api.ts의 네트워크 오류와 같은 관례)을 쓰고
  // reason으로 구분한다. 200을 가짜로 쓰지 않는다 — 200은 "성공"이지 "0개 찾음"이 아니다.
  | { name: "error"; message: string; status: number; reason?: "empty" };

interface Props {
  mode: "on" | "sample";
  limit: number;
  locations: StorageLocation[];
  onAdded: (count: number) => Promise<void>;
  onManual: () => void;
  onClose: () => void;
  onLocationsStale?: () => void;
}

export default function ScanSheet({ mode, limit, locations, onAdded, onManual, onClose, onLocationsStale }: Props) {
  const [kind, setKind] = useState<ScanKind>("fridge");
  const [step, setStep] = useState<Step>({ name: "pick" });
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(false);

  // 시트를 닫으면(뒤로가기·배경 탭 포함) 진행 중인 인식 요청도 멈춘다
  useEffect(() => () => abortRef.current?.abort(), []);

  // 단계가 바뀌면(고르기→찾는 중→확인/실패, 취소로 되돌아갈 때 포함) 그 단계의 제목으로 포커스를 옮긴다.
  // loading·error는 본문에 자기 h2가 있으니 그걸, pick·review는 본문에 h2가 없으니 Sheet 자체 제목으로.
  // 최초 마운트(고르기 첫 화면)는 건너뛴다 — Sheet가 이미 dialog에 포커스를 둔다.
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const root = rootRef.current;
    if (!root) return;
    const ownHeading =
      step.name === "loading"
        ? root.querySelector<HTMLElement>(".scan-wait h2")
        : step.name === "error"
          ? root.querySelector<HTMLElement>(".scan-fail h2")
          : null;
    const heading = ownHeading ?? root.querySelector<HTMLElement>(".sheet-header h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [step.name]);

  // ScanSheet가 떠 있는 동안 계속 마운트된 알림 영역. 단계별 시각적 문구를 중복해서 role=status/alert로
  // 두 번 읽지 않도록, 여기 하나로 모으고 본문 쪽 role은 뺀다.
  const liveText =
    step.name === "loading"
      ? "사진에서 재료를 찾고 있어요"
      : step.name === "review"
        ? `재료 ${step.result.items.length}개를 찾았어요`
        : step.name === "error"
          ? step.message
          : "";

  const choose = (next: ScanKind) => {
    setKind(next);
    fileRef.current?.click();
  };

  const retake = () => fileRef.current?.click();

  const scan = async (file: File) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setStep({ name: "loading" });
    try {
      const blob = await resizeImage(file);
      if (controller.signal.aborted) return;
      if (blob.size > 10 * 1024 * 1024) {
        setStep({ name: "error", message: TOO_BIG, status: 0 });
        return;
      }
      // 리사이즈가 원본 그대로 떨어졌다(디코딩 실패) + 원래도 못 읽는 형식이면 서버에 보내 봐야 415만 받는다
      if (blob === file && !READABLE_TYPES.includes(file.type)) {
        setStep({ name: "error", message: UNREADABLE_FORMAT, status: 0 });
        return;
      }
      const form = new FormData();
      form.append("image", blob, "photo.jpg");
      const result = await api<ScanResult>(`/api/scan?kind=${kind}`, {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setStep(
        result.items.length > 0
          ? { name: "review", result }
          : { name: "error", message: NOT_FOUND, status: 0, reason: "empty" },
      );
    } catch (e) {
      if (controller.signal.aborted) return;
      setStep({ name: "error", message: (e as Error).message, status: e instanceof ApiError ? e.status : 0 });
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    setStep({ name: "pick" });
  };

  const choice = SCAN_CHOICES.find((c) => c.kind === kind) ?? SCAN_CHOICES[0];
  // 한도 초과(429, 하루 한도·짧은 시간 연속 호출 모두)·기능 꺼짐(503)은 다시 찍어도 같으므로 '닫기'를 보여 준다
  const canRetake = step.name === "error" && step.status !== 429 && step.status !== 503;
  const photoTip = step.name === "error" && (step.status === 502 || step.reason === "empty");

  const sheetProps =
    step.name === "review"
      ? { title: `찾은 재료 ${step.result.items.length}개`, description: "넣을 재료만 체크해주세요", className: "scan-tall" }
      : step.name === "pick"
        ? { title: "사진으로 추가" }
        : { title: step.name === "loading" ? "재료를 찾는 중" : "인식 실패", hideHeader: true };

  return (
    <div ref={rootRef}>
      <Sheet {...sheetProps} onClose={onClose}>
        <p className="sr-only" role="status" aria-live="polite">
          {liveText}
        </p>
        {/* capture 속성 없음: 폰이 카메라·갤러리 중에서 고르게 한다 (사용자 결정 2026-09-13) */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // 같은 사진을 다시 골라도 change가 일어나게
            if (file) scan(file);
          }}
        />

        {step.name === "pick" && (
          <>
            <div className="scan-choices">
              {SCAN_CHOICES.map((c) => (
                <button key={c.kind} type="button" className="scan-choice" onClick={() => choose(c.kind)}>
                  <span className="scan-choice-icon">
                    <Icon name={c.icon} />
                  </span>
                  <span className="row-main">
                    <span className="row-title">{c.title}</span>
                    <span className="row-sub">{c.hint}</span>
                  </span>
                </button>
              ))}
            </div>
            <p className="hint scan-quota">
              <Icon name="info" size={16} />
              {mode === "sample"
                ? "지금은 사진을 실제로 읽지 않고 예시 재료를 보여줘요"
                : `하루 ${limit}번까지 쓸 수 있어요 · 인식에 실패해도 1번으로 세요`}
            </p>
          </>
        )}

        {step.name === "loading" && (
          <>
            <div className="scan-wait">
              <div className="scan-thumb" aria-hidden="true">
                <div className="scan-paper">
                  <i className="b" />
                  <i />
                  <i className="r" />
                  <i className="s" />
                  <i className="r" />
                  <i />
                  <i className="s" />
                  <i className="r" />
                  <div className="scan-beam" />
                </div>
                <img className="scan-mascot" src="/mark.svg" width="56" height="56" alt="" />
              </div>
              <div>
                <h2>사진에서 재료를 찾고 있어요…</h2>
                <p className="sheet-desc">{choice.photo} 1장</p>
              </div>
              <div className="scan-progress" />
            </div>
            <button type="button" className="btn secondary" onClick={cancel}>
              취소
            </button>
          </>
        )}

        {step.name === "review" && (
          <ScanReview
            kind={kind}
            result={step.result}
            locations={locations}
            onRetake={retake}
            onAdded={onAdded}
            onLocationsStale={onLocationsStale}
          />
        )}

        {step.name === "error" && (
          <>
            <div className="scan-fail">
              <span className="scan-fail-icon">
                <Icon name="alert" size={28} />
              </span>
              <h2>{step.message}</h2>
              {photoTip && <p className="hint">밝은 곳에서 글자가 잘 보이게 찍으면 더 잘 찾아요</p>}
              {step.status === 415 && <p className="hint">{HEIF_HINT}</p>}
            </div>
            <div className="actions">
              {canRetake ? (
                <button type="button" className="btn secondary" onClick={retake}>
                  다시 찍기
                </button>
              ) : (
                <button type="button" className="btn secondary" onClick={onClose}>
                  닫기
                </button>
              )}
              <button type="button" className="btn primary" onClick={onManual}>
                <Icon name="pencil" />
                직접 입력하기
              </button>
            </div>
          </>
        )}
      </Sheet>
    </div>
  );
}
