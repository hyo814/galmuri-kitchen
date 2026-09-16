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

test("영상 검색은 설명까지 찾고, 채널을 고르면 그 채널 안 YouTube 검색으로 잇는다", async ({ page }) => {
  // 예시 채널은 유튜브 채널 ID가 없어서, 첫 채널(집밥 연구소)에 ID가 있는 것처럼 응답을 바꾼다
  const youtubeId = "UCabcdefghijklmnopqrstuv";
  await page.route("**/api/channels", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.items[0].youtube_id = youtubeId;
    await route.fulfill({ response, json: body });
  });
  await openRecipes(page, "영상");
  const search = page.getByRole("searchbox", { name: "영상 제목·설명에서 찾기" });
  // YouTube 찾기 링크는 검색 결과를 다 받은 뒤에 생기므로, 링크부터 기다리고 목록을 본다
  await search.fill("대파"); // 예시 영상 두 개의 설명에만 있다
  await expect(page.getByRole("link", { name: "YouTube에서 더 찾기" })).toHaveAttribute(
    "href",
    `https://www.youtube.com/results?search_query=${encodeURIComponent("대파 레시피")}`,
  );
  await expect(page.getByText("냉장고 털이 두부조림 10분 완성")).toBeVisible();
  await expect(page.getByText("제육볶음 황금레시피, 이렇게만 하세요")).toBeVisible();
  await expect(page.getByText("국물이 진한 된장찌개 비법 3가지")).toHaveCount(0);

  await page.getByRole("button", { name: "집밥 연구소", exact: true }).click();
  await expect(page.getByRole("link", { name: "YouTube 집밥 연구소 채널에서 더 찾기" })).toHaveAttribute(
    "href",
    `https://www.youtube.com/channel/${youtubeId}/search?query=${encodeURIComponent("대파")}`,
  );
  await expect(page.getByText("제육볶음 황금레시피, 이렇게만 하세요")).toBeVisible();
  await expect(page.getByText("냉장고 털이 두부조림 10분 완성")).toHaveCount(0);

  await search.fill("계란말이"); // 이 채널에는 없다 → 결과 없음 화면에도 채널 안 찾기
  await expect(page.getByRole("link", { name: "YouTube 집밥 연구소 채널에서 찾기" })).toHaveAttribute(
    "href",
    `https://www.youtube.com/channel/${youtubeId}/search?query=${encodeURIComponent("계란말이")}`,
  );
  await expect(page.getByRole("button", { name: "전체 채널에서 찾기" })).toBeVisible();
});
