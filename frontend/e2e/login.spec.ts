import { expect, test } from "@playwright/test";

test("로그인 없이 체험하기 → 예시 재고가 보이고, 로그아웃하면 로그인 화면으로 돌아간다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "로그인 없이 체험하기" }).click();

  await expect(page.getByText("두부").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "재고" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", { name: "더보기" }).click();
  page.once("dialog", (dialog) => dialog.accept()); // "로그아웃할까요?"
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByRole("button", { name: "로그인 없이 체험하기" })).toBeVisible();
});
