import { useEffect, useState } from "react";
import type { User } from "../api";
import { quantityText } from "../shopping/sync";
import { LAST_STORE_KEY, storeLinks, type StoreId } from "../storeLinks";
import Icon from "./Icon";
import Sheet from "./Sheet";

export interface FindAllItem {
  /** 행 key(장보기 목록의 keyOf와 같은 값) */
  key: string;
  name: string;
  quantity: number;
  unit: string;
}

interface Props {
  /** 장보기 목록 순서 그대로, 체크 안 한 것만 */
  items: FindAllItem[];
  affiliates: User["shop_affiliates"];
  onClose: () => void;
}

/** 시안 docs/design/store-multi 옵션 A(②③): 쇼핑몰을 한 번 고르면 품목마다 차례로 찾기 링크를 연다 */
export default function StoreFindAllSheet({ items, affiliates, onClose }: Props) {
  const [lastUsed] = useState(() => {
    try {
      return localStorage.getItem(LAST_STORE_KEY) as StoreId | null;
    } catch {
      return null;
    }
  });
  const [selected, setSelected] = useState<StoreId | null>(null);
  // 시트가 열려 있는 동안만 기억한다(다시 열면 처음부터)
  const [opened, setOpened] = useState<Set<string>>(() => new Set());
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  // 쇼핑몰 이름·순서(지난번 맨 위)·광고 표시는 대표 품목 하나로 구한다(URL은 품목마다 따로 만든다)
  const onlyVerified = !import.meta.env.DEV;
  const stores = storeLinks(items[0].name, affiliates, { lastUsed, onlyVerified });

  const remember = (store: StoreId) => {
    try {
      localStorage.setItem(LAST_STORE_KEY, store);
    } catch {
      // 저장이 막힌 브라우저에서는 순서만 기억하지 못한다
    }
  };

  if (selected === null) {
    return (
      <Sheet title="어디서 살까요?" description={`고른 쇼핑몰에서 살 것 ${items.length}개를 차례로 찾아요`} onClose={onClose}>
        <div className="sh-storepick">
          {stores.map((s) => (
            <button
              key={s.store}
              type="button"
              className={s.store === lastUsed ? "sh-storepick-btn last" : "sh-storepick-btn"}
              onClick={() => {
                setSelected(s.store);
                setOpened(new Set());
              }}
            >
              <span className="sh-storepick-name">
                {s.name}
                {s.store === "naver" && <small>가격 비교</small>}
                {s.store === lastUsed && <small>지난번</small>}
              </span>
              {s.ad && <span className="sh-ad">광고</span>}
            </button>
          ))}
        </div>
      </Sheet>
    );
  }

  const store = stores.find((s) => s.store === selected)!;
  const firstToOpen = items.find((i) => !opened.has(i.key))?.key;
  const description = !online ? "인터넷이 연결되면 열려요" : `누르면 ${store.name} 검색 결과가 새 창으로 열려요`;

  return (
    <Sheet
      title={`${store.name}에서 찾기`}
      description={description}
      action={
        <button type="button" className="text-btn strong sh-changestore" onClick={() => setSelected(null)}>
          쇼핑몰 바꾸기
        </button>
      }
      onClose={onClose}
    >
      <div className="sh-find-progress">
        <span>
          {items.length}개 중 <b>{opened.size}개</b> 열어봤어요
        </span>
        <div className="sh-find-bar">
          <span style={{ width: `${(opened.size / items.length) * 100}%` }} />
        </div>
      </div>
      <ul className="sh-find-list">
        {items.map((item) => {
          const isOpen = opened.has(item.key);
          const url = storeLinks(item.name, affiliates, { onlyVerified }).find((s) => s.store === selected)!.links[0].url;
          return (
            <li key={item.key} className="sh-find-row">
              <span>
                <b>{item.name}</b>
                <small>{quantityText(item.quantity, item.unit)}</small>
              </span>
              {isOpen ? (
                <span className="sh-find-go done">
                  <Icon name="check" size={16} />
                  열어봤어요
                </span>
              ) : (
                <a
                  className={item.key === firstToOpen ? "sh-find-go next" : "sh-find-go"}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${store.name}${store.ad ? " 광고" : ""} ${item.name} 찾기 (새 창)`}
                  aria-disabled={online ? undefined : true}
                  onClick={(e) => {
                    if (!online) {
                      e.preventDefault(); // 인터넷이 없으면 열지 않는다(설명 줄이 안내)
                      return;
                    }
                    remember(selected);
                    setOpened((prev) => new Set(prev).add(item.key));
                  }}
                >
                  찾기
                  <Icon name="external" size={16} />
                </a>
              )}
            </li>
          );
        })}
      </ul>
      <p className="hint">산 건 장보기에서 체크하면 재고에 넣을 수 있어요.</p>
      {store.ad && (
        <p className="mo-note">
          <Icon name="info" size={16} />
          <span>
            ‘광고’가 붙은 쇼핑몰로 사면 갈무리부엌이 수수료를 받을 수 있어요.
            {/* 쿠팡 파트너스 이용 가이드의 경제적 이해관계 표시 문구를 화면 말투로 옮김(스펙 16절) */}
            {store.store === "coupang" && (
              <>
                <br />
                쿠팡 파트너스 활동의 일환으로, 쿠팡 링크로 사면 갈무리부엌이 일정액의 수수료를 받아요.
              </>
            )}
          </span>
        </p>
      )}
      <button type="button" className="btn secondary" onClick={onClose}>
        닫기
      </button>
    </Sheet>
  );
}
