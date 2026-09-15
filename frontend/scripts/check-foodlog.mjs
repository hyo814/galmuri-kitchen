// 먹은 기록 달력·날짜 상세 순수 로직 검사 (4b-3 Task 7·8). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
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

console.log("check-foodlog: ok");
