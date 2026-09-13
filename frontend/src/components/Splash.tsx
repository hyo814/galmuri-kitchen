import { useEffect } from "react";

interface Props {
  leaving: boolean;
  onGone: () => void;
}

export default function Splash({ leaving, onGone }: Props) {
  // 사라지는 전환(220ms) 뒤에 떼어 낸다. 동작 줄이기 설정이면 전환이 없어도 타이머로 떼어 낸다.
  useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(onGone, 260);
    return () => clearTimeout(timer);
  }, [leaving, onGone]);

  return (
    <div className={`splash${leaving ? " leaving" : ""}`} role="status" aria-label="갈무리부엌을 여는 중">
      <img className="splash-mark" src="/mark.svg" width="96" height="96" alt="" />
      <p className="splash-name">갈무리부엌</p>
      <p className="splash-tagline">사둔 재료, 남김없이 챙겨요</p>
    </div>
  );
}
