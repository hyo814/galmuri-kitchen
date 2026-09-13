import Icon, { type IconName } from "./Icon";

interface Tab {
  path: string;
  label: string;
  icon: IconName;
  match: (route: string) => boolean;
}

// 최종 탭 순서(사용자 결정 2026-09-13): 재고 · 레시피 · 장보기 · 식단 · 더보기. 기능이 생기는 단계에서 해당 탭을 이 목록에 끼워 넣는다.
export const TABS: Tab[] = [
  { path: "/", label: "재고", icon: "fridge", match: (r) => r === "/" },
  { path: "/more", label: "더보기", icon: "menu", match: (r) => r === "/more" || r === "/tools" },
];

export default function TabBar({ route }: { route: string }) {
  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => (
        <a
          key={tab.path}
          className="tab"
          href={`#${tab.path}`}
          aria-current={tab.match(route) ? "page" : undefined}
          onClick={(e) => {
            e.preventDefault();
            location.replace("#" + tab.path); // 탭 전환은 히스토리를 쌓지 않는다
          }}
        >
          <Icon name={tab.icon} size={24} />
          <span>{tab.label}</span>
        </a>
      ))}
    </nav>
  );
}
