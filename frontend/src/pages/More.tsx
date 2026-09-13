import Icon from "../components/Icon";

export const MORE_ITEMS = [{ path: "/tools", label: "주방 도구", desc: "프라이팬 코팅 점검 같은 도구 관리" }];

export default function More() {
  return (
    <div className="page">
      <header className="topbar">
        <h1>더보기</h1>
      </header>
      <ul className="list">
        {MORE_ITEMS.map((item) => (
          <li key={item.path}>
            <a
              className="row-btn"
              href={`#${item.path}`}
              onClick={(e) => {
                e.preventDefault();
                // pushState는 hashchange 이벤트를 스스로 쏘지 않으므로 직접 알린다.
                history.pushState({ fromMore: true }, "", `#${item.path}`);
                window.dispatchEvent(new HashChangeEvent("hashchange"));
              }}
            >
              <Icon name="pan" size={20} color="var(--text-2)" />
              <span className="row-main">
                <span className="row-title">{item.label}</span>
                <span className="row-sub">{item.desc}</span>
              </span>
              <Icon name="chevron" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
