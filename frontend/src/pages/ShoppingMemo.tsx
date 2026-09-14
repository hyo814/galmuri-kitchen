// 시안 MemoPage `장보기 메모`(4단계 계획 Task 10) + 메모 목록. 저장 버튼 없이 입력이 1초 멈추면·화면을 나갈 때 저장한다.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { AiUsage, User } from "../api";
import Icon from "../components/Icon";
import MemoScanReview from "../components/MemoScanReview";
import Sheet from "../components/Sheet";
import {
  MAX_NOTES, MemoBackupNotice, PhotoImg, editedAfter, firstLine, matchesRef, newMemo, openMemo, refOf, savedMemoRef,
} from "../components/ShoppingMemoCard";
import { resizeImage } from "../image";
import type { Ref, ViewNote, ViewPhoto } from "../shopping/sync";
import { useShopping } from "../shopping/useShopping";
import { goBack, navigate } from "../useHashRoute";
import { useResource } from "../useResource";
import { showShoppingNotice } from "./Shopping";

const MAX_PHOTOS = 10;
const MAX_PHOTO_BYTES = 3 * 1024 * 1024; // 서버 한 장 상한
const SAVE_DELAY_MS = 1000;
/** 서버 503(사진 저장소 꺼짐) 문구의 바뀌지 않는 부분(backend/app/shopping.py `사진을 지금은 올릴 수 없어요.`).
 *  ponytail: 실패 목록(FailedOp)에 상태 코드가 없어 문구로 알아본다 — 문구를 바꾸면 여기도, 늘어나면 FailedOp에 status를 넣는다 */
const STORAGE_OFF_TEXT = "지금은 올릴 수 없어요";

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
  const { view } = useShopping();
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
      {view && notes.length === 0 && <p className="center muted">아직 쓴 메모가 없어요</p>}
      <div className="rc-actions">
        <button type="button" className="btn outline" disabled={full} onClick={() => navigate("/shopping/memos/new")}>
          <Icon name="plus" />
          새 메모
        </button>
        {full && <p className="hint">메모는 {MAX_NOTES}개까지 둘 수 있어요</p>}
      </div>
    </main>
  );
}

/** `#/shopping/memos/new`: 빈 메모를 만들고 `#/shopping/memos/local`로 바꾼다(뒤로가기에 남지 않게) */
export function NewShoppingMemo() {
  const { act } = useShopping();
  const created = useRef(false); // StrictMode 이중 실행에 두 개 만들지 않게
  useEffect(() => {
    if (created.current) return;
    created.current = true;
    newMemo(act);
  }, [act]);
  return (
    <main className="page">
      <p className="center muted">불러오는 중…</p>
    </main>
  );
}

/** `#/shopping/memos/:id`(서버 메모) · `#/shopping/memos/local`(sessionStorage의 메모 — 기기에서 막 만든 메모도) */
export default function ShoppingMemo({ id, user }: { id?: string; user: User }) {
  const shopping = useShopping();
  const { view, act, addPhoto, photoBlob, failed, offline, keepBackup } = shopping;
  const [ref] = useState<Ref | null>(() => (id ? { id: Number(id) } : savedMemoRef()));
  const note = ref ? view?.notes.find((n) => matchesRef(n, ref)) : undefined;

  const [place, setPlace] = useState("");
  const [body, setBody] = useState("");
  const [dirty, setDirty] = useState(false);
  /** 쓰는 중에 다른 기기에서 고친 메모가 들어왔다 — 입력칸을 덮지 않고 알린다 */
  const [held, setHeld] = useState(false);
  const [heldOpen, setHeldOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [announce, setAnnounce] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [viewing, setViewing] = useState<number | null>(null);
  const [notFound, setNotFound] = useState(false);
  /** 사진에서 살 것 뽑기: 사진 고르기 시트 → 읽는 사진 */
  const [scan, setScan] = useState<"choose" | { image: Blob } | null>(null);
  const [scanHint, setScanHint] = useState("");
  const { data: usage, reload: reloadUsage } = useResource<AiUsage>("/api/ai-usage");
  const scanFileRef = useRef<HTMLInputElement>(null);
  // 이 화면에 들어온 뒤 실패한 사진 올리기만 보여준다(예: 운영에서 사진 저장소가 꺼져 있을 때)
  const [seenFailed] = useState(() => new Set(failed.flatMap((f) => (f.op.op === "photo_add" ? [f.op.client_id] : []))));
  const fileRef = useRef<HTMLInputElement>(null);
  const addRef = useRef<HTMLButtonElement>(null);
  const photosTitleRef = useRef<HTMLHeadingElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  /** 화면이 받아들인(입력칸에 반영했거나 이 기기에서 보낸) 메모 시각. 저장 시각은 늘 이것보다 늦게 */
  const synced = useRef<string | null>(null);
  /** 한 번 쓰기(입력칸에 들어와 나갈 때까지)에 `저장했어요`는 한 번만 읽어 준다 */
  const announced = useRef(false);
  /** 마지막으로 따로 보관한 기기 글(같은 글을 두 번 보관하지 않게) */
  const kept = useRef("");
  const busy = useRef(0);
  const deleted = useRef(false);
  const latest = useRef({ note, place, body, offline, dirty, held });
  latest.current = { note, place, body, offline, dirty, held };

  const adopt = (n: ViewNote) => {
    synced.current = n.updated_at;
    setPlace(n.place ?? "");
    setBody(n.body);
    setHeld(false);
  };

  // useLayoutEffect: 새 서버 메모를 받아들이기 전에 알림이 한 번 그려지지 않게
  useLayoutEffect(() => {
    if (!note) return;
    if (!synced.current) return adopt(note);
    if (Date.parse(note.updated_at) <= Date.parse(synced.current)) {
      if (held) setHeld(false);
      return;
    }
    if (dirty) setHeld(true);
    else if (!held) adopt(note);
  }, [note?.updated_at, dirty, held]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (note) return;
    const timer = setTimeout(() => setNotFound(true), 1500); // 방금 만든 메모가 기기 저장소에 들어갈 때까지
    return () => clearTimeout(timer);
  }, [!!note]); // eslint-disable-line react-hooks/exhaustive-deps

  /** 이 기기에서 쓰던 글을 보내지 않고 따로 보관한다(서버 메모와 같거나 이미 보관한 글이면 건너뛴다) */
  function keepDeviceCopy() {
    const { note, place, body } = latest.current;
    if (!note || ((note.place ?? "").trim() === place.trim() && note.body === body)) return;
    const fields = { place: place.trim() || null, body };
    const key = JSON.stringify(fields);
    if (kept.current === key) return;
    kept.current = key;
    void keepBackup(refOf(note), fields);
  }

  function save() {
    clearTimeout(saveTimer.current);
    saveTimer.current = undefined;
    const { note, place, body, offline, dirty, held } = latest.current;
    if (!note || deleted.current || !dirty) return;
    latest.current.dirty = false;
    setDirty(false);
    // 받아들이지 않은 다른 기기 메모가 있으면 보내지 않고(대기열에 넣지 않고) 따로 보관만 한다
    if (held) return keepDeviceCopy();
    if ((note.place ?? "").trim() === place.trim() && note.body === body) return;
    const edited_at = editedAfter(synced.current ?? note.updated_at);
    synced.current = edited_at;
    void act({ op: "note_save", ref: refOf(note), fields: { place: place.trim() || null, body }, edited_at });
    const text = offline ? "연결되면 저장돼요" : "저장했어요";
    setStatus(text);
    if (!announced.current) {
      announced.current = true;
      setAnnounce(text);
    }
  }

  function edit(next: { place?: string; body?: string }) {
    if (next.place !== undefined) setPlace(next.place);
    if (next.body !== undefined) setBody(next.body);
    if (!announced.current) setAnnounce(""); // 같은 문구도 이번 쓰기에서 다시 읽히게
    latest.current.dirty = true;
    setDirty(true);
    clearTimeout(saveTimer.current);
    // 다른 기기 메모를 어떻게 할지 고르기 전에는 자동 저장하지 않는다(앱을 숨기거나 나갈 때 따로 보관된다)
    saveTimer.current = latest.current.held ? undefined : setTimeout(save, SAVE_DELAY_MS);
  }

  /** 입력칸을 나갈 때: 쓰던 글을 저장하고, 다음 쓰기에서 `저장했어요`를 다시 한 번 읽어 준다 */
  function blur() {
    if (!latest.current.held) save();
    announced.current = false;
  }

  // 나갈 때: 쓰던 글 저장, 글도 사진도 없으면 메모를 지운다(빈 메모가 쌓이지 않게).
  // setTimeout: StrictMode의 가짜 언마운트에서는 다시 마운트되며 취소된다
  useEffect(() => {
    clearTimeout(leaveTimer.current);
    const onHide = () => {
      if (document.visibilityState === "hidden") save();
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      leaveTimer.current = setTimeout(() => {
        save();
        const { note, place, body } = latest.current;
        if (note && !deleted.current && !busy.current && !place.trim() && !body.trim() && !note.photos.length)
          void act({ op: "note_delete", ref: refOf(note), at: new Date().toISOString() });
      }, 0);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function pickPhotos(files: File[]) {
    const current = latest.current.note;
    if (!current || !files.length) return;
    const room = MAX_PHOTOS - current.photos.length;
    const hints = new Set<string>();
    if (files.length > room) hints.add(`사진은 메모 하나에 ${MAX_PHOTOS}장까지 넣을 수 있어요.`);
    setPhotoHint("");
    busy.current++; // 기기에 넣는 동안 나가도 메모를 지우지 않게
    try {
      for (const file of files.slice(0, room)) {
        const out = await resizeImage(file);
        // 긴 변 1568px JPEG로 다시 그린 것만 올린다. 못 읽으면 resizeImage가 원본을 돌려주는데, 원본에는 위치 같은 사진 정보가 남아 있을 수 있어 올리지 않는다
        if (out === file || out.size > MAX_PHOTO_BYTES) {
          hints.add("이 사진은 올릴 수 없어요. 다른 사진을 골라주세요.");
          continue;
        }
        await addPhoto(refOf(current), out);
      }
    } finally {
      busy.current--;
      setPhotoHint([...hints].join(" "));
    }
  }

  function startScan() {
    const photos = latest.current.note?.photos ?? [];
    if (latest.current.offline) return setScanHint("인터넷이 연결되면 읽을 수 있어요");
    setScanHint("");
    if (!photos.length) scanFileRef.current?.click(); // 메모에 사진이 없으면 읽을 사진만 고른다(메모에 넣지는 않는다)
    else if (photos.length === 1) void scanPhoto(photos[0]);
    else setScan("choose");
  }

  async function scanPhoto(photo: ViewPhoto) {
    setScan(null);
    const blob = await photoBlob(photo);
    if (blob) setScan({ image: blob });
    else setScanHint("사진을 불러오지 못했어요. 다시 시도해주세요.");
  }

  if (!note)
    return (
      <main className="page">
        <BackLink />
        {notFound ? (
          <>
            <div className="empty">
              <h1 className="sr-only">장보기 메모</h1>
              <p>메모를 찾을 수 없어요</p>
              <p className="muted">다른 기기에서 지웠을 수 있어요.</p>
            </div>
            <MemoBackupNotice shopping={shopping} />
          </>
        ) : (
          <p className="center muted">불러오는 중…</p>
        )}
      </main>
    );

  const photos = note.photos;
  const newFailures = failed.filter((f) => f.op.op === "photo_add" && !seenFailed.has(f.op.client_id) && matchesRef(note, f.op.note));
  const photoErrors = newFailures.length
    ? ["사진은 저장되지 않았어요.", ...new Set(newFailures.map((f) => (f.error.includes(STORAGE_OFF_TEXT) ? "사진 저장은 지금 쓸 수 없어요." : f.error)))]
    : [];
  const shown = viewing === null ? undefined : photos[viewing];

  return (
    <main className="page">
      <BackLink />
      <header className="topbar">
        <h1>장보기 메모</h1>
      </header>
      {held && (
        <p className="sh-memo-notice">
          <Icon name="info" size={18} />
          <span>다른 기기에서 고친 내용이 있어요</span>
          <button type="button" onClick={() => setHeldOpen(true)}>
            보기
          </button>
        </p>
      )}
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
            onBlur={blur}
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
            onBlur={blur}
          />
          <p className="hint" aria-hidden="true">
            {held ? "" : dirty ? "저장 중…" : status}
          </p>
          <p className="sr-only" role="status">
            {announce}
          </p>
        </div>
      </section>

      <section className="rc-sec" aria-labelledby="memo-photos-title">
        <div className="rc-sec-head">
          <h2 id="memo-photos-title" ref={photosTitleRef} tabIndex={-1}>
            사진
          </h2>
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
            <button ref={addRef} type="button" className="sh-photo add" onClick={() => fileRef.current?.click()}>
              <Icon name="camera" size={22} />
              사진 추가
            </button>
          )}
        </div>
        {(photoHint || photoErrors.length > 0) && (
          <p className="rc-err sh-photo-err" role="alert">
            <Icon name="alert" size={16} />
            {[photoHint, ...photoErrors].filter(Boolean).join(" ")}
          </p>
        )}
        {user.scan !== "off" && (
          <>
            <input
              ref={scanFileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) setScan({ image: file });
              }}
            />
            <button type="button" className="btn secondary sh-ai" onClick={startScan}>
              <Icon name="sparkle" size={18} />
              사진에서 살 것 뽑기
            </button>
            {user.scan === "on" && usage && (
              <p className="hint sh-ai-hint">
                {usage.scan.used < usage.scan.limit ? `오늘 ${usage.scan.limit - usage.scan.used}번 남음` : "오늘은 다 썼어요"}
              </p>
            )}
            <p className="rc-err sh-ai-hint" role="status">
              {scanHint}
            </p>
          </>
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
            void act({ op: "note_delete", ref: refOf(note), at: new Date().toISOString() });
            goBack("/shopping");
          }}
        >
          메모 삭제
        </button>
      </div>

      {heldOpen && (
        <Sheet title="어느 글로 둘까요?" description="이 기기에서 쓰는 동안 다른 기기에서 먼저 고친 메모가 있어요." onClose={() => setHeldOpen(false)}>
          <div className="sh-compare">
            <p className="field-label">다른 기기에서 고친 메모</p>
            <div className="sh-backup">
              {note.place && <p className="sh-memo-title">{note.place}</p>}
              <p>{note.body || "내용이 없어요"}</p>
            </div>
            <p className="field-label">이 기기에서 쓰던 글</p>
            <div className="sh-backup">
              {place.trim() && <p className="sh-memo-title">{place.trim()}</p>}
              <p>{body || "내용이 없어요"}</p>
            </div>
          </div>
          <div className="rc-actions sh-backup-actions">
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                keepDeviceCopy(); // 쓰던 글은 따로 보관(메모 위 알림에서 다시 볼 수 있다)
                clearTimeout(saveTimer.current);
                saveTimer.current = undefined;
                latest.current.dirty = false;
                setDirty(false);
                adopt(note); // 이후 쓰는 글은 이 버전을 바탕으로 저장된다
                setHeldOpen(false);
              }}
            >
              다른 기기 글로 바꾸기
            </button>
            <button
              type="button"
              className="btn outline"
              onClick={() => {
                if (!confirm("다른 기기에서 고친 내용이 사라지고 이 기기에서 쓰던 글로 바뀌어요. 덮어쓸까요?")) return;
                synced.current = note.updated_at; // 본 버전보다 늦은 시각으로 쓰던 글을 저장한다
                latest.current.held = false;
                latest.current.dirty = true;
                setHeld(false);
                setHeldOpen(false);
                save();
              }}
            >
              쓰던 글로 덮어쓰기
            </button>
          </div>
        </Sheet>
      )}

      {scan === "choose" && (
        <Sheet title="어느 사진에서 뽑을까요?" onClose={() => setScan(null)}>
          <div className="sh-photos">
            {photos.map((photo, i) => (
              <button key={photo.client_id ?? photo.id} type="button" className="sh-photo" aria-label={`메모 사진 ${i + 1}에서 뽑기`} onClick={() => void scanPhoto(photo)}>
                <PhotoImg photo={photo} photoBlob={photoBlob} alt="" />
              </button>
            ))}
          </div>
        </Sheet>
      )}

      {scan && scan !== "choose" && (
        <MemoScanReview
          image={scan.image}
          sourceLabel={note.place?.trim() || "장보기 메모"}
          listed={view?.items.map((i) => i.name) ?? []}
          today={view?.today ?? ""}
          onScanned={() => void reloadUsage()}
          onDone={(text) => {
            showShoppingNotice(text);
            navigate("/shopping", { replace: true });
          }}
          onClose={() => setScan(null)}
        />
      )}

      {shown && viewing !== null && (
        <PhotoSheet
          note={note}
          index={viewing}
          onMove={setViewing}
          onClose={() => setViewing(null)}
          onDelete={() => {
            if (!confirm("사진을 삭제할까요?")) return;
            void act({
              op: "photo_delete",
              note: refOf(note),
              photo: shown.id !== undefined ? { id: shown.id } : { client_id: shown.client_id! },
              at: new Date().toISOString(),
            });
            setViewing(null);
            // 시트가 닫히며 지운 사진 칸으로 돌아가지 않게
            setTimeout(() => (addRef.current ?? photosTitleRef.current)?.focus(), 0);
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
  const first = index === 0;
  const last = index === count - 1;
  return (
    <Sheet title={`사진 ${index + 1} / ${count}`} className="sh-viewer" onClose={onClose}>
      <div className="sh-viewer-img">
        <PhotoImg key={photo.client_id ?? photo.id} photo={photo} photoBlob={photoBlob} alt={`메모 사진 ${index + 1}`} />
      </div>
      {count > 1 && (
        // aria-disabled: 끝에 닿아도 포커스가 버튼에 남게
        <div className="sh-viewer-nav">
          <button type="button" className="btn outline" aria-disabled={first} onClick={() => !first && onMove(index - 1)}>
            <Icon name="back" size={18} />
            이전 사진
          </button>
          <button type="button" className="btn outline" aria-disabled={last} onClick={() => !last && onMove(index + 1)}>
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
