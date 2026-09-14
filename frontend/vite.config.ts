import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { writeServiceWorker } from "./scripts/sw-precache.mjs";

// 다른 프로젝트(5173·5000 등)와 겹치지 않도록 이 앱 전용 포트를 고정한다
const backend = "http://127.0.0.1:5181";

/** 빌드가 끝나면 dist/sw.js에 화면 파일 목록·버전을 넣는다(오프라인으로 앱 열기, 스펙 19절) */
const serviceWorkerPrecache = (): Plugin => {
  let root = "";
  let outDir = "";
  return {
    name: "galmuri-sw-precache",
    apply: "build",
    configResolved: (config) => void ({ root, build: { outDir } } = config),
    closeBundle: () => void writeServiceWorker(root, outDir),
  };
};

export default defineConfig({
  plugins: [react(), serviceWorkerPrecache()],
  server: { port: 5180, strictPort: true, proxy: { "/api": backend, "/auth": backend } },
});
