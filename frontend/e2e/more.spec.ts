import type { Page } from "@playwright/test";
import { expect, openTab, test } from "./fixtures";

// ---- 날짜 계산(브라우저 locale·timezoneId는 Asia/Seoul, api.ts localToday()와 같은 방식) ----
const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const seoulToday = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
function addDays(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + delta)).toISOString().slice(0, 10);
}
/** 달력 칸 aria-label 앞부분 "9월 16일 수요일" (foodlog/log.ts cellLabel과 같은 규칙) */
function dateLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${m}월 ${d}일 ${DOW[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}요일`;
}

// 1x1 검정 PNG — 사진 업로드 흐름(resizeImage가 createImageBitmap으로 읽을 수 있는 진짜 이미지)용
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);
const pngFile = (name: string) => ({ name, mimeType: "image/png", buffer: PNG });

async function openFoodLog(page: Page) {
  await openTab(page, "더보기");
  await page.getByRole("button", { name: /먹은 기록/ }).click();
  await expect(page.getByRole("heading", { name: "먹은 기록", level: 1 })).toBeVisible();
}

/** 달력에서 날짜 칸을 눌러 날짜 상세 시트를 연다 */
async function openDayCell(page: Page, iso: string, todaySuffix = false) {
  const name = new RegExp(`^${dateLabel(iso)}${todaySuffix ? " · 오늘" : ""}`);
  await page.getByRole("button", { name }).click();
}

test.describe("먹은 기록", () => {
  test("식단 칸을 '먹었어요'로 남기면 달력·시트에 보이고 새로고침해도 남는다", async ({ page }) => {
    const today = seoulToday();
    await openFoodLog(page);
    await openDayCell(page, today, true);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(today)}`) });
    await expect(daySheet.getByText("식단에")).toBeVisible();
    await daySheet.getByRole("button", { name: "식단 된장찌개 먹었어요" }).click();

    // 식단 제안 줄이 사라지고(먼저 기다린다) 저녁 목록에 기록으로 바뀐다
    await expect(daySheet.getByRole("button", { name: "식단 된장찌개 먹었어요" })).toHaveCount(0);
    await expect(daySheet.getByRole("button", { name: /된장찌개/ })).toBeVisible();

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /된장찌개/ })).toBeVisible();
  });

  test("내 레시피를 찾아 추가하면 목록에 생기고 새로고침해도 남는다", async ({ page }) => {
    const today = seoulToday();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await page.getByRole("button", { name: "점심 먹은 것 추가" }).click();

    const addSheet = page.getByRole("dialog", { name: /먹은 것 추가/ });
    await expect(addSheet.getByRole("group", { name: "무엇을 먹었나요" })).toBeVisible();
    await addSheet.getByLabel("내 레시피 찾기").fill("김치찌개");
    await addSheet.getByRole("radiogroup", { name: "내 레시피" }).getByText("김치찌개").click();
    await addSheet.getByRole("button", { name: "집밥" }).click();
    await addSheet.getByRole("button", { name: "남기기" }).click();
    await expect(addSheet).toHaveCount(0);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(today)}`) });
    await expect(daySheet.getByRole("button", { name: /김치찌개/ })).toBeVisible();

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /김치찌개/ })).toBeVisible();
  });

  test("음식을 찾아 무게(g)로 추가하면 미리보기가 보이고 목록에 생긴다", async ({ page }) => {
    const today = seoulToday();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await page.getByRole("button", { name: "간식 먹은 것 추가" }).click();

    const addSheet = page.getByRole("dialog", { name: /먹은 것 추가/ });
    await addSheet.getByRole("group", { name: "무엇을 먹었나요" }).getByRole("button", { name: "음식 찾기" }).click();
    await addSheet.getByLabel("먹은 음식 이름").fill("비빔밥");
    await addSheet.getByRole("radiogroup", { name: "음식" }).getByText("비빔밥").click();
    const amountField = addSheet.getByRole("group", { name: "얼마나 먹었어요?" });
    await expect(amountField.getByText(/kcal/)).toBeVisible();

    await amountField.getByRole("button", { name: "g" }).click();
    await addSheet.getByLabel("먹은 양(g)").fill("300");
    await expect(amountField.getByText(/kcal/)).toBeVisible();

    await addSheet.getByRole("button", { name: "남기기" }).click();
    await expect(addSheet).toHaveCount(0);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(today)}`) });
    await expect(daySheet.getByRole("button", { name: /비빔밥/ })).toBeVisible();
    await expect(daySheet.getByText("300g")).toBeVisible();

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /비빔밥/ })).toBeVisible();
  });

  test("이름만 직접 남기면 목록에 생기고 새로고침해도 남는다", async ({ page }) => {
    const today = seoulToday();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await page.getByRole("button", { name: "저녁 먹은 것 추가" }).click();

    const addSheet = page.getByRole("dialog", { name: /먹은 것 추가/ });
    await addSheet.getByRole("group", { name: "무엇을 먹었나요" }).getByRole("button", { name: "직접" }).click();
    await addSheet.getByLabel("무엇을 먹었나요?").fill("닭가슴살 샐러드");
    await addSheet.getByRole("button", { name: "집밥" }).click();
    await addSheet.getByRole("button", { name: "남기기" }).click();
    await expect(addSheet).toHaveCount(0);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(today)}`) });
    await expect(daySheet.getByRole("button", { name: /닭가슴살 샐러드/ })).toBeVisible();

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /닭가슴살 샐러드/ })).toBeVisible();
  });

  test("먹은 기록을 고치면(이름·별점·메모) 목록에 반영되고 새로고침해도 남는다", async ({ page }) => {
    const today = seoulToday();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await page.getByRole("dialog").getByRole("button", { name: /토스트/ }).click();

    const editSheet = page.getByRole("dialog", { name: /먹은 것 고치기/ });
    await expect(editSheet.getByText("토스트")).toBeVisible();
    await editSheet.getByRole("button", { name: "바꾸기" }).click();
    await editSheet.getByLabel("무엇을 먹었나요?").fill("구운 계란과 시금치");
    await editSheet.getByRole("radiogroup", { name: "만족도" }).getByRole("radio", { name: "2점" }).click();
    await editSheet.locator("textarea").fill("아점 대신 제대로 챙겼어요");
    await editSheet.getByRole("button", { name: "저장" }).click();
    await expect(editSheet).toHaveCount(0);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(today)}`) });
    await expect(daySheet.getByRole("button", { name: /구운 계란과 시금치/ })).toBeVisible();
    await expect(daySheet.getByText("아점 대신 제대로 챙겼어요")).toBeVisible();
    await expect(daySheet.getByRole("img", { name: "만족도 2점" })).toBeVisible();

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /구운 계란과 시금치/ })).toBeVisible();
  });

  test("사진을 추가했다가 빼고 저장하면, 다시 열어 지운 사진도 서버에서 없어진다", async ({ page }) => {
    const today = seoulToday();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await page.getByRole("button", { name: "간식 먹은 것 추가" }).click();

    const addSheet = page.getByRole("dialog", { name: /먹은 것 추가/ });
    await addSheet.getByRole("group", { name: "무엇을 먹었나요" }).getByRole("button", { name: "직접" }).click();
    await addSheet.getByLabel("무엇을 먹었나요?").fill("심야간식");

    const albumInput = addSheet.locator('input[type="file"][multiple]');
    await albumInput.setInputFiles([pngFile("a.png"), pngFile("b.png")]);
    await expect(addSheet.getByRole("button", { name: "사진 1 빼기" })).toBeVisible();
    await expect(addSheet.getByRole("button", { name: "사진 2 빼기" })).toBeVisible();
    await addSheet.getByRole("button", { name: "사진 2 빼기" }).click();
    await expect(addSheet.getByRole("button", { name: "사진 2 빼기" })).toHaveCount(0);

    await addSheet.getByRole("button", { name: "남기기" }).click();
    await expect(addSheet).toHaveCount(0);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(today)}`) });
    const logButton = daySheet.getByRole("button", { name: /심야간식/ });
    await expect(logButton).toBeVisible();
    await expect(logButton.locator("img")).toHaveCount(1);

    await logButton.click();
    const editSheet = page.getByRole("dialog", { name: /먹은 것 고치기/ });
    await expect(editSheet.getByRole("button", { name: "사진 1 빼기" })).toBeVisible();
    await editSheet.getByRole("button", { name: "사진 1 빼기" }).click();
    await editSheet.getByRole("button", { name: "저장" }).click();
    await expect(editSheet).toHaveCount(0);
    await expect(logButton.locator("img")).toHaveCount(0);

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, today, true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /심야간식/ }).locator("img")).toHaveCount(0);
  });

  test("먹은 기록을 지우면 목록에서 사라지고 새로고침해도 없다", async ({ page }) => {
    const yesterday = addDays(seoulToday(), -1);
    await openFoodLog(page);
    await openDayCell(page, yesterday);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(yesterday)}`) });
    await daySheet.getByRole("button", { name: /김치찌개/ }).click();

    const editSheet = page.getByRole("dialog", { name: /먹은 것 고치기/ });
    page.once("dialog", (d) => d.accept()); // "이 기록을 지울까요?"
    await editSheet.getByRole("button", { name: "기록 지우기" }).click();
    await expect(editSheet).toHaveCount(0);
    await expect(daySheet.getByRole("button", { name: /김치찌개/ })).toHaveCount(0);

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, yesterday);
    await expect(page.getByRole("dialog").getByRole("button", { name: /김치찌개/ })).toHaveCount(0);
  });

  test("사진만 먼저 남기면 오늘 자리에 사진 기록이 생긴다", async ({ page }) => {
    await openFoodLog(page);
    await page.getByRole("button", { name: "사진만 먼저 남기기" }).click();

    const quickSheet = page.getByRole("dialog", { name: "빠르게 사진만 남기기" });
    const albumInput = quickSheet.locator('input[type="file"]:not([capture])');
    await albumInput.setInputFiles(pngFile("quick.png"));
    await expect(quickSheet).toHaveCount(0);

    const daySheet = page.getByRole("dialog", { name: new RegExp(`^${dateLabel(seoulToday())}`) });
    await expect(daySheet.getByRole("button", { name: /사진 기록/ })).toBeVisible();

    await page.reload();
    await openFoodLog(page);
    await openDayCell(page, seoulToday(), true);
    await expect(page.getByRole("dialog").getByRole("button", { name: /사진 기록/ })).toBeVisible();
  });
});

test("내 몸 정보로 하루 칼로리 목표를 정하면 더보기 카드에 반영되고 새로고침해도 남는다", async ({ page }) => {
  await openTab(page, "더보기");
  await expect(page.getByRole("button", { name: /하루 칼로리 목표.*키·몸무게로/ })).toBeVisible();
  await page.getByRole("button", { name: /하루 칼로리 목표/ }).click();

  const sheet = page.getByRole("dialog", { name: "하루 칼로리 목표 정하기" });
  await sheet.getByRole("group", { name: "성별" }).getByRole("button", { name: "여성" }).click();
  await sheet.getByLabel("태어난 해").fill("1994");
  await sheet.getByLabel("키").fill("165");
  await sheet.getByLabel("몸무게").fill("60");
  await sheet.getByRole("group", { name: "활동량" }).getByRole("button", { name: "보통" }).click();
  await expect(sheet.getByText(/기초대사량/)).toBeVisible();
  await sheet.getByRole("button", { name: "저장" }).click();
  await expect(sheet).toHaveCount(0);

  await expect(page.getByRole("button", { name: /하루 칼로리 목표.*유지 · 하루 [\d,]+kcal/ })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: /하루 칼로리 목표.*유지 · 하루 [\d,]+kcal/ })).toBeVisible();
});

test("주방 도구를 추가·점검하고 삭제하면 목록에 반영된다", async ({ page }) => {
  await openTab(page, "더보기");
  await page.getByRole("button", { name: /주방 도구/ }).click();
  await expect(page.getByRole("heading", { name: "주방 도구" })).toBeVisible();
  await expect(page.getByText("등록한 도구가 없어요.")).toBeVisible();

  await page.getByRole("button", { name: "도구 추가" }).click();
  const addSheet = page.getByRole("dialog", { name: "도구 추가" });
  await addSheet.getByLabel("이름").fill("코팅 프라이팬");
  await expect(addSheet.getByRole("group", { name: "점검 주기" }).getByRole("button", { name: "6개월" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await addSheet.getByRole("button", { name: "저장" }).click();
  await expect(addSheet).toHaveCount(0);

  const row = page.getByRole("button", { name: /코팅 프라이팬/ });
  await expect(row).toContainText("6개월마다 점검");

  await row.click();
  const editSheet = page.getByRole("dialog", { name: "도구 수정" });
  await editSheet.getByRole("button", { name: "점검했어요" }).click();
  await expect(editSheet).toHaveCount(0);
  await expect(row).toContainText("마지막 점검");

  await row.click();
  page.once("dialog", (d) => d.accept()); // "코팅 프라이팬을 삭제할까요?"
  await page.getByRole("dialog", { name: "도구 수정" }).getByRole("button", { name: "이 도구 삭제" }).click();
  await expect(page.getByText("등록한 도구가 없어요.")).toBeVisible();
});

test("데이터 내보내기를 누르면 zip 파일을 받는다", async ({ page }) => {
  await openTab(page, "더보기");
  await page.getByRole("button", { name: /데이터 내보내기/ }).click();

  const sheet = page.getByRole("dialog", { name: "데이터 내보내기" });
  await expect(sheet.getByText("재고")).toBeVisible();
  const downloadButton = sheet.getByRole("button", { name: "내려받기" });
  await expect(downloadButton).toBeEnabled();

  const downloadPromise = page.waitForEvent("download");
  await downloadButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.zip$/);
});
