import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./install";
import "./styles.css";

// ponytail: 개발 서버에서도 등록한다(폰 설치 테스트용). 개발 서버에서는 미리 받을 목록이 비어 화면 이동만 네트워크 우선으로 다뤄 코드 변경이 바로 보인다.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        // 새 버전(화면 파일)은 앱을 떠날 때 바꾼다 — 쓰는 도중에 캐시가 바뀌지 않게. 다음에 열면 새 화면이다
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "hidden") registration.waiting?.postMessage("SKIP_WAITING");
        });
      })
      .catch(() => {});
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
