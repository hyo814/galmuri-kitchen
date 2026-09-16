import type { Page } from "@playwright/test";
import { app, expect, openTab, test } from "./fixtures";

// 5단계 요리 일기·집밥 리포트(스펙 29절). 체험 계정 예시(backend/app/demo.py): 레시피 김치찌개(사 먹으면 9,000원 · 예시 추정)·
// 된장찌개(8,000원), 요리 일기 3개(오늘로부터 2일 전 김치찌개 · 메모 `두부 마저 썼어요`, 5일 전 된장찌개, 35일 전 김치찌개),
// 오늘 저녁 식단 칸 된장찌개. 예시 날짜가 오늘 기준이라 달 초에는 이번 달 숫자가 달라진다 — 날짜에 걸리는 값은 화면과 같은 API로 확인한다.

const seoulToday = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });

/** 앱 전체에 하나인 되돌리기 알림. 시트의 <output>·닫히는 시트의 읽힘 영역도 role=status라 이 요소로 좁힌다 */
const undoToast = (page: Page) => page.locator("div.ck-toast");

/** 요리 일기 목록 줄(버튼 이름 끝이 숨은 ` 일기 보기`) */
const diaryRows = (page: Page) => app(page).getByRole("button", { name: /일기 보기$/ });

/** 재고 이름 → 수량(서버 값) */
async function stock(page: Page): Promise<Record<string, number>> {
  const res = await page.request.get("/api/ingredients");
  expect(res.ok(), await res.text()).toBeTruthy();
  const items: { name: string; quantity: number }[] = await res.json();
  return Object.fromEntries(items.map((i) => [i.name, i.quantity]));
}

async function openCookDiary(page: Page) {
  await openTab(page, "더보기");
  await page.getByRole("button", { name: /^요리 일기/ }).click();
  await expect(page.getByRole("heading", { name: "요리 일기", level: 1 })).toBeVisible();
}

test("레시피 상세에서 요리했어요를 저장하면 재고에서 빠지고, 알림의 되돌리기로 재고가 돌아온다", async ({ page }) => {
  await openTab(page, "레시피");
  await page.getByRole("group", { name: "레시피 보기" }).getByRole("button", { name: "내 레시피" }).click();
  await app(page).getByRole("link", { name: /^김치찌개/ }).click();
  await expect(page.getByRole("heading", { name: "김치찌개", level: 1 })).toBeVisible();
  await expect(app(page).getByText("요리 2번")).toBeVisible(); // 예시 일기 2개

  await page.getByRole("button", { name: "요리했어요", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "김치찌개 요리했어요" });
  await expect(sheet.getByText("2인분", { exact: true })).toBeVisible(); // 레시피 인분으로 시작
  // 재고에 있는 재료는 켜진 채 레시피 양(재고 단위)으로 채워진다. 대파는 단위가 달라(대·단) 1단이라 재고를 다 쓴다
  for (const name of ["김치", "돼지고기 앞다리살", "두부", "대파"]) {
    await expect(sheet.getByRole("checkbox", { name: `${name} 재고에서 빼기` })).toBeChecked();
  }
  const tofu = sheet.getByRole("textbox", { name: "두부 쓴 양" });
  await expect(tofu).toHaveValue("0.5");
  await expect(sheet.getByText("마저 써요")).toHaveCount(1);
  await expect(sheet.getByText("재고에 없는 재료: 고춧가루 · 다진 마늘 · 식용유")).toBeVisible();
  await sheet.getByRole("button", { name: "인분 늘리기" }).click();
  await expect(tofu).toHaveValue("0.75"); // 인분만큼 다시 채운다
  await sheet.getByRole("button", { name: "인분 줄이기" }).click();
  await expect(tofu).toHaveValue("0.5");
  await expect(sheet.getByRole("group", { name: "언제" }).getByRole("button", { name: "오늘" })).toHaveAttribute("aria-pressed", "true");
  await expect(sheet.getByLabel("사 먹으면 얼마 (1인분)")).toHaveValue("9,000");
  await expect(sheet.getByText("추정 · 고칠 수 있어요")).toBeVisible();

  await sheet.getByRole("button", { name: "저장하고 재고에서 빼기" }).click();
  await expect(sheet).toHaveCount(0);

  // 9,000원 × 2인분 − 재료비(김치 3,870 + 돼지고기 2,450 + 두부 1,240 + 대파 2,500) = 7,940원 → 100원 단위
  const toast = undoToast(page);
  await expect(toast).toContainText("재고에서 김치·돼지고기 앞다리살·두부 외 1개를 뺐어요");
  await expect(toast).toContainText("약 7,900원 아꼈어요");
  await toast.hover(); // 알림은 10초 뒤 사라진다 — 마우스를 올려 멈춰 두고(결정 7) 재고를 확인한다
  const cooked = await stock(page);
  expect(cooked.두부).toBe(0.5);
  expect(cooked.대파).toBeUndefined(); // 다 쓴 재료는 재고에서 지워진다
  await expect(app(page).getByText("요리 3번")).toBeVisible();

  await toast.getByRole("button", { name: "방금 한 요리 되돌리기" }).click();
  await expect(toast).toHaveText("재고를 되돌렸어요");
  expect(await stock(page)).toMatchObject({ 두부: 1, 대파: 1 });
  await expect(app(page).getByText("요리 2번")).toBeVisible(); // 일기도 지워진다
});

test("식단 칸 상세에서 요리했어요를 저장하면 칸 상세가 닫히고 알림이 뜨며 칸이 먹었어요로 바뀐다", async ({ page }) => {
  await openTab(page, "식단");
  const todayCard = page.locator(".ml-day.today");
  await todayCard.getByRole("button", { name: /저녁 된장찌개/ }).click();
  const slotSheet = page.getByRole("dialog", { name: "된장찌개", exact: true });
  // 예시 칸은 레시피와 같은 2인분이라, 칸 인분을 3인분으로 바꿔 요리했어요 시트가 칸 인분으로 열리는지 본다
  await slotSheet.getByRole("button", { name: "인분 늘리기" }).click();
  await expect(slotSheet.getByText("3인분", { exact: true })).toBeVisible();
  await slotSheet.getByRole("button", { name: "요리했어요" }).click();

  const cookSheet = page.getByRole("dialog", { name: "된장찌개 요리했어요" });
  await expect(cookSheet.getByText("3인분", { exact: true })).toBeVisible();
  await expect(cookSheet.getByRole("textbox", { name: "두부 쓴 양" })).toHaveValue("0.75"); // 레시피 1/2모 × 3/2
  await cookSheet.getByRole("button", { name: "저장하고 재고에서 빼기" }).click();

  await expect(cookSheet).toHaveCount(0);
  await expect(slotSheet).toHaveCount(0);
  const toast = undoToast(page);
  await expect(toast).toContainText("재고에서 두부·애호박·감자 외 2개를 뺐어요");
  await expect(toast.getByRole("button", { name: "방금 한 요리 되돌리기" })).toBeVisible();
  await expect(todayCard.getByRole("button", { name: /저녁 된장찌개, 3인분.*, 먹었어요$/ })).toBeVisible();
});

test("요리 일기에서 예시 일기의 계산표를 보고, 고치고 지우면 목록에 반영되고 새로고침해도 없다", async ({ page }) => {
  await openCookDiary(page);
  const rows = diaryRows(page);
  await expect(rows).toHaveText([/^김치찌개/, /^된장찌개/, /^김치찌개/]); // 날짜 역순

  await rows.filter({ hasText: "두부 마저 썼어요" }).click();
  const detail = page.getByRole("dialog", { name: "김치찌개", exact: true });
  await expect(detail.getByRole("img", { name: "별점 4점" })).toBeVisible();
  const calc = detail.getByRole("region", { name: "아낀 돈" });
  await expect(calc.getByText("약 10,400원", { exact: true })).toBeVisible();
  await expect(calc.getByRole("term")).toHaveText([
    "사 먹으면 9,000원 × 2인분 추정",
    "김치 0.3kg / 1kg 12,900원",
    "두부 1모 / 1모 2,480원",
    "대파 0.5단 / 1단 2,500원",
    "재료비 7,600원",
  ]);
  await expect(calc.getByRole("definition")).toHaveText(["18,000원", "− 3,870원", "− 2,480원", "− 1,250원", "아낀 돈 약 10,400원"]);
  await expect(calc).toContainText("양념은 계산에 넣지 않아요 · 참고용이에요");

  await detail.getByRole("button", { name: "고치기" }).click();
  const edit = page.getByRole("dialog", { name: "김치찌개 고치기" });
  await edit.getByRole("radiogroup", { name: "별점" }).getByRole("radio", { name: "2점" }).click();
  await edit.getByLabel("메모").fill("두부 대신 순두부를 넣었어요");
  await edit.getByRole("button", { name: "저장", exact: true }).click();
  await expect(edit).toHaveCount(0);
  await expect(detail.getByRole("img", { name: "별점 2점" })).toBeVisible();
  await expect(detail.getByText("두부 대신 순두부를 넣었어요")).toBeVisible();

  page.once("dialog", (d) => d.accept()); // "이 일기를 지울까요? 재고는 되돌리지 않아요."
  await detail.getByRole("button", { name: "일기 지우기" }).click();
  await expect(detail).toHaveCount(0);
  await expect(rows).toHaveText([/^된장찌개/, /^김치찌개/]);

  await page.reload();
  await expect(page.getByRole("heading", { name: "요리 일기", level: 1 })).toBeVisible();
  await expect(rows).toHaveText([/^된장찌개/, /^김치찌개/]);
  await expect(rows.filter({ hasText: "순두부" })).toHaveCount(0);
});

test("요리 일기 이번 달 카드로 집밥 리포트를 열고 달을 오가며, 뒤로 링크로 요리 일기에 돌아온다", async ({ page }) => {
  const today = seoulToday();
  const [y, m] = today.split("-").map(Number);
  const res = await page.request.get(`/api/cook-report?month=${today.slice(0, 7)}`);
  expect(res.ok(), await res.text()).toBeTruthy();
  const r: { cooked: number; counted: number; saved_total: number; logged_days: number; home_percent: number | null; discarded: number } =
    await res.json();
  const title = (year: number, month: number) => page.getByRole("heading", { name: `${year}년 ${month}월 집밥 리포트`, level: 1 });

  await openCookDiary(page);
  await app(page).getByRole("button", { name: /집밥 리포트 보기/ }).click();
  await expect(title(y, m)).toBeVisible();

  const hero = app(page).getByRole("region", { name: "이번 달 집밥으로" });
  if (r.counted) {
    await expect(hero).toContainText(`약 ${(Math.round(r.saved_total / 100) * 100).toLocaleString("ko-KR")}원`);
    await expect(hero).toContainText(`요리 ${r.cooked}번 중 ${r.counted}번 계산`);
  } else {
    await expect(hero).toContainText(r.cooked ? "계산한 요리가 없어요" : "요리 일기가 없어요"); // 달 초
  }
  await expect(app(page).locator(".ck-stats4 > div")).toHaveText(
    [`${r.cooked}번 요리`, `${r.logged_days}일 기록한 날`, `${r.home_percent === null ? "—" : `${r.home_percent}%`} 집밥`, `${r.discarded}개 버린 재료`],
    { useInnerText: true }, // 숫자(block)와 이름이 두 줄
  );

  const next = page.getByRole("button", { name: "다음 달" });
  await expect(next).toBeDisabled(); // 이번 달 뒤로는 못 간다
  await page.getByRole("button", { name: "지난달" }).click();
  await expect(m === 1 ? title(y - 1, 12) : title(y, m - 1)).toBeVisible();
  await expect(next).toBeEnabled();
  await next.click();
  await expect(title(y, m)).toBeVisible();
  await expect(next).toBeDisabled();

  await page.getByRole("link", { name: "요리 일기로 돌아가기" }).click();
  await expect(page.getByRole("heading", { name: "요리 일기", level: 1 })).toBeVisible();
});

test("먹은 기록 달력에서 요리 일기가 있는 날에 요 표시가 있고, 날짜 상세의 보기로 그 일기를 연다", async ({ page }) => {
  const res = await page.request.get("/api/cook-logs?limit=20");
  expect(res.ok(), await res.text()).toBeTruthy();
  const { items }: { items: { title: string; cooked_on: string }[] } = await res.json();
  const log = items[0]; // 가장 최근 예시 일기(오늘로부터 2일 전)
  const [, m, d] = log.cooked_on.split("-").map(Number);

  await openTab(page, "더보기");
  await page.getByRole("button", { name: /^먹은 기록/ }).click();
  await expect(page.getByRole("heading", { name: "먹은 기록", level: 1 })).toBeVisible();
  if (log.cooked_on.slice(0, 7) !== seoulToday().slice(0, 7)) await page.getByRole("button", { name: "지난달" }).click(); // 달 초

  // 칸 이름 "9월 14일 월요일, 요리 일기 있음"(foodlog/log.ts cellLabel)
  const cell = page.getByRole("button", { name: new RegExp(`^${m}월 ${d}일 .*, 요리 일기 있음$`) });
  await expect(cell.getByText("요", { exact: true })).toBeVisible();
  await cell.click();

  const daySheet = page.getByRole("dialog", { name: new RegExp(`^${m}월 ${d}일 `) });
  await expect(daySheet.getByText(`요리 일기 ${log.title}`)).toBeVisible();
  await daySheet.getByRole("button", { name: `요리 일기 ${log.title} 보기` }).click();

  await expect(page.getByRole("heading", { name: "요리 일기", level: 1 })).toBeVisible();
  const detail = page.getByRole("dialog", { name: log.title, exact: true });
  await expect(detail).toHaveAccessibleDescription(new RegExp(`^${m}월 ${d}일 `)); // 그날 일기 상세
});

test("요리 일기의 일기 쓰기로 레시피 없이 쓰면 재고는 그대로 알림이 뜨고, 목록 꼬리표와 상세 계산표가 적은 재료비로 보인다", async ({ page }) => {
  const before = await stock(page);
  await openCookDiary(page);
  await app(page).getByRole("button", { name: "일기 쓰기" }).click();

  const pick = page.getByRole("dialog", { name: "무엇을 요리했나요?" });
  await expect(pick.getByRole("radio", { name: "김치찌개" })).toHaveAccessibleDescription(/^요리 2번 · 마지막 \d+월 \d+일$/); // 예시 일기 2개
  await pick.getByRole("button", { name: "다음" }).press("Enter"); // 고른 게 없으면 aria-disabled — 눌러 보면 무엇이 모자란지 알린다
  await expect(pick.getByRole("alert")).toHaveText("레시피를 고르거나 요리 이름을 적어주세요");
  await pick.getByLabel("요리 이름").fill("제육덮밥");
  await pick.getByRole("button", { name: "다음" }).click();

  const sheet = page.getByRole("dialog", { name: "제육덮밥 요리했어요" });
  await expect(sheet).toHaveAccessibleDescription("레시피가 없어 재고는 그대로예요");
  await expect(sheet.getByText("2인분", { exact: true })).toBeVisible();
  await expect(sheet.getByRole("button", { name: /추정해줘요/ })).toHaveCount(0); // 레시피가 없어 AI 추정은 없다
  await sheet.getByLabel("사 먹으면 얼마 (1인분)").fill("9000");
  await sheet.getByLabel("재료비 (선택)").fill("6500");
  await expect(sheet.getByLabel("재료비 (선택)")).toHaveAccessibleDescription("2인분을 합친 값이에요"); // 옆 칸은 1인분이라
  await sheet.getByRole("radiogroup", { name: "별점" }).getByRole("radio", { name: "5점" }).click();
  await sheet.getByRole("button", { name: "메모 (선택)" }).click();
  await sheet.getByLabel("메모").fill("양념을 조금 줄였더니 딱 좋았어요");
  await expect(sheet.getByRole("switch", { name: "먹은 기록에도 남기기" })).toBeChecked();
  await sheet.getByRole("button", { name: "일기 저장" }).click();
  await expect(sheet).toHaveCount(0);

  const toast = undoToast(page);
  await expect(toast).toContainText("요리 일기에 남겼어요");
  await expect(toast).toContainText("약 11,500원 아꼈어요"); // 9,000원 × 2인분 − 6,500원
  expect(await stock(page)).toEqual(before);
  const day = await page.request.get(`/api/food-logs?date=${seoulToday()}`);
  const { logs }: { logs: { title: string; source: string; recipe_id: number | null }[] } = await day.json();
  expect(logs.filter((log) => log.title === "제육덮밥")).toEqual([expect.objectContaining({ source: "cook_log", recipe_id: null })]);

  const row = diaryRows(page).filter({ hasText: "양념을 조금" });
  await expect(row).toContainText("직접 쓴 일기");
  await expect(row).toContainText("약 11,500원 아낌");
  await row.click();
  const detail = page.getByRole("dialog", { name: "제육덮밥", exact: true });
  await expect(detail).toHaveAccessibleDescription(/ · 2인분 · 직접 쓴 일기$/);
  const calc = detail.getByRole("region", { name: "아낀 돈" });
  await expect(calc.getByRole("term")).toHaveText(["사 먹으면 9,000원 × 2인분", "재료비 (직접 적음)", "아낀 돈"]);
  await expect(calc.getByRole("definition")).toHaveText(["18,000원", "− 6,500원", "약 11,500원"]);
  await expect(calc).toContainText("레시피가 없어 재료별로 나누지 않았어요 · 참고용이에요");
  await expect(detail.getByText("일기를 지워도 재고는 되돌리지 않아요.")).toHaveCount(0); // 재고를 건드리지 않은 일기

  // 재료비를 비우면 계산하지 못했다고 알려준다
  await detail.getByRole("button", { name: "고치기" }).click();
  const edit = page.getByRole("dialog", { name: "제육덮밥 고치기" });
  await expect(edit.getByLabel("재료비 (선택)")).toHaveValue("6,500");
  await edit.getByLabel("재료비 (선택)").fill("");
  await edit.getByRole("button", { name: "저장", exact: true }).click();
  await expect(edit).toHaveCount(0);
  await expect(calc.getByText("계산하지 못했어요")).toBeVisible();
  await expect(calc.getByRole("definition")).toHaveText(["18,000원", "재료비를 적으면 아낀 돈을 계산해요"]);
});

test("일기 쓰기에서 내 레시피를 고르면 요리했어요 시트로 이어지고, 취소·닫기 뒤 포커스는 일기 쓰기로 돌아온다", async ({ page }) => {
  await openCookDiary(page);
  const write = app(page).getByRole("button", { name: "일기 쓰기" });
  const pick = page.getByRole("dialog", { name: "무엇을 요리했나요?" });
  await write.click();
  await pick.getByRole("button", { name: "취소" }).click();
  await expect(pick).toHaveCount(0);
  await expect(write).toBeFocused();

  await write.click();
  const radio = pick.getByRole("radio", { name: "김치찌개" });
  await pick.getByLabel("요리 이름").fill("라면");
  await pick.getByText("김치찌개", { exact: true }).click(); // 줄을 누르면 고르고, 적던 이름은 비운다
  await expect(radio).toBeChecked();
  await expect(pick.getByLabel("요리 이름")).toHaveValue("");
  await pick.getByRole("button", { name: "다음" }).click();
  const sheet = page.getByRole("dialog", { name: "김치찌개 요리했어요" });
  await expect(sheet.getByRole("checkbox", { name: "김치 재고에서 빼기" })).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
  await expect(write).toBeFocused(); // 시트가 두 번 바뀌어도 여는 버튼으로

  // 고른 레시피로 저장하면 재고에서 빼고 목록 맨 위에 생긴다
  const before = await stock(page);
  await write.click();
  await pick.getByText("김치찌개", { exact: true }).click();
  await pick.getByRole("button", { name: "다음" }).click();
  await sheet.getByRole("button", { name: "저장하고 재고에서 빼기" }).click();
  await expect(sheet).toHaveCount(0);
  await expect(undoToast(page)).toContainText("재고에서 김치");
  await expect(diaryRows(page)).toHaveText([/^김치찌개/, /^김치찌개/, /^된장찌개/, /^김치찌개/]);
  expect((await stock(page)).김치).toBeLessThan(before.김치);
});

test("추천 레시피의 요리했어요는 내 레시피에 저장한 뒤 같은 시트를 열고, 저장하면 알림이 뜨며 내 레시피에 생긴다", async ({ page }) => {
  await openTab(page, "레시피");
  await page.getByRole("region", { name: "예시 레시피" }).getByRole("link", { name: "두부조림" }).click();
  await expect(page.getByRole("heading", { name: "두부조림", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "내 레시피로 저장만 하기" })).toBeVisible();

  await page.getByRole("button", { name: "요리했어요", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "두부조림 요리했어요" });
  await expect(sheet.getByText("두부조림을 내 레시피에 저장했어요. 다음부터는 내 레시피에서 열 수 있어요.")).toBeVisible();
  await expect(sheet.getByRole("checkbox", { name: "두부 재고에서 빼기" })).toBeChecked();
  await sheet.getByRole("button", { name: "저장하고 재고에서 빼기" }).click();
  await expect(sheet).toHaveCount(0);
  await expect(undoToast(page)).toContainText("재고에서 두부");
  await expect(page.getByRole("heading", { name: "두부조림", level: 1 })).toBeVisible(); // 추천 레시피 화면에 남는다

  // 다시 누르면 저장해 둔 복사본을 쓴다(새로 저장하지 않는다)
  await page.getByRole("button", { name: "요리했어요", exact: true }).click();
  const again = page.getByRole("dialog", { name: "두부조림 요리했어요" });
  await expect(again.getByText("두부조림은 이미 내 레시피에 있어요. 다음부터는 내 레시피에서 열 수 있어요.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(again).toHaveCount(0);

  await openTab(page, "레시피");
  await page.getByRole("group", { name: "레시피 보기" }).getByRole("button", { name: "내 레시피" }).click();
  await expect(app(page).getByRole("link", { name: /^두부조림/ })).toHaveCount(1);
  await app(page).getByRole("link", { name: /^두부조림/ }).click();
  await expect(page.getByRole("heading", { name: "두부조림", level: 1 })).toBeVisible();
  await expect(app(page).getByText("요리 1번")).toBeVisible();
});
