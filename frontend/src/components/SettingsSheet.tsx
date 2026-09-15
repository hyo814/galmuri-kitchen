import Icon from "./Icon";
import Sheet from "./Sheet";
import { navigate } from "../useHashRoute";

export type SettingsTarget = "locations" | "staples";

const MENU: { target: SettingsTarget; label: string }[] = [
  { target: "locations", label: "보관 위치" },
  { target: "staples", label: "필수품" },
];

interface Props {
  onOpen: (target: SettingsTarget) => void;
  onClose: () => void;
}

/** 재고 화면 톱니바퀴: 자주 쓰는 보관 위치·필수품만 남기고 나머지는 더보기로 (스펙 27절) */
export default function SettingsSheet({ onOpen, onClose }: Props) {
  return (
    <Sheet title="재고 설정" onClose={onClose}>
      <ul className="plain-list mo-menu">
        {MENU.map((item) => (
          <li key={item.target}>
            <button className="plain-row menu-row" onClick={() => onOpen(item.target)}>
              <span className="row-title">{item.label}</span>
              <Icon name="chevron" />
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="mo-more-link"
        onClick={() => {
          onClose();
          navigate("/more");
        }}
      >
        <span>품목별 경고·로그아웃은 더보기로 옮겼어요</span>
        <b>더보기로 가기</b>
      </button>
    </Sheet>
  );
}
