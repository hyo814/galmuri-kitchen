import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./install";
import "./styles.css";

// ponytail: 개발 서버에서도 등록한다(폰 설치 테스트용). 서비스 워커는 화면 이동만 네트워크 우선으로 다뤄 코드 변경이 바로 보인다.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
