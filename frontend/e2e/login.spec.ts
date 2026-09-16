import { expect, test, type Page } from "@playwright/test";
import { app, test as demoTest } from "./fixtures";

test("로그인 없이 체험하기 → 예시 재고가 보이고, 로그아웃하면 로그인 화면으로 돌아간다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "로그인 없이 체험하기" }).click();

  await expect(app(page).getByText("두부").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "재고" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", { name: "더보기" }).click();
  page.once("dialog", (dialog) => dialog.accept()); // "로그아웃할까요?"
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByRole("button", { name: "로그인 없이 체험하기" })).toBeVisible();
});

/** 이 페이지가 보낸 체험 로그인 요청 수(page.request로 보낸 건 세지 않는다) */
function countDemoLogins(page: Page) {
  const count = { value: 0 };
  page.on("request", (req) => {
    if (req.method() === "POST" && new URL(req.url()).pathname === "/api/demo-login") count.value++;
  });
  return count;
}

const myId = async (page: Page) => ((await (await page.request.get("/api/me")).json()) as { id: number }).id;

test("바로 체험 주소(/?demo=1) → 로그인 화면 없이 재고가 열리고, 주소에서 demo가 빠져 새로고침해도 같은 계정이다", async ({ page }) => {
  const demoLogins = countDemoLogins(page);
  // 로그인 화면이 한 번이라도 그려졌는지 적어 둔다(시작 화면에 가려도 DOM에는 생긴다)
  await page.addInitScript(() => {
    new MutationObserver(() => {
      if (document.querySelector("main.login")) sessionStorage.setItem("sawLogin", "1");
    }).observe(document, { childList: true, subtree: true });
  });

  await page.goto("/?demo=1");
  await expect(page.getByRole("link", { name: "재고" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("region", { name: "체험 안내" })).toBeVisible(); // 체험 첫 30초 안내(스펙 30절 C)
  await expect(page).toHaveURL("/");
  expect(await page.evaluate(() => sessionStorage.getItem("sawLogin"))).toBeNull();
  expect(demoLogins.value).toBe(1);
  const id = await myId(page);

  await page.reload();
  await expect(page.getByRole("region", { name: "체험 안내" })).toBeVisible();
  expect(demoLogins.value).toBe(1);
  expect(await myId(page)).toBe(id);
  expect(await page.evaluate(() => sessionStorage.getItem("sawLogin"))).toBeNull();
});

demoTest("이미 로그인한 채 바로 체험 주소를 열면 체험 계정을 새로 만들지 않고 해시 경로 그대로 연다(나중에 로그아웃해도)", async ({ page }) => {
  const id = await myId(page);
  const demoLogins = countDemoLogins(page);

  await page.goto("/?demo=1#/more");
  await expect(page.getByRole("link", { name: "더보기" })).toHaveAttribute("aria-current", "page");
  await expect(page).toHaveURL("/#/more");
  expect(demoLogins.value).toBe(0);
  expect(await myId(page)).toBe(id);

  page.once("dialog", (dialog) => dialog.accept()); // "로그아웃할까요?"
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByRole("button", { name: "로그인 없이 체험하기" })).toBeVisible();
  expect(demoLogins.value).toBe(0);
});

test("바로 체험 주소에서 체험 계정을 못 만들면(429) 로그인 화면에 버튼과 같은 오류가 보이고, 다시 누르면 열린다", async ({ page }) => {
  const message = "지금 같은 인터넷으로 체험하는 분이 많아요. 잠시 뒤 다시 누르거나 카카오·네이버로 로그인해주세요.";
  await page.route("**/api/demo-login", (route) => route.fulfill({ status: 429, json: { error: message } }));

  await page.goto("/?demo=1");
  await expect(page.getByRole("alert")).toHaveText(message);
  await expect(page).toHaveURL("/");

  await page.unroute("**/api/demo-login");
  await page.getByRole("button", { name: "로그인 없이 체험하기" }).click();
  await expect(page.getByRole("region", { name: "체험 안내" })).toBeVisible();
});
