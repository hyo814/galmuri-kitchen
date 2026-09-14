/** 원형 채널 썸네일(외부 사진이라 리퍼러 없이), 없으면 이름 첫 글자 */
export default function Avatar({ title, src }: { title: string; src: string | null }) {
  return (
    <span className="r3-avatar" aria-hidden="true">
      {src ? <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" /> : title.trim().charAt(0)}
    </span>
  );
}
