// 하루 칼로리 목표 계산 순수 로직 검사 (4b-2 Task 6). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import { ageOf, dailyTarget, kcalNumber, parseProfileInput, targetNote } from "../src/nutrition/body.ts";

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

console.log("check-nutrition: ok");
