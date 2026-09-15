import { expect, test as base } from "@playwright/test";

/** 테스트마다 새 체험 계정(예시 재고가 든)으로 로그인한 채 재고 탭을 연다. */
export const test = base.extend({
  page: async ({ page }, use) => {
    const res = await page.request.post("/api/demo-login", { headers: { "X-Requested-With": "fetch" } });
    expect(res.ok(), await res.text()).toBeTruthy();
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
    await use(page);
  },
});

export { expect };

/** 아래 탭 막대에서 탭을 누른다. */
export async function openTab(page: import("@playwright/test").Page, label: "재고" | "레시피" | "장보기" | "식단" | "더보기") {
  await page.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link", { name: label }).click();
}
