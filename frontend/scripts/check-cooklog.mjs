// 요리 일기 순수 로직 검사 (5단계 Task 8, Task 10·11이 이어 붙인다). `npm run check` — Node 24가 .ts를 바로 읽는다.
import assert from "node:assert/strict";
import {
  aboutWon,
  amountHint,
  cookMeal,
  cookedLine,
  costLine,
  dateChip,
  deductedText,
  defaultAmount,
  defaultChecked,
  diaryDateText,
  diaryHeader,
  eatOutLine,
  excludedNote,
  firstLine,
  foodLogLine,
  parseAmountInput,
  parseWon,
  savedRowText,
  savedText,
  seoulHour,
  stockText,
  undoneText,
  usesUp,
  withEunNeun,
  wonFieldText,
} from "../src/cooklog/cook.ts";
import { starsText } from "../src/foodlog/log.ts";

// 쓴 양 기본값: 레시피 양 × 인분 배율(소수 셋째), 모르면 1
assert.equal(defaultAmount({ base_amount: 0.3 }, 2, 2), 0.3);
assert.equal(defaultAmount({ base_amount: 0.3 }, 3, 2), 0.45);
assert.equal(defaultAmount({ base_amount: 1 }, 1, 3), 0.333);
assert.equal(defaultAmount({ base_amount: null }, 4, 2), 1);
assert.equal(defaultAmount({ base_amount: 1 }, 2, 0), 2);
// 식단 칸 3인분에서 열면 2인분 레시피 두부 1모의 처음 양도 3인분 기준(시트 첫 인분 = start.servings)
assert.equal(defaultAmount({ base_amount: 1 }, 3, 2), 1.5);

// 처음 체크: 재고에 있고 양념이 아니면
assert.equal(defaultChecked({ ingredient_id: 1, seasoning: false }), true);
assert.equal(defaultChecked({ ingredient_id: 1, seasoning: true }), false);
assert.equal(defaultChecked({ ingredient_id: null, seasoning: false }), false);

// 마저 써요
assert.equal(usesUp(1, 1), true);
assert.equal(usesUp(0.9995, 1), true);
assert.equal(usesUp(0.99, 1), false);

// 쓴 양 입력
assert.equal(parseAmountInput("1.5"), 1.5);
assert.equal(parseAmountInput("0,3"), 0.3);
assert.equal(parseAmountInput("0"), null);
assert.equal(parseAmountInput(""), null);
assert.equal(parseAmountInput("abc"), null);
assert.equal(parseAmountInput("100001"), null);
// 서버가 소수 셋째 자리로 반올림한 뒤 0이면 400 — 화면도 같은 기준(리뷰 M1)
assert.equal(parseAmountInput("0.0004"), null);
assert.equal(parseAmountInput("0.0005"), 0.0005);

// 저장을 누른 뒤 쓴 양 안내(리뷰 M7): 비었거나 0 이하·숫자 아님 → 체크 끄기 안내, 서버 상한 초과 → 서버 문구(cooklog.AMOUNT_ERROR)
assert.equal(amountHint("0.3"), null);
assert.equal(amountHint(""), "쓴 양을 입력하거나, 안 썼으면 체크를 꺼주세요");
assert.equal(amountHint("0"), "쓴 양을 입력하거나, 안 썼으면 체크를 꺼주세요");
assert.equal(amountHint("0.0004"), "쓴 양을 입력하거나, 안 썼으면 체크를 꺼주세요");
assert.equal(amountHint("abc"), "쓴 양을 입력하거나, 안 썼으면 체크를 꺼주세요");
assert.equal(amountHint("100001"), "쓴 양은 0보다 커야 해요.");

// 사 먹으면 얼마 입력
assert.equal(parseWon("9,000원"), 9000);
assert.equal(parseWon(""), null);
assert.equal(parseWon(" "), null);
assert.equal(parseWon("9천"), undefined);
assert.equal(parseWon("1000001"), undefined);
assert.equal(parseWon("0"), 0);

// 입력 칸 표시: 틀린 입력은 쓴 글자 그대로(개정 1 T8①)
assert.equal(wonFieldText(9000, "9000"), "9,000");
assert.equal(wonFieldText(null, ""), "");
assert.equal(wonFieldText(undefined, "9천"), "9천");
assert.equal(wonFieldText(parseWon("a"), "a"), "a");

// 약 N원(100원 단위)·아낀 돈
assert.equal(aboutWon(10820), "약 10,800원");
assert.equal(aboutWon(10850), "약 10,900원");
assert.equal(aboutWon(-1250), "약 1,300원");
assert.equal(savedText(10820), "약 10,800원 아꼈어요");
assert.equal(savedText(-1200), "약 1,200원 더 들었어요");
assert.equal(savedText(0), "약 0원 아꼈어요");

// 끼니: 식단 칸 → 오늘이면 시각 → 지난 날은 저녁
assert.equal(cookMeal("2026-09-15", "2026-09-15", 12), "lunch");
assert.equal(cookMeal("2026-09-15", "2026-09-15", 4), "snack");
assert.equal(cookMeal("2026-09-15", "2026-09-15", 5), "breakfast");
assert.equal(cookMeal("2026-09-15", "2026-09-15", 20), "dinner");
assert.equal(cookMeal("2026-09-15", "2026-09-15", 21), "snack");
assert.equal(cookMeal("2026-09-14", "2026-09-15", 8), "dinner");
assert.equal(cookMeal("2026-09-14", "2026-09-15", 8, "breakfast"), "breakfast");

// 서울 시(時)
assert.equal(seoulHour(new Date("2026-09-15T03:41:00Z")), 12);
assert.equal(seoulHour(new Date("2026-09-14T15:00:00Z")), 0);

assert.equal(foodLogLine("2026-09-15", "dinner"), "9월 15일 저녁 · 집밥");

// 언제 칩
assert.equal(dateChip("2026-09-15", "2026-09-15", "2026-09-14"), "today");
assert.equal(dateChip("2026-09-14", "2026-09-15", "2026-09-14"), "yesterday");
assert.equal(dateChip("2026-09-10", "2026-09-15", "2026-09-14"), "pick");

// 저장 후 알림 첫 줄
assert.equal(deductedText(["김치", "두부", "대파"]), "재고에서 김치·두부·대파를 뺐어요");
assert.equal(deductedText(["두부", "김치", "대파", "양파", "감자"]), "재고에서 두부·김치·대파 외 2개를 뺐어요");
assert.equal(deductedText(["김치찌개용 돼지고기"]), "재고에서 김치찌개용 돼지고기를 뺐어요");
assert.equal(deductedText(["떡"]), "재고에서 떡을 뺐어요");
assert.equal(deductedText([]), "요리 일기에 남겼어요");

// 되돌린 뒤 알림
assert.equal(undoneText({ skipped: [] }), "재고를 되돌렸어요");
assert.equal(undoneText({ skipped: ["대파"] }), "재고를 되돌렸어요 · 대파는 그사이 바뀌어 그대로 뒀어요");
assert.equal(undoneText({ skipped: ["대파", "김"] }), "재고를 되돌렸어요 · 대파·김은 그사이 바뀌어 그대로 뒀어요");

// 쓴 양 칸 옆 재고
assert.equal(stockText({ stock_quantity: 600, stock_unit: "g" }), "재고 600g");
assert.equal(stockText({ stock_quantity: 0.5, stock_unit: "모" }), "재고 0.5모");
assert.equal(stockText({ stock_quantity: null, stock_unit: null }), "재고에 없어요");

// 레시피 상세 요리 표시(실제 starsText, 개정 1 T8③)
assert.equal(cookedLine({ last_on: "2026-09-15", last_rating: 4 }, starsText), "마지막 9월 15일 · ★★★★☆");
assert.equal(cookedLine({ last_on: "2026-09-15", last_rating: null }, starsText), "마지막 9월 15일");

// ---- Task 10: 요리 일기 목록·상세 ----
// 목록 행 아낀 돈 조각(결정 14·15)
assert.deepEqual(savedRowText({ saved: 10820, eat_out_price: 9000, excluded_count: 0 }), { text: "약 10,800원 아낌", good: true });
assert.deepEqual(savedRowText({ saved: -1200, eat_out_price: 9000, excluded_count: 0 }), { text: "약 1,200원 더 듦", good: false });
assert.deepEqual(savedRowText({ saved: null, eat_out_price: null, excluded_count: 0 }), { text: "사 먹으면 얼마 모름", good: false });
assert.deepEqual(savedRowText({ saved: null, eat_out_price: 9000, excluded_count: 2 }), { text: "재료 2개 가격 모름", good: false });
assert.deepEqual(savedRowText({ saved: null, eat_out_price: 9000, excluded_count: 0 }), { text: "재료 가격 모름", good: false });

assert.equal(diaryDateText({ cooked_on: "2026-09-15", servings: 2 }), "9월 15일 · 2인분");
assert.equal(diaryDateText({ cooked_on: "2026-09-05", servings: 1 }), "9월 5일 · 1인분"); // 앞자리 0 없이
assert.equal(firstLine("두부 마저 썼어요\n김치가 시어서"), "두부 마저 썼어요");
assert.equal(firstLine(null), "");

// 목록 위 이번 달 카드
assert.equal(diaryHeader({ month: "2026-09", cooked: 12, counted: 10, saved_total: 86000 }), "9월 요리 12번 · 약 86,000원 아꼈어요");
assert.equal(diaryHeader({ month: "2026-09", cooked: 12, counted: 0, saved_total: 0 }), "9월 요리 12번");
assert.equal(diaryHeader({ month: "2026-09", cooked: 3, counted: 2, saved_total: -2000 }), "9월 요리 3번 · 약 2,000원 더 들었어요");

// 계산표 줄
assert.equal(eatOutLine(9000, 2), "사 먹으면 9,000원 × 2인분");
assert.equal(costLine({ name: "김치", used: 0.3, unit: "kg", price: 12900, price_quantity: 1 }), "김치 0.3kg / 1kg 12,900원");
assert.equal(costLine({ name: "두부", used: 1, unit: "모", price: 2480, price_quantity: 1 }), "두부 1모 / 1모 2,480원");

// 계산표 아래 안내(시안 4)
const item = { used: null, unit: null, amount_text: null, excluded: null };
assert.equal(
  excludedNote([
    { ...item, name: "돼지고기", amount_text: "200g", excluded: "no_price" },
    { ...item, name: "고춧가루", amount_text: "1큰술", excluded: "seasoning" },
  ]),
  "돼지고기 200g은 가격 모름이라 뺐어요 · 양념은 계산에 넣지 않아요 · 참고용이에요",
);
assert.equal(
  excludedNote([
    { ...item, name: "애호박", used: 0.33, unit: "개", excluded: "no_price" },
    { ...item, name: "양파", amount_text: "1/2개", excluded: "no_price" },
  ]),
  "애호박 0.33개 외 1개는 가격 모름이라 뺐어요 · 참고용이에요",
);
assert.equal(excludedNote([]), "참고용이에요");

// 은/는: 영문 단위·숫자 끝은 읽는 소리로(개정 1 T10②)
assert.equal(withEunNeun("돼지고기 200g"), "돼지고기 200g은");
assert.equal(withEunNeun("우유 1L"), "우유 1L는");
assert.equal(withEunNeun("우유 500ml"), "우유 500ml는");
assert.equal(withEunNeun("계란 2개"), "계란 2개는");
assert.equal(withEunNeun("두부 3"), "두부 3은");
assert.equal(withEunNeun("계란 2"), "계란 2는");
assert.equal(withEunNeun("김치 0.3kg"), "김치 0.3kg은");
assert.equal(withEunNeun("양파"), "양파는");

console.log("check-cooklog: ok");
