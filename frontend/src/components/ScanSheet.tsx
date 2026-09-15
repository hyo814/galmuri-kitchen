import { useEffect, useRef, useState, type ChangeEvent, type ReactNode, type RefObject } from "react";
import { ApiError, api, type AiUsage, type ScanKind, type ScanResult, type StorageLocation } from "../api";
import { remainingText } from "../format";
import { resizeImage } from "../image";
import { useResource } from "../useResource";
import Icon, { type IconName } from "./Icon";
import ScanReview from "./ScanReview";
import Sheet from "./Sheet";

export const SCAN_CHOICES: { kind: ScanKind; icon: IconName; title: string; hint: string; photo: string; tip: string }[] = [
  { kind: "fridge", icon: "fridge", title: "냉장고 사진", hint: "냉장고 안을 찍으면 보이는 재료를 찾아요", photo: "냉장고 사진", tip: "칸마다 따로 찍으면 더 잘 찾아요 · 5장까지" },
  { kind: "receipt", icon: "receipt", title: "영수증", hint: "마트 영수증에서 식재료만 골라요", photo: "영수증", tip: "긴 영수증은 나눠 찍어도 돼요 · 5장까지" },
  { kind: "order", icon: "phone", title: "온라인 주문 캡처", hint: "쿠팡·컬리·네이버 등 주문 완료 화면", photo: "주문 캡처", tip: "여러 화면이면 나눠 캡처해도 돼요 · 5장까지" },
];

const MAX_PHOTOS = 5; // backend/app/scan.py MAX_PHOTOS
const PHOTO_CAP = "사진은 5장까지 읽어요. 앞의 5장만 넣었어요";
const NOT_FOUND = "사진에서 재료를 찾지 못했어요.";
const TOO_BIG = "사진이 너무 커요. 10MB 이하로 올려주세요.";
const UNREADABLE_FORMAT = "이 사진 형식은 읽을 수 없어요. 카메라 설정에서 HEIF를 끄거나 스크린샷으로 올려주세요.";
const HEIF_HINT = "카메라 설정에서 HEIF를 끄거나 스크린샷으로 올려주세요.";
const READABLE_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** 사진을 긴 변 1568px로 줄여 보낼 준비를 한다(재고 사진·장보기 메모·레시피 사진). 10MB 넘거나 못 읽는 사진은 Error.
 *  strict면 다시 그리지 못한 사진을 모두 뺀다(메모 사진 올리기와 같은 규칙 — 원본의 위치 같은 사진 정보를 보내지 않게) */
export async function preparePhoto(file: Blob, strict = false): Promise<Blob> {
  const blob = await resizeImage(file);
  if (blob.size > 10 * 1024 * 1024) throw new Error(TOO_BIG);
  // 리사이즈가 원본 그대로 떨어졌다(디코딩 실패) + 원래도 못 읽는 형식이면 서버에 보내 봐야 415만 받는다
  if (blob === file && (strict || !READABLE_TYPES.includes(file.type))) throw new Error(UNREADABLE_FORMAT);
  return blob;
}

/** 사진(1~5장, 보이는 순서대로)을 줄여 kind로 한 번에 읽는다(재고 사진으로 추가·장보기 메모). memo는 다시 그리지 못한 사진을 모두 뺀다 */
export async function uploadScan(kind: ScanKind, files: Blob[], signal: AbortSignal): Promise<ScanResult> {
  const form = new FormData();
  for (const file of files) {
    form.append("image", await preparePhoto(file, kind === "memo"), "photo.jpg");
    signal.throwIfAborted();
  }
  return api<ScanResult>(`/api/scan?kind=${kind}`, { method: "POST", body: form, signal });
}

// 단계가 바뀌면(고르기→모으기→찾는 중→확인/실패, 취소로 되돌아갈 때 포함) 그 단계의 제목으로 포커스를 옮긴다.
// loading·error는 본문에 자기 h2가 있으니 그걸, 나머지는 본문에 h2가 없으니 Sheet 자체 제목으로.
// 최초 마운트는 건너뛴다 — Sheet가 이미 dialog에 포커스를 둔다.
export function useStepFocus(rootRef: RefObject<HTMLElement | null>, step: string) {
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const root = rootRef.current;
    if (!root) return;
    const heading = root.querySelector<HTMLElement>(".scan-wait h2, .scan-fail h2") ?? root.querySelector<HTMLElement>(".sheet-header h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps
}

/** visual: 기본 영수증 그림 대신 보여줄 그림(재고 사진은 모은 사진 겹쳐 보이기) */
export function ScanWait({ title, photo, visual, onCancel }: { title: string; photo: ReactNode; visual?: ReactNode; onCancel: () => void }) {
  return (
    <>
      <div className="scan-wait">
        {visual ?? (
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
        )}
        <div>
          <h2>{title}</h2>
          <p className="sheet-desc">{photo}</p>
        </div>
        <div className="scan-progress" />
      </div>
      <button type="button" className="btn secondary" onClick={onCancel}>
        취소
      </button>
    </>
  );
}

/** 인식 실패 문구와 도움말(버튼은 부르는 쪽에서) */
export function ScanFail({ message, status, reason }: { message: string; status: number; reason?: "empty" }) {
  return (
    <div className="scan-fail">
      <span className="scan-fail-icon">
        <Icon name="alert" size={28} />
      </span>
      <h2>{message}</h2>
      {(status === 502 || reason === "empty") && <p className="hint">밝은 곳에서 글자가 잘 보이게 찍으면 더 잘 찾아요</p>}
      {status === 415 && <p className="hint">{HEIF_HINT}</p>}
    </div>
  );
}

type Step =
  | { name: "pick" }
  | { name: "collect" }
  | { name: "loading" }
  | { name: "review"; result: ScanResult }
  // status: 실제 HTTP 상태가 없을 때(찾은 재료 0개)는 0("상태 없음", api.ts의 네트워크 오류와 같은 관례)을 쓰고
  // reason으로 구분한다. 200을 가짜로 쓰지 않는다 — 200은 "성공"이지 "0개 찾음"이 아니다.
  | { name: "error"; message: string; status: number; reason?: "empty" };

interface Photo {
  id: number;
  file: File;
  /** 미리보기 object URL — 빼거나 시트가 닫히면 revoke */
  url: string;
}

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
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [capped, setCapped] = useState(false);
  const { data: usage, reload: reloadUsage } = useResource<AiUsage>("/api/ai-usage");
  const cameraRef = useRef<HTMLInputElement>(null);
  const albumRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const trayRef = useRef<HTMLUListElement>(null);
  const nextId = useRef(0);
  const photosRef = useRef(photos);
  photosRef.current = photos;

  // 시트를 닫으면(뒤로가기·배경 탭 포함) 진행 중인 인식 요청도 멈추고 미리보기 URL을 놓는다
  useEffect(
    () => () => {
      abortRef.current?.abort();
      photosRef.current.forEach((p) => URL.revokeObjectURL(p.url));
    },
    [],
  );

  useStepFocus(rootRef, step.name);

  const count = photos.length;
  // ScanSheet가 떠 있는 동안 계속 마운트된 알림 영역. 단계별 시각적 문구를 중복해서 role=status/alert로
  // 두 번 읽지 않도록, 여기 하나로 모으고 본문 쪽 role은 뺀다.
  const liveText =
    step.name === "collect"
      ? capped
        ? PHOTO_CAP
        : ""
      : step.name === "loading"
        ? `사진 ${count}장에서 재료를 찾고 있어요`
        : step.name === "review"
          ? `재료 ${step.result.items.length}개를 찾았어요`
          : step.name === "error"
            ? step.message
            : "";

  const retakeLabel = kind === "order" ? "다시 고르기" : "다시 찍기";
  const backToPhotos = () => setStep(count ? { name: "collect" } : { name: "pick" });

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    e.target.value = ""; // 같은 사진을 다시 골라도 change가 일어나게
    if (!picked.length) return;
    const room = MAX_PHOTOS - count;
    const added = picked.slice(0, room).map((file) => ({ id: nextId.current++, file, url: URL.createObjectURL(file) }));
    setCapped(picked.length > room);
    setPhotos([...photos, ...added]);
    setStep({ name: "collect" });
  };

  const remove = (index: number) => {
    URL.revokeObjectURL(photos[index].url);
    const rest = photos.filter((_, i) => i !== index);
    setPhotos(rest);
    setCapped(false);
    if (!rest.length) {
      setStep({ name: "pick" });
      return;
    }
    // 뺀 자리의 다음 버튼(다음 사진의 ✕, 마지막이었으면 더 찍기)으로 포커스를 옮긴다 — 사라진 버튼에 포커스가 남지 않게
    requestAnimationFrame(() => trayRef.current?.querySelectorAll("button")[index]?.focus());
  };

  const read = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setCapped(false);
    setStep({ name: "loading" });
    try {
      const result = await uploadScan(kind, photos.map((p) => p.file), controller.signal);
      if (controller.signal.aborted) return;
      setStep(
        result.items.length > 0
          ? { name: "review", result }
          : { name: "error", message: NOT_FOUND, status: 0, reason: "empty" },
      );
    } catch (e) {
      if (controller.signal.aborted) return;
      setStep({ name: "error", message: (e as Error).message, status: e instanceof ApiError ? e.status : 0 });
    } finally {
      void reloadUsage(); // 오늘 남은 횟수(다시 모으기 화면)
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    setStep({ name: "collect" });
  };

  const choice = SCAN_CHOICES.find((c) => c.kind === kind) ?? SCAN_CHOICES[0];
  // 한도 초과(429, 하루 한도·짧은 시간 연속 호출 모두)·기능 꺼짐(503)은 다시 찍어도 같으므로 '닫기'를 보여 준다
  const canRetake = step.name === "error" && step.status !== 429 && step.status !== 503;

  const sheetProps =
    step.name === "review"
      ? {
          title: `찾은 재료 ${step.result.items.length}개`,
          description:
            count > 1 ? `사진 ${count}장에서 찾았어요 · 겹친 재료는 합쳤어요 · 넣을 재료만 체크해주세요` : "넣을 재료만 체크해주세요",
          className: "scan-tall",
        }
      : step.name === "pick"
        ? { title: "사진으로 추가" }
        : step.name === "collect"
          ? { title: `${choice.photo} ${count}장`, description: choice.tip }
          : { title: step.name === "loading" ? "재료를 찾는 중" : "인식 실패", hideHeader: true };

  return (
    <div ref={rootRef}>
      <Sheet {...sheetProps} onClose={onClose}>
        <p className="sr-only" role="status" aria-live="polite">
          {liveText}
        </p>
        {/* 안드로이드 14+는 capture 없이 열면 시스템 사진 선택기가 뜨는데 거기엔 카메라가 없다.
            그래서 카메라용·앨범용 입력을 따로 두고 버튼으로 고르게 한다 (사용자 결정 2026-09-14) */}
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={onFile} />
        <input ref={albumRef} type="file" accept="image/*" multiple hidden onChange={onFile} />

        {step.name === "pick" && (
          <>
            <div className="scan-choices" role="radiogroup" aria-label="사진 종류">
              {SCAN_CHOICES.map((c) => (
                <button
                  key={c.kind}
                  type="button"
                  role="radio"
                  aria-checked={kind === c.kind}
                  className="scan-choice"
                  onClick={() => {
                    setKind(c.kind);
                    if (count) setStep({ name: "collect" }); // 바꾸기로 왔으면 모은 사진으로 돌아간다
                  }}
                >
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
            <div className="actions actions-even">
              {kind === "order" ? (
                <>
                  <button type="button" className="btn secondary" onClick={() => cameraRef.current?.click()}>
                    <Icon name="camera" size={18} />
                    카메라로 찍기
                  </button>
                  <button type="button" className="btn primary" onClick={() => albumRef.current?.click()}>
                    <Icon name="file" size={18} />
                    앨범에서 고르기
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="btn secondary" onClick={() => albumRef.current?.click()}>
                    <Icon name="file" size={18} />
                    앨범에서 고르기
                  </button>
                  <button type="button" className="btn primary" onClick={() => cameraRef.current?.click()}>
                    <Icon name="camera" size={18} />
                    카메라로 찍기
                  </button>
                </>
              )}
            </div>
            <p className="hint scan-quota">
              <Icon name="info" size={16} />
              {mode === "sample"
                ? "지금은 사진을 실제로 읽지 않고 예시 재료를 보여줘요"
                : `하루 ${limit}번까지 쓸 수 있어요 · 인식에 실패해도 1번으로 세요`}
            </p>
          </>
        )}

        {step.name === "collect" && (
          <>
            <div className="scan-kindline">
              <span className="scan-choice-icon" aria-hidden="true">
                <Icon name={choice.icon} size={18} />
              </span>
              <span className="row-title">{choice.title}</span>
              <button type="button" className="scan-change" aria-label="사진 종류 바꾸기" onClick={() => setStep({ name: "pick" })}>
                바꾸기
              </button>
            </div>
            <p className="scan-count">
              <span>사진</span>
              <b>
                {count} / {MAX_PHOTOS}
              </b>
            </p>
            <ul className="scan-tray" ref={trayRef}>
              {photos.map((p, i) => (
                <li key={p.id} className="scan-photo">
                  <img src={p.url} alt={`${i + 1}번 사진`} />
                  <span className="scan-photo-n" aria-hidden="true">
                    {i + 1}
                  </span>
                  <button type="button" className="scan-photo-x" aria-label={`${i + 1}번 사진 빼기`} onClick={() => remove(i)}>
                    <span>
                      <Icon name="close" size={14} />
                    </span>
                  </button>
                </li>
              ))}
              {count < MAX_PHOTOS && (
                <>
                  <li>
                    <button type="button" className="scan-add" onClick={() => cameraRef.current?.click()}>
                      <Icon name="camera" size={22} />더 찍기
                    </button>
                  </li>
                  <li>
                    <button type="button" className="scan-add" onClick={() => albumRef.current?.click()}>
                      <Icon name="file" size={22} />
                      앨범
                    </button>
                  </li>
                </>
              )}
            </ul>
            {capped && <p className="notice">{PHOTO_CAP}</p>}
            <p className="hint scan-quota">
              <Icon name="info" size={16} />
              {mode === "sample"
                ? "지금은 사진을 실제로 읽지 않고 예시 재료를 보여줘요"
                : `여러 장이어도 오늘 남은 횟수는 1번만 줄어요${remainingText(usage, "scan")}`}
            </p>
            <div className="actions">
              <button type="button" className="btn secondary" onClick={onClose}>
                취소
              </button>
              <button type="button" className="btn primary" onClick={read}>
                {count}장 읽기
              </button>
            </div>
          </>
        )}

        {step.name === "loading" && (
          <ScanWait
            title={`사진 ${count}장에서 재료를 찾고 있어요`}
            photo={count > 1 ? "겹치는 재료는 하나로 합쳐요 · 20초쯤 걸려요" : "10초쯤 걸려요"}
            visual={
              <div className="scan-stack" aria-hidden="true">
                {photos.slice(0, 3).map((p) => (
                  <img key={p.id} src={p.url} alt="" />
                ))}
              </div>
            }
            onCancel={cancel}
          />
        )}

        {step.name === "review" && (
          <ScanReview
            kind={kind}
            result={step.result}
            locations={locations}
            onRetake={backToPhotos}
            onAdded={onAdded}
            onLocationsStale={onLocationsStale}
          />
        )}

        {step.name === "error" && (
          <>
            <ScanFail message={step.message} status={step.status} reason={step.reason} />
            <div className="actions">
              {canRetake ? (
                <button type="button" className="btn secondary" onClick={backToPhotos}>
                  {retakeLabel}
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
