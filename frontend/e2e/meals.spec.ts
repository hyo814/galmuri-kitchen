import { expect, openTab, test } from "./fixtures";
import type { Page } from "@playwright/test";

// 체험 계정 예시 식단(backend/app/demo.py MEAL_PLAN_SLOTS): 저녁은 매일(오늘 저녁 된장찌개), 점심은 사흘(내일 점심 김치찌개),
// 아침은 내일 토스트 하나. 직접 쓴 칸(토스트·카레라이스·김밥·비빔밥·잔치국수·제육덮밥)은 1인분 kcal이 있다. 7일 × 4끼 = 28칸 중 11칸.
// 모두 2인분이고 마지막 날 저녁 된장찌개만 3인분(장보기에 모자란 애호박이 생기게).

const todayCard = (page: Page) => page.locator(".ml-day.today");

async function goToMeals(page: Page) {
  await openTab(page, "식단");
  await expect(page.locator(".topbar .summary")).toBeVisible();
}

test("체험 계정 예시 식단이 처음부터 채워져 보인다", async ({ page }) => {
  await goToMeals(page);
  await expect(page.locator(".topbar .summary")).toHaveText("28칸 중 11칸 채웠어요");
  await expect(todayCard(page).getByRole("button", { name: /저녁 된장찌개/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /점심 김치찌개/ })).toBeVisible();
  // 빈 날이 없다: 7일 모두 저녁이 있고 `0 / 4`인 날이 없다
  await expect(page.locator(".ml-day")).toHaveCount(7);
  await expect(page.locator('.ml-day .ml-slot[data-meal="dinner"]')).toHaveCount(7);
  await expect(page.locator(".ml-day .ml-count", { hasText: "0 / 4" })).toHaveCount(0);
  // 직접 쓴 칸도 AI 초안 칸처럼 1인분 kcal이 보인다
  await expect(page.getByRole("button", { name: /아침 토스트, 2인분, 1인분 약 366kcal$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /저녁 제육덮밥, 2인분, 1인분 약 950kcal$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /저녁 된장찌개, 3인분,/ })).toBeVisible();
  await expect(page.locator(".ml-slot .ml-sub", { hasText: "3인분" })).toHaveCount(1);
});

test("새 식단을 만들면 바로 보이고 식단 고르기 목록에도 생기며 새로고침해도 남는다", async ({ page }) => {
  await goToMeals(page);
  await page.getByRole("button", { name: /다른 식단 고르기$/ }).click();
  await expect(page.getByRole("heading", { name: "식단 고르기" })).toBeVisible();
  await page.getByRole("button", { name: "새 식단 만들기" }).click();
  await expect(page.getByRole("heading", { name: "식단 만들기" })).toBeVisible();
  await page.getByLabel("이름").fill("테스트 식단");
  await page.getByRole("button", { name: "만들기", exact: true }).click();

  await expect(page.getByRole("button", { name: "테스트 식단, 다른 식단 고르기" })).toBeVisible();

  await page.reload();
  await goToMeals(page);
  await page.getByRole("button", { name: /다른 식단 고르기$/ }).click();
  await expect(page.getByRole("list").getByRole("button", { name: /테스트 식단/ })).toBeVisible();
});

test("빈 칸을 내 레시피로 채우면 칸에 생기고 새로고침해도 남는다", async ({ page }) => {
  await goToMeals(page);
  const today = todayCard(page);
  await today.getByRole("button", { name: /아침 채우기$/ }).click();
  await expect(page.getByRole("heading", { name: "아침 채우기" })).toBeVisible();
  // sr-only 라디오가 보이는 점(mo-dot)에 가려 pointer 판정에 걸린다 — 실제 값 반영은 그대로 된다
  await page.getByRole("radio", { name: "김치찌개" }).check({ force: true });
  await page.getByRole("button", { name: "넣기" }).click();

  await expect(today.getByRole("button", { name: /아침 김치찌개/ })).toBeVisible();

  await page.reload();
  await goToMeals(page);
  await expect(todayCard(page).getByRole("button", { name: /아침 김치찌개/ })).toBeVisible();
});

test("칸을 비우면 칸에서 사라지고 새로고침해도 그대로다", async ({ page }) => {
  await goToMeals(page);
  const today = todayCard(page);
  await today.getByRole("button", { name: /저녁 된장찌개/ }).click();
  await expect(page.getByRole("heading", { name: "된장찌개" })).toBeVisible();
  await page.getByRole("button", { name: "칸 비우기" }).click();

  await expect(today.getByRole("button", { name: /저녁 채우기$/ })).toBeVisible();
  await expect(today.getByRole("button", { name: /저녁 된장찌개/ })).toHaveCount(0);

  await page.reload();
  await goToMeals(page);
  await expect(todayCard(page).getByRole("button", { name: /저녁 채우기$/ })).toBeVisible();
  await expect(todayCard(page).getByRole("button", { name: /저녁 된장찌개/ })).toHaveCount(0);
});

test("이번 주 복사를 하면 다음 주 칸이 채워지고 새로고침해도 남는다", async ({ page }) => {
  await goToMeals(page);
  await expect(page.locator(".topbar .summary")).toHaveText("28칸 중 11칸 채웠어요");

  await page.getByRole("button", { name: "식단 메뉴" }).click();
  await page.getByRole("button", { name: "이번 주 복사" }).click();
  await expect(page.getByRole("heading", { name: "이번 주 복사" })).toBeVisible();
  await page.getByRole("button", { name: "1주에 복사" }).click();

  // 복사로 다음 주까지 들어가 식단 기간이 14일(56칸)로 늘어난다(MealCopySheet 안내와 같음)
  await expect(page.locator(".ml-copied")).toContainText("칸을 복사했어요");
  await expect(page.locator(".topbar .summary")).toHaveText("56칸 중 22칸 채웠어요");

  await page.reload();
  await goToMeals(page);
  await expect(page.locator(".topbar .summary")).toHaveText("56칸 중 22칸 채웠어요");
});

test("AI 식단 초안(예시 결과)을 넣으면 칸이 늘고 새로고침해도 남는다", async ({ page }) => {
  await goToMeals(page);
  await expect(page.locator(".topbar .summary")).toHaveText("28칸 중 11칸 채웠어요");

  await page.getByRole("button", { name: "AI 초안" }).click();
  await expect(page.getByRole("heading", { name: "AI 식단 초안" })).toBeVisible();
  await page.getByRole("button", { name: /^초안 만들기/ }).click();

  await expect(page.getByRole("button", { name: /칸 식단에 넣기$/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("오늘 체험용 AI를 다 써서 예시 식단을 보여줘요")).toBeVisible();
  await page.getByRole("button", { name: /칸 식단에 넣기$/ }).click();

  await expect(page.locator(".ml-copied")).toContainText("칸을 넣었어요");
  await expect(page.locator(".topbar .summary")).not.toHaveText("28칸 중 11칸 채웠어요");
  const filledText = await page.locator(".topbar .summary").textContent();

  await page.reload();
  await goToMeals(page);
  await expect(page.locator(".topbar .summary")).toHaveText(filledText!);
});

test("식단으로 장보기 목록을 만들면 장보기 탭에 생기고 새로고침해도 남는다", async ({ page }) => {
  await goToMeals(page);
  await page.getByRole("button", { name: "장보기 목록 만들기" }).click();
  await expect(page.getByRole("heading", { name: "장보기 목록 만들기" })).toBeVisible();
  await expect(page.locator(".topbar .summary")).toBeVisible(); // 재료 계산이 끝나야 담을 줄이 보인다

  // 마지막 날 된장찌개가 3인분이라 애호박이 모자라 체크된 줄 하나로 시작한다(담을 양은 정수로 올리고 필요 양은 소수 한 자리)
  const zucchini = page.getByRole("checkbox", { name: "애호박 1개 담기" });
  await expect(zucchini).toBeChecked();
  await expect(page.locator(".ml-prow", { has: zucchini }).getByText("1.2개 필요 · 1개 있어요")).toBeVisible();
  const addButton = page.getByRole("button", { name: /개 장보기에 담기$/ });
  await expect(addButton).toHaveText("1개 장보기에 담기");

  // 재고에 없는 숟가락 양 재료(된장 2큰술 등)는 `양념` 묶음에 꺼진 채로 있다(집에 있는 양념을 자동으로 담지 않게) — 된장만 켠다
  const seasoning = page.locator("section", { has: page.getByRole("heading", { name: /^양념 · 집에 없으면 골라주세요/ }) });
  const doenjang = seasoning.getByRole("checkbox", { name: "된장 1개 담기" });
  await expect(doenjang).not.toBeChecked();
  const doenjangRow = seasoning.locator(".ml-prow", { has: page.getByRole("checkbox", { name: "된장 1개 담기" }) });
  await expect(doenjangRow.getByText("7큰술 필요 · 없어요")).toBeVisible(); // 2큰술 × 2·2·3인분
  await expect(page.getByText("단위가 달라요 · 직접 골라주세요")).toHaveCount(0);
  await doenjang.click();
  await expect(doenjang).toBeChecked();
  await expect(addButton).toHaveText("2개 장보기에 담기");
  await addButton.click();

  await expect(page.locator("p.notice")).toContainText("식단에서 2개를 담았어요");
  for (const name of ["애호박", "된장"]) await expect(page.getByRole("checkbox", { name: `${name} 샀어요` })).toBeVisible();

  await page.reload();
  await openTab(page, "장보기");
  for (const name of ["애호박", "된장"]) await expect(page.getByRole("checkbox", { name: `${name} 샀어요` })).toBeVisible();
});
