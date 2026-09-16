import { useEffect, useState, type ReactNode } from "react";
import { api, type AuthOptions, type User } from "../api";
import ProviderLogo, { type LoginProvider } from "../components/ProviderLogo";

const LAST_LOGIN_KEY = "lastLoginProvider";
const LOGIN_PROVIDERS: LoginProvider[] = ["kakao", "naver", "google"];
const PROVIDER_LABELS: Record<LoginProvider, string> = { kakao: "카카오 로그인", naver: "네이버 로그인", google: "Google로 계속하기" };

/** 로그인에 성공한 소셜 로그인을 기기에 기억한다(계정이 로그인 방법마다 따로라 다음에 같은 버튼을 누르게). 로그아웃해도 지우지 않는다 */
export function rememberLoginProvider(provider: string) {
  if (!LOGIN_PROVIDERS.includes(provider as LoginProvider)) return;
  try {
    localStorage.setItem(LAST_LOGIN_KEY, provider);
  } catch {
    // 저장소를 못 쓰는 브라우저(사생활 보호 모드 등)는 표시 없이 지나간다
  }
}

/** 바로 체험 주소(`/?demo=1`, 스펙 30절 D)로 열었는지. 앱을 열 때 한 번 읽고 주소에서 지운다 — 새로고침하거나 주소를 공유해도 되풀이되지 않게(해시 경로는 그대로) */
let demoLink = (() => {
  const params = new URLSearchParams(location.search);
  if (!params.has("demo")) return false;
  params.delete("demo");
  const search = params.toString();
  history.replaceState(history.state, "", `${location.pathname}${search && `?${search}`}${location.hash}`);
  return true;
})();

/** 이미 로그인돼 있었으면 바로 체험 주소를 버린다(나중에 로그아웃해도 체험 계정을 새로 만들지 않게) */
export function dropDemoLink() {
  demoLink = false;
}

function lastLoginProvider(): string | null {
  try {
    return localStorage.getItem(LAST_LOGIN_KEY);
  } catch {
    return null;
  }
}

const PEEK_SLIDES: { step: string; title: string; body: ReactNode }[] = [
  {
    step: "찰칵",
    title: "영수증 찍으면 끝이에요",
    body: (
      <div className="peek-receipt">
        <span className="peek-paper" aria-hidden="true" />
        <span className="peek-arrow" aria-hidden="true">
          →
        </span>
        <ul className="peek-rows">
          <li><span>두부 1모</span><span className="peek-won">1,800원</span></li>
          <li><span>대파 1단</span><span className="peek-won">2,480원</span></li>
          <li><span>우유 1L</span><span className="peek-won">2,980원</span></li>
        </ul>
      </div>
    ),
  },
  {
    step: "잠깐만요",
    title: "두부가 내일까지래요",
    body: (
      <ul className="peek-rows">
        <li><span>두부</span><span className="badge urgent">D-1</span></li>
        <li><span>대파</span><span className="badge urgent">D-2</span></li>
        <li><span>김치</span><span className="badge old">구입 10일째</span></li>
      </ul>
    ),
  },
  {
    step: "그럼 오늘은",
    title: "두부조림 어때요?",
    body: (
      <ul className="peek-rows">
        <li><span>두부조림</span><span className="badge info">재료 4/5</span></li>
        <li><span>김치찌개</span><span className="badge info">재료 5/6</span></li>
        <li><span>간장만 사면 돼요</span><span className="badge">장보기에 담기</span></li>
      </ul>
    ),
  },
];

/** 로그인 화면 미리보기 3장(첫인상 B). 4초마다 넘기고, 점을 누르면 멈춘다. 올려두거나 포커스가 안에 있으면 잠깐 멈추고, 움직임 줄이기면 넘기지 않는다 */
function Peek() {
  const [current, setCurrent] = useState(0);
  const [picked, setPicked] = useState(false);
  const [paused, setPaused] = useState(false);
  const [reduceMotion] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  const rotating = !picked && !reduceMotion;

  useEffect(() => {
    if (!rotating || paused) return;
    const timer = setInterval(() => setCurrent((i) => (i + 1) % PEEK_SLIDES.length), 4000);
    return () => clearInterval(timer);
  }, [rotating, paused]);

  return (
    <section
      className="peek"
      aria-roledescription="캐러셀"
      aria-label="갈무리부엌 미리보기"
      // 터치의 탭은 가짜 mouseenter를 남겨 계속 멈춰 있게 되므로 마우스일 때만 멈춘다
      onPointerEnter={(e) => e.pointerType === "mouse" && setPaused(true)}
      onPointerLeave={(e) => e.pointerType === "mouse" && setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setPaused(false);
      }}
    >
      <div className="peek-track" aria-live={rotating ? "off" : "polite"}>
        {PEEK_SLIDES.map((slide, i) => (
          <div
            key={slide.step}
            className={i === current ? "peek-slide on" : "peek-slide"}
            role="group"
            aria-roledescription="슬라이드"
            aria-label={`${i + 1} / ${PEEK_SLIDES.length}`}
            aria-hidden={i !== current}
            inert={i !== current}
          >
            <span className="peek-step">{slide.step}</span>
            <p className="peek-title">{slide.title}</p>
            {slide.body}
          </div>
        ))}
      </div>
      <div className="peek-dots" role="group" aria-label="미리보기 고르기">
        <span className="sr-only">점을 누르면 넘기기를 멈춰요</span>
        {PEEK_SLIDES.map((slide, i) => (
          <button
            key={slide.step}
            type="button"
            aria-label={`${i + 1}번째 미리보기`}
            aria-current={i === current}
            onClick={() => {
              setPicked(true);
              setCurrent(i);
            }}
          />
        ))}
      </div>
    </section>
  );
}

export default function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [error, setError] = useState(
    new URLSearchParams(location.search).has("login_error") ? "로그인에 실패했어요. 다시 시도해주세요." : "",
  );

  useEffect(() => {
    if (new URLSearchParams(location.search).has("login_error")) {
      history.replaceState(null, "", location.pathname);
    }
  }, []);

  useEffect(() => {
    api<AuthOptions>("/api/auth-options").then(setOptions, (e: Error) => setError(e.message));
  }, []);

  const [last] = useState(lastLoginProvider);
  const [busy, setBusy] = useState(false);
  // 바로 체험 주소로 왔으면 로그인 화면 대신 여는 중 안내를 보인다(실패하면 로그인 화면과 오류)
  const [opening, setOpening] = useState(demoLink);
  const postLogin = async (url: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      onLogin(await api<User>(url, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
      setOpening(false);
    }
  };

  // 체험하기를 누른 것처럼 한 번만 연다 — StrictMode에서 두 번 돌거나 로그아웃 뒤 다시 떠도 계정을 또 만들지 않게
  useEffect(() => {
    if (!demoLink) return;
    demoLink = false;
    void postLogin("/api/demo-login");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const providers = LOGIN_PROVIDERS.filter((name) => options?.providers.includes(name));
  // 처음 온 분은 체험하기를 먼저, 이 기기에서 소셜 로그인한 적 있는 분은 그 버튼을 먼저 보여준다
  const demoFirst = !!options?.demo_login && !providers.some((name) => name === last);
  const social = providers.map((name) => (
    <div className="login-provider" key={name}>
      {last === name && (
        <span className="login-last" id={`login-last-${name}`}>
          지난번에 이걸로 로그인했어요
        </span>
      )}
      <a className={`btn ${name}`} href={`/auth/login/${name}`} aria-describedby={last === name ? `login-last-${name}` : undefined}>
        <ProviderLogo name={name} />
        {PROVIDER_LABELS[name]}
      </a>
    </div>
  ));
  const demo = options?.demo_login && (
    <>
      <button className={demoFirst ? "btn primary" : "btn secondary"} onClick={() => postLogin("/api/demo-login")} disabled={busy}>
        로그인 없이 체험하기
      </button>
      <p className="login-note">예시 재고가 들어 있는 체험 공간이 열려요. 하루 뒤 사라져요.</p>
    </>
  );

  if (opening)
    return (
      <p className="center muted" role="status">
        체험 공간을 여는 중이에요
      </p>
    );

  return (
    <main className="login">
      <div className="login-hero">
        <img src="/mark.svg" width="56" height="56" alt="" />
        <h1>갈무리부엌</h1>
        <p>냉장고 속 재료로 오늘 뭐 해 먹을지 정해요.</p>
      </div>
      <Peek />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {demoFirst && demo}
      {demoFirst && social.length > 0 && <p className="login-divider">계정으로 계속하기</p>}
      {social}
      {!demoFirst && demo}
      {options?.dev_login && (
        <button className="btn secondary" onClick={() => postLogin("/api/dev-login")} disabled={busy}>
          개발용 로그인
        </button>
      )}
      {options && options.providers.length === 0 && !options.dev_login && !options.demo_login && (
        <p className="center muted">아직 로그인 방법이 설정되지 않았어요.</p>
      )}
      <p className="legal-links">
        <a href="/terms.html">이용약관</a> · <a href="/privacy.html">개인정보처리방침</a>
      </p>
    </main>
  );
}
