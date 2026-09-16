// 화면 글자 다듬기 순수 함수 검사. `npm run check`
import assert from "node:assert/strict";
import { missingAmountCount, pickRowSummary, remainingRowSummary, shortChannelName } from "../src/format.ts";

// 영상 칸 채널 칩: 한글 이름 뒤 영어만 뗀다(목록의 채널명은 전체 이름)
assert.equal(shortChannelName("자취요리신 simple cooking"), "자취요리신");
assert.equal(shortChannelName("편스토랑X   FUNSTAURANT-X"), "편스토랑X");
assert.equal(shortChannelName("요리왕비룡 셰프TV "), "요리왕비룡 셰프TV");
assert.equal(shortChannelName("딸을 위한 레시피 Recipes for daughters"), "딸을 위한 레시피");
assert.equal(shortChannelName("1분다이어터 1mindiet"), "1분다이어터");
assert.equal(shortChannelName("Maangchi"), "Maangchi");

// 여러 요리 가져오기(17절) 고르기·이어서 화면의 줄 요약
const named = (...names) => names.map((name) => ({ name, amount: "1개" }));
assert.equal(pickRowSummary(named("떡", "어묵", "고추장", "설탕", "물엿"), ["1", "2", "3", "4", "5"]), "떡 · 어묵 · 고추장 · 설탕 외 1개 · 만드는 법 5단계");
assert.equal(pickRowSummary(named("떡", "어묵"), ["1"]), "떡 · 어묵 · 만드는 법 1단계"); // 4개 이하면 외 N개 없이 모두 보여준다

const amounts = (...amounts) => amounts.map((amount) => ({ amount }));
assert.equal(missingAmountCount(amounts("300g", "", "2큰술", "")), 2);
assert.equal(remainingRowSummary(amounts("300g", "2큰술"), ["1", "2", "3"]), "재료 2개 · 만드는 법 3단계");
assert.equal(remainingRowSummary(amounts("300g", "", ""), ["1", "2"]), "재료 3개 · 양 확인 2개"); // 양이 빠지면 단계 수 대신 보여준다
console.log("check-format: ok");
