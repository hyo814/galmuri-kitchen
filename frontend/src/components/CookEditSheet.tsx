import { useId, useState, type MouseEvent } from "react";
import { api, type CookLogDetail } from "../api";
import { parseWon, wonFieldText } from "../cooklog/cook.ts";
import { resizeImage } from "../image.ts";
import { useAsyncAction } from "../useAsyncAction";
import { DateChips, PhotoPicker, WonField, forgetCookCaches } from "./CookSheet";
import Sheet from "./Sheet";
import StarPicker from "./StarPicker";

interface Props {
  log: CookLogDetail;
  today: string;
  /** 사진 저장소가 꺼져 있으면 사진 칸을 숨긴다(R10-13) */
  photos: boolean;
  onSaved: (log: CookLogDetail) => void;
  onClose: () => void;
}

/** 일기 고치기(결정 18): 날짜·사 먹으면 얼마·별점·사진·메모만. 인분·쓴 재료는 재고와 어긋나서 고치지 않는다 */
export default function CookEditSheet({ log: logProp, today, photos, onSaved, onClose }: Props) {
  // 글 칸 저장(PATCH)은 됐는데 사진 단계만 실패하면 시트에 남는다 — 그 뒤 비교 기준·닫을 때 넘길 값은 저장된 일기(FoodLogSheet savedLog와 같게, R10-6)
  const [savedLog, setSavedLog] = useState<CookLogDetail | null>(null);
  const log = savedLog ?? logProp;
  const [date, setDate] = useState(logProp.cooked_on);
  const [priceText, setPriceText] = useState(() => wonFieldText(logProp.eat_out_price, ""));
  const [priceTouched, setPriceTouched] = useState(false);
  const [rating, setRating] = useState(logProp.rating);
  const [memo, setMemo] = useState(logProp.memo ?? "");
  const [file, setFile] = useState<Blob | null>(null);
  const [photoRemoved, setPhotoRemoved] = useState(false);
  const [photoError, setPhotoError] = useState("");
  const save = useAsyncAction();
  const id = useId();
  const invalid = parseWon(priceText) === undefined;

  function closeSheet() {
    if (savedLog) onSaved(savedLog);
    else onClose();
  }

  function submit(e: MouseEvent<HTMLButtonElement>) {
    if (invalid) {
      e.currentTarget.closest("dialog")?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      return;
    }
    const body: Record<string, unknown> = {};
    const price = parseWon(priceText) ?? null;
    const memoValue = memo.trim() || null;
    if (date !== log.cooked_on) body.cooked_on = date;
    if (price !== log.eat_out_price) body.eat_out_price = price;
    if (rating !== log.rating) body.rating = rating;
    if (memoValue !== log.memo) body.memo = memoValue;
    // 새로 고른 사진이 있으면 바꾸기만, 없이 지금 사진을 뺐으면 지우기만(R10-5)
    const removePhoto = !file && photoRemoved && log.photo_url !== null;
    if (!Object.keys(body).length && !file && !removePhoto) {
      closeSheet(); // 앞선 저장이 서버를 바꿨으면(savedLog) 닫으면서 넘긴다
      return;
    }
    setPhotoError("");
    void save.run(async () => {
      let result = log;
      if (Object.keys(body).length) {
        result = await api<CookLogDetail>(`/api/cook-logs/${log.id}`, { method: "PATCH", body });
        forgetCookCaches();
        setSavedLog(result);
      }
      try {
        if (file) {
          const out = await resizeImage(file);
          // 못 읽으면 resizeImage가 원본을 돌려주는데, 원본에는 위치 같은 사진 정보가 남아 있을 수 있어 올리지 않는다(CookSheet와 같은 가드, R10-4)
          if (out === file) throw new Error("이 사진은 올릴 수 없어요. 다른 사진을 골라주세요.");
          const form = new FormData();
          form.append("image", out, "photo.jpg");
          result = await api<CookLogDetail>(`/api/cook-logs/${log.id}/photo`, { method: "PUT", body: form });
          forgetCookCaches();
        } else if (removePhoto) {
          await api(`/api/cook-logs/${log.id}/photo`, { method: "DELETE" });
          forgetCookCaches();
          // DELETE는 빈 응답이라 새로 받아 넘긴다. 다시 받기만 실패하면 사진은 빠졌으니 사진 없는 일기로 닫는다(R10-F5)
          const removed = { ...result, photo_url: null };
          result = await api<CookLogDetail>(`/api/cook-logs/${log.id}`).catch(() => removed);
        }
      } catch (err) {
        // 이번이나 앞선 저장에서 글 칸은 이미 저장됐으면 그렇다고 먼저 알린다(R10-F6)
        const kept = Object.keys(body).length > 0 || savedLog !== null ? "다른 칸은 저장했어요. " : "";
        setPhotoError(`${kept}${file ? "사진은 올리지 못했어요" : "사진은 빼지 못했어요"} · ${(err as Error).message}`);
        return;
      }
      onSaved(result);
    });
  }

  return (
    <Sheet title={`${logProp.title} 고치기`} description="인분과 쓴 재료는 고칠 수 없어요" focusTitle locked={save.busy} onClose={closeSheet}>
      <DateChips value={date} today={today} onChange={setDate} />

      <WonField
        value={priceText}
        source={priceTouched ? null : log.eat_out_source}
        estimating={false}
        onChange={(text) => {
          setPriceTouched(true);
          setPriceText(text);
        }}
      />

      <div className="ck-row">
        <b>별점</b>
        <StarPicker value={rating} label="별점" onChange={setRating} />
      </div>

      {photos && (
        <div className="field">
          <span className="field-label" id={`${id}-photo`}>
            사진
          </span>
          <div className="ck-row" role="group" aria-labelledby={`${id}-photo`}>
            <PhotoPicker file={file} currentUrl={photoRemoved ? null : log.photo_url} onPick={setFile} onRemoveCurrent={() => setPhotoRemoved(true)} />
          </div>
        </div>
      )}

      <div className="field fl-memo">
        <label className="field-label" htmlFor={`${id}-memo`}>
          메모 <span className="optional">(선택)</span>
        </label>
        <textarea id={`${id}-memo`} className="input" rows={3} maxLength={500} value={memo} onChange={(e) => setMemo(e.target.value)} />
        <span className="muted" aria-hidden="true">
          {memo.length} / 500
        </span>
      </div>

      {(save.error || photoError) && (
        <p className="error" role="alert">
          {save.error || photoError}
        </p>
      )}
      <div className="actions">
        <button type="button" className="btn secondary" disabled={save.busy} onClick={closeSheet}>
          취소
        </button>
        <button type="button" className="btn primary" disabled={save.busy} aria-disabled={invalid || undefined} onClick={submit}>
          {save.busy ? "저장하는 중…" : "저장"}
        </button>
      </div>
    </Sheet>
  );
}
