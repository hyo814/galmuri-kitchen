import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, api, onUnauthorized, type User } from "./api";
import Splash from "./components/Splash";
import TabBar from "./components/TabBar";
import ComingSoon from "./pages/ComingSoon";
import Fridge from "./pages/Fridge";
import Login from "./pages/Login";
import More from "./pages/More";
import RecipeAi, { RecipeAiDetail, resetAiRecipes } from "./pages/RecipeAi";
import RecipeDetail from "./pages/RecipeDetail";
import RecipeForm, { resetRecipeDraft } from "./pages/RecipeForm";
import Shopping from "./pages/Shopping";
import ShoppingStock from "./pages/ShoppingStock";
import SeasoningCalc from "./pages/SeasoningCalc";
import SeasoningForm, { resetSeasoningDraft } from "./pages/SeasoningForm";
import Recipes, { resetRecipesSegment } from "./pages/Recipes";
import Tools from "./pages/Tools";
import Channels from "./pages/Channels";
import VideoPlayer from "./pages/VideoPlayer";
import { scrollTops, useHashRoute, type Route, type RoutePattern } from "./useHashRoute";
import { forgetResources } from "./useResource";
import { clearShoppingDevice, pauseShopping, rememberUser, savedUser, startShopping } from "./shopping/useShopping";

interface PageProps {
  route: Route;
  user: User;
  onLogout: () => void;
}

// 경로 → 화면. 새 화면은 useHashRoute의 ROUTES와 여기에 한 줄씩 추가한다.
const PAGES: Record<RoutePattern, (props: PageProps) => ReactNode> = {
  "/": ({ user }) => <Fridge user={user} />,
  "/recipes": ({ user }) => <Recipes user={user} />,
  "/recipes/new": () => <RecipeForm />,
  "/recipes/mine/:id": ({ route }) => <RecipeDetail kind="mine" id={route.params.id} />,
  "/recipes/mine/:id/edit": ({ route }) => <RecipeForm id={route.params.id} />,
  "/recipes/public/:id": ({ route }) => <RecipeDetail kind="public" id={route.params.id} />,
  "/recipes/ai": () => <RecipeAi />,
  "/recipes/ai/:n": ({ route }) => <RecipeAiDetail index={Number(route.params.n)} />,
  "/recipes/videos/:id": ({ route, user }) => <VideoPlayer id={route.params.id} user={user} />,
  "/recipes/channels": ({ user }) => <Channels user={user} />,
  "/recipes/seasonings/new": () => <SeasoningForm />,
  "/recipes/seasonings/preset/:id": ({ route }) => <SeasoningCalc kind="preset" id={route.params.id} />,
  "/recipes/seasonings/:id": ({ route }) => <SeasoningCalc kind="mine" id={route.params.id} />,
  "/recipes/seasonings/:id/edit": ({ route }) => <SeasoningForm id={route.params.id} />,
  "/shopping": ({ user }) => <Shopping user={user} />,
  "/shopping/stock": () => <ShoppingStock />,
  "/meals": () => <ComingSoon route="/meals" />,
  "/more": ({ user, onLogout }) => <More user={user} onLogout={onLogout} />,
  "/tools": () => <Tools />,
};

export default function App() {
  // undefined: 확인 중, null: 비로그인
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [offline, setOffline] = useState(false);
  const route = useHashRoute();

  useEffect(() => {
    const onScroll = () => scrollTops.set(route.path, window.scrollY);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [route.path]);

  useLayoutEffect(() => {
    const savedY = scrollTops.get(route.path) ?? 0;
    window.scrollTo(0, savedY);
    if (savedY === 0) return;

    // 재고처럼 데이터를 여러 번에 걸쳐 비동기로 받는 화면(재고 목록 → 필수품 배너 순)은
    // 이 시점엔 내용이 짧아 스크롤이 그만큼 안 먹을 수 있고, 나중에 위쪽에 내용이 더 끼어들면
    // 브라우저가 스크롤 위치를 슬쩍 밀기도 한다(scroll anchoring). 그래서 한 번 맞춰도 계속 지켜보다가
    // 사용자가 직접 스크롤을 시작하면(휠·터치) 그만두거나, ~2초 뒤엔 그만둔다.
    let stopped = false;
    function stop() {
      if (stopped) return;
      stopped = true;
      observer.disconnect();
      clearTimeout(timer);
      window.removeEventListener("wheel", stop);
      window.removeEventListener("touchstart", stop);
      window.removeEventListener("pointerdown", stop);
      window.removeEventListener("keydown", stop);
    }
    const observer = new ResizeObserver(() => {
      if (document.documentElement.scrollHeight - window.innerHeight >= savedY) window.scrollTo(0, savedY);
    });
    observer.observe(document.body);
    const timer = setTimeout(stop, 2000);
    window.addEventListener("wheel", stop, { passive: true, once: true });
    window.addEventListener("touchstart", stop, { passive: true, once: true });
    window.addEventListener("pointerdown", stop, { passive: true, once: true });
    window.addEventListener("keydown", stop, { passive: true, once: true });

    return stop;
  }, [route.path]);

  // U-S1/S2: 경로가 바뀌면(첫 렌더 제외) 새 화면의 제목(h1)으로 포커스를 옮긴다 — 스크린리더 사용자가
  // 화면이 바뀐 걸 알 수 있게. 이미 자동 포커스된 입력(예: 레시피 추가 폼의 이름 칸)이 있으면 건너뛴다.
  const isFirstRoute = useRef(true);
  useEffect(() => {
    if (isFirstRoute.current) {
      isFirstRoute.current = false;
      return;
    }
    const main = document.querySelector("main.page");
    if (!main) return;
    if (document.activeElement && main.contains(document.activeElement)) return; // 자동 포커스된 입력이 이미 있다

    const focusHeading = () => {
      const heading = main.querySelector("h1");
      if (!heading) return false;
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      return true;
    };
    if (focusHeading()) return;

    // 상세·수정 화면처럼 데이터를 비동기로 받아 오는 화면은 이 시점에 h1이 아직 없을 수 있다.
    // 생기는 대로(불러오는 중 → 실제 내용으로 바뀔 때) 한 번만 포커스한다.
    const observer = new MutationObserver(() => {
      if (focusHeading()) observer.disconnect();
    });
    observer.observe(main, { childList: true, subtree: true });
    const timer = setTimeout(() => observer.disconnect(), 5000); // 계속 없으면(오류 화면 등) 포기
    return () => {
      observer.disconnect();
      clearTimeout(timer);
    };
  }, [route.path]);

  // 로그아웃·세션 만료: 다른 계정으로 들어와도 이전 사용자의 화면 캐시·탭·스크롤이 보이지 않게 (M9)
  const resetScreens = useCallback(() => {
    forgetResources();
    resetRecipesSegment();
    resetSeasoningDraft();
    resetAiRecipes();
    resetRecipeDraft();
    scrollTops.clear();
    setUser(null);
  }, []);
  // 401(세션 만료): 장보기 대기 변경은 남기고 보내기만 멈춘다 — 같은 사람이 다시 로그인하면 이어서 보낸다(다른 사람이면 rememberUser가 지운다)
  const signOut = useCallback(() => {
    pauseShopping();
    resetScreens();
  }, [resetScreens]);
  // 직접 로그아웃(더보기에서 확인한 뒤): 같은 폰을 다른 사람이 써도 장보기 목록이 남지 않게 기기 데이터를 지운다
  const logout = useCallback(() => {
    void clearShoppingDevice();
    resetScreens();
  }, [resetScreens]);

  // 기기 데이터가 이 사용자 것인지 확인한 뒤에 화면을 연다(다른 사용자의 대기 변경을 보내지 않게)
  const signIn = useCallback((me: User) => {
    void rememberUser(me).then(() => {
      setUser(me);
      startShopping();
    });
  }, []);

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
    api<User>("/api/me").then(signIn, async (e: unknown) => {
      if (e instanceof ApiError && (e.status === 0 || e.status >= 500)) {
        // 인터넷이 없거나 서버가 잠시 안 되면 마지막으로 로그인한 사용자로 연다(마트 지하에서 장보기, 스펙 19절). 세션이 끝났으면 다음 요청의 401이 로그인으로 보낸다
        const saved = await savedUser();
        if (saved) {
          setUser(saved);
          startShopping();
        } else setOffline(true);
      } else if (!(e instanceof ApiError && e.status === 401)) setUser(null); // 401은 전역 핸들러가 처리
    });
  };

  useEffect(() => {
    onUnauthorized(signOut);
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
        <Login onLogin={signIn} />
      </>
    );
  return (
    <>
      {splash}
      {/* key: 경로가 바뀌면 화면을 새로 만든다(상세 3 → 상세 4에서 이전 데이터가 남지 않게) */}
      <Fragment key={route.path}>{PAGES[route.pattern]({ route, user, onLogout: logout })}</Fragment>
      <TabBar path={route.path} />
    </>
  );
}
