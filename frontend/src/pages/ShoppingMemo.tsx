// 시안 MemoPage `장보기 메모`(4단계 계획 Task 10) + 메모 목록. 저장 버튼 없이 입력이 1초 멈추면·화면을 나갈 때 저장한다.
import { useEffect, useRef, useState } from "react";
import Icon from "../components/Icon";
import Sheet from "../components/Sheet";
import {
  MAX_NOTES, MemoBackupNotice, PhotoImg, editedAfter, firstLine, matchesRef, newMemo, openMemo, refOf, savedMemoRef,
} from "../components/ShoppingMemoCard";
import { resizeImage } from "../image";
import type { Ref, ViewNote } from "../shopping/sync";
import { useShopping } from "../shopping/useShopping";
import { goBack } from "../useHashRoute";

const MAX_PHOTOS = 10;
const SAVE_DELAY_MS = 1000;

function BackLink() {
  return (
    <a
      className="back-link"
      href="#/shopping"
      onClick={(e) => {
        e.preventDefault();
        goBack("/shopping");
      }}
    >
      <Icon name="back" size={18} />
      장보기
    </a>
  );
}

/** `#/shopping/memos` */
export function ShoppingMemos() {
  const { view, act } = useShopping();
  const notes = view?.notes ?? [];
  const full = notes.length >= MAX_NOTES;
  return (
    <main className="page">
      <BackLink />
      <header className="topbar">
        <h1>장보기 메모</h1>
      </header>
      {notes.length > 0 && (
        <ul className="list sh-memo-list">
          {notes.map((note) => (
            <li key={note.client_id ?? note.id}>
              <button type="button" className="mo-row" onClick={() => openMemo(note)}>
                <span className="mo-ico">
                  <Icon name="memo" />
                </span>
                <span className="row-main">
                  <span className="row-title">{note.place || "메모"}</span>
                  <span className="row-sub">
                    {[firstLine(note.body), note.photos.length ? `사진 ${note.photos.length}장` : ""].filter(Boolean).join(" · ") || "빈 메모"}
                  </span>
                </span>
                <Icon name="chevron" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="rc-actions">
        <button type="button" className="btn outline" disabled={full} onClick={() => newMemo(act)}>
          <Icon name="plus" />
          새 메모
        </button>
        {full && <p className="hint">메모는 {MAX_NOTES}개까지 둘 수 있어요</p>}
      </div>
    </main>
  );
}

/** `#/shopping/memos/:id`(서버 메모) · `#/shopping/memos/new`(sessionStorage의 메모 — 기기에서 막 만든 메모도) */
export default function ShoppingMemo({ id }: { id?: string }) {
  const shopping = useShopping();
  const { view, act, addPhoto, photoBlob, failed, offline } = shopping;
  const [ref] = useState<Ref | null>(() => (id ? { id: Number(id) } : savedMemoRef()));
  const note = ref ? view?.notes.find((n) => matchesRef(n, ref)) : undefined;

  const [place, setPlace] = useState("");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [viewing, setViewing] = useState<number | null>(null);
  const [notFound, setNotFound] = useState(false);
  // 이 화면에 들어온 뒤 실패한 사진 올리기만 보여준다(예: 운영에서 사진 저장소가 꺼져 있을 때)
  const [seenFailed] = useState(() => new Set(failed.flatMap((f) => (f.op.op === "photo_add" ? [f.op.client_id] : []))));
  const fileRef = useRef<HTMLInputElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  /** 마지막으로 화면에 받아들이거나 보낸 메모 시각. 이보다 새 서버 메모(다른 기기)만 입력칸에 덮어쓴다 */
  const synced = useRef<string | null>(null);
  const busy = useRef(0);
  const deleted = useRef(false);
  const latest = useRef({ note, place, body, offline });
  latest.current = { note, place, body, offline };

  useEffect(() => {
    if (!note || saveTimer.current) return; // 쓰는 중이면 쓰는 글이 앞선다
    if (synced.current && Date.parse(note.updated_at) <= Date.parse(synced.current)) return;
    synced.current = note.updated_at;
    setPlace(note.place ?? "");
    setBody(note.body);
  }, [note?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (note) return;
    const timer = setTimeout(() => setNotFound(true), 1500); // 방금 만든 메모가 기기 저장소에 들어갈 때까지
    return () => clearTimeout(timer);
  }, [!!note]); // eslint-disable-line react-hooks/exhaustive-deps

  function save() {
    clearTimeout(saveTimer.current);
    saveTimer.current = undefined;
    const { note, place, body, offline } = latest.current;
    if (!note || deleted.current) return;
    if ((note.place ?? "").trim() === place.trim() && note.body === body) return;
    const edited_at = editedAfter(note);
    synced.current = edited_at;
    act({ op: "note_save", ref: refOf(note), fields: { place: place.trim() || null, body }, edited_at });
    setStatus(offline ? "연결되면 저장돼요" : "저장했어요");
  }

  function edit(next: { place?: string; body?: string }) {
    if (next.place !== undefined) setPlace(next.place);
    if (next.body !== undefined) setBody(next.body);
    setStatus("");
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(save, SAVE_DELAY_MS);
  }

  // 나갈 때: 쓰던 글 저장, 글도 사진도 없으면 메모를 지운다(빈 메모가 쌓이지 않게).
  // setTimeout: StrictMode의 가짜 언마운트에서는 다시 마운트되며 취소된다
  useEffect(() => {
    clearTimeout(leaveTimer.current);
    const onHide = () => {
      if (document.visibilityState === "hidden" && saveTimer.current) save();
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      leaveTimer.current = setTimeout(() => {
        if (saveTimer.current) save();
        const { note, place, body } = latest.current;
        if (note && !deleted.current && !busy.current && !place.trim() && !body.trim() && !note.photos.length)
          act({ op: "note_delete", ref: refOf(note), at: new Date().toISOString() });
      }, 0);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function pickPhotos(files: File[]) {
    const current = latest.current.note;
    if (!current || !files.length) return;
    const room = MAX_PHOTOS - current.photos.length;
    setPhotoHint(files.length > room ? `사진은 메모 하나에 ${MAX_PHOTOS}장까지 넣을 수 있어요` : "");
    busy.current++;
    try {
      // 긴 변 1568px JPEG로 다시 그려 올린다(용량 절약, 위치 같은 사진 정보도 빠진다)
      for (const file of files.slice(0, room)) addPhoto(refOf(current), await resizeImage(file));
    } finally {
      busy.current--;
    }
  }

  if (!note)
    return (
      <main className="page">
        <BackLink />
        {notFound ? (
          <div className="empty">
            <h1 className="sr-only">장보기 메모</h1>
            <p>메모를 찾을 수 없어요</p>
            <p className="muted">다른 기기에서 지웠을 수 있어요.</p>
          </div>
        ) : (
          <p className="center muted">불러오는 중…</p>
        )}
      </main>
    );

  const photos = note.photos;
  const photoErrors = [
    ...new Set(
      failed.flatMap((f) => (f.op.op === "photo_add" && !seenFailed.has(f.op.client_id) && matchesRef(note, f.op.note) ? [f.error] : [])),
    ),
  ];
  const shown = viewing === null ? undefined : photos[viewing];

  return (
    <main className="page">
      <BackLink />
      <header className="topbar">
        <h1>장보기 메모</h1>
      </header>
      <MemoBackupNotice shopping={shopping} note={note} />

      <section className="rc-sec rc-form">
        <div className="field">
          <label className="field-label" htmlFor="memo-place">
            어디서
          </label>
          <input
            id="memo-place"
            className="input"
            value={place}
            maxLength={30}
            placeholder="이마트 성수점"
            onChange={(e) => edit({ place: e.target.value })}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="memo-body">
            메모
          </label>
          <textarea
            id="memo-body"
            className="input rc-area"
            value={body}
            maxLength={2000}
            rows={3}
            onChange={(e) => edit({ body: e.target.value })}
          />
          <p className="hint" role="status">
            {status}
          </p>
        </div>
      </section>

      <section className="rc-sec" aria-labelledby="memo-photos-title">
        <div className="rc-sec-head">
          <h2 id="memo-photos-title">사진</h2>
          <span className="hint">
            {photos.length} / {MAX_PHOTOS}
          </span>
        </div>
        {/* capture 속성 없음: 폰이 카메라·앨범 중에서 고르게 한다(ScanSheet와 같은 사용자 결정 2026-09-13) */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            const files = [...(e.target.files ?? [])];
            e.target.value = ""; // 같은 사진을 다시 골라도 change가 일어나게
            void pickPhotos(files);
          }}
        />
        <div className="sh-photos">
          {photos.map((photo, i) => (
            <button key={photo.client_id ?? photo.id} type="button" className="sh-photo" onClick={() => setViewing(i)}>
              <PhotoImg photo={photo} photoBlob={photoBlob} alt={`메모 사진 ${i + 1}`} />
              {photo.pending && <span className="sh-photo-pending">저장 전</span>}
            </button>
          ))}
          {photos.length < MAX_PHOTOS && (
            <button type="button" className="sh-photo add" onClick={() => fileRef.current?.click()}>
              <Icon name="camera" size={22} />
              사진 추가
            </button>
          )}
        </div>
        {(photoHint || photoErrors.length > 0) && (
          <p className="rc-err sh-photo-err" role="alert">
            <Icon name="alert" size={16} />
            {[photoHint, ...photoErrors].filter(Boolean).join(" · ")}
          </p>
        )}
        {photos.length > 0 && (
          // ponytail: Task 11(사진에서 살 것 뽑기)이 연결한다. 그 전에는 눌리지 않는다
          <button type="button" className="btn secondary sh-ai" disabled>
            <Icon name="sparkle" size={18} />
            사진에서 살 것 뽑기
          </button>
        )}
      </section>

      <div className="rc-actions">
        <button
          type="button"
          className="btn danger-text"
          onClick={() => {
            if (!confirm("메모와 사진을 삭제할까요?")) return;
            deleted.current = true;
            clearTimeout(saveTimer.current);
            saveTimer.current = undefined;
            act({ op: "note_delete", ref: refOf(note), at: new Date().toISOString() });
            goBack("/shopping");
          }}
        >
          메모 삭제
        </button>
      </div>

      {shown && viewing !== null && (
        <PhotoSheet
          note={note}
          index={viewing}
          onMove={setViewing}
          onClose={() => setViewing(null)}
          onDelete={() => {
            if (!confirm("사진을 삭제할까요?")) return;
            act({
              op: "photo_delete",
              note: refOf(note),
              photo: shown.id !== undefined ? { id: shown.id } : { client_id: shown.client_id! },
              at: new Date().toISOString(),
            });
            setViewing(null);
          }}
          photoBlob={photoBlob}
        />
      )}
    </main>
  );
}

function PhotoSheet({ note, index, onMove, onClose, onDelete, photoBlob }: {
  note: ViewNote; index: number; onMove: (i: number) => void; onClose: () => void; onDelete: () => void;
  photoBlob: ReturnType<typeof useShopping>["photoBlob"];
}) {
  const photo = note.photos[index];
  const count = note.photos.length;
  return (
    <Sheet title={`사진 ${index + 1} / ${count}`} className="sh-viewer" onClose={onClose}>
      <div className="sh-viewer-img">
        <PhotoImg key={photo.client_id ?? photo.id} photo={photo} photoBlob={photoBlob} alt={`메모 사진 ${index + 1}`} />
      </div>
      {count > 1 && (
        <div className="sh-viewer-nav">
          <button type="button" className="btn outline" disabled={index === 0} onClick={() => onMove(index - 1)}>
            <Icon name="back" size={18} />
            이전 사진
          </button>
          <button type="button" className="btn outline" disabled={index === count - 1} onClick={() => onMove(index + 1)}>
            다음 사진
            <Icon name="chevron" size={18} />
          </button>
        </div>
      )}
      <button type="button" className="btn danger-text" onClick={onDelete}>
        사진 삭제
      </button>
    </Sheet>
  );
}
