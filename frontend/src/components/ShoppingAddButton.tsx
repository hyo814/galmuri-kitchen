import { useState } from "react";
import { ApiError, api, type ShoppingItem, type ShoppingSource } from "../api";
import { withJosa } from "../format";
import { forgetResources } from "../useResource";
import Icon from "./Icon";

const BULK_MAX = 50; // 서버 한 번에 담기 상한
const OFFLINE = "인터넷이 연결되면 담을 수 있어요";

interface Props {
  source: ShoppingSource;
  sourceLabel?: string;
  items: { name: string; quantity?: number; unit?: string }[];
  /** 버튼 글자, 예: `없는 재료 2개 장보기에 담기` */
  label: string;
  className?: string;
}

/** 레시피 없는 재료·떨어진 필수품·재료 고치기에서 장보기에 한 번에 담는다. 이미 목록에 있는 이름은 서버가 건너뛴다(시안 RecipeEntry) */
export default function ShoppingAddButton({ source, sourceLabel, items, label, className = "" }: Props) {
  // 담은 목록(이름들)이 바뀌면 다시 담을 수 있게, 담았을 때의 이름들을 기억한다
  const key = items.map((i) => i.name).join("\n");
  const [doneKey, setDoneKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const done = doneKey === key;

  const add = async () => {
    if (busy) return;
    // ponytail: 온라인 API만 쓴다. 장보기 오프라인 보관(useShopping)이 들어오면 그 addMany로 바꿔 오프라인에서도 담게 한다.
    if (!navigator.onLine) {
      setMessage({ text: OFFLINE, error: true });
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
            source_label: sourceLabel?.slice(0, 60) ?? null,
            items: items.slice(i, i + BULK_MAX).map((item) => ({ ...item, name: item.name.slice(0, 50) })),
          },
        });
        created += res.created.length;
        skipped.push(...res.skipped);
      }
      const shown = skipped.length > 3 ? `${skipped.slice(0, 3).join(", ")} 외 ${skipped.length - 3}개` : skipped.join(", ");
      const skippedText = skipped.length ? `이미 있는 ${withJosa(shown, "은", "는")} 뺐어요` : "";
      setMessage({
        text: created ? `장보기에 ${created}개 담았어요${skippedText ? ` · ${skippedText}` : ""}` : skippedText,
        error: false,
      });
      setDoneKey(key);
    } catch (e) {
      setMessage({ text: e instanceof ApiError && e.status === 0 ? OFFLINE : (e as Error).message, error: true });
    } finally {
      if (created || skipped.length) forgetResources("/api/shopping");
      setBusy(false);
    }
  };

  return (
    <div className={`sh-add ${className}`}>
      <button type="button" className="btn outline" disabled={busy || done} onClick={add}>
        <Icon name={done ? "check" : "cart"} size={20} />
        {busy ? "담는 중…" : done ? "장보기에 담았어요" : label}
      </button>
      <div role="status" className={message ? (message.error ? "error" : "sh-add-result") : undefined}>
        {message && (
          <>
            <span>{message.text}</span>
            {!message.error && (
              <a className="r3-link" href="#/shopping">
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
