import Icon, { type IconName } from "../components/Icon";

// ponytail: 기능이 만들어질 때까지 탭 자리만 잡아 두는 안내 화면. 각 단계에서 진짜 화면으로 교체한다.
const PAGES: Record<string, { title: string; icon: IconName; items: string[] }> = {
  "/shopping": {
    title: "장보기",
    icon: "cart",
    items: [
      "살 날짜를 정한 장보기 목록",
      "떨어진 필수품·부족한 재료 바로 담기",
      "쿠팡·네이버·컬리 등 쇼핑몰 검색 링크",
      "매장에서 쓰는 메모·사진 (인터넷 없이도)",
    ],
  },
  "/meals": {
    title: "식단",
    icon: "calendar",
    items: [
      "1주·1달 식단 달력",
      "내 몸 정보로 기초대사량·칼로리·당류 확인",
      "재고를 먼저 쓰는 식단 초안",
      "식단에 맞춰 장보기 목록 만들기",
    ],
  },
};

export default function ComingSoon({ route }: { route: string }) {
  const page = PAGES[route];
  if (!page) return null;
  return (
    <main className="page">
      <header className="topbar">
        <h1>{page.title}</h1>
      </header>
      <section className="empty">
        <Icon name={page.icon} size={32} color="var(--accent-strong)" />
        <p className="soon-title">준비 중이에요</p>
        <p className="muted">곧 이런 걸 할 수 있어요.</p>
        <ul className="soon-list">
          {page.items.map((item) => (
            <li key={item}>
              <Icon name="check" size={16} color="var(--accent-strong)" />
              {item}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
