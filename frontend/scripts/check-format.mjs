// 화면 글자 다듬기 순수 함수 검사. `npm run check`
import assert from "node:assert/strict";
import { shortChannelName, videoSource } from "../src/format.ts";

// 영상 칸 채널 칩: 한글 이름 뒤 영어만 뗀다(목록의 채널명은 전체 이름)
assert.equal(shortChannelName("자취요리신 simple cooking"), "자취요리신");
assert.equal(shortChannelName("편스토랑X   FUNSTAURANT-X"), "편스토랑X");
assert.equal(shortChannelName("요리왕비룡 셰프TV "), "요리왕비룡 셰프TV");
assert.equal(shortChannelName("딸을 위한 레시피 Recipes for daughters"), "딸을 위한 레시피");
assert.equal(shortChannelName("1분다이어터 1mindiet"), "1분다이어터");
assert.equal(shortChannelName("Maangchi"), "Maangchi");

// 화면 캡처 흐름: 유튜브 영상·인스타그램 게시물 링크만, 출처는 서버와 같은 표준 주소(서버 parse_link와 같은 규칙)
const youtube = (id) => ({ source: "youtube", source_url: `https://www.youtube.com/watch?v=${id}` });
assert.deepEqual(videoSource("https://m.youtube.com/shorts/abcdefghijk"), youtube("abcdefghijk"));
assert.deepEqual(videoSource(" https://youtu.be/abc-EFG_ijk?si=share "), youtube("abc-EFG_ijk"));
assert.deepEqual(videoSource("https://music.youtube.com/watch/?v=abcdefghijk&t=30"), youtube("abcdefghijk"));
assert.deepEqual(videoSource("http://www.youtube-nocookie.com/embed/abcdefghijk"), youtube("abcdefghijk"));
assert.deepEqual(videoSource("https://m.instagram.com/reels/Cabc123/?igsh=x"), {
  source: "instagram",
  source_url: "https://www.instagram.com/p/Cabc123/",
});
assert.equal(videoSource("https://www.youtube.com/@cookchannel"), null); // 영상 주소가 아니다(서버는 400)
assert.equal(videoSource("https://www.youtube.com/watch?v=tooshort"), null);
assert.equal(videoSource("https://www.instagram.com/stories/cook/1234567/"), null);
assert.equal(videoSource("https://blog.naver.com/cook/223456789012"), null);
assert.equal(videoSource("https://www.m.youtube.com/shorts/abcdefghijk"), null); // 서버도 앞의 하나만 뗀다
assert.equal(videoSource("https://youtube.com.example.net/shorts/abcdefghijk"), null);
assert.equal(videoSource("ftp://youtube.com/shorts/abcdefghijk"), null);
assert.equal(videoSource("youtube.com/shorts/abcdefghijk"), null); // 스킴 없음
console.log("check-format: ok");
