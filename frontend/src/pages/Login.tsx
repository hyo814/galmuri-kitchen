import { useEffect, useState } from "react";
import { api, type AuthOptions, type User } from "../api";
import ProviderLogo from "../components/ProviderLogo";

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
      {options?.providers.includes("kakao") && (
        <a className="btn kakao" href="/auth/login/kakao">
          <ProviderLogo name="kakao" />
          카카오 로그인
        </a>
      )}
      {options?.providers.includes("naver") && (
        <a className="btn naver" href="/auth/login/naver">
          <ProviderLogo name="naver" />
          네이버 로그인
        </a>
      )}
      {options?.providers.includes("google") && (
        <a className="btn google" href="/auth/login/google">
          <ProviderLogo name="google" />
          Google로 계속하기
        </a>
      )}
      {options?.demo_login && (
        <>
          <button className="btn secondary" onClick={() => postLogin("/api/demo-login")} disabled={busy}>
            로그인 없이 체험하기
          </button>
          <p className="login-note">예시 재고가 들어 있는 체험 공간이 열려요. 하루 뒤 사라져요.</p>
        </>
      )}
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
