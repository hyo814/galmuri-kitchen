import { useEffect, useState } from "react";
import { api, type AuthOptions, type User } from "../api";

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

  const devLogin = async () => {
    try {
      onLogin(await api<User>("/api/dev-login", { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
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
          카카오 로그인
        </a>
      )}
      {options?.providers.includes("google") && (
        <a className="btn google" href="/auth/login/google">
          Google로 계속하기
        </a>
      )}
      {options?.dev_login && (
        <button className="btn secondary" onClick={devLogin}>
          개발용 로그인
        </button>
      )}
      {options && options.providers.length === 0 && !options.dev_login && (
        <p className="center muted">아직 로그인 방법이 설정되지 않았어요.</p>
      )}
    </main>
  );
}
