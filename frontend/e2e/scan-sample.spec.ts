import { app, expect, test } from "./fixtures";

// 체험 계정 `예시 사진으로 해보기`(스펙 31절). E2E 서버는 키 없는 개발 모드라 사진 인식이 sample 모드(체험 AI를 다 쓴 것과 같다) —
// 예시 사진 id를 함께 보내면 서버가 그 사진을 미리 읽어둔 결과(backend/app/data/sample_scans.json)를 준다.
// 냉장고 사진의 결과는 16개(간장 포함)라, 일반 예시 결과(4개)와 달라 kind·sample이 함께 갔는지도 확인된다.
test("체험 AI를 다 썼으면 예시 사진(냉장고)의 읽어둔 결과를 사진 띠와 함께 확인해 재고에 넣는다", async ({ page }) => {
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
  await expect(scanDialog.getByText("오늘 체험용 AI를 다 써서 이 사진을 미리 읽어둔 결과를 보여줘요", { exact: true })).toBeVisible();
  await expect(scanDialog.getByRole("button", { name: "이 사진 읽기" })).toHaveCount(0); // 읽지 않으니 읽는다고 하지 않는다
  await scanDialog.getByRole("button", { name: "다른 사진" }).click(); // 고르기로 돌아갔다가 다시 고른다
  await samples.getByRole("button", { name: "냉장고 예시 사진" }).click();
  await scanDialog.getByRole("button", { name: "읽어둔 결과 보기" }).click();

  await expect(scanDialog.getByRole("heading", { name: "찾은 재료 16개" })).toBeVisible();
  await expect(
    scanDialog.getByText("오늘 체험용 AI를 다 써서 이 사진을 미리 읽어둔 결과를 보여줘요. 로그인하면 내 사진을 바로 읽어요.", { exact: true }),
  ).toBeVisible();
  await expect(scanDialog.getByText(/초 만에 읽었어요/)).toHaveCount(0); // 읽어둔 결과는 걸린 시간을 적지 않는다
  await expect(scanDialog.getByRole("checkbox", { name: "간장 넣기" })).toBeChecked();
  await expect(photo).toBeVisible();

  const fold = scanDialog.getByRole("button", { name: "사진 접기" });
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  await fold.click();
  await expect(scanDialog.getByRole("button", { name: "사진 펼치기" })).toHaveAttribute("aria-expanded", "false");
  await expect(photo).toBeHidden();

  await scanDialog.getByRole("button", { name: "오늘" }).click(); // 냉장고 사진은 구입일을 직접 골라야 한다
  await scanDialog.getByRole("button", { name: "16개 재고에 넣기" }).click();
  // 앱 전체 되돌리기 알림(ck-toast)과 닫히는 시트의 읽힘 영역도 role=status라, 본문(main)의 그 글자 알림만 찾는다
  await expect(page.getByRole("main").getByRole("status").filter({ hasText: "16개를 재고에 넣었어요" })).toBeVisible();
  await expect(app(page).getByRole("button", { name: /^간장/ })).toBeVisible();
});

// 체험 AI가 남은 모드(on)는 키 없는 서버로 만들 수 없어 /api/me의 scan만 on으로 바꾸고 /api/scan은 가짜 응답을 준다(실제 AI 호출 없음)
test("체험 AI가 남았으면 예시 사진(모바일 영수증)을 내 사진과 같은 길로 보내고 읽은 시간을 보여준다", async ({ page }) => {
  await page.route("**/api/me", async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), scan: "on" } });
  });
  const items = [
    { name: "애호박", quantity: 1, unit: "개", location_kind: "fridge", price: 1580 },
    { name: "고등어", quantity: 1, unit: "팩", location_kind: "freezer", price: 24980 },
  ];
  await page.route("**/api/scan**", (route) => route.fulfill({ json: { items, purchased_on: null, sample: false } }));
  await page.reload(); // 픽스처가 이미 받은 사용자 정보를 바꾼 값으로 다시 받는다
  await expect(page.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();

  await app(page).getByRole("button", { name: "사진으로 추가" }).click();
  const scanDialog = app(page).getByRole("dialog");
  await expect(scanDialog.getByText(/체험 계정은 하루 \d+번까지 · 예시 사진도 1번으로 세어요/)).toBeVisible();
  await scanDialog.getByRole("button", { name: "모바일 영수증 예시 사진" }).click();
  await expect(scanDialog.getByText(/이 사진을 AI가 지금 읽어요 · 오늘 \d+번 남음/)).toBeVisible();

  const request = page.waitForRequest((r) => r.url().includes("/api/scan") && r.method() === "POST");
  await scanDialog.getByRole("button", { name: "이 사진 읽기" }).click();
  const sent = await request;
  expect(new URL(sent.url()).searchParams.get("kind")).toBe("receipt");
  expect(sent.postDataBuffer()?.toString("latin1")).toMatch(/name="sample"\r\n\r\nereceipt\r\n/);

  await expect(scanDialog.getByRole("heading", { name: "찾은 재료 2개" })).toBeVisible();
  await expect(scanDialog.getByText(/사진 1장을 \d+초 만에 읽었어요/)).toBeVisible();
  await expect(scanDialog.getByText(/미리 읽어둔 결과/)).toHaveCount(0);
  await expect(scanDialog.getByRole("img", { name: /마트 앱 영수증 화면 캡처/ })).toBeVisible();
  await expect(scanDialog.getByRole("button", { name: "사진 접기" })).toHaveAttribute("aria-expanded", "true");
  await expect(scanDialog.getByRole("button", { name: /고등어.*24,980원/ })).toBeVisible(); // 가격은 재료 줄에 보인다
});
