import { useCallback, useEffect, useState } from "react";
import { ApiError, api, onUnauthorized, type User } from "./api";
import Splash from "./components/Splash";
import TabBar from "./components/TabBar";
import ComingSoon from "./pages/ComingSoon";
import Fridge from "./pages/Fridge";
import Login from "./pages/Login";
import More from "./pages/More";
import Tools from "./pages/Tools";
import { useHashRoute } from "./useHashRoute";

export default function App() {
  // undefined: 확인 중, null: 비로그인
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [offline, setOffline] = useState(false);
  const route = useHashRoute();

  // 시작 화면은 로그인 확인이 끝나고 최소 0.8초가 지날 때까지 보여 준다(너무 빨리 깜빡이지 않게)
  const [minSplashDone, setMinSplashDone] = useState(false);
  const [splashGone, setSplashGone] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setMinSplashDone(true), 800);
    return () => clearTimeout(timer);
  }, []);
  const hideSplash = useCallback(() => setSplashGone(true), []);
  const splash = !splashGone && <Splash leaving={minSplashDone && (user !== undefined || offline)} onGone={hideSplash} />;

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
      <>
        {splash}
        <div className="center">
          <p>서버에 연결할 수 없어요.</p>
          <button className="btn primary inline" onClick={checkMe}>
            다시 시도
          </button>
        </div>
      </>
    );

  if (user === undefined) return splash || <p className="center muted">불러오는 중…</p>;
  if (user === null)
    return (
      <>
        {splash}
        <Login onLogin={setUser} />
      </>
    );
  return (
    <>
      {splash}
      {route === "/more" ? (
        <More />
      ) : route === "/tools" ? (
        <Tools />
      ) : route === "/" ? (
        <Fridge user={user} onLogout={() => setUser(null)} />
      ) : (
        <ComingSoon route={route} />
      )}
      <TabBar route={route} />
    </>
  );
}
