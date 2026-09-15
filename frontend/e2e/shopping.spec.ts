import { expect, openTab, test } from "./fixtures";

type Page = import("@playwright/test").Page;

// 1x1 투명 PNG. 메모 사진에서 뽑기(사진 인식)에 넘길 최소 유효 이미지.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  "base64",
);

/** 장보기 살 것 추가 시트를 채워 저장하고, 서버에 담길 때까지 기다린다 */
async function addItem(page: Page, name: string, quantity: string) {
  await page.getByRole("button", { name: "항목 추가" }).click();
  await page.getByLabel("이름").fill(name);
  await page.getByLabel("수량").fill(quantity);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items") && r.request().method() === "POST" && r.ok()),
    page.getByRole("button", { name: "추가", exact: true }).click(),
  ]);
}

test("살 것을 추가해 체크하고 재고에 넣으면 목록에서 빠지고 재고 탭에 생긴다", async ({ page }) => {
  await openTab(page, "장보기");
  await addItem(page, "새우깡", "1봉");
  await expect(page.getByText("새우깡")).toBeVisible();

  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/") && r.request().method() === "PATCH" && r.ok()),
    page.getByRole("checkbox", { name: "새우깡 샀어요" }).click(),
  ]);
  await expect(page.locator(".sh-offline")).not.toBeVisible();

  await page.getByRole("button", { name: "재고에 넣기" }).click();
  await expect(page).toHaveURL(/#\/shopping\/stock/);

  await page.getByLabel("새우깡 보관 위치").selectOption({ label: "냉장실" });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/stock") && r.ok()),
    page.getByRole("button", { name: /개 넣기/ }).click(),
  ]);

  await expect(page).toHaveURL(/#\/shopping$/);
  await expect(page.getByText("새우깡")).toHaveCount(0); // 접힌 "산 것"에만 남아 화면엔 안 보인다

  await openTab(page, "재고");
  await expect(page.getByText("새우깡")).toBeVisible();
});

test("살 것을 고치면 목록에 바뀐 값이 보이고 새로고침해도 남는다", async ({ page }) => {
  await openTab(page, "장보기");
  await addItem(page, "고구마", "1개");
  await expect(page.getByText("고구마")).toBeVisible();

  await page.getByRole("button", { name: "고구마1개", exact: true }).click();
  await expect(page.getByRole("heading", { name: "살 것 고치기" })).toBeVisible();
  await page.getByLabel("수량").fill("5개");
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/") && r.request().method() === "PATCH" && r.ok()),
    page.getByRole("button", { name: "저장" }).click(),
  ]);

  await expect(page.getByRole("button", { name: /고구마.*5개/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: /고구마.*5개/ })).toBeVisible();
});

test("살 것을 목록에서 빼면 사라지고 새로고침해도 돌아오지 않는다", async ({ page }) => {
  await openTab(page, "장보기");
  await addItem(page, "건포도", "1봉");
  await expect(page.getByText("건포도")).toBeVisible();

  await page.getByRole("button", { name: "건포도1봉", exact: true }).click();
  page.once("dialog", (d) => d.accept()); // "목록에서 뺄까요?"
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/") && r.request().method() === "DELETE" && r.ok()),
    page.getByRole("button", { name: "목록에서 빼기" }).click(),
  ]);

  await expect(page.getByText("건포도")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("건포도")).toHaveCount(0);
});

test("쇼핑몰에서 찾기를 누르면 쇼핑몰 링크 시트가 열린다", async ({ page }) => {
  await openTab(page, "장보기");
  await page.getByRole("button", { name: "두부 쇼핑몰에서 찾기" }).click();
  await expect(page.getByRole("heading", { name: "두부 찾기" })).toBeVisible();
  await expect(page.getByRole("link").first()).toBeVisible();
});

test("장보기 메모를 지우고 새로 쓰면 카드에 나타나고 새로고침해도 남는다", async ({ page }) => {
  await openTab(page, "장보기");
  // 예시 메모가 이미 하나 있어(메모 카드는 1개일 땐 "더 보기"가 없다) 지운 뒤 "메모 쓰기"로 새로 만든다
  await page.getByRole("button", { name: /이마트 성수점/ }).click();
  await expect(page.getByRole("heading", { name: "장보기 메모" })).toBeVisible();
  page.once("dialog", (d) => d.accept()); // "메모와 사진을 삭제할까요?"
  await page.getByRole("button", { name: "메모 삭제" }).click();
  await expect(page).toHaveURL(/#\/shopping$/);

  await page.getByRole("button", { name: "메모 쓰기" }).click();
  await expect(page.getByRole("heading", { name: "장보기 메모" })).toBeVisible();
  const saved = page.waitForResponse((r) => r.url().includes("/api/shopping/notes/") && r.request().method() === "PUT" && r.ok());
  await page.getByLabel("어디서").fill("코스트코");
  await page.getByLabel("메모").fill("우유 사기");
  await page.getByRole("main").getByRole("link", { name: "장보기" }).click(); // 뒤로가기 링크(탭 막대의 "장보기"와 구분)
  await saved;

  await expect(page.getByText("코스트코")).toBeVisible();
  await expect(page.getByText("우유 사기")).toBeVisible();
  await page.reload();
  await expect(page.getByText("코스트코")).toBeVisible();
  await expect(page.getByText("우유 사기")).toBeVisible();
});

test("사진에서 살 것을 뽑으면(예시 결과) 담은 것만 장보기 목록에 들어간다", async ({ page }) => {
  await openTab(page, "장보기");
  await page.getByRole("button", { name: "항목 추가" }).click();
  await page.getByRole("button", { name: "사진에서 뽑기" }).click();
  await page.getByRole("button", { name: "앨범에서 고르기" }).click();

  await page
    .locator('input[type="file"]:not([capture])')
    .setInputFiles({ name: "memo.png", mimeType: "image/png", buffer: PNG });

  await expect(page.getByText(/찾은 살 것 \d+개/)).toBeVisible();
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/bulk") && r.ok()),
    page.getByRole("button", { name: /\d+개 장보기에 담기/ }).click(),
  ]);

  await expect(page.getByText(/장보기에 \d+개 담았어요/)).toBeVisible();
});

test("오프라인에서 체크하면 연결된 뒤 서버에 저장된다", async ({ page, context }) => {
  await openTab(page, "장보기");

  await context.setOffline(true);
  await expect(page.getByText("오프라인 · 연결되면 저장돼요")).toBeVisible();
  await page.getByRole("checkbox", { name: "두부 샀어요" }).click();
  await expect(page.getByRole("checkbox", { name: "두부 샀어요" })).toHaveAttribute("aria-checked", "true");

  await context.setOffline(false);
  await expect(page.locator(".sh-offline")).not.toBeVisible(); // 오프라인 띠 → 저장 중 띠가 사라질 때까지

  const res = await page.request.get("/api/shopping");
  const body = await res.json();
  const item = body.items.find((i: { name: string }) => i.name === "두부");
  expect(item?.done_at).toBeTruthy();

  await page.reload();
  await expect(page.getByRole("checkbox", { name: "두부 샀어요" })).toHaveAttribute("aria-checked", "true");
});
