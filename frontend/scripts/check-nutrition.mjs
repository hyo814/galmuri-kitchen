// 하루 칼로리 목표 계산 순수 로직 검사 (4b-2 Task 6). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import { ageOf, dailyTarget, kcalNumber, parseProfileInput, targetNote } from "../src/nutrition/body.ts";
import {
  dailyValue, daySum, dayHeadText, fillTargets, goalFor, macroSplit, meterPercent, slotKcalText, sodiumDay, sugarDay,
} from "../src/nutrition/day.ts";

const TODAY = "2026-09-15";

assert.equal(ageOf(1994, TODAY), 32);

// 시안 입력: 여성 1994 162 58 가벼움
const female = { sex: "female", birth_year: 1994, height_cm: 162, weight_kg: 58, activity: "light", goal: "lose" };
const lose = dailyTarget(female, TODAY);
assert.equal(lose.bmr, 1272);
assert.equal(lose.tdee, 1748);
assert.equal(lose.target, 1272);
assert.equal(lose.floored, true);
const maintain = dailyTarget({ ...female, goal: "maintain" }, TODAY);
assert.equal(maintain.target, 1748);
assert.equal(dailyTarget({ ...female, goal: "gain" }, TODAY).target, 2248);

// 남성 1990 175 70 보통 감량(2026년 기준)
const male = dailyTarget({ sex: "male", birth_year: 1990, height_cm: 175, weight_kg: 70, activity: "moderate", goal: "lose" }, TODAY);
assert.equal(male.bmr, 1619);
assert.equal(male.tdee, 2509);
assert.equal(male.target, 2009);
assert.equal(male.floored, false);

// 증량 상한: 남성 2006 230 250 매우 많음 증량
const bigGain = dailyTarget({ sex: "male", birth_year: 2006, height_cm: 230, weight_kg: 250, activity: "very_active", goal: "gain" }, TODAY);
assert.equal(bigGain.target, 5000);
assert.equal(bigGain.capped, true);

// targetNote: 감량 floored는 전체 문구, 유지는 뒷부분만
assert.equal(
  targetNote(lose, "lose"),
  "필요량 − 500kcal이지만 기초대사량보다 낮게는 제안하지 않아요. Mifflin–St Jeor 식 × 활동계수 1.375 · 의료 조언이 아니라 참고용이에요.",
);
assert.equal(targetNote(maintain, "maintain"), "Mifflin–St Jeor 식 × 활동계수 1.375 · 의료 조언이 아니라 참고용이에요.");
// 감량인데 기초대사량에 안 걸림(남성 케이스): 앞부분이 다른 문구
assert.equal(
  targetNote(male, "lose"),
  "필요량 − 500kcal이에요. Mifflin–St Jeor 식 × 활동계수 1.55 · 의료 조언이 아니라 참고용이에요.",
);
// 증량 상한(bigGain): 앞부분이 5,000kcal 안내
assert.equal(
  targetNote(bigGain, "gain"),
  "필요량 + 500kcal이지만 5,000kcal까지만 제안해요. Mifflin–St Jeor 식 × 활동계수 1.9 · 의료 조언이 아니라 참고용이에요.",
);

// parseProfileInput
const empty = parseProfileInput({ sex: null, birthYear: "", height: "", weight: "", activity: null, goal: "maintain" }, TODAY);
assert.equal(empty.value, null);
assert.deepEqual(empty.errors, {});

const badBirth = parseProfileInput({ sex: "female", birthYear: "1926", height: "162", weight: "58", activity: "light", goal: "lose" }, TODAY);
assert.equal(badBirth.errors.birthYear, "1927~2006년 사이로 입력해주세요");
assert.equal(badBirth.value, null);

const decimals = parseProfileInput({ sex: "female", birthYear: "1994", height: "162.34", weight: "58,5", activity: "light", goal: "lose" }, TODAY);
assert.equal(decimals.value.height_cm, 162.3);
assert.equal(decimals.value.weight_kg, 58.5);

const noSex = parseProfileInput({ sex: null, birthYear: "1994", height: "162", weight: "58", activity: "light", goal: "lose" }, TODAY);
assert.equal(noSex.value, null);

// 키·몸무게 범위 밖 안내 문구
const P = (height, weight) => parseProfileInput({ sex: "female", birthYear: "1994", height, weight, activity: "light", goal: "lose" }, TODAY);
assert.equal(P("119", "58").errors.height, "120~230cm 사이로 입력해주세요");
assert.equal(P("231", "58").errors.height, "120~230cm 사이로 입력해주세요");
assert.equal(P("162", "29").errors.weight, "30~250kg 사이로 입력해주세요");
assert.equal(P("162", "251").errors.weight, "30~250kg 사이로 입력해주세요");

assert.equal(kcalNumber(1748.4), "1,748");

// ---- day.ts (4b-2 Task 7) ----
const N = (kcal, source, approx, extra = {}) => ({
  kcal,
  carbs_g: source === "ai" ? null : (extra.carbs_g ?? 0),
  protein_g: source === "ai" ? null : (extra.protein_g ?? 0),
  fat_g: source === "ai" ? null : (extra.fat_g ?? 0),
  sugars_g: source === "ai" ? null : (extra.sugars_g ?? 0),
  sodium_mg: source === "ai" ? null : (extra.sodium_mg ?? 0),
  approx,
  source,
});

// 시안 하루: 310·400 정확 + 480 약
const day1 = daySum([{ nutrition: N(310, "calc", false) }, { nutrition: N(400, "calc", false) }, { nutrition: N(480, "calc", true) }]);
assert.equal(day1.kcal, 1190);
assert.equal(day1.approx, true);
assert.equal(dayHeadText(day1, 1294), "약 1,190 / 1,294kcal");
assert.equal(dayHeadText(day1, null), "약 1,190kcal");

// 정확한 하루(목표 넘음): "약" 없이
const day2 = daySum([{ nutrition: N(1520, "calc", false) }]);
assert.equal(dayHeadText(day2, 1294), "1,520 / 1,294kcal");

// 빈 칸 없는 날
assert.equal(daySum([]), null);

// nutrition null 칸이 섞이면: approx true, counted 1, filled 2
const mixed = daySum([{ nutrition: null }, { nutrition: N(500, "calc", false) }]);
assert.equal(mixed.approx, true);
assert.equal(mixed.counted, 1);
assert.equal(mixed.filled, 2);

// ai 칸: hasAi true, 탄단지 안 더함(값이 있어도)
const aiDay = daySum([{ nutrition: { kcal: 420, carbs_g: 999, protein_g: 999, fat_g: 999, sugars_g: 999, sodium_mg: 999, approx: true, source: "ai" } }]);
assert.equal(aiDay.hasAi, true);
assert.equal(aiDay.carbs_g, 0);

assert.equal(meterPercent(1190, 1294), 92);
assert.equal(meterPercent(1520, 1294), 100);

assert.deepEqual(macroSplit(41, 29, 17), [38, 27, 35]);
assert.deepEqual(macroSplit(143, 71, 37), [48, 24, 28]);
assert.deepEqual(macroSplit(0, 0, 0), [0, 0, 0]);

assert.deepEqual(sugarDay(22, 1190), { text: "총 에너지의 7% · WHO 10% 미만", percent: 74, warn: false });

assert.deepEqual(sodiumDay(2380), { text: "1일 기준치 넘었어요", percent: 100, warn: true });
assert.equal(sodiumDay(1000).text, "1일 기준치의 50%");

assert.deepEqual(dailyValue(6, 100), { text: "1일 기준치의 6%", percent: 6, warn: false });
const overDaily = dailyValue(1720, 2000);
assert.equal(overDaily.warn, true);
assert.equal(overDaily.text, "1일 기준치의 86%");

assert.equal(slotKcalText(null), "");

assert.equal(goalFor(null, 1800), 1800);
assert.equal(goalFor(1272, 1800), 1272);

// fillTargets: 날짜 밖·pending 아님·직접 쓰기 칸 제외·중복 한 번
const fillDates = ["2026-09-14", "2026-09-15", "2026-09-16"];
assert.deepEqual(
  fillTargets(
    [
      { date: "2026-09-15", recipe_id: 1 },
      { date: "2026-09-16", recipe_id: 1 }, // 중복
      { date: "2026-09-20", recipe_id: 2 }, // 날짜 밖
      { date: "2026-09-15", recipe_id: 3 }, // pending 아님
      { date: "2026-09-15", recipe_id: null }, // 직접 쓰기 칸
    ],
    fillDates,
    [1],
  ),
  [1],
);

console.log("check-nutrition: ok");
