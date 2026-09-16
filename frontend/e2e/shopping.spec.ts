import { app, expect, openTab, test } from "./fixtures";

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
  await expect(page.getByText("저장 전")).toHaveCount(0); // 이 체크가 서버까지 저장돼 "저장 전" 표시가 없어질 때까지

  await page.getByRole("button", { name: "재고에 넣기" }).click();
  await expect(page).toHaveURL(/#\/shopping\/stock/);

  await page.getByLabel("새우깡 보관 위치").selectOption({ label: "냉장실" });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/stock") && r.ok()),
    page.getByRole("button", { name: /개 넣기/ }).click(),
  ]);

  await expect(page).toHaveURL(/#\/shopping$/);
  // 재고에 넣기 뒤 목록이 새로 받아질 때까지(대파·우유도 체크돼 있어 함께 재고로 들어간다 — 체크 안 한 두부로 로딩 완료를 확인)
  await expect(app(page).getByText("두부")).toBeVisible();
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
  await expect(app(page).getByText("두부")).toBeVisible(); // 목록이 다시 불러와질 때까지 기다린 뒤
  await expect(page.getByText("건포도")).toHaveCount(0);
});

test("쇼핑몰에서 찾기를 누르면 쇼핑몰 링크 시트가 열린다", async ({ page }) => {
  await openTab(page, "장보기");
  await page.getByRole("button", { name: "두부 쇼핑몰에서 찾기" }).click();
  const dialog = page.getByRole("dialog"); // 시트 안 링크만(탭 막대에도 "장보기" 등 링크가 있어 페이지 전체에서 찾으면 안 된다)
  await expect(dialog.getByRole("heading", { name: "두부 찾기" })).toBeVisible();
  await expect(dialog.getByRole("link", { name: "쿠팡 검색 결과로 두부 찾기 (새 창)" })).toBeVisible();
  // 쇼핑몰 7곳마다 링크가 하나 이상(확인된 쇼핑몰은 정렬 칩 여러 개로 바뀌어 총 개수는 고정하지 않는다, storeLinks.ts verified)
  for (const store of ["쿠팡", "네이버 쇼핑", "컬리", "이마트몰", "홈플러스", "롯데마트", "G마켓"])
    await expect(dialog.getByRole("link", { name: new RegExp(`^${store} .*두부 찾기 \\(새 창\\)$`) }).first()).toBeVisible();
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

test("사진에서 살 것을 뽑으면(예시 결과) 체크한 것만 장보기 목록에 들어가고 새로고침해도 남는다", async ({ page }) => {
  await openTab(page, "장보기");
  await page.getByRole("button", { name: "항목 추가" }).click();
  await page.getByRole("button", { name: "사진에서 뽑기" }).click();
  await page.getByRole("button", { name: "앨범에서 고르기" }).click();

  await page
    .locator('input[type="file"]:not([capture])')
    .setInputFiles({ name: "memo.png", mimeType: "image/png", buffer: PNG });

  await expect(page.getByText(/찾은 살 것 \d+개/)).toBeVisible();
  // 예시 결과(backend/app/ai.py SAMPLES["memo"]): 대파·두부·계란·수세미는 이미 목록에 있어 기본으로 꺼져 있고,
  // 참기름·양파만 기본으로 켜져 있다(양파는 이미 재고로 들어간 "산 것"이라 목록엔 없어 켜짐)
  await expect(page.getByRole("checkbox", { name: "참기름 담기" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("checkbox", { name: "대파 담기" })).toHaveAttribute("aria-checked", "false");
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/shopping/items/bulk") && r.ok()),
    page.getByRole("button", { name: /\d+개 장보기에 담기/ }).click(),
  ]);

  await expect(page.getByText(/장보기에 \d+개 담았어요/)).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "참기름 샀어요" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "양파 샀어요" })).toBeVisible();
  await expect(app(page).getByText("대파")).toHaveCount(1); // 이미 있던 대파는 다시 담기지 않아 한 줄 그대로

  await page.reload();
  await expect(page.getByRole("checkbox", { name: "참기름 샀어요" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "양파 샀어요" })).toBeVisible();
});

test("오프라인에서 체크하면 연결된 뒤 서버에 저장된다", async ({ page, context }) => {
  await openTab(page, "장보기");

  await context.setOffline(true);
  await expect(page.getByText("오프라인 · 연결되면 저장돼요")).toBeVisible();
  await page.getByRole("checkbox", { name: "두부 샀어요" }).click();
  await expect(page.getByRole("checkbox", { name: "두부 샀어요" })).toHaveAttribute("aria-checked", "true");

  await context.setOffline(false);
  // 화면 상태가 아니라 서버 값으로 저장됐는지 직접 기다린다(연결되는 대로 밀린 변경을 보낸다)
  await expect
    .poll(async () => {
      const res = await page.request.get("/api/shopping");
      const body = await res.json();
      return body.items.find((i: { name: string }) => i.name === "두부")?.done_at ?? null;
    })
    .toBeTruthy();

  await page.reload();
  await expect(page.getByRole("checkbox", { name: "두부 샀어요" })).toHaveAttribute("aria-checked", "true");
});
