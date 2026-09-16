// 화면 글자 다듬기 순수 함수 검사. `npm run check`
import assert from "node:assert/strict";
import { shortChannelName } from "../src/format.ts";

// 영상 칸 채널 칩: 한글 이름 뒤 영어만 뗀다(목록의 채널명은 전체 이름)
assert.equal(shortChannelName("자취요리신 simple cooking"), "자취요리신");
assert.equal(shortChannelName("편스토랑X   FUNSTAURANT-X"), "편스토랑X");
assert.equal(shortChannelName("요리왕비룡 셰프TV "), "요리왕비룡 셰프TV");
assert.equal(shortChannelName("딸을 위한 레시피 Recipes for daughters"), "딸을 위한 레시피");
assert.equal(shortChannelName("1분다이어터 1mindiet"), "1분다이어터");
assert.equal(shortChannelName("Maangchi"), "Maangchi");
console.log("check-format: ok");
