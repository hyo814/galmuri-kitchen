import { useCallback, useEffect, useState } from "react";
import { api, type ChannelList, type Video, type VideoPage } from "../api";
import Icon from "../components/Icon";
import InfiniteSentinel from "../components/InfiniteSentinel";
import { formatDuration, timeAgo, withJosa } from "../format";
import { navigate } from "../useHashRoute";
import { useInfiniteList, type Page } from "../useInfiniteList";
import { useResource } from "../useResource";

// ponytail: 영상에서 돌아와도 고른 채널·검색어를 유지한다(Recipes의 lastSegment와 같은 모듈 변수). 목록 캐시 키와 스크롤도 그대로 맞는다.
let lastFilter: { channel: number | null; q: string } = { channel: null, q: "" };

export function resetVideoFilter() {
  lastFilter = { channel: null, q: "" };
}

/** 썸네일(없으면 자리 표시) + 오른쪽 아래 길이 배지 */
function Thumb({ video }: { video: Video }) {
  const duration = formatDuration(video.duration_seconds);
  return (
    <span className={video.thumbnail_url ? "r3-vthumb" : "r3-vthumb noimg"}>
      {video.thumbnail_url ? (
        <img src={video.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
      ) : (
        <Icon name="play" size={22} />
      )}
      {duration && <span className="dur">{duration}</span>}
    </span>
  );
}

/** 레시피 탭 `영상` 칸: 제목 검색 · 채널 칩 · 작은 썸네일 한 줄 목록 (시안 Videos) */
export default function Videos({ sample }: { sample: boolean }) {
  const [input, setInput] = useState(lastFilter.q);
  const [q, setQ] = useState(lastFilter.q);
  const [selected, setSelected] = useState(lastFilter.channel);
  const { data: channels } = useResource<ChannelList>("/api/channels");
  const chips = channels?.items.filter((c) => !c.hidden && !c.unavailable) ?? [];
  // 뺀·숨긴 채널을 고른 채였으면 전체로
  const channel = channels && !chips.some((c) => c.id === selected) ? null : selected;

  // 입력을 멈추고 300ms 뒤에 찾는다
  useEffect(() => {
    const timer = setTimeout(() => setQ(input.trim()), 300);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    lastFilter = { channel, q };
  }, [channel, q]);

  const fetchPage = useCallback(
    async (cursor: string | null): Promise<Page<Video>> => {
      const params = new URLSearchParams({ limit: "30" });
      if (cursor) params.set("cursor", cursor);
      if (channel !== null) params.set("channel", String(channel));
      if (q) params.set("q", q);
      const data = await api<VideoPage>(`/api/videos?${params}`);
      return { items: data.items, next: data.next_cursor };
    },
    [channel, q],
  );
  const { items, loading, error, hasMore, multiPage, loadMore, reload } = useInfiniteList<Video>(fetchPage, ["videos", channel, q]);
  const settled = !loading && !hasMore && !error;

  const noMatch = `제목에 「${q}」${withJosa(q, "이", "가").slice(q.length)} 들어간 영상이 없어요.`;
  let status = "";
  if (q && settled) status = items.length ? `영상 ${items.length}개를 찾았어요` : noMatch;

  return (
    <>
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(input.trim());
        }}
      >
        <label className="r3-search">
          <Icon name="search" size={20} />
          <span className="sr-only">영상 제목에서 찾기</span>
          <input type="search" placeholder="영상 제목에서 찾기" maxLength={50} enterKeyHint="search" value={input} onChange={(e) => setInput(e.target.value)} />
        </label>
      </form>

      <div className="r3-chips" role="group" aria-label="채널로 거르기">
        <button type="button" className="r3-fchip icon" onClick={() => navigate("/recipes/channels")}>
          <Icon name="sliders" size={16} />
          채널
        </button>
        <button type="button" className="r3-fchip" aria-pressed={channel === null} onClick={() => setSelected(null)}>
          전체
        </button>
        {chips.map((c) => (
          <button key={c.id} type="button" className="r3-fchip" aria-pressed={channel === c.id} onClick={() => setSelected(c.id)}>
            {c.title}
          </button>
        ))}
      </div>

      {sample && (
        <p className="rc-sample">
          <Icon name="info" size={16} />
          예시 영상으로 보여줘요
        </p>
      )}
      <p className="sr-only" role="status" aria-live="polite">
        {status}
      </p>

      {items.length === 0 ? (
        error ? (
          <div className="list-end">
            <p className="error" role="alert">
              {error}
            </p>
            <button className="btn secondary inline" onClick={reload}>
              <Icon name="refresh" size={16} />
              다시 불러오기
            </button>
          </div>
        ) : !settled ? (
          <p className="center muted">불러오는 중…</p>
        ) : (
          <section className="empty">
            <p>
              {q
                ? noMatch
                : channels && chips.length === 0
                  ? "채널을 추가하면 새 영상을 모아 보여줘요."
                  : "아직 모아 둔 영상이 없어요."}
            </p>
          </section>
        )
      ) : (
        <>
          <ul className="r3-vlist">
            {items.map((video) => (
              <li key={video.id}>
                <a
                  className="r3-vrow"
                  href={`#/recipes/videos/${video.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`/recipes/videos/${video.id}`);
                  }}
                >
                  <Thumb video={video} />
                  <span className="r3-vtext">
                    <span className="r3-vtitle">{video.title}</span>
                    <span className="r3-vsub">
                      {video.channel_title} · {timeAgo(video.published_at)}
                    </span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <InfiniteSentinel onVisible={loadMore} hasMore={hasMore} multiPage={multiPage} loading={loading} error={error} onRetry={loadMore} />
          <p className="r3-credit">YouTube 제공</p>
        </>
      )}
    </>
  );
}
