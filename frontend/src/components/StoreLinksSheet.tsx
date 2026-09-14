import { useEffect, useState } from "react";
import type { User } from "../api";
import { LAST_STORE_KEY, storeLinks, type StoreId } from "../storeLinks";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  name: string;
  affiliates: User["shop_affiliates"];
  onClose: () => void;
}

/** 받침이 있으면(ㄹ 제외) "으로", 없으면 "로" */
function ro(word: string) {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  const final = code >= 0 && code < 11172 ? code % 28 : 0;
  return final && final !== 8 ? "으로" : "로";
}

/** 시안 StoreSheet: 쇼핑몰마다 정렬 칩(새 창 링크). 마지막으로 연 쇼핑몰이 다음에 맨 위 */
export default function StoreLinksSheet({ name, affiliates, onClose }: Props) {
  // 시트가 열려 있는 동안에는 순서가 바뀌지 않게 열 때 한 번만 읽는다
  const [lastUsed] = useState(() => {
    try {
      return localStorage.getItem(LAST_STORE_KEY) as StoreId | null;
    } catch {
      return null;
    }
  });
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

  // 폰에서 확인하기 전 주소는 운영 화면에 내보내지 않는다(개발 서버에서만 후보를 모두 보여준다)
  const stores = storeLinks(name, affiliates, { lastUsed, onlyVerified: !import.meta.env.DEV });
  const itemName = name.trim();
  const description = !online
    ? "인터넷이 연결되면 열려요"
    : stores.length
      ? "누르면 쇼핑몰 검색 결과로 이동해요. 결제는 쇼핑몰에서 해요."
      : undefined;

  const remember = (store: StoreId) => {
    try {
      localStorage.setItem(LAST_STORE_KEY, store);
    } catch {
      // 저장이 막힌 브라우저에서는 순서만 기억하지 못한다
    }
  };

  return (
    <Sheet title={`${itemName} 찾기`} description={description} onClose={onClose}>
      {stores.length === 0 ? (
        <p className="sh-stores-empty">쇼핑몰 링크를 준비하고 있어요</p>
      ) : (
        <div className="sh-stores">
          {stores.map((s) => (
            <div key={s.store} className="sh-store">
              <div className="sh-store-head">
                {s.name}
                {s.ad && <span className="sh-ad">광고</span>}
              </div>
              <div className="sh-sorts">
                {s.links.map((l, i) => (
                  <a
                    key={l.label}
                    className={i === 0 ? "first" : undefined}
                    href={l.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`${s.name}${s.ad ? " 광고" : ""} ${l.label}${ro(l.label)} ${itemName} 찾기 (새 창)`}
                    aria-disabled={online ? undefined : true}
                    onClick={(e) => {
                      if (online) remember(s.store);
                      else e.preventDefault(); // 인터넷이 없으면 열지 않는다(설명 줄이 안내)
                    }}
                  >
                    {l.label}
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {stores.some((s) => s.ad) && (
        <p className="mo-note">
          <Icon name="info" size={16} />
          <span>‘광고’가 붙은 링크로 사면 갈무리부엌이 수수료를 받을 수 있어요. 순서와는 상관없어요.</span>
        </p>
      )}
    </Sheet>
  );
}
