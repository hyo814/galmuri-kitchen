// 식단 날짜 계산 순수 로직 검사 (4b-1 Task 5). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
  defaultPlanName, weekStarts, weekDates, initialWeek, rangeText, dayHead, slotDateText, monthGrid,
  copyMaxWeeks, copyTarget, pickPlan, daysBetween, dateWithDow, planEnd, slotsOutside, weekOf,
  emptySlotCount, kcalText, urgentChip, buyDayText, previewDetail,
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
const dec = monthGrid(2026, 12); // 12월 → 다음 해 1월로 넘어가는 끝
assert.equal(dec.length, 5);
assert.equal(dec[0][0], "2026-11-30");
assert.equal(dec.at(-1).at(-1), "2027-01-03");

// 주 복사(서버 copy-week와 같은 계산)
assert.equal(copyMaxWeeks({ start_on: "2026-09-14" }, "2026-09-14"), 3);
assert.equal(copyMaxWeeks({ start_on: "2026-09-14" }, "2026-09-21"), 2);
assert.equal(copyMaxWeeks({ start_on: "2026-09-14" }, "2026-10-05"), 0);
assert.deepEqual(copyTarget({ start_on: "2026-09-14", days: 7 }, "2026-09-14", 2), { start: "2026-09-21", end: "2026-10-04", extendedDays: 21 });
assert.deepEqual(copyTarget({ start_on: "2026-09-14", days: 14 }, "2026-09-14", 1), { start: "2026-09-21", end: "2026-09-27", extendedDays: null });

// 기간을 바꾸면 밖으로 나가는 채운 칸(결정 1): 앞·뒤·안
const S = (date) => ({ date });
assert.equal(slotsOutside([S("2026-09-13"), S("2026-09-14"), S("2026-09-20"), S("2026-09-21")], "2026-09-14", 7), 2);
assert.equal(slotsOutside([S("2026-09-14"), S("2026-09-27")], "2026-09-14", 14), 0);
assert.equal(slotsOutside([S("2026-09-14")], "2026-09-15", 7), 1);

// 날짜가 든 주 페이지: 시작일·8일째·밖
const plan21 = { start_on: "2026-09-14", days: 21 };
assert.equal(weekOf(plan21, "2026-09-14"), "2026-09-14");
assert.equal(weekOf(plan21, "2026-09-21"), "2026-09-21");
assert.equal(weekOf(plan21, "2026-09-20"), "2026-09-14");
assert.equal(weekOf(plan21, "2026-10-05"), null);
assert.equal(weekOf(plan21, "2026-09-13"), null);

// 처음 보여줄 식단
const P = (id, start_on, end_on) => ({ id, name: "", start_on, end_on, days: 7, default_servings: 1, filled: 0, total: 28 });
const later = P(2, "2026-09-21", "2026-09-27");
const current = P(1, "2026-09-14", "2026-09-20");
assert.equal(pickPlan([later, current], "2026-09-15"), current);
assert.equal(pickPlan([later, current], "2026-10-15"), later);
assert.equal(pickPlan([], "2026-09-15"), undefined);

assert.equal(daysBetween("2026-09-28", "2026-10-04"), 6);
assert.equal(daysBetween("2026-02-27", "2026-03-01"), 2);

// AI 초안: 고른 끼니의 빈 칸 수·kcal 합·곧 먹어야 할 재료 칩(Task 8)
const D2 = ["2026-09-14", "2026-09-15"];
assert.equal(emptySlotCount(D2, ["lunch", "dinner"], []), 4);
assert.equal(emptySlotCount(D2, ["lunch", "dinner"], [{ date: "2026-09-14", meal: "lunch" }, { date: "2026-09-14", meal: "breakfast" }, { date: "2026-09-16", meal: "lunch" }]), 3);
assert.equal(emptySlotCount(D2, [], []), 0);
assert.equal(kcalText([]), "");
assert.equal(kcalText([null, null]), "");
assert.equal(kcalText([420, null, 620]), "약 1,040kcal");
assert.equal(kcalText([0]), "약 0kcal");
assert.equal(urgentChip("두부", "2026-09-15", "2026-09-14"), "두부 D-1");
assert.equal(urgentChip("대파", "2026-09-14", "2026-09-14"), "대파 D-0");
assert.equal(urgentChip("우유", "2026-09-10", "2026-09-14"), "우유 D-0");
assert.equal(urgentChip("양파", null, "2026-09-14"), "양파");

// 장보기 미리보기 줄 설명·살 날 태그(Task 9, 시안 ShoppingPreview 문구 그대로)
const R = (need, have, reason = null, need_extra = []) => ({
  name: "", quantity: 1, unit: "개", planned_on: "2026-09-14", reason, need_extra,
  need: need.map(([quantity, unit]) => ({ quantity, unit })), have: have.map(([quantity, unit]) => ({ quantity, unit })),
});
assert.equal(previewDetail(R([[2, "모"]], [[1, "모"]])), "2모 필요 · 1모 있어요"); // 두부
assert.equal(previewDetail(R([[2, "개"]], [])), "2개 필요 · 없어요"); // 청양고추
assert.equal(previewDetail(R([[2, "판"]], [[8, "개"]])), "있음 8개 · 필요 2판"); // 달걀(단위가 달라요)
assert.equal(previewDetail(R([[4, "대"]], [[1, "단"]])), "있음 1단 · 필요 4대"); // 대파
assert.equal(previewDetail(R([[0.5, "포기"]], [[1, "포기"]], "enough")), "½포기 필요 · 1포기 있어요"); // 김치
assert.equal(previewDetail(R([[1, "개"]], [], "listed")), "장보기 목록에 이미 있어서 건너뛰어요"); // 양파
assert.equal(previewDetail(R([], [], null, ["약간"])), "약간 필요 · 없어요"); // 소금(재고 없음 → 양념 묶음)
assert.equal(previewDetail(R([], [], null, ["2큰술", "1큰술"])), "2큰술 + 1큰술 필요 · 없어요"); // 된장(재고 없음 → 양념 묶음)
// 필요·있음 양은 딱 떨어지는 분수가 아니면 소수 첫째 자리까지(운영에서 1.67개·616.67g이 보였다), .0은 뺀다
assert.equal(previewDetail(R([[1.67, "개"]], [[1, "개"]])), "1.7개 필요 · 1개 있어요"); // 애호박 ⅓개 × 5
assert.equal(previewDetail(R([[616.67, "g"]], [[600, "g"]])), "616.7g 필요 · 600g 있어요"); // 돼지고기 925g × ⅔
assert.equal(previewDetail(R([[0.33, "모"]], [[2.5, "모"]], "enough")), "0.3모 필요 · 2½모 있어요");
assert.equal(previewDetail(R([[2, "모"], [1.05, "g"]], [])), "2모 + 1.1g 필요 · 없어요");
assert.equal(previewDetail(R([[0.03, "모"]], [])), "0.1모 필요 · 없어요"); // 아주 적어도 0으로 보이지 않게
assert.equal(previewDetail(R([], [[1, "병"]], "enough", ["2큰술"])), "2큰술 필요 · 1병 있어요"); // 간장
assert.equal(buyDayText("2026-09-14", "2026-09-14"), "오늘 사요");
assert.equal(buyDayText("2026-09-13", "2026-09-14"), "오늘 사요");
assert.equal(buyDayText("2026-09-16", "2026-09-14"), "16일(수)에 사요");

console.log("check-meals: ok");
