import { confirmLeave } from "../useHashRoute";
import Icon, { type IconName } from "./Icon";

interface Tab {
  path: string;
  label: string;
  icon: IconName;
  match: (path: string) => boolean;
}

// 탭 순서(사용자 결정 2026-09-13): 재고 · 레시피 · 장보기 · 식단 · 더보기.
export const TABS: Tab[] = [
  { path: "/", label: "재고", icon: "fridge", match: (r) => r === "/" },
  { path: "/recipes", label: "레시피", icon: "book", match: (r) => r === "/recipes" || r.startsWith("/recipes/") },
  { path: "/shopping", label: "장보기", icon: "cart", match: (r) => r === "/shopping" || r.startsWith("/shopping/") },
  { path: "/meals", label: "식단", icon: "calendar", match: (r) => r === "/meals" || r.startsWith("/meals/") },
  { path: "/more", label: "더보기", icon: "menu", match: (r) => r === "/more" || r === "/tools" || r === "/food-log" || r === "/cook-logs" },
];

export default function TabBar({ path }: { path: string }) {
  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => (
        <a
          key={tab.path}
          className="tab"
          href={`#${tab.path}`}
          aria-current={tab.match(path) ? "page" : undefined}
          onClick={(e) => {
            e.preventDefault();
            if (!confirmLeave()) return; // 작성 중인 폼이면 나가기 확인
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
