import { app, expect, test } from "./fixtures";

// 체험 계정 `예시 사진으로 해보기`(스펙 31절). E2E 서버는 키 없는 개발 모드라 사진 인식이 sample 모드 —
// 예시 사진 id를 함께 보내면 서버가 그 사진을 미리 읽어 둔 결과(backend/app/data/sample_scans.json)를 준다.
// 냉장고 사진의 결과는 16개(간장 포함)라, 일반 예시 결과(4개)와 달라 kind·sample이 함께 갔는지도 확인된다.
test("예시 사진(냉장고)을 골라 사진을 확인하고 읽으면, 미리 읽어 둔 재료를 사진 띠와 함께 확인해 재고에 넣는다", async ({ page }) => {
  // 체험 안내 카드가 떠 있어도 아래 고정 버튼으로 연다(카드 버튼 이름은 `사진 찍어보기`). 흔한 이름은 앱 화면·시트 안에서만 찾는다
  await app(page).getByRole("button", { name: "사진으로 추가" }).click();
  const scanDialog = app(page).getByRole("dialog");
  const samples = scanDialog.getByRole("list", { name: "예시 사진으로 해보기" });
  await expect(samples.getByRole("button")).toHaveText(["모바일 영수증", "냉장고"]);
  // 테스트 브라우저는 마우스 기기라 카메라 대신 파일 올리기 하나(시안 결정 D)
  await expect(scanDialog.getByRole("button", { name: "사진 파일 올리기" })).toBeVisible();
  await expect(scanDialog.getByRole("button", { name: "카메라로 찍기" })).toHaveCount(0);

  const photo = scanDialog.getByRole("img", { name: /냉장고 문칸 사진/ });
  await samples.getByRole("button", { name: "냉장고 예시 사진" }).click();
  await expect(scanDialog.getByRole("heading", { name: "냉장고 예시" })).toBeVisible();
  await expect(photo).toBeVisible();
  await scanDialog.getByRole("button", { name: "다른 사진" }).click(); // 고르기로 돌아갔다가 다시 고른다
  await samples.getByRole("button", { name: "냉장고 예시 사진" }).click();
  await scanDialog.getByRole("button", { name: "이 사진 읽기" }).click();

  await expect(scanDialog.getByRole("heading", { name: "찾은 재료 16개" })).toBeVisible();
  await expect(scanDialog.getByText(/이 사진을 미리 읽어 둔 결과를 보여줘요\. 로그인하면 내 사진을 바로 읽어요/)).toBeVisible();
  await expect(scanDialog.getByRole("checkbox", { name: "간장 넣기" })).toBeChecked();
  await expect(photo).toBeVisible();

  const fold = scanDialog.getByRole("button", { name: "사진 접기" });
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  await fold.click();
  await expect(scanDialog.getByRole("button", { name: "사진 펼치기" })).toHaveAttribute("aria-expanded", "false");
  await expect(photo).toBeHidden();

  await scanDialog.getByRole("button", { name: "오늘" }).click(); // 냉장고 사진은 구입일을 직접 골라야 한다
  await scanDialog.getByRole("button", { name: "16개 재고에 넣기" }).click();
  await expect(app(page).getByRole("status")).toContainText("16개를 재고에 넣었어요");
  await expect(app(page).getByRole("button", { name: /^간장/ })).toBeVisible();
});
