import { useState, type ReactNode } from "react";
import { api, type AiUsage, type ExportSummary, type ItemRule, type Staple, type StorageLocation, type User } from "../api";
import Icon from "../components/Icon";
import LocationsSheet from "../components/LocationsSheet";
import RulesSheet from "../components/RulesSheet";
import Sheet from "../components/Sheet";
import StaplesSheet from "../components/StaplesSheet";
import { useInstallPrompt } from "../install";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import { forgetRecipeCaches, useResource } from "../useResource";

type Theme = "system" | "light" | "dark";

const THEMES: { value: Theme; label: string; short: string; sub?: string }[] = [
  { value: "system", label: "시스템 설정 따르기", short: "시스템 설정", sub: "폰이 어두운 모드면 어둡게 보여줘요" },
  { value: "light", label: "밝게", short: "밝게" },
  { value: "dark", label: "어둡게", short: "어둡게" },
];

const PROVIDERS: Record<User["provider"], { mark: ReactNode; label: string }> = {
  kakao: { mark: "K", label: "카카오로 로그인했어요" },
  naver: { mark: "N", label: "네이버로 로그인했어요" },
  google: { mark: "G", label: "구글로 로그인했어요" },
  dev: { mark: <Icon name="settings" />, label: "개발용 계정으로 로그인했어요" },
};

/** 화면 테마를 이 기기에 저장하고 바로 적용한다. 첫 화면 적용은 index.html의 인라인 스크립트가 같은 방식으로 한다 */
function applyTheme(theme: Theme) {
  try {
    if (theme === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", theme);
  } catch {
    // 저장이 막힌 브라우저(사생활 보호 모드 등)는 이번 방문에만 적용된다
  }
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((meta) => {
    const dark = theme === "system" ? meta.media.includes("dark") : theme === "dark";
    meta.content = dark ? "#0e0f11" : "#f3f4f6";
  });
}

interface RowProps {
  icon: ReactNode;
  iconClass?: string;
  title: string;
  sub?: string;
  value?: string;
  className?: string;
  /** 없으면 누를 수 없는 표시용 행 */
  onClick?: () => void;
  chevron?: boolean;
}

function Row({ icon, iconClass = "", title, sub, value, className = "", onClick, chevron = true }: RowProps) {
  const inner = (
    <>
      <span className={`mo-ico ${iconClass}`} aria-hidden="true">
        {icon}
      </span>
      <span className="row-main">
        <span className="row-title">{title}</span>
        {sub && <span className="row-sub">{sub}</span>}
      </span>
      {value && <span className="mo-val">{value}</span>}
      {onClick && chevron && <Icon name="chevron" />}
    </>
  );
  return (
    <li>
      {onClick ? (
        <button className={`mo-row ${className}`} onClick={onClick}>
          {inner}
        </button>
      ) : (
        <div className={`mo-row ${className}`}>{inner}</div>
      )}
    </li>
  );
}

/** 오늘 AI 사용량(스펙 27절). 키가 없는 운영 설정(scan off)에서는 쓸 수 없으니 보이지 않는다 */
function AiUsageRow() {
  const { data } = useResource<AiUsage>("/api/ai-usage");
  return (
    <Row
      icon={<Icon name="sparkle" />}
      title="AI 사용량"
      sub={
        data
          ? `오늘 사진 인식 ${data.scan.used}/${data.scan.limit}회 · AI 레시피 ${data.recipe.used}/${data.recipe.limit}회`
          : "불러오는 중…"
      }
    />
  );
}

function ThemeSheet({ value, onChange, onClose }: { value: Theme; onChange: (theme: Theme) => void; onClose: () => void }) {
  return (
    <Sheet title="화면 테마" description="이 기기에서만 바뀌어요" onClose={onClose}>
      <div className="mo-radios" role="radiogroup" aria-label="화면 테마">
        {THEMES.map((t) => (
          <button
            key={t.value}
            className="mo-radio"
            role="radio"
            aria-checked={value === t.value}
            onClick={() => onChange(t.value)}
          >
            <span className="mo-dot" aria-hidden="true" />
            <span className="row-main">
              <span className="row-title">{t.label}</span>
              {t.sub && <span className="row-sub">{t.sub}</span>}
            </span>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

/** 데이터 내보내기(스펙 27절): 서버가 CSV를 zip 하나로 묶어 준다. 하루 횟수 제한은 서버가 센다 */
function ExportSheet({ onClose }: { onClose: () => void }) {
  const summary = useResource<ExportSummary>("/api/export/summary");
  const { busy, error, run } = useAsyncAction();
  const data = summary.data;
  const count = (n: number | undefined) => (n === undefined ? "…" : `${n}개`);

  const download = async () => {
    const ok = await run(async () => {
      const res = await api<Response>("/api/export", { raw: true });
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = match ? decodeURIComponent(match[1] ?? match[2]) : "galmuri-kitchen.zip";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000); // 바로 지우면 일부 브라우저가 받기 전에 끊는다
    });
    if (ok) onClose();
  };

  return (
    <Sheet
      title="데이터 내보내기"
      description="표 파일(CSV)을 zip 하나로 묶어 내려받아요. 엑셀이나 구글 시트에서 열 수 있어요."
      onClose={onClose}
    >
      <ul className="mo-inc">
        <li>
          <span>재고</span>
          <b>{count(data?.ingredients)}</b>
        </li>
        <li>
          <span>내 레시피</span>
          <b>{count(data?.recipes)}</b>
        </li>
        <li>
          <span>내 양념 비율</span>
          <b>{count(data?.seasonings)}</b>
        </li>
      </ul>
      <p className="mo-note">
        <Icon name="info" size={16} />
        <span>
          사진은 들어가지 않고 파일 이름만 적어요. 하루 {data?.limit ?? 5}번까지 받을 수 있어요.
          {data && data.remaining < data.limit && (data.remaining > 0 ? ` 오늘 ${data.remaining}번 남았어요.` : " 오늘은 다 받았어요.")}
        </span>
      </p>
      {(error || summary.error) && (
        <p className="error" role="alert">
          {error || summary.error}
        </p>
      )}
      <div className="actions">
        <button className="btn outline" onClick={onClose}>
          취소
        </button>
        <button className="btn primary" disabled={busy || !data || data.remaining <= 0} onClick={download}>
          {!busy && <Icon name="download" />}
          {busy ? "준비하는 중…" : "내려받기"}
        </button>
      </div>
    </Sheet>
  );
}

type Panel = "locations" | "staples" | "rules" | "theme" | "export" | "install";

export default function More({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { canPrompt, installed, prompt } = useInstallPrompt();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme | undefined) ?? "system");
  // 재고 화면 톱니바퀴에 있던 설정을 여기서도 연다. 재고 화면처럼 바뀌면 추천·레시피 캐시를 지운다 (I1)
  const locations = useResource<StorageLocation[]>("/api/locations");
  const staples = useResource<Staple[]>("/api/staples");
  const rules = useResource<ItemRule[]>("/api/item-rules");
  const changed = (reload: () => Promise<void>) => () => {
    forgetRecipeCaches();
    return reload();
  };
  const loadError = locations.error || staples.error || rules.error;
  const provider = PROVIDERS[user.provider] ?? PROVIDERS.dev;

  const onInstallClick = async () => {
    if (canPrompt) await prompt();
    else setPanel("install");
  };

  const chooseTheme = (next: Theme) => {
    applyTheme(next);
    setTheme(next);
    setPanel(null);
  };

  const logout = async () => {
    if (!confirm("로그아웃할까요?")) return;
    await api("/api/logout", { method: "POST" }).catch(() => {});
    onLogout();
  };

  return (
    <main className="page">
      <header className="topbar">
        <h1>더보기</h1>
      </header>

      {loadError && (
        <p className="error" role="alert">
          {loadError}
        </p>
      )}

      <h2 className="mo-group">우리 부엌</h2>
      <ul className="list">
        <Row
          icon={<Icon name="box" />}
          title="보관 위치"
          sub="냉장·냉동·실온 칸 이름과 종류"
          onClick={() => setPanel("locations")}
        />
        <Row
          icon={<Icon name="star" />}
          title="필수품"
          sub={staples.data?.length ? `떨어지면 알려줄 재료 ${staples.data.length}개` : "떨어지면 알려줄 재료"}
          onClick={() => setPanel("staples")}
        />
        <Row
          icon={<Icon name="bell" />}
          title="품목별 경고"
          sub="계란 30일처럼 품목마다 기준"
          onClick={() => setPanel("rules")}
        />
        <Row icon={<Icon name="pan" />} title="주방 도구" sub="프라이팬 코팅 점검" onClick={() => navigate("/tools")} />
      </ul>

      {user.scan !== "off" && (
        <>
          <h2 className="mo-group">나</h2>
          <ul className="list">
            <AiUsageRow />
          </ul>
        </>
      )}

      <h2 className="mo-group">앱</h2>
      <ul className="list">
        {!installed && (
          <Row
            icon={<Icon name="download" />}
            title="홈 화면에 앱 설치"
            sub="앱처럼 바로 열 수 있어요"
            onClick={onInstallClick}
          />
        )}
        <Row
          icon={<Icon name="moon" />}
          title="화면 테마"
          value={THEMES.find((t) => t.value === theme)?.short}
          onClick={() => setPanel("theme")}
        />
        <Row
          icon={<Icon name="file" />}
          title="데이터 내보내기"
          sub="재고·레시피를 파일로 받아요"
          onClick={() => setPanel("export")}
        />
      </ul>

      <h2 className="mo-group">계정</h2>
      <ul className="list">
        <Row
          icon={provider.mark}
          iconClass={`mo-provider ${user.provider}`}
          title={provider.label}
          sub={user.nickname}
        />
        <Row
          icon={<Icon name="logout" />}
          title="로그아웃"
          className="mo-logout"
          chevron={false}
          onClick={logout}
        />
      </ul>

      {panel === "locations" && locations.data && (
        <LocationsSheet locations={locations.data} onChanged={changed(locations.reload)} onClose={() => setPanel(null)} />
      )}
      {panel === "staples" && staples.data && (
        <StaplesSheet staples={staples.data} onChanged={changed(staples.reload)} onClose={() => setPanel(null)} />
      )}
      {panel === "rules" && rules.data && (
        <RulesSheet rules={rules.data} onChanged={changed(rules.reload)} onClose={() => setPanel(null)} />
      )}
      {panel === "theme" && <ThemeSheet value={theme} onChange={chooseTheme} onClose={() => setPanel(null)} />}
      {panel === "export" && <ExportSheet onClose={() => setPanel(null)} />}
      {panel === "install" && (
        <Sheet title="홈 화면에 설치하기" onClose={() => setPanel(null)}>
          <p>안드로이드(삼성 인터넷·크롬): 오른쪽 위 메뉴(점 세 개) → "앱 설치" 또는 "홈 화면에 추가"를 눌러주세요.</p>
          <p>아이폰(사파리): 아래 공유 버튼 → "홈 화면에 추가"를 눌러주세요.</p>
          <p>설치 버튼이 안 보이면: 지금 주소가 https가 아니면 설치할 수 없어요. 배포 후에 다시 시도해주세요.</p>
          <button className="btn secondary" onClick={() => setPanel(null)}>
            닫기
          </button>
        </Sheet>
      )}
    </main>
  );
}
