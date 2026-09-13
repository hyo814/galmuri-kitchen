import { useEffect, useState } from "react";
import { ApiError, api, onUnauthorized, type User } from "./api";
import Fridge from "./pages/Fridge";
import Login from "./pages/Login";

export default function App() {
  // undefined: 확인 중, null: 비로그인
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [offline, setOffline] = useState(false);

  const checkMe = () => {
    setOffline(false);
    setUser(undefined);
    api<User>("/api/me").then(setUser, (e: unknown) => {
      if (e instanceof ApiError && e.status === 0) setOffline(true);
      else if (!(e instanceof ApiError && e.status === 401)) setUser(null); // 401은 전역 핸들러가 처리
    });
  };

  useEffect(() => {
    onUnauthorized(() => setUser(null));
    checkMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (offline)
    return (
      <div className="center">
        <p>서버에 연결할 수 없어요.</p>
        <button className="btn primary inline" onClick={checkMe}>
          다시 시도
        </button>
      </div>
    );

  if (user === undefined) return <p className="center muted">불러오는 중…</p>;
  if (user === null) return <Login onLogin={setUser} />;
  return <Fridge onLogout={() => setUser(null)} />;
}
