// 장보기 탭의 메모 카드(시안 ShoppingList `sh-memo`)와 메모 화면이 같이 쓰는 조각들(4단계 계획 Task 10).
import { useEffect, useState } from "react";
import { newClientId, type NoteFields, type Ref, type ViewNote, type ViewPhoto } from "../shopping/sync";
import type { useShopping } from "../shopping/useShopping";
import { navigate } from "../useHashRoute";
import Icon from "./Icon";
import Sheet from "./Sheet";

export type Shopping = ReturnType<typeof useShopping>;

export const MAX_NOTES = 20;
/** `#/shopping/memos/new`가 열 메모(서버 id가 아직 없는 메모도 열리게, 새로고침에도 남게) */
const MEMO_REF_KEY = "shopping-memo-ref";

/** 새 변경은 서버 id를 알면 id로 보낸다(client_id로 보내면 이미 올라간 메모를 찾지 못한다) */
export const refOf = (note: ViewNote): Ref => (note.id !== undefined ? { id: note.id } : { client_id: note.client_id! });

export const matchesRef = (note: ViewNote, ref: Ref) => ("id" in ref ? note.id === ref.id : note.client_id === ref.client_id);

/** 보고 있는 메모보다 늦은 시각으로 저장한다 — 다른 기기 시계가 앞서 있어도 방금 본 메모를 고친 게 겹침(409)이 되지 않게 */
export const editedAfter = (note: ViewNote) => new Date(Math.max(Date.now(), Date.parse(note.updated_at) + 1)).toISOString();

export const firstLine = (body: string) => body.split("\n").find((line) => line.trim())?.trim() ?? "";

export function savedMemoRef(): Ref | null {
  try {
    return JSON.parse(sessionStorage.getItem(MEMO_REF_KEY) ?? "null") as Ref | null;
  } catch {
    return null;
  }
}

function openRef(ref: Ref) {
  if ("id" in ref) return navigate(`/shopping/memos/${ref.id}`);
  try {
    sessionStorage.setItem(MEMO_REF_KEY, JSON.stringify(ref));
  } catch {
    // ponytail: sessionStorage를 못 쓰면 이 메모는 목록에서 다시 연다
  }
  navigate("/shopping/memos/new");
}

export const openMemo = (note: ViewNote) => openRef(refOf(note));

/** 빈 메모를 만들고 바로 연다(오프라인에서도) */
export function newMemo(act: Shopping["act"], fields: NoteFields = { place: null, body: "" }) {
  const client_id = newClientId();
  act({ op: "note_add", client_id, fields, at: new Date().toISOString() });
  openRef({ client_id });
}

/** 기기에 있는 사진(없으면 서버에서 받아 기기에 남긴다)을 보여준다 */
export function PhotoImg({ photo, photoBlob, alt }: { photo: ViewPhoto; photoBlob: Shopping["photoBlob"]; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    let url: string | null = null;
    void photoBlob(photo).then((blob) => {
      if (!live || !blob) return;
      url = URL.createObjectURL(blob);
      setSrc(url);
    });
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photo.blob_key, photo.id]);
  return src ? <img src={src} alt={alt} /> : <span className="sh-photo-ph" role={alt ? "img" : undefined} aria-label={alt || undefined} />;
}

/** 다른 기기에서 먼저 고친 메모가 있어 이 기기에서 쓴 내용을 따로 보관했을 때(스펙 19절) 한 줄 알림 + 보관본 시트 */
export function MemoBackupNotice({ shopping, note }: { shopping: Shopping; note?: ViewNote }) {
  const { backups, view, act, dismissBackup } = shopping;
  const [open, setOpen] = useState(false);
  // 메모 화면에서는 그 메모의 보관본만
  const index = backups.findIndex((b) => !note || matchesRef(note, b.note_ref));
  const backup = backups[index];
  if (!backup) return null;

  const restore = () => {
    const target = view?.notes.find((n) => matchesRef(n, backup.note_ref));
    if (target) act({ op: "note_save", ref: refOf(target), fields: backup.fields, edited_at: editedAfter(target) });
    else act({ op: "note_add", client_id: newClientId(), fields: backup.fields, at: new Date().toISOString() }); // 다른 기기에서 지운 메모
    dismissBackup(index);
    setOpen(false);
  };

  return (
    <>
      <p className="sh-memo-notice">
        <Icon name="info" size={18} />
        <span>다른 기기에서 먼저 고친 메모가 있어요</span>
        <button type="button" onClick={() => setOpen(true)}>
          보기
        </button>
      </p>
      {open && (
        <Sheet title="이 기기에서 쓴 메모" description="다른 기기에서 먼저 고친 메모가 있어서 따로 보관했어요." onClose={() => setOpen(false)}>
          <div className="sh-backup">
            {backup.fields.place && <p className="sh-memo-title">{backup.fields.place}</p>}
            <p>{backup.fields.body || "내용이 없어요"}</p>
          </div>
          <div className="rc-actions sh-backup-actions">
            <button type="button" className="btn primary" onClick={restore}>
              이걸로 바꾸기
            </button>
            <button
              type="button"
              className="btn danger-text"
              onClick={() => {
                if (!confirm("따로 보관한 메모를 지울까요?")) return;
                dismissBackup(index);
                setOpen(false);
              }}
            >
              지우기
            </button>
          </div>
        </Sheet>
      )}
    </>
  );
}

/** 시안 ShoppingList `sh-memo`: 가장 최근 메모 한 개 + `메모 N개 더 보기`. 메모가 없으면 `메모 쓰기` */
export default function ShoppingMemoCard({ shopping }: { shopping: Shopping }) {
  if (!shopping.view) return null;
  const notes = shopping.view.notes;
  const latest = notes[0];

  return (
    <div className="sh-memo-wrap">
      {latest ? (
        <button type="button" className="sh-memo" onClick={() => openMemo(latest)}>
          <span className="mo-ico">
            <Icon name="memo" />
          </span>
          <span className="sh-memo-body">
            <span className="sh-memo-title">{latest.place ? `메모 · ${latest.place}` : "메모"}</span>
            {firstLine(latest.body) && <span className="sh-memo-text">{firstLine(latest.body)}</span>}
            {latest.photos.length > 0 && (
              <span className="sh-thumbs">
                {latest.photos.slice(0, 2).map((photo) => (
                  <i key={photo.client_id ?? photo.id}>
                    <PhotoImg photo={photo} photoBlob={shopping.photoBlob} alt="" />
                  </i>
                ))}
              </span>
            )}
          </span>
          <Icon name="chevron" />
        </button>
      ) : (
        <button type="button" className="sh-memo sh-memo-new" onClick={() => newMemo(shopping.act)}>
          <span className="mo-ico">
            <Icon name="memo" />
          </span>
          <span className="sh-memo-title">메모 쓰기</span>
        </button>
      )}
      <MemoBackupNotice shopping={shopping} />
      {notes.length > 1 && (
        <button type="button" className="sh-memo-more" onClick={() => navigate("/shopping/memos")}>
          메모 {notes.length - 1}개 더 보기
          <Icon name="chevron" size={16} />
        </button>
      )}
    </div>
  );
}
