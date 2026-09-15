import { expect, test } from "./fixtures";

// 사진 인식 흐름에서 쓰는 아주 작은 PNG(1x1) — 서버는 DEV_MODE라 내용과 무관하게 예시 결과를 준다.
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

/** 재고 목록에서 이름으로 재료를 눌러 `재료 수정` 시트를 연다. */
async function openItem(page: import("@playwright/test").Page, name: string | RegExp) {
  await page.getByRole("button", { name }).click();
  return page.getByRole("dialog", { name: "재료 수정" });
}

test("예시 재고와 유통기한 배지가 보인다", async ({ page }) => {
  await expect(page.getByRole("button", { name: /두부/ })).toContainText("D-1");
  await expect(page.getByRole("button", { name: /대파/ })).toContainText("D-2");
  await expect(page.getByText("재료 10개")).toBeVisible();
});

test("재료를 직접 추가하면 목록에 생기고 새로고침해도 남는다", async ({ page }) => {
  await page.getByRole("button", { name: "재료 추가" }).click();
  const dialog = page.getByRole("dialog", { name: "재료 추가" });
  await dialog.getByLabel("이름").fill("브로콜리");
  await dialog.getByRole("button", { name: "저장", exact: true }).click();
  await expect(dialog).toBeHidden();

  const row = page.getByRole("button", { name: /브로콜리/ });
  await expect(row).toBeVisible();
  await expect(row).toContainText("구입"); // 구입일 칩(기본값 오늘)이 저장한 재료에도 남는다

  await page.reload();
  await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
  await expect(page.getByRole("button", { name: /브로콜리/ })).toBeVisible();
});

test("재료를 수정하면 목록에 반영되고 새로고침해도 남는다", async ({ page }) => {
  const dialog = await openItem(page, /애호박/);
  await dialog.getByRole("spinbutton", { name: "수량" }).fill("2");
  await dialog.getByRole("button", { name: "저장", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /애호박/ })).toContainText("2개");

  await page.reload();
  await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
  await expect(page.getByRole("button", { name: /애호박/ })).toContainText("2개");
});

test("수량을 0으로 저장하면 다 먹은 재료로 자동 삭제되고 새로고침해도 남지 않는다", async ({ page }) => {
  const dialog = await openItem(page, /두부/);
  await dialog.getByRole("spinbutton", { name: "수량" }).fill("0");
  await dialog.getByRole("button", { name: "다 먹었어요 (삭제)" }).click();
  await page.getByRole("dialog", { name: "두부 지우기" }).getByRole("button", { name: "지우기" }).click();

  // 목록이 실제로 다시 불러와진 뒤(달걀은 그대로 남아 있다) 두부가 없어졌는지 본다 —
  // 그냥 toHaveCount(0)만 보면 목록이 아직 불러와지기 전(빈 화면)에도 통과해 버릴 수 있다.
  await expect(page.getByRole("button", { name: /달걀/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /두부/ })).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
  await expect(page.getByRole("button", { name: /달걀/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /두부/ })).toHaveCount(0);
});

test("재료 삭제 이유를 골라 지울 수 있고 새로고침해도 남지 않는다", async ({ page }) => {
  const dialog = await openItem(page, /김치/);
  await dialog.getByRole("button", { name: "이 재료 삭제" }).click();
  const confirmDialog = page.getByRole("dialog", { name: "김치 지우기" });
  await confirmDialog.getByRole("radio", { name: /버렸어요/ }).click();
  await confirmDialog.getByRole("button", { name: "지우기" }).click();

  await expect(page.getByRole("button", { name: /달걀/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /김치/ })).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
  await expect(page.getByRole("button", { name: /달걀/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /김치/ })).toHaveCount(0);
});

test("필수품이 떨어지면 배너가 보이고, 채워 넣으면 배너가 사라지며 새로고침해도 그대로다", async ({ page }) => {
  const banner = page.getByRole("button", { name: /필수품 1개가 떨어졌어요/ });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("간장");
  await banner.click();

  const staplesDialog = page.getByRole("dialog", { name: "필수품" });
  await staplesDialog.getByRole("button", { name: "간장 떨어짐, 재고에 추가" }).click();

  const addDialog = page.getByRole("dialog", { name: "재료 추가" });
  await expect(addDialog.getByLabel("이름")).toHaveValue("간장");
  await addDialog.getByRole("button", { name: "저장", exact: true }).click();
  await expect(addDialog).toBeHidden();

  await expect(page.getByRole("button", { name: /간장/ })).toBeVisible(); // 재고에 실제로 들어갔다
  await expect(page.getByRole("button", { name: /필수품.*떨어졌어요/ })).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
  await expect(page.getByRole("button", { name: /간장/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /필수품.*떨어졌어요/ })).toHaveCount(0);
});

test("설정에서 필수품을 추가하고 지울 수 있다", async ({ page }) => {
  await page.getByRole("button", { name: "설정" }).click();
  await page.getByRole("dialog", { name: "재고 설정" }).getByRole("button", { name: "필수품" }).click();

  const staplesDialog = page.getByRole("dialog", { name: "필수품" });
  await staplesDialog.getByLabel("필수품 이름").fill("후추");
  await staplesDialog.getByRole("button", { name: "추가", exact: true }).click();
  await expect(staplesDialog.getByText("후추")).toBeVisible();

  await staplesDialog.getByRole("button", { name: "편집" }).click();
  page.once("dialog", (d) => d.accept()); // "후추를 필수품에서 뺄까요?"
  await staplesDialog.getByRole("listitem").filter({ hasText: "후추" }).getByRole("button", { name: "삭제" }).click();
  await expect(staplesDialog.getByText("후추")).toHaveCount(0);
});

test("사진으로 재료를 추가하면(예시 결과) 검토한 뒤 재고에 들어간다", async ({ page }) => {
  await page.getByRole("button", { name: "사진으로 추가" }).click();
  // 시트 제목이 단계마다 바뀌므로(사진으로 추가 → 냉장고 사진 N장 → 찾은 재료 N개) 이름 없이 찾는다(이 흐름에는 시트가 하나뿐).
  const scanDialog = page.getByRole("dialog");
  await scanDialog.getByRole("radio", { name: "냉장고 사진" }).click();
  // 카메라·앨범 버튼은 숨은 <input type=file>을 연다 — 사진을 바로 그 입력에 넣는다.
  await scanDialog.locator('input[type="file"][multiple]').setInputFiles({
    name: "photo.png",
    mimeType: "image/png",
    buffer: TINY_PNG,
  });

  await scanDialog.getByRole("button", { name: "1장 읽기" }).click();
  await expect(scanDialog.getByText("찾은 재료 4개")).toBeVisible();
  await scanDialog.getByRole("button", { name: "오늘" }).click(); // 냉장고 사진은 구입일을 직접 골라야 한다
  await scanDialog.getByRole("button", { name: "4개 재고에 넣기" }).click();

  await expect(page.getByRole("status")).toContainText("4개를 재고에 넣었어요");
  await expect(page.getByRole("button", { name: /냉동만두/ })).toBeVisible();
});

test("보관 위치를 추가하고 수정할 수 있다", async ({ page }) => {
  await page.getByRole("button", { name: "위치 관리" }).click();
  const dialog = page.getByRole("dialog", { name: "위치 관리" });
  await dialog.getByLabel("새 위치").fill("베란다");
  await dialog.getByRole("button", { name: "위치 추가" }).click();
  await expect(dialog.getByText("베란다")).toBeVisible();

  await dialog.getByRole("button", { name: "베란다 수정" }).click();
  await dialog.getByLabel("위치 이름").fill("다용도실");
  await dialog.getByRole("button", { name: "저장", exact: true }).click();
  await expect(dialog.getByText("다용도실")).toBeVisible();
  await expect(dialog.getByText("베란다")).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "보관 위치" }).getByRole("button", { name: "다용도실" })).toBeVisible();
});
