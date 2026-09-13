import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 다른 프로젝트(5173·5000 등)와 겹치지 않도록 이 앱 전용 포트를 고정한다
const backend = "http://127.0.0.1:5181";

export default defineConfig({
  plugins: [react()],
  server: { port: 5180, strictPort: true, proxy: { "/api": backend, "/auth": backend } },
});
