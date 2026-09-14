// 사진에서 살 것 뽑기: 카메라·앨범 고르기 → MemoScanReview. ShoppingMemo(메모에 사진 없을 때)와
// ShoppingItemSheet의 "사진에서 뽑기" 링크(메모 없이 바로)가 함께 쓰는 부분만 뽑았다.
// 어느 사진인지 고르는 단계("choose", 메모에 사진이 여러 장일 때)는 메모에만 있어 ShoppingMemo가 그대로 갖는다.
import { useRef } from "react";
import MemoScanReview from "./MemoScanReview";
import Sheet from "./Sheet";
import Icon from "./Icon";

export type ScanState = "source" | { image: Blob } | null;

interface Props {
  scan: ScanState;
  onScanChange: (next: ScanState) => void;
  sourceLabel: string;
  listed: string[];
  today: string;
  onScanned: () => void;
  onDone: (text: string) => void;
}

export default function MemoPhotoScan({ scan, onScanChange, sourceLabel, listed, today, onScanned, onDone }: Props) {
  const cameraRef = useRef<HTMLInputElement>(null);
  const albumRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onScanChange({ image: file });
        }}
      />
      <input
        ref={albumRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onScanChange({ image: file });
        }}
      />
      {scan === "source" && (
        <Sheet title="사진에서 살 것 뽑기" description="메모·전단지를 찍거나 앨범에서 골라주세요" onClose={() => onScanChange(null)}>
          <div className="actions actions-even">
            <button
              type="button"
              className="btn secondary"
              onClick={() => {
                onScanChange(null);
                albumRef.current?.click();
              }}
            >
              <Icon name="file" size={18} />
              앨범에서 고르기
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                onScanChange(null);
                cameraRef.current?.click();
              }}
            >
              <Icon name="camera" size={18} />
              카메라로 찍기
            </button>
          </div>
        </Sheet>
      )}
      {scan && typeof scan === "object" && (
        <MemoScanReview
          image={scan.image}
          sourceLabel={sourceLabel}
          listed={listed}
          today={today}
          onScanned={onScanned}
          onDone={onDone}
          onClose={() => onScanChange(null)}
        />
      )}
    </>
  );
}
