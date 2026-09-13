import Icon from "./Icon";
import Sheet from "./Sheet";

export type SettingsTarget = "locations";

const MENU: { target: SettingsTarget; label: string }[] = [{ target: "locations", label: "보관 위치" }];

interface Props {
  onOpen: (target: SettingsTarget) => void;
  onLogout: () => void;
  onClose: () => void;
}

export default function SettingsSheet({ onOpen, onLogout, onClose }: Props) {
  return (
    <Sheet title="설정" onClose={onClose}>
      <ul className="plain-list">
        {MENU.map((item) => (
          <li key={item.target}>
            <button className="plain-row menu-row" onClick={() => onOpen(item.target)}>
              <span className="row-title">{item.label}</span>
              <Icon name="chevron" />
            </button>
          </li>
        ))}
        <li>
          <button className="plain-row menu-row logout" onClick={onLogout}>
            로그아웃
          </button>
        </li>
      </ul>
    </Sheet>
  );
}
