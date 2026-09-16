import { useState } from "react";
import type { RecipeInput } from "../api";
import { missingAmountCount, pickRowSummary } from "../format";
import Icon from "./Icon";
import Sheet from "./Sheet";

/** 찾은 레시피 한 개. order는 페이지에서 찾은 순서(1부터, "N개 중 K번째"의 K로도 쓴다) */
export interface PickSlot {
  order: number;
  draft: RecipeInput;
}

const MANY_IMAGES_NOTICE = "본문 사진이 많아 앞쪽 5장만 읽었어요. 빠진 요리는 사진으로 가져오기에 그 사진을 올려주세요.";

interface Props {
  title: string;
  subtitle?: string;
  items: PickSlot[];
  /** 이 호출에 사진을 함께 보냈는지(레시피별이 아니라 전체 기준) */
  fromImage?: boolean;
  imagesTruncated?: boolean;
  note?: string;
  onPick: (order: number) => void;
  onClose: () => void;
}

/** 여러 요리 가져오기(17절) 고르기 화면. 처음 찾았을 때(③)와 확인 화면의 `요리 바꾸기`가 함께 쓴다. */
export default function RecipePickSheet({ title, subtitle, items, fromImage, imagesTruncated, note, onPick, onClose }: Props) {
  const [order, setOrder] = useState(items[0]?.order ?? 0);
  return (
    <Sheet title={title} description={subtitle} onClose={onClose}>
      {imagesTruncated && (
        <p className="mo-note warn" role="alert">
          <Icon name="alert" size={16} />
          <span>{MANY_IMAGES_NOTICE}</span>
        </p>
      )}
      <div className="mo-radios" role="radiogroup" aria-label="가져올 요리">
        {items.map((item) => {
          const missing = missingAmountCount(item.draft.ingredients);
          return (
            <label key={item.order} className="mo-radio" aria-checked={order === item.order}>
              <input
                className="sr-only"
                type="radio"
                name="recipe-pick-order"
                checked={order === item.order}
                onChange={() => setOrder(item.order)}
                aria-label={item.draft.title}
              />
              <span className="mo-dot" aria-hidden="true" />
              <span className="row-main">
                <span className="row-title">{item.draft.title}</span>
                <span className="row-sub">{pickRowSummary(item.draft.ingredients, item.draft.steps)}</span>
                {(fromImage || missing > 0) && (
                  <span className="sh-meta">
                    {fromImage && <span className="sh-tag info">사진에서 읽었어요</span>}
                    {missing > 0 && <span className="sh-tag warn">양이 안 보이는 재료 {missing}개</span>}
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </div>
      {note && (
        <p className="mo-note">
          <Icon name="info" size={16} />
          <span>{note}</span>
        </p>
      )}
      <div className="actions">
        <button type="button" className="btn outline" onClick={onClose}>
          취소
        </button>
        <button type="button" className="btn primary" onClick={() => onPick(order)}>
          이 요리 확인하기
        </button>
      </div>
    </Sheet>
  );
}
