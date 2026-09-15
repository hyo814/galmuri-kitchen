// 먹은 기록 달력·날짜 상세 순수 로직 검사 (4b-3 Task 7·8). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
  MAX_SERVINGS,
  MIN_SERVINGS,
  createBody,
  dishGrams,
  dishSub,
  logKind,
  parseGrams,
  patchBody,
  previewText,
  scaleNutrition,
  stepServings,
  cellKcalText,
  cellLabel,
  dayDescription,
  dayTotals,
  logSubText,
  mealKcalText,
  monthLabel,
  servingsText,
  shiftMonth,
  starsText,
  summaryView,
  timeText,
  todayRowSub,
} from "../src/foodlog/log.ts";

// 달 이동
assert.equal(shiftMonth("2026-01", -1), "2025-12");
assert.equal(shiftMonth("2026-12", 1), "2027-01");
assert.equal(shiftMonth("2026-09", 0), "2026-09");

assert.equal(monthLabel("2026-09"), "2026년 9월");

// 칸 작은 kcal
assert.equal(cellKcalText({ kcal: 1780, approx: true }), "약 1,780");
assert.equal(cellKcalText({ kcal: 1420, approx: false }), "1,420");
assert.equal(cellKcalText({ kcal: null, approx: false }), "");
assert.equal(cellKcalText(undefined), "");

// 칸 버튼 이름
assert.equal(
  cellLabel("2026-09-14", { date: "2026-09-14", meals: 3, count: 3, kcal: 1190, approx: true, photo_url: "/api/photos/x" }, "2026-09-15"),
  "9월 14일 월요일, 끼니 3개, 약 1,190kcal, 사진 있음",
);
assert.equal(cellLabel("2026-09-15", undefined, "2026-09-15"), "9월 15일 화요일 · 오늘, 기록 없음");
// kcal 없는 날은 지난 날짜로 확인한다(리뷰 fix round 1 — 미래 날짜는 애초에 칸 버튼으로 그리지 않는다)
assert.equal(
  cellLabel("2026-09-13", { date: "2026-09-13", meals: 1, count: 1, kcal: null, approx: false, photo_url: null }, "2026-09-15"),
  "9월 13일 일요일, 끼니 1개",
);

// 월 요약 카드
assert.deepEqual(summaryView({ logged_days: 12, avg_kcal: 1640, avg_approx: true, home: 18, out: 7, home_percent: 72 }), {
  days: "12일",
  kcal: "약 1,640",
  home: "72%",
  split: [72, 28],
  note: "집밥 18끼 · 외식 7끼 · 기록한 날 기준이에요",
});
assert.deepEqual(summaryView({ logged_days: 0, avg_kcal: null, avg_approx: false, home: 0, out: 0, home_percent: null }), {
  days: "0일",
  kcal: "—",
  home: "—",
  split: null,
  note: "집밥·외식을 고르면 비율을 보여줘요",
});

// 더보기 줄 부제
assert.equal(todayRowSub([{ meal: "breakfast" }, { meal: "breakfast" }, { meal: "lunch" }]), "오늘 2끼 남겼어요");
assert.equal(todayRowSub([]), "먹은 것·사진을 달력에 남겨요");
assert.equal(todayRowSub(undefined), "");

// 날짜 상세(Task 8) — 시안 DAY 세 기록: 토스트 310 exact, 제육덮밥 400 approx(당류 11·나트륨 820), 김치찌개 480 approx(당류 6·나트륨 1160)
const dayLogs = [
  { title: "토스트", nutrition: { kcal: 310, carbs_g: 40, protein_g: 10, fat_g: 8, sugars_g: 5, sodium_mg: 400 }, approx: false },
  { title: "제육덮밥", nutrition: { kcal: 400, carbs_g: 30, protein_g: 20, fat_g: 15, sugars_g: 11, sodium_mg: 820 }, approx: true },
  { title: "김치찌개", nutrition: { kcal: 480, carbs_g: 25, protein_g: 22, fat_g: 20, sugars_g: 6, sodium_mg: 1160 }, approx: true },
];
const dayT = dayTotals(dayLogs);
assert.equal(dayT.kcal, 1190);
assert.equal(dayT.approx, true);
assert.equal(dayT.sugars_g, 22);
assert.equal(dayT.sodium_mg, 2380);
assert.equal(dayDescription(dayLogs, 1294), "약 1,190 / 목표 1,294kcal · 당류 22g · 나트륨 2,380mg");
assert.equal(dayDescription(dayLogs, null), "약 1,190kcal · 당류 22g · 나트륨 2,380mg");

// nutrition이 없는 기록은 approx가 true여도 합계·약에서 아예 빠진다(사진 기록의 남은 approx 값을 실수로 쓰지 않는다, fix round 1)
assert.equal(dayTotals([{ nutrition: null, approx: true }]), null);
assert.equal(mealKcalText([{ nutrition: null, approx: true, title: null }]), "");

// 사진만 먼저: 토스트 + 이름 없는 사진 기록
assert.equal(
  dayDescription(
    [{ title: "토스트", nutrition: { kcal: 310, carbs_g: null, protein_g: null, fat_g: null, sugars_g: null, sodium_mg: null }, approx: false }, { title: null, nutrition: null, approx: false }],
    null,
  ),
  "310kcal · 이름을 넣으면 kcal을 계산해요",
);
assert.equal(dayDescription([], null), "아직 남긴 기록이 없어요");
assert.equal(dayDescription([{ title: "샐러드", nutrition: null, approx: false }], null), "kcal을 계산할 수 있는 기록이 없어요");

assert.equal(mealKcalText([]), "");
assert.equal(mealKcalText([{ nutrition: { kcal: 400, carbs_g: 30, protein_g: 20, fat_g: 15, sugars_g: 11, sodium_mg: 820 }, approx: true, title: "제육덮밥" }]), "약 400kcal");

// 인분 글자
assert.equal(servingsText(0.5), "½인분");
assert.equal(servingsText(1.5), "1½인분");
assert.equal(servingsText(2), "2인분");

// 서울 시각
assert.equal(timeText("2026-09-15T03:41:00+00:00"), "12:41");

// 기록 줄 보조 글자(시안 DAY 세 줄 + 변형)
const n480 = { kcal: 480, carbs_g: 25, protein_g: 22, fat_g: 20, sugars_g: 6, sodium_mg: 1160 };
assert.equal(
  logSubText({ title: "토스트", servings: 1, grams: null, slot_servings: null, nutrition: { kcal: 310, carbs_g: 40, protein_g: 10, fat_g: 8, sugars_g: 5, sodium_mg: 400 }, approx: false, created_at: "2026-09-14T00:00:00+00:00" }),
  "1인분 · 310kcal",
);
assert.equal(
  logSubText({ title: "제육덮밥", servings: 1, grams: null, slot_servings: null, nutrition: { kcal: 400, carbs_g: 30, protein_g: 20, fat_g: 15, sugars_g: 11, sodium_mg: 820 }, approx: true, created_at: "2026-09-14T00:00:00+00:00" }),
  "1인분 · 약 400kcal",
);
assert.equal(
  logSubText({ title: "김치찌개", servings: 1, grams: null, slot_servings: 2, nutrition: n480, approx: true, created_at: "2026-09-14T00:00:00+00:00" }),
  "2인분 중 1인분 · 약 480kcal",
);
assert.equal(
  logSubText({ title: "떡볶이", servings: null, grams: 300, slot_servings: null, nutrition: { kcal: 555, carbs_g: 90, protein_g: 8, fat_g: 12, sugars_g: 20, sodium_mg: 1500 }, approx: true, created_at: "2026-09-14T00:00:00+00:00" }),
  "300g · 약 555kcal",
);
assert.equal(
  logSubText({ title: null, servings: null, grams: null, slot_servings: null, nutrition: null, approx: false, created_at: "2026-09-15T03:41:00+00:00" }),
  "12:41 · 누르면 무엇을 먹었는지 채워요",
);
assert.equal(
  logSubText({ title: "샐러드", servings: 1, grams: null, slot_servings: null, nutrition: null, approx: false, created_at: "2026-09-14T00:00:00+00:00" }),
  "1인분",
);

// 만족도 별 글자
assert.equal(starsText(4), "★★★★☆");

// ---- 먹은 것 추가·고치기 시트(Task 9) ----
assert.equal(MIN_SERVINGS, 0.5);
assert.equal(MAX_SERVINGS, 20);
assert.equal(stepServings(0.5, -1), 0.5);
assert.equal(stepServings(1, -1), 0.5);
assert.equal(stepServings(20, 1), 20);
assert.equal(stepServings(1, 1), 1.5);

// 시안 제육덮밥(100g당 값 + 1인분 400g)
const jeyuk = { group: "음식", kcal: 185, carbs_g: 22, protein_g: 8.5, fat_g: 6.8, sugars_g: 5.5, sodium_mg: 410, serving_g: 400 };
assert.equal(dishGrams(jeyuk, { servings: 0.5 }), 200);
const jeyukHalf = scaleNutrition(jeyuk, dishGrams(jeyuk, { servings: 0.5 }) / 100);
assert.deepEqual(jeyukHalf, { kcal: 370, carbs_g: 44, protein_g: 17, fat_g: 13.6, sugars_g: 11, sodium_mg: 820 });
assert.equal(previewText(jeyukHalf, true), "약 370kcal · 당류 11g · 나트륨 820mg");
assert.equal(dishSub(jeyuk), "음식 · 1인분(400g) 약 740kcal");
assert.equal(dishSub({ group: "음식", serving_g: null, kcal: 185 }), "음식 · 100g당 185kcal");
// 가공식품도 음식 뒤에 온다(Ruling C6) — 설명 앞머리는 응답 group 그대로
assert.equal(dishSub({ group: "가공식품", serving_g: 300, kcal: 150 }), "가공식품 · 1인분(300g) 약 450kcal");
assert.equal(dishGrams({ serving_g: null }, { servings: 1 }), null);
assert.equal(dishGrams({ serving_g: null }, { grams: 250 }), 250);

// 레시피 1인분 × 1.5(값 없는 영양소는 null 그대로)
const recipe15 = scaleNutrition({ kcal: 134, carbs_g: 10.2, protein_g: null, fat_g: null, sugars_g: null, sodium_mg: 333 }, 1.5);
assert.equal(recipe15.kcal, 201);
assert.equal(recipe15.carbs_g, 15.3);
assert.equal(recipe15.protein_g, null);
assert.equal(recipe15.sodium_mg, 500);
assert.equal(previewText(recipe15, false), "201kcal · 나트륨 500mg");
assert.equal(previewText(null, false), "");

assert.equal(parseGrams("250"), 250);
assert.equal(parseGrams(" 300 "), 300);
for (const bad of ["0", "3001", "1.5", "", "abc"]) assert.equal(parseGrams(bad), null);

// 새 기록 body(무엇 네 갈래)
const extra = { place: "out", rating: 3, memo: " 회사 앞 · 조금 짰어요 " };
assert.deepEqual(createBody("2026-09-14", { meal: "lunch", what: { kind: "plan", slotId: 7 }, amount: { servings: 1 }, place: "home", rating: null, memo: "" }), {
  meal_slot_id: 7, servings: 1, place: "home", rating: null, memo: null,
});
assert.deepEqual(createBody("2026-09-14", { meal: "lunch", what: { kind: "recipe", recipeId: 3 }, amount: { servings: 1.5 }, ...extra }), {
  eaten_on: "2026-09-14", meal: "lunch", recipe_id: 3, servings: 1.5, place: "out", rating: 3, memo: "회사 앞 · 조금 짰어요",
});
assert.deepEqual(createBody("2026-09-14", { meal: "lunch", what: { kind: "food", foodCode: "D1" }, amount: { grams: 300 }, ...extra }), {
  eaten_on: "2026-09-14", meal: "lunch", food_code: "D1", grams: 300, place: "out", rating: 3, memo: "회사 앞 · 조금 짰어요",
});
assert.deepEqual(createBody("2026-09-14", { meal: "dinner", what: { kind: "direct", title: " 샐러드 " }, amount: { servings: 0.5 }, place: null, rating: null, memo: "" }), {
  eaten_on: "2026-09-14", meal: "dinner", title: "샐러드", servings: 0.5, place: null, rating: null, memo: null,
});

// 고치기 body: 바뀐 칸만
const saved = { meal: "lunch", title: "제육덮밥", servings: 0.5, grams: null, place: "out", rating: 3, memo: "회사 앞 · 조금 짰어요", meal_slot_id: null, recipe_id: null, food_code: "D1" };
const same = { meal: "lunch", what: null, amount: { servings: 0.5 }, place: "out", rating: 3, memo: "회사 앞 · 조금 짰어요 " };
assert.deepEqual(patchBody(saved, same), {});
assert.deepEqual(patchBody(saved, { ...same, amount: { grams: 300 } }), { grams: 300 });
assert.deepEqual(patchBody(saved, { ...same, meal: "dinner", rating: null, memo: "", place: null }), { meal: "dinner", rating: null, memo: null, place: null });
// 바꾸기로 무엇을 고르면 무엇 + 양을 함께 보낸다(양을 안 보내면 서버가 1인분으로 둔다)
assert.deepEqual(patchBody(saved, { ...same, what: { kind: "direct", title: "김밥" } }), { title: "김밥", servings: 0.5 });
assert.deepEqual(patchBody(saved, { ...same, what: { kind: "plan", slotId: 9 }, amount: { servings: 1 } }), { meal_slot_id: 9, servings: 1 });
// 사진 기록(제목 없음): 무엇 없이 양만 바뀐 것처럼 보여도 양은 보내지 않는다
const photo = { ...saved, title: null, servings: null, food_code: null, place: null, rating: null, memo: null };
assert.deepEqual(patchBody(photo, { meal: "lunch", what: null, amount: { servings: 1 }, place: null, rating: 4, memo: "" }), { rating: 4 });
assert.deepEqual(patchBody(photo, { meal: "lunch", what: { kind: "food", foodCode: "D2" }, amount: { servings: 1 }, place: "out", rating: null, memo: "" }), {
  food_code: "D2", servings: 1, place: "out",
});

// 기록이 어떤 갈래로 남았는지(고치기 `바꾸기` 줄)
assert.equal(logKind({ meal_slot_id: 1, recipe_id: 2, food_code: null }), "plan");
assert.equal(logKind({ meal_slot_id: null, recipe_id: 2, food_code: null }), "recipe");
assert.equal(logKind({ meal_slot_id: null, recipe_id: null, food_code: "D1" }), "food");
assert.equal(logKind({ meal_slot_id: null, recipe_id: null, food_code: null }), "direct");

console.log("check-foodlog: ok");
