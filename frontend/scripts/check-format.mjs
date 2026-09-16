// 화면 글자 다듬기 순수 함수 검사. `npm run check`
import assert from "node:assert/strict";
import { isVideoLink, shortChannelName } from "../src/format.ts";

// 영상 칸 채널 칩: 한글 이름 뒤 영어만 뗀다(목록의 채널명은 전체 이름)
assert.equal(shortChannelName("자취요리신 simple cooking"), "자취요리신");
assert.equal(shortChannelName("편스토랑X   FUNSTAURANT-X"), "편스토랑X");
assert.equal(shortChannelName("요리왕비룡 셰프TV "), "요리왕비룡 셰프TV");
assert.equal(shortChannelName("딸을 위한 레시피 Recipes for daughters"), "딸을 위한 레시피");
assert.equal(shortChannelName("1분다이어터 1mindiet"), "1분다이어터");
assert.equal(shortChannelName("Maangchi"), "Maangchi");
// 글 붙여넣기 경고 아래 화면 캡처 안내: 유튜브·인스타그램 링크만(서버 parse_link와 같은 호스트)
assert.equal(isVideoLink("https://m.youtube.com/shorts/abcdefghijk"), true);
assert.equal(isVideoLink(" https://youtu.be/abcdefghijk "), true);
assert.equal(isVideoLink("https://music.youtube.com/watch?v=abcdefghijk"), true);
assert.equal(isVideoLink("http://www.instagram.com/reel/Cabc123/"), true);
assert.equal(isVideoLink("https://blog.naver.com/cook/223456789012"), false);
assert.equal(isVideoLink("https://www.m.youtube.com/shorts/abcdefghijk"), false); // 서버도 앞의 하나만 뗀다
assert.equal(isVideoLink("https://youtube.com.example.net/shorts/abcdefghijk"), false);
assert.equal(isVideoLink("https://notyoutube.com/watch?v=abcdefghijk"), false);
assert.equal(isVideoLink("youtube.com/shorts/abcdefghijk"), false); // 스킴 없음
console.log("check-format: ok");
