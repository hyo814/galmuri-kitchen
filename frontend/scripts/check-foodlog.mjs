// 먹은 기록 달력 순수 로직 검사 (4b-3 Task 7). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import { cellKcalText, cellLabel, monthLabel, shiftMonth, summaryView, todayRowSub } from "../src/foodlog/log.ts";

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
assert.equal(
  cellLabel("2026-09-16", { date: "2026-09-16", meals: 1, count: 1, kcal: null, approx: false, photo_url: null }, "2026-09-15"),
  "9월 16일 수요일, 끼니 1개",
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

console.log("check-foodlog: ok");
