import { app, expect, openTab, test } from "./fixtures";
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

// --- 여러 요리 가져오기(17절, 2026-09-17) ---

const MULTI_TITLES = ["오리지날 떡볶이", "부트졸로키아 떡볶이", "옥황상제 떡볶이"];

function multiDraft(title: string, missingAmount = false) {
  return {
    title,
    servings: 2,
    ingredients: [
      { name: "떡", amount: "300g" },
      { name: "고추장", amount: missingAmount ? "" : "2큰술" },
    ],
    steps: ["끓는 물에 떡을 삶아요.", "양념을 넣고 볶아요."],
  };
}

/** JSON 요청에만 응답하고(사진 multipart는 그대로 흘려보내고) 부른 횟수를 센다 */
function jsonRoute(page: Page, json: unknown) {
  const calls = { count: 0 };
  page.route("**/api/recipes/import", (route) => {
    if (!route.request().headers()["content-type"]?.startsWith("application/json")) return route.continue();
    calls.count++;
    return route.fulfill({ json });
  });
  return calls;
}

test("여러 요리 가져오기: 골라서 확인하고, 요리를 바꿔도 고친 내용이 남고, 저장한 뒤 남은 요리를 이어서 확인한다", async ({ page }) => {
  const sheet = page.getByRole("dialog");
  const calls = jsonRoute(page, {
    recipes: [multiDraft(MULTI_TITLES[0]), multiDraft(MULTI_TITLES[1]), multiDraft(MULTI_TITLES[2], true)],
    from_image: true,
    images_truncated: true,
    source: "blog",
    source_url: "https://recipe.example.com/many",
    source_card: { title: "우주떡집 메뉴", author: "에그이즈커밍", thumbnail_url: null },
    sample: false,
  });

  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await sheet.getByRole("button", { name: "링크로 가져오기" }).click();
  await sheet.getByLabel("링크", { exact: true }).fill("https://recipe.example.com/many");
  await sheet.getByRole("button", { name: "가져오기", exact: true }).click();

  // ③ 고르기: 3개, ⑥ 사진이 많다는 안내, 양이 안 보이는 재료 배지
  await expect(sheet.getByRole("heading", { name: "요리가 3개 있어요" })).toBeVisible();
  await expect(sheet.getByText("본문 사진이 많아 앞쪽 5장만 읽었어요")).toBeVisible();
  await expect(sheet.getByText("양이 안 보이는 재료 1개")).toBeVisible();
  await expect(sheet.getByRole("radio")).toHaveCount(3);
  await sheet.getByRole("radio", { name: MULTI_TITLES[1] }).check({ force: true });
  await sheet.getByRole("button", { name: "이 요리 확인하기" }).click();

  // ④ 확인: 3개 중 2번째, 이름을 고친다
  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(app(page).getByText(`3개 중 2번째 · ${MULTI_TITLES[1]}`)).toBeVisible();
  await page.getByLabel("이름", { exact: true }).fill(`${MULTI_TITLES[1]} 특제`);

  // 요리 바꾸기: 지금 편집 중인 건 목록에 없다(둘만)
  await page.getByRole("button", { name: "요리 바꾸기" }).click();
  await expect(sheet.getByRole("heading", { name: "요리 바꾸기" })).toBeVisible();
  await expect(sheet.getByRole("radio")).toHaveCount(2);
  await sheet.getByRole("radio", { name: MULTI_TITLES[0] }).check({ force: true });
  await sheet.getByRole("button", { name: "이 요리 확인하기" }).click();
  await expect(app(page).getByText(`3개 중 1번째 · ${MULTI_TITLES[0]}`)).toBeVisible();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue(MULTI_TITLES[0]);

  // 다시 바꾸면(고친 이름) 그대로 남아 있다
  await page.getByRole("button", { name: "요리 바꾸기" }).click();
  await sheet.getByRole("radio", { name: MULTI_TITLES[1] }).check({ force: true });
  await sheet.getByRole("button", { name: "이 요리 확인하기" }).click();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue(`${MULTI_TITLES[1]} 특제`);

  // 저장 → ⑤ 이어서 화면(2개 남음)
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: `${MULTI_TITLES[1]} 특제를 저장했어요` })).toBeVisible();
  await expect(app(page).getByText("같은 페이지의 요리 2개가 남았어요")).toBeVisible();

  // 남은 것 중 하나 확인하기 → 저장(1개 남음)
  await app(page).getByRole("listitem").filter({ hasText: MULTI_TITLES[2] }).getByRole("button", { name: "확인하기" }).click();
  await expect(app(page).getByText(`3개 중 3번째 · ${MULTI_TITLES[2]}`)).toBeVisible();
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: `${MULTI_TITLES[2]}를 저장했어요` })).toBeVisible();
  await expect(app(page).getByText("같은 페이지의 요리 1개가 남았어요")).toBeVisible();

  // 그만하고 레시피 보기 → 저장한 레시피 상세로, 남은 목록은 지운다
  await page.getByRole("button", { name: "그만하고 레시피 보기" }).click();
  await expect(page.getByRole("heading", { name: MULTI_TITLES[2] })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("recipe-multi"))).toBeNull();
  expect(calls.count).toBe(1); // AI는 한 번만
});

test("요리가 1개면 여러 요리 고르기 없이 지금 확인 화면 그대로다", async ({ page }) => {
  // 서버는 1개일 때 목록(recipes)이 아니라 지금과 같은 평평한 모양으로 준다(17절, 하위 호환)
  jsonRoute(page, { ...multiDraft("된장찌개"), source: "text", source_url: null, source_card: null, sample: false });
  const sheet = page.getByRole("dialog");
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await sheet.getByRole("button", { name: "글 붙여넣기" }).click();
  await sheet.getByLabel("레시피 글").fill("된장찌개 재료: 두부 1모, 애호박 1/2개");
  await sheet.getByRole("button", { name: "정리하기" }).click();

  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue("된장찌개");
  await expect(app(page).getByText(/개 중 \d+번째/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "요리 바꾸기" })).toHaveCount(0);
});

const VIDEO_MISS = "영상 설명에서 레시피를 찾지 못했어요. 설명에 있으면 복사해 붙여 넣고, 영상에만 있으면 보면서 재료와 만드는 법을 아래에 적어주세요.";
const CAPTURE_HINT = "영상을 멈추고 재료와 만드는 법이 나온 화면을 캡처해 올려주세요 · 5장까지";
const PHOTO_MISS = "사진에서 레시피를 찾지 못했어요. 글자가 잘 보이는 사진으로 다시 올리거나 글 붙여넣기를 써주세요.";
const TEXT_MISS = "레시피를 찾지 못했어요. 재료와 만드는 법이 담긴 글을 붙여 넣어주세요.";
const RECIPE_TEXT = "제육볶음 만드는 법. 돼지고기 앞다리살 600g, 양파 1개, 고추장 2큰술로 볶아요.";
const WATCH_SAMPLE = "https://www.youtube.com/watch?v=sample00001"; // 예시 영상(영상 칸 첫 줄)의 표준 주소

/** 키 없는 서버는 가져오기마다 예시 초안을 주므로 422 need_text로 바꾼다. 영상 링크는 서버처럼 출처·표준 주소(watch?v=)도 준다.
 *  글은 앞의 textMisses번만, 사진(multipart)은 photos면 못 읽음 — 그 밖에는 서버의 예시 초안 그대로. 링크·글 요청 수를 센다 */
async function missImports(page: Page, { photos = false, textMisses = Infinity } = {}) {
  const sent = { count: 0 };
  let texts = 0;
  await page.route("**/api/recipes/import", (route) => {
    const request = route.request();
    if (!request.headers()["content-type"]?.startsWith("application/json"))
      return photos ? route.fulfill({ status: 422, json: { error: PHOTO_MISS, need_text: true } }) : route.continue();
    sent.count++;
    const { url } = request.postDataJSON() as { url?: string };
    if (!url) return texts++ < textMisses ? route.fulfill({ status: 422, json: { error: TEXT_MISS, need_text: true } }) : route.continue();
    if (url.includes("blog.naver.com"))
      return route.fulfill({ status: 422, json: { error: "이 링크에서는 레시피를 읽지 못했어요. 글을 복사한 뒤 아래에 붙여 넣어주세요.", need_text: true } });
    const id = url.match(/(?:v=|shorts\/|youtu\.be\/)([\w-]{11})/)?.[1];
    return route.fulfill({
      status: 422,
      json: { error: VIDEO_MISS, need_text: true, source: "youtube", source_url: `https://www.youtube.com/watch?v=${id}` },
    });
  });
  return sent;
}

/** 레시피 추가 시트에서 링크를 가져오고, 못 읽어 글 붙여넣기로 바뀔 때까지 기다린다 */
async function importFailingLink(page: Page, link: string) {
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("button", { name: "링크로 가져오기" }).click();
  await sheet.getByLabel("링크", { exact: true }).fill(link);
  await sheet.getByRole("button", { name: "가져오기", exact: true }).click();
  await expect(sheet.getByRole("heading", { name: "글 붙여넣기" })).toBeVisible();
}

test("유튜브 링크를 못 읽었을 때만 경고 아래에 화면 캡처로 가져오기가 보이고, 앨범 먼저인 사진 단계에서 취소하면 쓰던 글로 돌아온다", async ({ page }) => {
  await missImports(page, { photos: true });
  const sheet = page.getByRole("dialog");
  const capture = sheet.getByRole("button", { name: "화면 캡처로 가져오기" });
  const textArea = sheet.getByLabel("레시피 글");
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();

  await importFailingLink(page, "https://blog.naver.com/cook/223456789012");
  await expect(sheet.getByRole("alert")).toContainText("이 링크에서는 레시피를 읽지 못했어요");
  await expect(capture).toHaveCount(0);

  await sheet.getByRole("button", { name: "취소" }).click();
  await importFailingLink(page, "https://m.youtube.com/shorts/abcdefghijk");
  await expect(sheet.getByRole("alert")).toHaveText(VIDEO_MISS);
  await expect(capture).toHaveAccessibleDescription(CAPTURE_HINT);
  await textArea.fill("돼지고기 앞다리살 600g"); // 글 붙여넣기는 그대로 쓸 수 있다
  await capture.click();

  // 화면 캡처로 온 사진 단계: 경고 없이 앨범이 먼저(주 버튼), 사용량 줄 아래 취소
  await expect(sheet.getByRole("heading", { name: "사진으로 가져오기" })).toBeFocused();
  await expect(sheet.getByRole("alert")).toHaveCount(0);
  await expect(sheet.getByRole("button")).toHaveText(["앨범에서 고르기", "카메라로 찍기", "취소"]);
  await expect(sheet.getByRole("button", { name: "앨범에서 고르기" })).toHaveClass(/\bprimary\b/);

  // 사진을 못 읽어도(422) 경고와 함께 앨범 먼저·취소는 그대로
  await sheet.locator("input[type=file][multiple]").setInputFiles({ name: "capture.png", mimeType: "image/png", buffer: TINY_PNG });
  await expect(sheet.getByRole("alert")).toHaveText(PHOTO_MISS);
  await expect(sheet.getByRole("button")).toHaveText(["앨범에서 고르기", "카메라로 찍기", "취소"]);
  await sheet.getByRole("button", { name: "취소" }).click();

  // 글 단계로 돌아오면 쓰던 글·경고·캡처 버튼이 그대로
  await expect(sheet.getByRole("heading", { name: "글 붙여넣기" })).toBeFocused();
  await expect(textArea).toHaveValue("돼지고기 앞다리살 600g");
  await expect(sheet.getByRole("alert")).toHaveText(VIDEO_MISS);
  await expect(capture).toBeVisible();

  // 글을 보냈는데 또 못 읽으면 그 경고 아래에는 캡처 버튼을 두지 않는다
  await sheet.getByRole("button", { name: "정리하기" }).click();
  await expect(sheet.getByRole("alert")).toHaveText(TEXT_MISS);
  await expect(capture).toHaveCount(0);

  // 영상 링크를 또 못 읽은 뒤 방법 고르기로 돌아가 고른 사진 단계는 예전 그대로(카메라 먼저, 취소 없음)
  await sheet.getByRole("button", { name: "취소" }).click();
  await importFailingLink(page, "https://m.youtube.com/shorts/abcdefghijk");
  await expect(capture).toBeVisible();
  await sheet.getByRole("button", { name: "취소" }).click();
  await sheet.getByRole("button", { name: "사진으로 가져오기" }).click();
  await expect(sheet.getByRole("button")).toHaveText(["카메라로 찍기", "앨범에서 고르기"]);
});

test("화면 캡처로 가져온 레시피는 못 읽은 영상 링크를 출처로 남긴다", async ({ page }) => {
  await missImports(page);
  const sheet = page.getByRole("dialog");
  const watchUrl = "https://www.youtube.com/watch?v=abcdefghijk"; // 서버가 422에 준 표준 주소
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await importFailingLink(page, "https://youtu.be/abcdefghijk?si=share");
  await sheet.getByRole("button", { name: "화면 캡처로 가져오기" }).click();
  await sheet.locator("input[type=file][multiple]").setInputFiles({ name: "capture.png", mimeType: "image/png", buffer: TINY_PNG });

  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(app(page).getByText("유튜브 영상", { exact: true })).toBeVisible(); // 출처 카드 없이 이름·원본만
  await expect(app(page).getByRole("link", { name: /원본/ })).toHaveAttribute("href", watchUrl);
  await page.getByRole("button", { name: "저장" }).click();

  await expect(page.getByRole("heading", { name: "제육볶음" })).toBeVisible();
  await expect(app(page).getByRole("main")).toContainText("유튜브에서 가져옴");
  await expect(app(page).getByRole("link", { name: /원본 보기/ })).toHaveAttribute("href", watchUrl);
});

test("영상 보기에서 가져오기를 못 하면 화면 캡처로 가져오기가 남고, 링크를 다시 읽지 않고 사진 시트를 연다", async ({ page }) => {
  const sent = await missImports(page);
  const sheet = page.getByRole("dialog");
  await openRecipes(page, "영상");
  await page.getByRole("link", { name: /제육볶음 황금레시피/ }).click();
  await page.getByRole("button", { name: "레시피로 가져오기" }).click();
  await expect(sheet.getByRole("alert")).toHaveText(VIDEO_MISS); // 글 붙여넣기 시트에도 캡처 버튼이 있다
  await expect(sheet.getByRole("button", { name: "화면 캡처로 가져오기" })).toBeVisible();
  await page.keyboard.press("Escape");

  const capture = page.locator(".cta-bar").getByRole("button", { name: "화면 캡처로 가져오기" });
  await expect(capture).toHaveAccessibleDescription(CAPTURE_HINT);
  await capture.click();
  await expect(sheet.getByRole("heading", { name: "사진으로 가져오기" })).toBeFocused();
  await expect(sheet.getByRole("button")).toHaveText(["앨범에서 고르기", "카메라로 찍기", "취소"]);
  await sheet.getByRole("button", { name: "취소" }).click(); // 영상으로 돌아가 캡처한 뒤 다시 연다
  await expect(sheet).toHaveCount(0);
  await expect(capture).toBeFocused();

  await capture.click();
  await sheet.locator("input[type=file][multiple]").setInputFiles({ name: "capture.png", mimeType: "image/png", buffer: TINY_PNG });
  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(app(page).getByRole("link", { name: /원본/ })).toHaveAttribute("href", WATCH_SAMPLE);
  expect(sent.count).toBe(1); // 사진 시트는 링크를 다시 읽지 않는다
});

test("영상 링크를 못 읽은 뒤 글로 가져온 레시피도 그 영상을 출처로 남긴다(글을 한 번 못 읽어도)", async ({ page }) => {
  await missImports(page, { textMisses: 1 });
  const sheet = page.getByRole("dialog");
  const watchUrl = "https://www.youtube.com/watch?v=abcdefghijk";
  await openRecipes(page, "내 레시피");
  await page.getByRole("button", { name: "레시피 추가" }).click();
  await importFailingLink(page, "https://m.youtube.com/shorts/abcdefghijk");
  await sheet.getByLabel("레시피 글").fill(RECIPE_TEXT);
  await sheet.getByRole("button", { name: "정리하기" }).click();
  await expect(sheet.getByRole("alert")).toHaveText(TEXT_MISS);
  await sheet.getByRole("button", { name: "정리하기" }).click(); // 두 번째는 서버의 예시 초안

  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(app(page).getByRole("link", { name: /원본/ })).toHaveAttribute("href", watchUrl);
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("heading", { name: "제육볶음" })).toBeVisible();
  await expect(app(page).getByRole("main")).toContainText("유튜브에서 가져옴");
  await expect(app(page).getByRole("link", { name: /원본 보기/ })).toHaveAttribute("href", watchUrl);
});

test("영상 보기에서 가져오기를 다시 누른 채 화면 캡처를 열어도 늦은 응답이 시트를 바꾸지 않고, 글로 가져온 레시피는 영상을 출처로 남긴다", async ({ page }) => {
  await missImports(page, { textMisses: 0 });
  const sheet = page.getByRole("dialog");
  const importButton = page.locator(".cta-bar .btn.primary");
  const capture = page.locator(".cta-bar").getByRole("button", { name: "화면 캡처로 가져오기" });
  await openRecipes(page, "영상");
  await page.getByRole("link", { name: /제육볶음 황금레시피/ }).click();
  await importButton.click();
  await expect(sheet.getByRole("alert")).toHaveText(VIDEO_MISS);
  await page.keyboard.press("Escape");

  // 다시 누른 가져오기의 응답을 붙잡아 두었다가 화면 캡처 시트를 연 뒤에 보낸다(화면이 요청을 멈췄으면 채우지 못한다)
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  let answered: Promise<unknown> = Promise.resolve();
  await page.route(
    "**/api/recipes/import",
    (route) =>
      (answered = held
        .then(() => route.fulfill({ status: 422, json: { error: VIDEO_MISS, need_text: true, source: "youtube", source_url: WATCH_SAMPLE } }))
        .catch(() => {})),
    { times: 1 },
  );
  const retried = page.waitForRequest("**/api/recipes/import");
  await importButton.click();
  await retried;
  await expect(importButton).toHaveText("정리하는 중…");
  await capture.click();
  await expect(sheet.getByRole("heading", { name: "사진으로 가져오기" })).toBeFocused();
  release();
  await answered;
  await expect(importButton).toHaveText("레시피로 가져오기");
  await sheet.getByRole("button", { name: "취소" }).click();
  await expect(sheet).toHaveCount(0);

  // 영상 보기의 글 붙여넣기 시트로 가져와도 출처는 이 영상
  await importButton.click();
  await sheet.getByLabel("레시피 글").fill(RECIPE_TEXT);
  await sheet.getByRole("button", { name: "정리하기" }).click();
  await expect(page.getByRole("heading", { name: "가져온 레시피 확인" })).toBeVisible();
  await expect(app(page).getByRole("link", { name: /원본/ })).toHaveAttribute("href", WATCH_SAMPLE);
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
  // 예시 채널은 유튜브 채널 ID가 없어서, 집밥 연구소에 ID가 있는 것처럼 응답을 바꾼다
  const youtubeId = "UCabcdefghijklmnopqrstuv";
  await page.route("**/api/channels", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.items.find((c: { title: string }) => c.title === "집밥 연구소").youtube_id = youtubeId;
    await route.fulfill({ response, json: body });
  });
  await openRecipes(page, "영상");
  const search = page.getByRole("searchbox", { name: "영상 제목·설명에서 찾기" });
  const rows = page.locator(".r3-vlist > li");
  // 검색어·채널을 바꾼 직후에는 목록이 잠깐 비어 '없음' 검사가 그냥 통과하므로, 새 결과의 줄 수부터 맞춘 뒤 본다
  await search.fill("대파"); // 예시 영상 두 개의 설명에만 있다(검색 전 목록은 5줄)
  await expect(rows).toHaveCount(2);
  await expect(page.getByText("냉장고 털이 두부조림 10분 완성")).toBeVisible();
  await expect(page.getByText("제육볶음 황금레시피, 이렇게만 하세요")).toBeVisible();
  await expect(page.getByText("국물이 진한 된장찌개 비법 3가지")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "YouTube에서 더 찾기" })).toHaveAttribute(
    "href",
    `https://www.youtube.com/results?search_query=${encodeURIComponent("대파 레시피")}`,
  );

  await page.getByRole("button", { name: "집밥 연구소", exact: true }).click();
  await expect(rows).toHaveCount(1); // 바꾸기 전 목록은 2줄
  await expect(page.getByText("제육볶음 황금레시피, 이렇게만 하세요")).toBeVisible();
  await expect(page.getByText("냉장고 털이 두부조림 10분 완성")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "YouTube 집밥 연구소 채널에서 더 찾기" })).toHaveAttribute(
    "href",
    `https://www.youtube.com/channel/${youtubeId}/search?query=${encodeURIComponent("대파")}`,
  );

  await search.fill("계란말이"); // 이 채널에는 없다 → 결과 없음 화면에도 채널 안 찾기
  await expect(page.getByRole("link", { name: "YouTube 집밥 연구소 채널에서 찾기" })).toHaveAttribute(
    "href",
    `https://www.youtube.com/channel/${youtubeId}/search?query=${encodeURIComponent("계란말이")}`,
  );
  await expect(page.getByRole("button", { name: "전체 채널에서 찾기" })).toBeVisible();
});
