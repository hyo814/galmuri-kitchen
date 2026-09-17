// 장보기 탭의 메모 카드(시안 ShoppingList `sh-memo`)와 메모 화면이 같이 쓰는 조각들(4단계 계획 Task 10).
import { useEffect, useState } from "react";
import { newClientId, type Ref, type ViewNote, type ViewPhoto } from "../shopping/sync";
import type { useShopping } from "../shopping/useShopping";
import { navigate } from "../useHashRoute";
import Icon from "./Icon";
import Sheet from "./Sheet";

export type Shopping = ReturnType<typeof useShopping>;

export const MAX_NOTES = 20;
/** `#/shopping/memos/local`이 열 메모(서버 id가 아직 없는 메모도 열리게, 새로고침에도 남게) */
const MEMO_REF_KEY = "shopping-memo-ref";

/** 새 변경은 서버 id를 알면 id로 보낸다(client_id로 보내면 이미 올라간 메모를 찾지 못한다) */
export const refOf = (note: ViewNote): Ref => (note.id !== undefined ? { id: note.id } : { client_id: note.client_id! });

export const matchesRef = (note: ViewNote, ref: Ref) => ("id" in ref ? note.id === ref.id : note.client_id === ref.client_id);

/** 화면이 받아들인 메모 시각(based)보다 늦은 시각으로 저장한다 — 다른 기기 시계가 앞서 있어도 본 메모를 고친 게 겹침(409)이 되지 않게.
 *  화면이 받아들이지 않은 서버 메모 시각을 넣으면 진짜 겹침도 덮어쓰니 based는 늘 화면에 반영한 버전 */
export const editedAfter = (based: string) => new Date(Math.max(Date.now(), Date.parse(based) + 1)).toISOString();

export const firstLine = (body: string) => body.split("\n").find((line) => line.trim())?.trim() ?? "";

export function savedMemoRef(): Ref | null {
  try {
    return JSON.parse(sessionStorage.getItem(MEMO_REF_KEY) ?? "null") as Ref | null;
  } catch {
    return null;
  }
}

function openRef(ref: Ref, replace = false) {
  if ("id" in ref) return navigate(`/shopping/memos/${ref.id}`, { replace });
  try {
    sessionStorage.setItem(MEMO_REF_KEY, JSON.stringify(ref));
  } catch {
    // ponytail: sessionStorage를 못 쓰면 이 메모는 목록에서 다시 연다
  }
  navigate("/shopping/memos/local", { replace });
}

export const openMemo = (note: ViewNote) => openRef(refOf(note));

/** `#/shopping/memos/new`에서: 빈 메모를 기기에 넣은 뒤 그 자리를 메모 화면으로 바꾼다(오프라인에서도).
 *  메모 화면은 나갈 때 빈 메모를 지우는데, 메모가 기기에 들어가기 전에 열었다 나가면 메모를 못 봐서 빈 메모가 남았다.
 *  그래서 넣은 뒤에 연다. 그사이 이 화면을 나갔으면(here가 false) 연 적 없는 빈 메모이니 지운다(아직 안 보낸 추가면 요청 없이 사라진다) */
export function newMemo(act: Shopping["act"], here: () => boolean) {
  const client_id = newClientId();
  const open = () => here() && openRef({ client_id }, true);
  void act({ op: "note_add", client_id, fields: { place: null, body: "" }, at: new Date().toISOString() }).then(
    () => (here() ? open() : act({ op: "note_delete", ref: { client_id }, at: new Date().toISOString() })),
    open, // 기기에 못 넣었으면 전처럼 메모 화면이 `메모를 찾을 수 없어요`를 보여준다
  );
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

/** 다른 기기와 겹쳐 이 기기에서 쓴 내용을 따로 보관했을 때(스펙 19절) 한 줄 알림 + 보관본 시트.
 *  메모가 아직 있으면 다른 기기가 먼저 고친 것(409), 없으면 다른 기기가 지운 것(404) */
export function MemoBackupNotice({ shopping, note }: { shopping: Shopping; note?: ViewNote }) {
  const { backups, view, act, dismissBackup } = shopping;
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  // 가장 최근 보관본. 메모 화면에서는 그 메모의 것만
  let index = -1;
  backups.forEach((b, i) => {
    if (!note || matchesRef(note, b.note_ref)) index = i;
  });
  const backup = backups[index];
  if (!backup) return null;
  const target = view?.notes.find((n) => matchesRef(n, backup.note_ref));

  const restore = async () => {
    if (!target && (view?.notes.length ?? 0) >= MAX_NOTES) {
      setError(`메모는 ${MAX_NOTES}개까지 둘 수 있어요. 다른 메모를 지운 뒤 다시 해주세요.`);
      return; // 보관본은 그대로 둔다
    }
    // 사용자가 보관본을 고른 것이니 지금 서버 메모보다 늦은 시각으로 덮는다
    if (target) await act({ op: "note_save", ref: refOf(target), fields: backup.fields, edited_at: editedAfter(target.updated_at) });
    else await act({ op: "note_add", client_id: newClientId(), fields: backup.fields, at: new Date().toISOString() });
    dismissBackup(index); // 기기 대기열에 들어간 뒤에 지운다
    setOpen(false);
  };

  return (
    <>
      <p className="sh-memo-notice">
        <Icon name="info" size={18} />
        <span>{target ? "다른 기기에서 고친 메모가 있어서 이 기기에서 쓴 내용을 따로 보관했어요" : "다른 기기에서 지운 메모예요"}</span>
        <button type="button" onClick={() => setOpen(true)}>
          {target ? "보기" : "내 글 보기"}
        </button>
      </p>
      {open && (
        <Sheet
          title="이 기기에서 쓴 메모"
          description={target ? "다른 기기에서 먼저 고친 메모가 있어서 따로 보관했어요." : "다른 기기에서 지운 메모라 따로 보관했어요."}
          onClose={() => {
            setOpen(false);
            setError("");
          }}
        >
          <div className="sh-backup">
            {backup.fields.place && <p className="sh-memo-title">{backup.fields.place}</p>}
            <p>{backup.fields.body || "내용이 없어요"}</p>
          </div>
          {error && (
            <p className="rc-err" role="alert">
              <Icon name="alert" size={16} />
              {error}
            </p>
          )}
          <div className="rc-actions sh-backup-actions">
            <button type="button" className="btn primary" onClick={() => void restore()}>
              {target ? "이걸로 바꾸기" : "새 메모로 살리기"}
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
        <button type="button" className="sh-memo sh-memo-new" onClick={() => navigate("/shopping/memos/new")}>
          <span className="mo-ico">
            <Icon name="memo" />
          </span>
          <span className="sh-memo-title">메모 쓰기</span>
        </button>
      )}
      <MemoBackupNotice shopping={shopping} />
      {/* 메모가 1개뿐이면 카드에는 그 메모 하나만 보여 새 메모를 쓸 길이 없었다 — 목록(거기 `새 메모` 버튼이 있다)으로 보낸다(리뷰 발견) */}
      {notes.length > 0 && (
        <button type="button" className="sh-memo-more" onClick={() => navigate("/shopping/memos")}>
          {notes.length > 1 ? `메모 ${notes.length - 1}개 더 보기` : "메모 목록 보기"}
          <Icon name="chevron" size={16} />
        </button>
      )}
    </div>
  );
}
