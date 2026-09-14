import { useEffect, useState } from "react";

// ponytail: 라우터 라이브러리 대신 브라우저 해시(#/recipes/mine/3) + 작은 경로표. 뒤로가기가 그대로 동작한다.
// 경로 모양이 복잡해지면(중첩 레이아웃, 검색 파라미터) react-router의 createHashRouter로 교체.
export const ROUTES = [
  "/",
  "/recipes",
  "/recipes/new",
  "/recipes/mine/:id",
  "/recipes/mine/:id/edit",
  "/recipes/public/:id",
  "/recipes/seasonings/new",
  "/recipes/seasonings/preset/:id",
  "/recipes/seasonings/:id",
  "/recipes/seasonings/:id/edit",
  "/shopping",
  "/meals",
  "/more",
  "/tools",
] as const;

export type RoutePattern = (typeof ROUTES)[number];

export interface Route {
  path: string;
  pattern: RoutePattern;
  params: Record<string, string>;
}

/** "/recipes/mine/3" → { pattern: "/recipes/mine/:id", params: { id: "3" } }. :id는 숫자만. 모르는 경로는 null */
export function matchRoute(path: string): Route | null {
  const parts = path.split("/");
  for (const pattern of ROUTES) {
    const want = pattern.split("/");
    if (want.length !== parts.length) continue;
    const params: Record<string, string> = {};
    const ok = want.every((segment, i) => {
      if (!segment.startsWith(":")) return segment === parts[i];
      params[segment.slice(1)] = parts[i];
      return /^\d+$/.test(parts[i]);
    });
    if (ok) return { path, pattern, params };
  }
  return null;
}

const currentRoute = (): Route => {
  let path = location.hash.replace(/^#/, "") || "/";
  if (path.length > 1) path = path.replace(/\/$/, ""); // "/tools/" → "/tools"
  const route = matchRoute(path);
  if (route) return route;
  location.replace("#/");
  return { path: "/", pattern: "/", params: {} };
};

// 경로별 마지막 스크롤 위치: 상세에서 돌아오면 목록을 보던 자리로, 처음 여는 화면은 맨 위로
export const scrollTops = new Map<string, number>();
history.scrollRestoration = "manual";

/** path의 저장된 스크롤을 지운다. 새로 들어가는 화면(push)은 이전에 그 경로를 보던 자리가 아니라 맨 위에서 시작해야 한다 (I2) */
export function forgetScroll(path: string) {
  scrollTops.delete(path);
}

/**
 * 화면 이동. 기본은 히스토리에 쌓아 폰 뒤로가기로 돌아올 수 있게 한다(상세·폼).
 * replace는 지금 칸을 바꾼다(저장 후 상세로 넘어갈 때). 탭 전환은 TabBar가 location.replace를 쓴다.
 */
export function navigate(path: string, { replace = false } = {}) {
  if (replace) history.replaceState(history.state, "", `#${path}`);
  else {
    forgetScroll(path); // 새 push는 맨 위에서 시작한다(뒤로가기·탭 복귀는 그대로 복원, I2)
    history.pushState({ from: location.hash.replace(/^#/, "") || "/" }, "", `#${path}`);
  }
  // pushState·replaceState는 hashchange를 스스로 쏘지 않으므로 직접 알린다.
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** 앱 안에서 들어왔으면 뒤로가기(히스토리·스크롤 유지), 주소로 바로 열었으면 fallback으로 이동 */
export function goBack(fallback: string) {
  if ((history.state as { from?: string } | null)?.from) history.back();
  else navigate(fallback, { replace: true });
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState(currentRoute);
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
