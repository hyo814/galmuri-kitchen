import { useEffect, useState } from "react";
import type { User, VideoDetail } from "../api";
import AddRecipeSheet from "../components/AddRecipeSheet";
import Icon from "../components/Icon";
import { timeAgo } from "../format";
import { useResource } from "../useResource";
import { BackLink } from "./RecipeDetail";
import { setRecipesSegment } from "./Recipes";

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

/** 원형 채널 썸네일, 없으면 이름 첫 글자 */
export function Avatar({ title, src }: { title: string; src: string | null }) {
  return (
    <span className="r3-avatar" aria-hidden="true">
      {src ? <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" /> : title.trim().charAt(0)}
    </span>
  );
}

/** 영상 보기: 유튜브 공식 삽입 플레이어 · 제목 · 채널 · 설명 앞부분 · 레시피로 가져오기 (시안 VideoPlay) */
export default function VideoPlayer({ id, user }: { id: string; user: User }) {
  const { data: video, error, status, reload } = useResource<VideoDetail>(`/api/videos/${id}`);
  const [importing, setImporting] = useState(false);
  useEffect(() => setRecipesSegment("video"), []); // 주소로 바로 열고 뒤로 가도 영상 칸으로

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

  const playable = user.videos === "on" && VIDEO_ID.test(video.video_id);
  const watchUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(video.video_id)}`;
  const [firstLine, ...rest] = (video.description ?? "").trim().split("\n");

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
            loading="lazy"
          />
        ) : (
          <>
            <span className="r3-player-msg">
              <span className="r3-play" aria-hidden="true">
                <Icon name="play" size={26} />
              </span>
              예시 영상이라 재생되지 않아요
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
              {timeAgo(video.published_at)} ·{" "}
              <a className="r3-yt-link" href={watchUrl} target="_blank" rel="noopener noreferrer">
                YouTube에서 보기
              </a>
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
          <button className="btn primary" onClick={() => setImporting(true)}>
            <Icon name="book" />
            레시피로 가져오기
          </button>
        </div>
      )}
      {importing && <AddRecipeSheet initialStep="link" initialUrl={watchUrl} onClose={() => setImporting(false)} />}
    </main>
  );
}
