import { useState } from "react";
import { ApiError, api, type ShoppingItem, type ShoppingSource } from "../api";
import { withJosa } from "../format";
import { forgetResources } from "../useResource";
import Icon from "./Icon";

const BULK_MAX = 50; // 서버 한 번에 담기 상한
const OFFLINE = "인터넷이 연결되면 담을 수 있어요";

/** 이모지(서로게이트 쌍)를 반으로 자르지 않게 글자 단위로 자른다 */
export const cut = (s: string, n: number) => Array.from(s).slice(0, n).join("");

interface Props {
  source: ShoppingSource;
  sourceLabel?: string;
  items: { name: string; quantity?: number; unit?: string }[];
  /** 버튼 글자, 예: `없는 재료 2개 장보기에 담기` */
  label: string;
  className?: string;
  /** `장보기 보기`로 떠나기 전 확인(작성 중인 폼). false면 머문다 */
  canLeave?: () => boolean;
}

/** 레시피 없는 재료·떨어진 필수품·재료 고치기에서 장보기에 한 번에 담는다. 이미 목록에 있는 이름은 서버가 건너뛴다(시안 RecipeEntry) */
export default function ShoppingAddButton({ source, sourceLabel, items, label, className = "", canLeave }: Props) {
  // 담을 것(이름·출처)이 바뀌면 다시 담을 수 있고 옛 결과도 숨긴다
  const key = JSON.stringify([source, sourceLabel ?? null, items.map((i) => i.name)]);
  const [doneKey, setDoneKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ key: string; text: string; error: boolean } | null>(null);
  const done = doneKey === key;
  const shown = message?.key === key ? message : null;

  const add = async () => {
    if (busy || done) return;
    const show = (text: string, error: boolean) => setMessage({ key, text, error });
    // ponytail: 온라인 API만 쓴다. 장보기 오프라인 보관(useShopping)이 들어오면 그 addMany로 바꿔 오프라인에서도 담게 한다.
    if (!navigator.onLine) {
      show(OFFLINE, true);
      return;
    }
    setBusy(true);
    setMessage(null);
    let created = 0;
    const skipped: string[] = [];
    try {
      for (let i = 0; i < items.length; i += BULK_MAX) {
        const res = await api<{ created: ShoppingItem[]; skipped: string[] }>("/api/shopping/items/bulk", {
          method: "POST",
          // 공공·AI 레시피는 제목·재료 이름이 서버 상한(60·50자)보다 길 수 있어 자른다
          body: {
            source,
            source_label: sourceLabel ? cut(sourceLabel, 60) : null,
            items: items.slice(i, i + BULK_MAX).map((item) => ({ ...item, name: cut(item.name, 50) })),
          },
        });
        created += res.created.length;
        skipped.push(...res.skipped);
      }
      const names = skipped.length > 3 ? `${skipped.slice(0, 3).join(", ")} 외 ${skipped.length - 3}개` : skipped.join(", ");
      const skippedText = skipped.length ? `이미 있는 ${withJosa(names, "은", "는")} 뺐어요` : "";
      show(created ? `장보기에 ${created}개 담았어요${skippedText ? ` · ${skippedText}` : ""}` : skippedText, false);
      setDoneKey(key);
    } catch (e) {
      let text = e instanceof ApiError && e.status === 0 ? OFFLINE : (e as Error).message;
      // 하나만 담을 때는 서버의 `1번째 재료: ` 앞말이 어색해 뺀다
      if (items.length === 1 && e instanceof ApiError && e.errors?.[0]) text = e.errors[0].error;
      show(created ? `${created}개는 담았어요 · ${text}` : text, true);
    } finally {
      if (created || skipped.length) forgetResources("/api/shopping");
      setBusy(false);
    }
  };

  return (
    <div className={`sh-add ${className}`}>
      <button type="button" className="btn outline" aria-disabled={busy || done} onClick={add}>
        <Icon name={done ? "check" : "cart"} size={20} />
        {busy ? "담는 중…" : done ? "장보기에 담았어요" : label}
      </button>
      <div role="status" className={shown ? (shown.error ? "error" : "sh-add-result") : undefined}>
        {shown && (
          <>
            <span>{shown.text}</span>
            {!shown.error && (
              <a
                className="r3-link"
                href="#/shopping"
                onClick={(e) => {
                  if (canLeave && !canLeave()) e.preventDefault();
                }}
              >
                장보기 보기
                <Icon name="chevron" size={16} />
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}
