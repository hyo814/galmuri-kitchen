// 식단 날짜 계산 순수 로직 검사 (4b-1 Task 5). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
  defaultPlanName, weekStarts, weekDates, initialWeek, rangeText, dayHead, slotDateText, monthGrid,
  copyMaxWeeks, copyTarget, pickPlan, daysBetween, dateWithDow, planEnd,
} from "../src/meals/plan.ts";

// 식단 이름: 월요일 시작 주, 1일이 든 주가 첫째. 28일 이상은 "N월 식단"
assert.equal(defaultPlanName("2026-09-14", 7), "9월 셋째 주");
assert.equal(defaultPlanName("2026-09-01", 7), "9월 첫째 주");
assert.equal(defaultPlanName("2026-09-07", 14), "9월 둘째 주");
assert.equal(defaultPlanName("2026-09-28", 7), "9월 다섯째 주");
assert.equal(defaultPlanName("2026-02-02", 30), "2월 식단");
assert.equal(planEnd("2026-09-14", 7), "2026-09-20");

// 주 페이지
const plan17 = { start_on: "2026-09-14", days: 17 };
assert.deepEqual(weekStarts(plan17), ["2026-09-14", "2026-09-21", "2026-09-28"]);
assert.deepEqual(weekDates("2026-09-28", plan17), ["2026-09-28", "2026-09-29", "2026-09-30"]);
assert.equal(weekDates("2026-09-14", plan17).length, 7);

// 처음 보여줄 주: 기간 전 → 첫 주, 안 → 오늘이 든 주, 뒤 → 마지막 주
assert.equal(initialWeek(plan17, "2026-09-01"), "2026-09-14");
assert.equal(initialWeek(plan17, "2026-09-14"), "2026-09-14");
assert.equal(initialWeek(plan17, "2026-09-23"), "2026-09-21");
assert.equal(initialWeek(plan17, "2026-10-20"), "2026-09-28");

// 글자
assert.equal(rangeText("2026-09-14", "2026-09-20"), "9월 14일–20일");
assert.equal(rangeText("2026-09-28", "2026-10-04"), "9월 28일–10월 4일");
assert.deepEqual(dayHead("2026-09-14"), { day: "14일", dow: "월요일" });
assert.equal(dateWithDow("2026-09-14"), "9월 14일 (월)");
assert.equal(slotDateText("2026-09-14", "2026-09-14"), "9월 14일 월요일 · 오늘");
assert.equal(slotDateText("2026-09-15", "2026-09-14"), "9월 15일 화요일");
assert.equal(slotDateText("2026-09-14", "2026-09-14", "dinner"), "9월 14일 월요일 · 저녁");

// 월 격자
const sep = monthGrid(2026, 9);
assert.equal(sep.length, 5);
assert.equal(sep[0][0], "2026-08-31");
assert.equal(sep.at(-1).at(-1), "2026-10-04");
assert.equal(monthGrid(2026, 2)[0][0], "2026-01-26");
assert.equal(monthGrid(2026, 12).at(-1).at(-1) >= "2026-12-31", true);

// 주 복사(서버 copy-week와 같은 계산)
assert.equal(copyMaxWeeks({ start_on: "2026-09-14" }, "2026-09-14"), 3);
assert.equal(copyMaxWeeks({ start_on: "2026-09-14" }, "2026-09-21"), 2);
assert.equal(copyMaxWeeks({ start_on: "2026-09-14" }, "2026-10-05"), 0);
assert.deepEqual(copyTarget({ start_on: "2026-09-14", days: 7 }, "2026-09-14", 2), { start: "2026-09-21", end: "2026-10-04", extendedDays: 21 });
assert.deepEqual(copyTarget({ start_on: "2026-09-14", days: 14 }, "2026-09-14", 1), { start: "2026-09-21", end: "2026-09-27", extendedDays: null });

// 처음 보여줄 식단
const P = (id, start_on, end_on) => ({ id, name: "", start_on, end_on, days: 7, default_servings: 1, filled: 0, total: 28 });
const later = P(2, "2026-09-21", "2026-09-27");
const current = P(1, "2026-09-14", "2026-09-20");
assert.equal(pickPlan([later, current], "2026-09-15"), current);
assert.equal(pickPlan([later, current], "2026-10-15"), later);
assert.equal(pickPlan([], "2026-09-15"), undefined);

assert.equal(daysBetween("2026-09-28", "2026-10-04"), 6);
assert.equal(daysBetween("2026-02-27", "2026-03-01"), 2);

console.log("check-meals: ok");
