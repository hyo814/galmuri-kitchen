import { useState } from "react";
import type { AiUsage, User } from "../api";
import Icon from "../components/Icon";
import Sheet from "../components/Sheet";
import { useInstallPrompt } from "../install";
import { navigate } from "../useHashRoute";
import { useResource } from "../useResource";

export const MORE_ITEMS = [{ path: "/tools", label: "주방 도구", desc: "프라이팬 코팅 점검 같은 도구 관리" }];

/** 오늘 AI 사용량(스펙 27절). 키가 없는 운영 설정(scan off)에서는 쓸 수 없으니 보이지 않는다 */
function AiUsageRow() {
  const { data } = useResource<AiUsage>("/api/ai-usage");
  return (
    <li>
      <div className="row-btn">
        <Icon name="sparkle" size={20} color="var(--text-2)" />
        <span className="row-main">
          <span className="row-title">AI 사용량</span>
          <span className="row-sub">
            {data
              ? `오늘 사진 인식 ${data.scan.used}/${data.scan.limit}회 · AI 레시피 ${data.recipe.used}/${data.recipe.limit}회`
              : "불러오는 중…"}
          </span>
        </span>
      </div>
    </li>
  );
}

export default function More({ user }: { user: User }) {
  const { canPrompt, installed, prompt } = useInstallPrompt();
  const [showInstallHelp, setShowInstallHelp] = useState(false);

  const onInstallClick = async () => {
    if (canPrompt) await prompt();
    else setShowInstallHelp(true);
  };

  return (
    <main className="page">
      <header className="topbar">
        <h1>더보기</h1>
      </header>
      <ul className="list">
        {!installed && (
          <li>
            <button className="row-btn" onClick={onInstallClick}>
              <Icon name="download" size={20} color="var(--text-2)" />
              <span className="row-main">
                <span className="row-title">홈 화면에 앱 설치</span>
                <span className="row-sub">앱처럼 바로 열 수 있어요</span>
              </span>
              <Icon name="chevron" />
            </button>
          </li>
        )}
        {MORE_ITEMS.map((item) => (
          <li key={item.path}>
            <a
              className="row-btn"
              href={`#${item.path}`}
              onClick={(e) => {
                e.preventDefault();
                navigate(item.path);
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
        {user.scan !== "off" && <AiUsageRow />}
      </ul>

      {showInstallHelp && (
        <Sheet title="홈 화면에 설치하기" onClose={() => setShowInstallHelp(false)}>
          <p>안드로이드(삼성 인터넷·크롬): 오른쪽 위 메뉴(점 세 개) → "앱 설치" 또는 "홈 화면에 추가"를 눌러주세요.</p>
          <p>아이폰(사파리): 아래 공유 버튼 → "홈 화면에 추가"를 눌러주세요.</p>
          <p>설치 버튼이 안 보이면: 지금 주소가 https가 아니면 설치할 수 없어요. 배포 후에 다시 시도해주세요.</p>
          <button className="btn secondary" onClick={() => setShowInstallHelp(false)}>
            닫기
          </button>
        </Sheet>
      )}
    </main>
  );
}
