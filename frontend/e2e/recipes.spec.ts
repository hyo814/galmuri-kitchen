import { expect, openTab, test } from "./fixtures";
import type { Page } from "@playwright/test";

// 1x1 PNG
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

async function openRecipes(page: Page, segment?: "내 레시피" | "영상" | "양념 비율") {
  await openTab(page, "레시피");
  if (segment) await page.getByRole("button", { name: segment }).click();
}

/** 내 레시피 탭에서 `직접 쓰기`로 재료 1개짜리 레시피를 만들고 상세 화면에 남는다. */
async function addManualRecipe(page: Page, title: string) {
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await page.getByRole("button", { name: "직접 쓰기" }).click();
  await page.getByLabel("이름", { exact: true }).fill(title);
  await page.getByLabel("1번째 재료 이름").fill("두부");
  await page.getByLabel("1번째 재료 양").fill("1모");
  await page.getByLabel("1단계", { exact: true }).fill("두부를 부쳐요.");
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

test("추천 탭의 예시 레시피를 내 레시피로 저장하면 내 레시피 탭에 생기고 새로고침해도 남는다", async ({ page }) => {
  // 체험 계정은 된장찌개·김치찌개를 이미 내 레시피로 갖고 있으므로(demo.py) 겹치지 않는 계란말이로 검증한다
  await openRecipes(page);
  await page.getByRole("region", { name: "예시 레시피" }).getByRole("link", { name: "계란말이" }).click();
  await expect(page.getByRole("heading", { name: "계란말이" })).toBeVisible();

  await page.getByRole("button", { name: "내 레시피로 저장" }).click();
  await expect(page.getByRole("button", { name: "수정" })).toBeVisible(); // 저장 뒤 내 레시피 상세로 바뀐다

  await openRecipes(page, "내 레시피");
  await expect(page.getByRole("link", { name: "계란말이" })).toBeVisible();

  await page.reload();
  await openRecipes(page, "내 레시피");
  await expect(page.getByRole("link", { name: "계란말이" })).toBeVisible();
});

test("레시피를 직접 추가한 뒤 수정하면 내용이 바뀌고 새로고침해도 남는다", async ({ page }) => {
  await addManualRecipe(page, "테스트 요리");

  await page.getByRole("button", { name: "수정" }).click();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue("테스트 요리");
  await page.getByLabel("이름", { exact: true }).fill("테스트 요리 (수정)");
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: "테스트 요리 (수정)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "테스트 요리 (수정)" })).toBeVisible();
});

test("레시피를 삭제하면 목록에서 사라지고 새로고침해도 안 보인다", async ({ page }) => {
  await addManualRecipe(page, "지울 요리");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "이 레시피 삭제" }).click();
  await expect(page.getByRole("heading", { name: "레시피" })).toBeVisible(); // 목록으로 돌아옴
  await expect(page.getByRole("link", { name: "지울 요리" })).toHaveCount(0);

  await page.reload();
  await openRecipes(page, "내 레시피");
  // 목록이 실제로 불러와졌는지부터 확인한다(그래야 아래 없음 검사가 "아직 안 불러옴"으로 통과하지 않는다)
  await expect(page.getByRole("link", { name: "된장찌개" })).toBeVisible();
  await expect(page.getByRole("link", { name: "지울 요리" })).toHaveCount(0);
});

test("식약처 레시피 제목을 검색하면 일치하는 레시피만 보인다", async ({ page }) => {
  await openRecipes(page);
  await page.getByPlaceholder("예시 레시피에서 찾기").fill("시금치");

  await expect(page.getByRole("link", { name: "시금치나물" })).toBeVisible();
  // "내 레시피" 칸은 검색과 무관하게 항상 보이므로(체험 계정이 이미 된장찌개를 갖고 있다) 검색 대상인 예시 레시피 칸만 본다
  await expect(page.getByRole("region", { name: "예시 레시피" }).getByText("된장찌개")).toHaveCount(0);
});

test("레시피 인분을 늘리면 큰술 재료 아래에 밥숟가락 개수가 보이고 레시피 인분으로 돌아오면 사라진다", async ({ page }) => {
  await openRecipes(page);
  await page.getByPlaceholder("예시 레시피에서 찾기").fill("제육볶음");
  await page.getByRole("region", { name: "예시 레시피" }).getByRole("link", { name: "제육볶음" }).click();
  // 만드는 법에도 "고추장"이 나오므로 재료 칸 안에서만 찾는다
  const ingredients = page.getByRole("region", { name: "재료", exact: true });
  const row = (name: string) => ingredients.getByRole("listitem").filter({ hasText: name });
  const stepper = ingredients.getByRole("group", { name: "인분 조절" });
  await expect(row("고추장")).toContainText("2큰술");
  await expect(ingredients.getByText("밥숟가락 약")).toHaveCount(0);

  await stepper.getByRole("button", { name: "인분 늘리기" }).click();
  await expect(stepper).toContainText("3인분");
  await expect(row("고추장")).toContainText("3큰술, 밥숟가락 약 4개"); // 쉼표는 스크린리더에만(양 다음에 이어 읽는다)
  await expect(row("고춧가루")).toContainText("1½큰술, 밥숟가락 약 2개");
  await expect(row("참기름")).toContainText("1½작은술");
  await expect(row("참기름")).not.toContainText("큰술"); // 3작은술이 안 되면 둘째 줄이 없다

  await stepper.getByRole("button", { name: "인분 줄이기" }).click();
  await expect(row("고추장")).toContainText("2큰술");
  await expect(ingredients.getByText("밥숟가락 약")).toHaveCount(0);
});

test("AI 레시피를 만들면 예시 결과 3개가 나오고 자세히 보기·저장이 된다", async ({ page }) => {
  await openRecipes(page);
  await page.getByRole("button", { name: "만들기" }).click();

  await expect(page.getByRole("heading", { name: "AI 레시피" })).toBeVisible();
  await expect(page.getByText("두부 대파 짜글이")).toBeVisible();

  await page.getByRole("button", { name: "두부 대파 짜글이 자세히" }).click();
  await expect(page.getByRole("heading", { name: "두부 대파 짜글이" })).toBeVisible();
  await page.getByRole("button", { name: "두부 대파 짜글이 저장" }).click();
  await expect(page.getByRole("button", { name: "두부 대파 짜글이 저장했어요" })).toBeVisible();

  await openRecipes(page, "내 레시피");
  await expect(page.getByRole("link", { name: "두부 대파 짜글이" })).toBeVisible();
});

test("글 붙여넣기로 레시피를 가져오면 확인 폼에 채워지고 저장하면 내 레시피에 생긴다", async ({ page }) => {
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await page.getByRole("button", { name: "글 붙여넣기" }).click();
  await page.getByLabel("레시피 글").fill("제육볶음 만드는 법. 돼지고기 앞다리살 600g, 양파 1개, 고추장 2큰술로 볶아요.");
  await page.getByRole("button", { name: "정리하기" }).click();

  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue("제육볶음");
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: "제육볶음" })).toBeVisible();

  await openRecipes(page, "내 레시피");
  await expect(page.getByRole("link", { name: "제육볶음" })).toBeVisible();
});

test("사진으로 레시피를 가져오면 확인 폼에 채워진다", async ({ page }) => {
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await page.getByRole("button", { name: "사진으로 가져오기" }).click();

  await page.locator('input[type="file"]').last().setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: TINY_PNG });

  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue("제육볶음");
});

test("양념 비율 프리셋에서 기준량을 바꾸면 양념 양이 그만큼 바뀐다", async ({ page }) => {
  await openRecipes(page, "양념 비율");
  await page.getByRole("region", { name: "기본 양념" }).getByRole("link", { name: "제육볶음 양념" }).click();
  await expect(page.getByRole("heading", { name: "제육볶음 양념" })).toBeVisible();

  const gochujangRow = page.locator("li").filter({ hasText: "고추장" });
  await expect(gochujangRow.getByText("2큰술")).toBeVisible();

  await page.getByRole("button", { name: "1.2kg" }).click();
  await expect(gochujangRow.getByText("4큰술")).toBeVisible();
});

test("내 양념 비율을 추가하면 목록에 생기고 삭제하면 사라진다", async ({ page }) => {
  await openRecipes(page, "양념 비율");
  await page.getByRole("button", { name: "내 비율 만들기" }).click();
  await page.getByLabel("이름", { exact: true }).fill("테스트 양념");
  await page.getByLabel("주재료 이름").fill("돼지고기");
  await page.getByLabel(/기준 양/).fill("500");
  await page.getByLabel("1번째 양념 이름").fill("소금");
  await page.getByLabel("1번째 양념 양").fill("1");
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: "테스트 양념" })).toBeVisible();

  await openRecipes(page, "양념 비율");
  await expect(page.getByRole("link", { name: "테스트 양념" })).toBeVisible();
  await page.getByRole("link", { name: "테스트 양념" }).click();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "이 비율 삭제" }).click();
  await openRecipes(page, "양념 비율");
  // 목록이 실제로 불러와졌는지부터 확인한다(그래야 아래 없음 검사가 "아직 안 불러옴"으로 통과하지 않는다)
  await expect(page.getByRole("link", { name: "우리집 제육볶음 양념" })).toBeVisible();
  await expect(page.getByRole("link", { name: "테스트 양념" })).toHaveCount(0);
});

test("영상 목록과 채널 화면이 키 없는 상태에서 예시로 보인다", async ({ page }) => {
  await openRecipes(page, "영상");
  await expect(page.getByText("예시 영상으로 보여줘요")).toBeVisible();
  await expect(page.getByText("제육볶음 황금레시피, 이렇게만 하세요")).toBeVisible();

  await page.getByRole("button", { name: "요리 채널 관리" }).click();
  await expect(page.getByRole("heading", { name: "요리 채널" })).toBeVisible();
  await expect(page.getByText("예시 채널로 보여줘요")).toBeVisible();
  await expect(page.getByText("집밥 연구소")).toBeVisible();
});
