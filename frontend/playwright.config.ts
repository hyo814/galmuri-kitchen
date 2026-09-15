import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

// 화면 단위 테스트(E2E). 빌드한 화면을 Flask가 그대로 내어 주는 운영과 같은 모양으로 띄운다.
// 개발 서버(5180·5181)·다른 세션 포트와 겹치지 않게 전용 포트를 쓴다.
const PORT = Number(process.env.E2E_PORT || 5320);
const DB = join(tmpdir(), `galmuri-e2e-${PORT}.sqlite3`);

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 384, height: 854 }, // 갤럭시 S22 Ultra 화면 폭(스펙 기준 기기)
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    serviceWorkers: "block", // 서비스워커 캐시가 새 빌드를 가리지 않게
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    // 매번 빈 DB로 시작한다. 테스트마다 '로그인 없이 체험하기'로 새 체험 계정(예시 재고)을 만들어 서로 섞이지 않는다
    command:
      `npm run build && cd ../backend && rm -f "${DB}" && .venv/bin/flask --app app db upgrade && ` +
      `.venv/bin/flask --app app seed-sample-recipes && exec .venv/bin/flask --app app run --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/auth-options`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      FLASK_SKIP_DOTENV: "1", // backend/.env의 실제 키를 읽지 않는다 — AI·유튜브·식약처는 개발 모드 예시 결과로 돈다
      DEV_MODE: "1",
      DEMO_LOGIN: "1",
      DEMO_IP_HOURLY_LIMIT: "100000",
      DEMO_IP_DAILY_LIMIT: "100000",
      DATABASE_URL: `sqlite:///${DB}`,
    },
  },
});
