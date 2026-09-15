import { useEffect, useState } from "react";
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

function lastLoginProvider(): string | null {
  try {
    return localStorage.getItem(LAST_LOGIN_KEY);
  } catch {
    return null;
  }
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
  const postLogin = async (url: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      onLogin(await api<User>(url, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

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

  return (
    <main className="login">
      <div className="login-hero">
        <img src="/mark.svg" width="72" height="72" alt="" />
        <h1>갈무리부엌</h1>
        <p>냉장고 속 재료로 오늘 뭐 해 먹을지 정해요.</p>
      </div>
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
