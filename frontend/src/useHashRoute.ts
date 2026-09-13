import { useEffect, useState } from "react";

// ponytail: 라우터 라이브러리 대신 브라우저 해시(#/tools). 뒤로가기가 그대로 동작한다. 경로 파라미터가 많아지면 react-router로 교체.
// 이후 단계에서 탭/화면이 늘어나면 이 목록에 추가한다.
export const KNOWN_ROUTES = ["/", "/recipes", "/shopping", "/meals", "/more", "/tools"];

const currentRoute = () => {
  let route = location.hash.replace(/^#/, "") || "/";
  if (route.length > 1) route = route.replace(/\/$/, ""); // "/tools/" → "/tools"
  if (!KNOWN_ROUTES.includes(route)) {
    location.replace("#/");
    return "/";
  }
  return route;
};

export function useHashRoute(): string {
  const [route, setRoute] = useState(currentRoute);
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
