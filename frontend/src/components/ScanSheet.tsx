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

type Step =
  | { name: "pick" }
  | { name: "loading" }
  | { name: "review"; result: ScanResult }
  | { name: "error"; message: string; status: number };

interface Props {
  mode: "on" | "sample";
  limit: number;
  locations: StorageLocation[];
  onAdded: (count: number) => Promise<void>;
  onManual: () => void;
  onClose: () => void;
}

export default function ScanSheet({ mode, limit, locations, onAdded, onManual, onClose }: Props) {
  const [kind, setKind] = useState<ScanKind>("fridge");
  const [step, setStep] = useState<Step>({ name: "pick" });
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 시트를 닫으면(뒤로가기·배경 탭 포함) 진행 중인 인식 요청도 멈춘다
  useEffect(() => () => abortRef.current?.abort(), []);

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
      const form = new FormData();
      form.append("image", await resizeImage(file), "photo.jpg");
      const result = await api<ScanResult>(`/api/scan?kind=${kind}`, {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setStep(result.items.length > 0 ? { name: "review", result } : { name: "error", message: NOT_FOUND, status: 200 });
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
  const photoTip = step.name === "error" && (step.status === 502 || step.status === 200);

  const sheetProps =
    step.name === "review"
      ? { title: `찾은 재료 ${step.result.items.length}개`, description: "넣을 재료만 체크해 주세요", className: "scan-tall" }
      : step.name === "pick"
        ? { title: "사진으로 추가" }
        : { title: step.name === "loading" ? "재료를 찾는 중" : "인식 실패", hideHeader: true };

  return (
    <Sheet {...sheetProps} onClose={onClose}>
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
            {mode === "sample" ? "API 키가 없어서 예시 결과를 보여 줘요" : `하루 ${limit}번까지 쓸 수 있어요`}
          </p>
        </>
      )}

      {step.name === "loading" && (
        <>
          <div className="scan-wait" role="status">
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
        <ScanReview kind={kind} result={step.result} locations={locations} onRetake={retake} onAdded={onAdded} />
      )}

      {step.name === "error" && (
        <>
          <div className="scan-fail" role="alert">
            <span className="scan-fail-icon">
              <Icon name="alert" size={28} />
            </span>
            <h2>{step.message}</h2>
            {photoTip && <p className="hint">밝은 곳에서 글자가 잘 보이게 찍으면 더 잘 찾아요</p>}
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
  );
}
