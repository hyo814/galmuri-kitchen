import { useEffect, useRef, useState } from "react";
import { ApiError, api, type RecipeDraft, type User, type VideoDetail } from "../api";
import AddRecipeSheet, { CaptureButton } from "../components/AddRecipeSheet";
import Avatar from "../components/Avatar";
import Icon from "../components/Icon";
import { timeAgo } from "../format";
import { navigate } from "../useHashRoute";
import { useResource } from "../useResource";
import { BackLink } from "./RecipeDetail";
import { openDraft } from "./RecipeForm";
import { setRecipesSegment } from "./Recipes";

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

/** 영상 보기: 유튜브 공식 삽입 플레이어 · 제목 · 채널 · 설명 앞부분 · 레시피로 가져오기 (시안 VideoPlay) */
export default function VideoPlayer({ id, user }: { id: string; user: User }) {
  const off = user.videos === "off";
  const { data: video, error, status, reload } = useResource<VideoDetail>(`/api/videos/${id}`);
  const [busy, setBusy] = useState(false);
  const [importError, setImportError] = useState("");
  // 링크를 못 읽은 이유(422 need_text) → 글 붙여넣기 시트. 한 번 못 읽으면 가져오기 아래에 화면 캡처로 가져오기를 계속 두고,
  // 누르면 링크를 다시 읽지 않고 사진 시트를 연다(시트를 닫고 영상을 멈춰 캡처한 뒤 돌아오게)
  const [needText, setNeedText] = useState("");
  const [sheet, setSheet] = useState<"text" | "photo" | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (off) navigate("/recipes", { replace: true }); // 영상을 쓸 수 없는데 주소로 바로 열었다
    else setRecipesSegment("video"); // 주소로 바로 열고 뒤로 가도 영상 칸으로
  }, [off]);
  useEffect(() => () => abortRef.current?.abort(), []); // 화면을 떠나면 가져오기도 멈춘다

  if (off) return null;
  if (!video)
    return (
      <main className="page">
        <BackLink label="영상" />
        {error ? (
          <div className="center">
            <p>{status === 404 ? "영상을 찾을 수 없어요." : error}</p>
            {status !== 404 && (
              <button className="btn secondary inline" onClick={reload}>
                <Icon name="refresh" size={16} />
                다시 불러오기
              </button>
            )}
          </div>
        ) : (
          <p className="center muted">불러오는 중…</p>
        )}
      </main>
    );

  const validId = VIDEO_ID.test(video.video_id);
  const playable = (user.videos === "on" || user.videos === "cached") && validId;
  const watchUrl = `https://www.youtube.com/watch?v=${video.video_id}`;
  // 예시 영상 ID는 가짜라 AI가 켜져 있으면(실제 가져오기) 보내지 않는다. AI도 예시 모드면 서버가 예시 초안을 준다.
  const sampleOnly = user.videos === "sample" && user.scan === "on";
  const importable = validId && !sampleOnly;
  const [firstLine, ...rest] = (video.description ?? "").trim().split("\n");

  const importRecipe = async () => {
    if (busy || !importable) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setImportError("");
    try {
      const draft = await api<RecipeDraft>("/api/recipes/import", { method: "POST", body: { url: watchUrl }, signal: controller.signal });
      if (!controller.signal.aborted) openDraft(draft);
    } catch (err) {
      if (controller.signal.aborted) return;
      setBusy(false);
      if (err instanceof ApiError && err.body?.need_text === true) {
        setNeedText(err.message);
        setSheet("text");
      } else setImportError((err as Error).message);
    }
  };

  return (
    <main className="page">
      <BackLink label="영상" />
      <div className="r3-player">
        {playable ? (
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${video.video_id}`}
            title={video.title}
            allow="accelerometer; encrypted-media; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        ) : (
          <>
            <span className="r3-player-msg">
              <span className="r3-play" aria-hidden="true">
                <Icon name="play" size={26} />
              </span>
              {user.videos === "sample" ? "예시 영상이라 재생되지 않아요" : "여기서는 재생할 수 없어요"}
            </span>
            <span className="r3-yt" aria-hidden="true">
              YouTube
            </span>
          </>
        )}
      </div>

      <header className="r3-vhead">
        <h1>{video.title}</h1>
        <div className="r3-chan">
          <Avatar title={video.channel_title} src={video.channel_thumbnail_url} />
          <span className="row-main">
            <span className="r3-chan-name">{video.channel_title}</span>
            <span className="r3-meta">
              {timeAgo(video.published_at)}
              {playable && (
                <>
                  {" · "}
                  <a className="r3-yt-link" href={watchUrl} target="_blank" rel="noopener noreferrer">
                    YouTube에서 보기<span className="sr-only">(새 창에서 열려요)</span>
                  </a>
                </>
              )}
            </span>
          </span>
        </div>
      </header>

      {firstLine && (
        <div className="r3-desc">
          <b>{firstLine}</b>
          {rest.length > 0 && <p>{rest.join("\n")}</p>}
        </div>
      )}

      {user.scan !== "off" && (
        <div className="cta-bar">
          <div className="r3-detail-save">
            {/* 정리하는 동안에도 같은 버튼(disabled 대신 aria-disabled)이라 포커스가 사라지지 않는다 */}
            <button
              type="button"
              className="btn primary"
              aria-busy={busy || undefined}
              aria-disabled={busy || !importable || undefined}
              aria-describedby={sampleOnly ? "video-import-note" : undefined}
              onClick={importRecipe}
            >
              <Icon name="book" />
              {busy ? "정리하는 중…" : "레시피로 가져오기"}
            </button>
            {sampleOnly && (
              <p className="hint r3-cta-note" id="video-import-note">
                예시 영상은 레시피로 가져올 수 없어요
              </p>
            )}
            {importError && (
              <p className="error" role="alert">
                {importError}
              </p>
            )}
            {needText && (
              <CaptureButton
                onPage
                onClick={() => {
                  // 가져오기를 다시 누른 채 열면 그 요청은 멈춘다 — 늦게 온 응답이 열린 사진 시트를 바꾸거나 초안으로 넘기지 않게
                  abortRef.current?.abort();
                  setBusy(false);
                  setSheet("photo");
                }}
              />
            )}
          </div>
        </div>
      )}
      {sheet && (
        <AddRecipeSheet
          initialStep={sheet}
          initialWarning={sheet === "text" ? needText : ""}
          failedLink={{ source: "youtube", source_url: watchUrl }}
          onClose={() => setSheet(null)}
        />
      )}
    </main>
  );
}
