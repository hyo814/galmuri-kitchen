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

/** 앱 화면(#root). index.html의 PC 소개(aside.pitch, 폰 폭에서는 숨김)에도 "두부·대파" 같은 글자가 있어서
 *  페이지 전체 getByText는 숨은 소개 문구에 먼저 걸린다(스펙 30절 A). 흔한 재료 이름은 이 안에서 찾는다 */
export const app = (page: import("@playwright/test").Page) => page.locator("#root");

/** 아래 탭 막대에서 탭을 누른다. */
export async function openTab(page: import("@playwright/test").Page, label: "재고" | "레시피" | "장보기" | "식단" | "더보기") {
  await page.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link", { name: label }).click();
}
