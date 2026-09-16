// 하루 칼로리 목표 계산 순수 로직 검사 (4b-2 Task 6). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import { ageOf, dailyTarget, kcalNumber, parseProfileInput, targetNote } from "../src/nutrition/body.ts";
import {
  MAX_FILL_ATTEMPTS, atLeast, candidateSub, closestMatch, dailyValue, daySum, dayHeadText, fillTargets, goalFor, gramsFieldValue, incompleteNotes,
  ingredientKcalText, ingredientNote, macroSplit, meterPercent, pickTitle, slotKcalText, sodiumDay, sugarDay, unitGramsFrom,
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
  incomplete: extra.incomplete ?? {},
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

// 자동 채우기는 레시피마다 두 번까지(Ruling 18: 첫 채우기가 찾기에 시간을 다 쓰면 한 번 더)
assert.equal(MAX_FILL_ATTEMPTS, 2);

// fillTargets: 날짜 밖·pending 아님·직접 쓰기 칸 제외·중복 한 번
const fillDates = ["2026-09-14", "2026-09-15", "2026-09-16"];
const fillSlots = [
  { date: "2026-09-15", recipe_id: 1 },
  { date: "2026-09-16", recipe_id: 1 }, // 중복
  { date: "2026-09-20", recipe_id: 2 }, // 날짜 밖
  { date: "2026-09-15", recipe_id: 3 }, // pending 아님
  { date: "2026-09-15", recipe_id: null }, // 직접 쓰기 칸
];
assert.deepEqual(fillTargets(fillSlots, fillDates, [1]), [1]);

// fillTargets: 이미 시도한 레시피는 pending에 남아 있어도 다시 부르지 않는다(I1 — 계속 fill을 부르지 않게)
assert.deepEqual(fillTargets(fillSlots, fillDates, [1], new Set([1])), []);
assert.deepEqual(
  fillTargets([...fillSlots, { date: "2026-09-14", recipe_id: 4 }], fillDates, [1, 4], new Set([1])),
  [4],
);

// daySum calcKcal(I2): ai 칸의 kcal은 당류가 없어 당류 비율 분모에서 뺀다
const mixedDay = daySum([{ nutrition: N(200, "calc", false, { sugars_g: 20 }) }, { nutrition: N(1200, "ai", true) }]);
assert.equal(mixedDay.kcal, 1400);
assert.equal(mixedDay.calcKcal, 200);
assert.equal(mixedDay.sugars_g, 20);
// 전체 kcal로 나누면 6%(WHO 기준 안전으로 잘못 보임), calcKcal로 나누면 40%(실제로는 초과)
assert.equal(sugarDay(mixedDay.sugars_g, mixedDay.kcal).warn, false);
assert.deepEqual(sugarDay(mixedDay.sugars_g, mixedDay.calcKcal), { text: "총 에너지의 40% · WHO 10% 미만", percent: 100, warn: true });

// ---- 값이 빠진 영양소(결정 14 개정 2): 아는 값만 더하고 "이상"·빠진 이름을 보여준다 ----
// 하루 합계는 계산 칸의 빠진 이름을 한 번씩 모은다. AI 추정 칸은 탄단지를 아예 더하지 않으므로(결정 16) 모으지 않는다
const leftOutDay = daySum([
  { nutrition: N(300, "calc", false, { sodium_mg: 7, incomplete: { sodium_mg: ["된장"], sugars_g: ["된장"] } }) },
  { nutrition: N(300, "calc", false, { sodium_mg: 400, incomplete: { sodium_mg: ["된장", "고추장"] } }) },
  { nutrition: { ...N(420, "ai", true), incomplete: { sodium_mg: ["무시"] } } },
  { nutrition: N(100, "calc", false) },
]);
assert.deepEqual(leftOutDay.incomplete, { sodium_mg: ["된장", "고추장"], sugars_g: ["된장"] });
assert.equal(leftOutDay.sodium_mg, 407);
assert.deepEqual(daySum([{ nutrition: N(100, "calc", false) }]).incomplete, {});

assert.equal(atLeast(leftOutDay.incomplete, "sodium_mg"), " 이상");
assert.equal(atLeast(leftOutDay.incomplete, "fat_g"), "");
assert.equal(atLeast({ fat_g: [] }, "fat_g"), "");

// 빠진 값이 있으면 기준치 대비는 넘은 게 확실할 때만(" 이상"), 아니면 null(막대·비율을 그리지 않는다)
assert.equal(dailyValue(7, 2000, true), null);
assert.deepEqual(dailyValue(1720, 2000, true), { text: "1일 기준치의 86% 이상", percent: 86, warn: true });
assert.deepEqual(dailyValue(6, 100, false), dailyValue(6, 100));
assert.equal(sodiumDay(407, true), null);
assert.deepEqual(sodiumDay(2380, true), sodiumDay(2380));
assert.equal(sugarDay(5, 1190, true), null);
assert.deepEqual(sugarDay(40, 1190, true), { text: "총 에너지의 13% 이상 · WHO 10% 미만", percent: 100, warn: true });

// 안내: 보이는 영양소만, 이름 목록이 같으면 한 줄로(탄단지 → 당류 → 나트륨 순), 둘 이상이면 "외 N개", 받침에 맞는 조사
const ALL = ["carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg"];
assert.deepEqual(incompleteNotes({ sodium_mg: ["된장"] }, ALL), ["된장은 나트륨 값이 없어 빼고 계산했어요"]);
assert.deepEqual(incompleteNotes({ sodium_mg: ["된장"], sugars_g: ["된장"] }, ALL), ["된장은 당류·나트륨 값이 없어 빼고 계산했어요"]);
assert.deepEqual(
  incompleteNotes({ sodium_mg: ["된장", "고추장"], sugars_g: ["된장"], fat_g: ["두부"] }, ALL),
  ["두부는 지방 값이 없어 빼고 계산했어요", "된장은 당류 값이 없어 빼고 계산했어요", "된장 외 1개는 나트륨 값이 없어 빼고 계산했어요"],
);
assert.deepEqual(incompleteNotes({ sodium_mg: ["된장", "고추장", "쌈장"] }, ALL), ["된장 외 2개는 나트륨 값이 없어 빼고 계산했어요"]);
assert.deepEqual(incompleteNotes({ fat_g: ["두부"], sodium_mg: ["된장"] }, ["sugars_g", "sodium_mg"]), ["된장은 나트륨 값이 없어 빼고 계산했어요"]);
assert.deepEqual(incompleteNotes({}, ALL), []);
assert.deepEqual(incompleteNotes({ sodium_mg: [] }, ALL), []);

// ---- day.ts (4b-2 Task 8: 레시피 상세 영양·식품 고르기 시트) ----
const row = (over) => ({
  name: "", amount: "", key: "", status: "ok", pending_reason: null, countable: false,
  quantity: null, unit: null, grams: null, unit_grams: null, unit_grams_source: null,
  food: null, estimate_food: false, kcal_per_serving: null,
  ...over,
});

assert.equal(ingredientKcalText(row({ status: "ok", kcal_per_serving: 198 })), "198");
assert.equal(ingredientKcalText(row({ status: "estimated", kcal_per_serving: 45 })), "약 45");
assert.equal(ingredientKcalText(row({ status: "trace", kcal_per_serving: null })), "0");
assert.equal(ingredientKcalText(row({ status: "unmatched", kcal_per_serving: null })), "—");

// 시안 RECIPE NUTRITION 세 줄
assert.deepEqual(
  ingredientNote(row({ status: "ok", food: { food_code: "x", name: "돼지고기, 앞다리, 생것", group: "원재료성", kcal: 132 } })),
  { text: "돼지고기, 앞다리, 생것", action: "바꾸기" },
);
assert.deepEqual(
  ingredientNote(
    row({
      status: "estimated", estimate_food: false, name: "김치", amount: "1/4포기", grams: 250,
      food: { food_code: "y", name: "배추김치", group: "가공식품", kcal: 32 },
    }),
  ),
  { text: "배추김치 · 1/4포기 ≈ 250g으로 추정", action: "바꾸기" },
);
assert.deepEqual(ingredientNote(row({ status: "unmatched", name: "두부" })), { text: "두부 · 맞는 식품을 골라주세요", action: "고르기" });

// unknown_amount·trace·pending·no_estimate·AI 추정 식품
assert.deepEqual(ingredientNote(row({ status: "unknown_amount" })), { text: "양을 알 수 없어 계산에서 뺐어요", action: null });
assert.deepEqual(ingredientNote(row({ status: "trace" })), { text: "조금이라 계산에서 뺐어요", action: null });
assert.deepEqual(ingredientNote(row({ status: "pending" })), { text: "계산하는 중이에요", action: "고르기" });
assert.deepEqual(ingredientNote(row({ status: "no_estimate", name: "설탕" })), { text: "설탕 · 추정할 수 없어요", action: "고르기" });
assert.deepEqual(
  ingredientNote(row({ status: "needs_weight", name: "양파", food: { food_code: "z", name: "양파", group: "원재료성", kcal: 34 } })),
  { text: "양파 · 무게를 알려주세요", action: "고르기" },
);
assert.deepEqual(
  ingredientNote(row({ status: "estimated", estimate_food: true, name: "고수" })),
  { text: "고수 · AI로 추정했어요", action: "바꾸기" },
);
// grams가 null이어도(방어) "0g으로 추정"으로 죽지 않는다
assert.deepEqual(
  ingredientNote(
    row({ status: "estimated", estimate_food: false, name: "뭔가", amount: "1개", grams: null, food: { food_code: "f", name: "뭔가", group: "원재료성", kcal: 1 } }),
  ),
  { text: "뭔가 · 1개 ≈ 0g으로 추정", action: "바꾸기" },
);

assert.equal(candidateSub("원재료성", 84), "원재료 · 100g당 84kcal");
assert.equal(candidateSub("", 84), "100g당 84kcal");

// closestMatch(결정 14): 원재료성이고 검색어 정규화 키가 이름 조각(밑줄·쉼표로 나눔) 중 하나와 같을 때만
assert.equal(closestMatch({ name: "파_대파_생것", group: "원재료성" }, "대파"), true);
assert.equal(closestMatch({ name: "굴국_두부", group: "음식" }, "두부"), false);
assert.equal(closestMatch({ name: "두부 (국산)", group: "원재료성" }, "두부"), true);
// 여러 낱말 검색어("돼지고기앞다리")는 이름 조각 하나와 같지 않다(조각은 "돼지고기"·"앞다리"·"생것" 각각)
assert.equal(closestMatch({ name: "돼지고기_앞다리_생것", group: "원재료성" }, "돼지고기 앞다리"), false);

assert.equal(pickTitle("두부"), "‘두부’는 어떤 식품인가요?");
assert.equal(pickTitle("김치찌개 양념장"), "‘김치찌개 양념장’은 어떤 식품인가요?");

assert.equal(gramsFieldValue({ quantity: 0.5, unit_grams: 300 }), "150");
assert.equal(gramsFieldValue({ quantity: null, unit_grams: 300 }), "");
assert.equal(gramsFieldValue({ quantity: 0.5, unit_grams: null }), "");

assert.equal(unitGramsFrom("150", 0.5), 300);
assert.equal(unitGramsFrom("0", 0.5), null);
assert.equal(unitGramsFrom("abc", 1), null);
assert.equal(unitGramsFrom("3000", 0.5), null); // 6000 > 5000
assert.equal(unitGramsFrom("1,5", 1), 1.5); // 쉼표 소수점
assert.equal(unitGramsFrom("100", null), null); // quantity 모름

console.log("check-nutrition: ok");
