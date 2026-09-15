import type { Video } from "../api";
import { formatDuration } from "../format";
import Icon from "./Icon";

/** 썸네일(없으면 자리 표시) + 오른쪽 아래 길이 배지. 영상 탭·식단 채우기 시트가 같이 쓴다 */
export default function VideoThumb({ video }: { video: Video }) {
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
