import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  ApiError,
  api,
  localToday,
  type AiUsage,
  type BodyProfileResponse,
  type CookReport,
  type ExportSummary,
  type FoodLogDay,
  type ItemRule,
  type Staple,
  type StorageLocation,
  type User,
} from "../api";
import BodyGoalSheet from "../components/BodyGoalSheet";
import Icon from "../components/Icon";
import LocationsSheet from "../components/LocationsSheet";
import ProviderLogo from "../components/ProviderLogo";
import RulesSheet from "../components/RulesSheet";
import Sheet from "../components/Sheet";
import StaplesSheet from "../components/StaplesSheet";
import { savedText } from "../cooklog/cook.ts";
import { monthOf, todayRowSub } from "../foodlog/log";
import { useInstallPrompt } from "../install";
import { dailyTarget, goalLabel, kcalNumber } from "../nutrition/body";
import { useAsyncAction } from "../useAsyncAction";
import { navigate } from "../useHashRoute";
import { forgetRecipeCaches, forgetResources, useResource } from "../useResource";
import { pendingShoppingChanges } from "../shopping/useShopping";
import { resetCookReportView } from "./CookReport";

type Theme = "system" | "light" | "dark";

const THEMES: { value: Theme; label: string; short: string; sub?: string }[] = [
  { value: "system", label: "시스템 설정 따르기", short: "시스템 설정", sub: "폰이 어두운 모드면 어둡게 보여줘요" },
  { value: "light", label: "밝게", short: "밝게" },
  { value: "dark", label: "어둡게", short: "어둡게" },
];

const PROVIDERS: Partial<Record<string, { mark: ReactNode; label: string }>> = {
  kakao: { mark: <ProviderLogo name="kakao" />, label: "카카오로 로그인했어요" },
  naver: { mark: <ProviderLogo name="naver" />, label: "네이버로 로그인했어요" },
  google: { mark: <ProviderLogo name="google" />, label: "구글로 로그인했어요" },
  dev: { mark: <Icon name="settings" />, label: "개발용 계정으로 로그인했어요" },
  demo: { mark: <Icon name="sparkle" />, label: "체험 계정으로 둘러보는 중이에요" },
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

/** 더보기 `나` 묶음 맨 위 줄(스펙 27절). 키와 관계없이 늘 보인다.
 * data는 More가 하나만 받아 이 줄과 아래 시트가 함께 쓴다(따로 받으면 시트에서 저장·삭제해도 이 줄이 그대로 남는다). */
function BodyGoalRow({ data, onOpen }: { data: BodyProfileResponse | undefined; onOpen: () => void }) {
  const profile = data?.profile;
  const sub = !data ? "" : profile ? `${goalLabel(profile.goal)} · 하루 ${kcalNumber(dailyTarget(profile, localToday()).target)}kcal` : "키·몸무게로 하루 필요 칼로리를 알려줘요";
  return <Row icon={<Icon name="bowl" />} title="하루 칼로리 목표" sub={sub} onClick={onOpen} />;
}

/** 더보기에서 여는 하루 칼로리 목표 시트: 받아온 뒤에야 시트를 그린다(불러오는 중·오류는 안에서) */
function BodyPanel({
  data,
  error,
  reload,
  set,
  onClose,
}: {
  data: BodyProfileResponse | undefined;
  error: string;
  reload: () => Promise<void>;
  set: (next: BodyProfileResponse) => void;
  onClose: () => void;
}) {
  if (!data)
    return (
      <Sheet title="하루 칼로리 목표 정하기" onClose={onClose}>
        {error ? (
          <>
            <p className="error" role="alert">
              {error}
            </p>
            <button type="button" className="btn secondary" onClick={reload}>
              다시 시도
            </button>
          </>
        ) : (
          <p className="muted" role="status">
            불러오는 중…
          </p>
        )}
      </Sheet>
    );
  return (
    <BodyGoalSheet
      today={localToday()}
      profile={data.profile}
      onSaved={(res) => {
        set(res);
        onClose();
      }}
      onDeleted={() => {
        set({ profile: null });
        onClose();
      }}
      onClose={onClose}
    />
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
  const group = useRef<HTMLDivElement>(null);
  // 시트가 열리면(Sheet의 showModal 뒤) 지금 고른 항목에 포커스
  useEffect(() => {
    group.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
  }, []);

  // 라디오 그룹 키보드: 위·아래 화살표는 포커스만 옮기고, 고르기는 Space·Enter·탭으로 (roving tabindex)
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const radios = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')];
    const i = radios.indexOf(document.activeElement as HTMLElement);
    radios[(i + (e.key === "ArrowDown" ? 1 : -1) + radios.length) % radios.length].focus();
  };

  return (
    <Sheet title="화면 테마" description="이 기기에서만 바뀌어요" onClose={onClose}>
      <div ref={group} className="mo-radios" role="radiogroup" aria-label="화면 테마" onKeyDown={onKeyDown}>
        {THEMES.map((t) => (
          <button
            key={t.value}
            className="mo-radio"
            role="radio"
            aria-checked={value === t.value}
            tabIndex={value === t.value ? 0 : -1}
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
    if (busy) return; // 준비 중에도 포커스가 버튼에 남도록 disabled 대신 aria-disabled
    const ok = await run(async () => {
      const res = await api<Response>("/api/export", { raw: true });
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const raw = match ? (match[1] ?? match[2]) : "galmuri-kitchen.zip";
      try {
        a.download = decodeURIComponent(raw);
      } catch {
        a.download = raw; // 잘못된 % 인코딩이면 받은 이름 그대로
      }
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000); // 바로 지우면 일부 브라우저가 받기 전에 끊는다
    });
    if (ok) {
      forgetResources("/api/export"); // 다음에 열면 남은 횟수를 새로 받는다
      onClose();
    } else summary.reload(); // 429 등: 남은 횟수·버튼 상태를 서버 값으로 맞춘다
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
        <li>
          <span>장보기 (산 것 포함)</span>
          <b>{count(data?.shopping)}</b>
        </li>
        <li>
          <span>장보기 메모</span>
          <b>{count(data?.memos)}</b>
        </li>
        <li>
          <span>식단</span>
          <b>{data?.meals === undefined ? "…" : `${data.meals}칸`}</b>
        </li>
        <li>
          <span>먹은 기록</span>
          <b>{count(data?.food_logs)}</b>
        </li>
        <li>
          <span>요리 일기</span>
          <b>{count(data?.cook_logs)}</b>
        </li>
      </ul>
      <p className="mo-note">
        <Icon name="info" size={16} />
        <span>
          사진은 들어가지 않고 파일 이름만 적어요.
          {data && ` 하루 ${data.limit}번까지 받을 수 있어요.`}
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
        <button
          className="btn primary"
          disabled={!data || data.remaining <= 0}
          aria-disabled={busy || undefined}
          onClick={download}
        >
          {!busy && <Icon name="download" />}
          {busy ? "준비하는 중…" : "내려받기"}
        </button>
      </div>
      <p className="sr-only" role="status">
        {busy ? "파일을 준비하는 중이에요" : ""}
      </p>
    </Sheet>
  );
}

/** 누르면 시트가 바로 열리고, 목록은 그때 불러온다(불러오는 중·오류도 시트 안에). 바뀌면 재고 화면처럼 추천·레시피 캐시를 지운다 (I1) */
function LoadedSheet<T>({
  url,
  title,
  onClose,
  children,
}: {
  url: string;
  title: string;
  onClose: () => void;
  children: (data: T, onChanged: () => Promise<void>) => ReactNode;
}) {
  const { data, error, reload } = useResource<T>(url);
  if (data)
    return children(data, () => {
      forgetRecipeCaches();
      return reload();
    });
  return (
    <Sheet title={title} onClose={onClose}>
      {error ? (
        <>
          <p className="error" role="alert">
            {error}
          </p>
          <button className="btn secondary" onClick={reload}>
            다시 시도
          </button>
        </>
      ) : (
        <p className="muted" role="status">
          불러오는 중…
        </p>
      )}
    </Sheet>
  );
}

type Panel = "locations" | "staples" | "rules" | "body" | "theme" | "export" | "install" | "credits" | "leave";

export default function More({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { canPrompt, installed, prompt } = useInstallPrompt();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme | undefined) ?? "system");
  const provider = PROVIDERS[user.provider];
  // 줄과 시트가 하나만 받아 나눠 쓴다(따로 받으면 시트에서 저장·삭제해도 줄이 갱신되지 않는다)
  const body = useResource<BodyProfileResponse>("/api/body-profile");
  const today = useResource<FoodLogDay>(`/api/food-logs?date=${localToday()}`);
  const report = useResource<CookReport>(`/api/cook-report?month=${monthOf(localToday())}`);

  const onInstallClick = async () => {
    if (canPrompt) await prompt();
    else setPanel("install");
  };

  const chooseTheme = (next: Theme) => {
    applyTheme(next);
    setTheme(next);
    setPanel(null);
  };

  const [logoutError, setLogoutError] = useState<string | null>(null);
  const logout = async () => {
    setLogoutError(null);
    const offlineText = "인터넷이 연결되면 로그아웃할 수 있어요";
    // 서버에서 로그아웃되기 전에 기기 데이터를 지우면 세션은 살아 있는데 대기 변경만 사라진다
    if (!navigator.onLine) return setLogoutError(offlineText);
    const pending = await pendingShoppingChanges();
    if (!confirm(pending ? `보내지 않은 변경 ${pending}건이 사라져요. 로그아웃할까요?` : "로그아웃할까요?")) return;
    try {
      await api("/api/logout", { method: "POST" });
    } catch (e) {
      return setLogoutError(e instanceof ApiError && e.status === 0 ? offlineText : (e as Error).message);
    }
    onLogout();
  };

  return (
    <main className="page">
      <header className="topbar">
        <h1>더보기</h1>
      </header>

      <h2 className="mo-group">기록</h2>
      <ul className="list">
        <Row
          icon={<Icon name="calendar" />}
          title="먹은 기록"
          sub={todayRowSub(today.data?.logs)}
          onClick={() => navigate("/food-log")}
        />
        <Row
          icon={<Icon name="pan" />}
          title="요리 일기"
          sub={report.data ? (report.data.cooked ? `이번 달 요리 ${report.data.cooked}번` : "요리한 기록을 모아봐요") : ""}
          onClick={() => navigate("/cook-logs")}
        />
        <Row
          icon={<Icon name="receipt" />}
          title="집밥 리포트"
          sub={report.data ? (report.data.counted ? `이번 달 ${savedText(report.data.saved_total)}` : "아낀 돈·버린 재료를 한 달씩 보여줘요") : ""}
          onClick={() => {
            resetCookReportView(); // 줄 문구가 이번 달이라 이번 달로 연다(R11-9)
            navigate("/cook-report");
          }}
        />
      </ul>

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
          sub="떨어지면 알려줄 재료"
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

      <h2 className="mo-group">나</h2>
      <ul className="list">
        <BodyGoalRow data={body.data} onOpen={() => setPanel("body")} />
        {user.scan !== "off" && <AiUsageRow />}
      </ul>

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
        <Row
          icon={<Icon name="info" />}
          title="데이터 출처"
          sub="레시피·소비기한 참고값·영상·글꼴·AI"
          onClick={() => setPanel("credits")}
        />
      </ul>

      <h2 className="mo-group">계정</h2>
      {user.provider === "demo" && <p className="mo-demo-banner">체험 계정이에요 · 하루 뒤 사라져요</p>}
      <ul className="list">
        <Row
          icon={provider ? provider.mark : <Icon name="check" />}
          iconClass={provider ? `mo-provider ${user.provider}` : ""}
          title={provider ? provider.label : "로그인했어요"}
          sub={user.nickname}
        />
        <Row
          icon={<Icon name="logout" />}
          title="로그아웃"
          className="mo-logout"
          chevron={false}
          onClick={logout}
        />
        <Row icon={<Icon name="trash" />} title="회원 탈퇴" className="mo-leave" onClick={() => setPanel("leave")} />
      </ul>
      {logoutError && (
        <p className="error" role="alert">
          {logoutError}
        </p>
      )}
      <p className="legal-links">
        <a href="/terms.html">이용약관</a> · <a href="/privacy.html">개인정보처리방침</a>
      </p>

      {panel === "leave" && <LeaveSheet onClose={() => setPanel(null)} onLeft={onLogout} />}

      {panel === "locations" && (
        <LoadedSheet<StorageLocation[]> url="/api/locations" title="위치 관리" onClose={() => setPanel(null)}>
          {(data, onChanged) => <LocationsSheet locations={data} onChanged={onChanged} onClose={() => setPanel(null)} />}
        </LoadedSheet>
      )}
      {panel === "staples" && (
        <LoadedSheet<Staple[]> url="/api/staples" title="필수품" onClose={() => setPanel(null)}>
          {(data, onChanged) => <StaplesSheet staples={data} onChanged={onChanged} onClose={() => setPanel(null)} />}
        </LoadedSheet>
      )}
      {panel === "rules" && (
        <LoadedSheet<ItemRule[]> url="/api/item-rules" title="품목별 경고" onClose={() => setPanel(null)}>
          {(data, onChanged) => <RulesSheet rules={data} onChanged={onChanged} onClose={() => setPanel(null)} />}
        </LoadedSheet>
      )}
      {panel === "body" && <BodyPanel data={body.data} error={body.error} reload={body.reload} set={body.set} onClose={() => setPanel(null)} />}
      {panel === "theme" && <ThemeSheet value={theme} onChange={chooseTheme} onClose={() => setPanel(null)} />}
      {panel === "export" && <ExportSheet onClose={() => setPanel(null)} />}
      {panel === "credits" && (
        <Sheet title="데이터 출처" description="갈무리부엌은 이런 공공 데이터와 서비스를 써요" onClose={() => setPanel(null)}>
          <ul className="mo-credits">
            <li>
              <b>식품의약품안전처 식품안전나라 조리식품 레시피 DB</b>
              <span>추천 레시피와 요리 사진을 가져와요</span>
            </li>
            <li>
              <b>식품의약품안전처 「식품유형별 소비기한 설정 보고서」</b>
              <span>품목별 기본 소비기한은 이 보고서의 참고값이에요</span>
            </li>
            <li>
              <b>식품의약품안전처 식품영양성분 DB(공공데이터포털)</b>
              <span>레시피·식단 영양 계산에 100g당 값을 써요</span>
            </li>
            <li>
              <b>YouTube</b>
              <span>영상과 썸네일은 YouTube에서 제공해요</span>
            </li>
            <li>
              <b>Google Fonts · IBM Plex Sans KR</b>
              <span>SIL Open Font License 1.1로 써요</span>
            </li>
            <li>
              <b>Anthropic Claude</b>
              <span>사진 인식·AI 레시피 만들기·재료 무게 추정에 써요</span>
            </li>
          </ul>
          <button className="btn secondary" onClick={() => setPanel(null)}>
            닫기
          </button>
        </Sheet>
      )}
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

/** 회원 탈퇴 확인 시트(스펙 27절). 되돌릴 수 없어 지워지는 것을 먼저 보여주고, 체크를 해야 버튼이 눌린다. */
function LeaveSheet({ onClose, onLeft }: { onClose: () => void; onLeft: () => void }) {
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const leave = async () => {
    setError(null);
    if (!navigator.onLine) return setError("인터넷이 연결되면 탈퇴할 수 있어요");
    setBusy(true);
    try {
      await api("/api/account", { method: "DELETE" });
    } catch (e) {
      setBusy(false);
      // 서버가 지우는 중에 끊기면 지워졌는지 알 수 없다 — "탈퇴 못 했다"고 단정하지 않는다
      return setError(e instanceof ApiError && e.status === 0 ? "지워졌는지 확인이 안 됐어요. 화면을 새로 고쳐 주세요" : (e as Error).message);
    }
    onLeft(); // 로그아웃과 같은 마무리(기기에 남은 것까지 지우고 로그인 화면으로)
  };

  return (
    <Sheet title="회원 탈퇴" description="지운 정보는 되돌릴 수 없어요" locked={busy} onClose={onClose}>
      <p>탈퇴하면 아래가 모두 지워져요.</p>
      <ul className="mo-leave-list">
        <li>재고·필수품·보관 위치</li>
        <li>레시피·양념 비율·식단</li>
        <li>장보기 목록과 메모 사진</li>
        <li>먹은 기록·요리 일기와 그 사진</li>
        <li>하루 칼로리 목표에 넣은 내 몸 정보</li>
      </ul>
      <label className="mo-leave-agree">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} disabled={busy} />
        <span>지워지는 내용을 확인했어요</span>
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="ml-stack">
        <button className="btn danger-fill" disabled={!agreed || busy} onClick={leave}>
          {busy ? "지우는 중…" : "탈퇴하고 모두 지우기"}
        </button>
        <button className="btn secondary" disabled={busy} onClick={onClose}>
          취소
        </button>
      </div>
    </Sheet>
  );
}
