// 체험 계정 첫 30초 안내 글자 검사(스펙 30절 C). `npm run check`
import assert from "node:assert/strict";
import { guideText, spotlightTip, urgentItems, withRo } from "../src/demoGuide.ts";

const item = (name, days_left, status = "urgent") => ({ name, days_left, status });

// 체험 계정 예시 재고(backend/app/demo.py): 두부 D-1, 대파 D-2, 우유 D-6(아직 여유), 김치(유통기한 없음)
const demo = [item("대파", 2), item("우유", 6, "ok"), item("김치", null, "old"), item("두부", 1)];
assert.deepEqual(urgentItems(demo).map((i) => i.name), ["두부", "대파"]);
assert.deepEqual(urgentItems([item("상한 우유", -1), item("달걀", null, "danger")]), []); // 지난 재료·날짜 없는 재료는 안 짚는다

assert.equal(withRo("두부"), "두부로");
assert.equal(withRo("돼지고기 앞다리살"), "돼지고기 앞다리살로"); // ㄹ받침은 로
assert.equal(withRo("떡국"), "떡국으로");
assert.equal(withRo("SPAM"), "SPAM(으)로");
assert.equal(withRo("두부 "), "두부로"); // 공백은 뗀다

assert.equal(guideText(demo).join(""), "갈무리부엌은 재료가 상하기 전에 알려주고, 그 재료로 만들 요리를 찾아줘요. 체험 냉장고를 채워뒀는데 두부가 내일까지예요! 두부로 뭘 만들 수 있을지 같이 볼까요?");
assert.equal(guideText(demo)[1], "두부가 내일까지예요!");
assert.equal(guideText([item("양상추", 0)])[1], "양상추가 오늘까지예요!");
assert.equal(guideText([item(" 두부 ", 1)]).join(""), "갈무리부엌은 재료가 상하기 전에 알려주고, 그 재료로 만들 요리를 찾아줘요. 체험 냉장고를 채워뒀는데 두부가 내일까지예요! 두부로 뭘 만들 수 있을지 같이 볼까요?");
assert.equal(guideText([item("SPAM", 2)])[1], "SPAM(이)가 2일 남았어요!");
assert.equal(guideText([item("당근", 3)]).join(""), "갈무리부엌은 재료가 상하기 전에 알려주고, 그 재료로 만들 요리를 찾아줘요. 체험 냉장고를 채워뒀는데 당근이 3일 남았어요! 당근으로 뭘 만들 수 있을지 같이 볼까요?");
assert.deepEqual(guideText([item("우유", 6, "ok")]), ["갈무리부엌은 재료가 상하기 전에 알려주고, 그 재료로 만들 요리를 찾아줘요. 체험 냉장고를 채워뒀어요. 곧 먹어야 할 재료로 뭘 만들 수 있을지 같이 볼까요?", "", ""]);

assert.equal(spotlightTip(["두부", "대파"]), "여기를 눌러보세요. 두부랑 대파로 만들 요리를 바로 골라줘요.");
assert.equal(spotlightTip(["김치", "두부", "대파"]), "여기를 눌러보세요. 김치랑 두부로 만들 요리를 바로 골라줘요."); // 앞 두 개만
assert.equal(spotlightTip(["당근", "떡국"]), "여기를 눌러보세요. 당근이랑 떡국으로 만들 요리를 바로 골라줘요."); // 로는 마지막 이름을 따른다
assert.equal(spotlightTip(["두부", "돼지고기 앞다리살"]), "여기를 눌러보세요. 두부랑 돼지고기 앞다리살로 만들 요리를 바로 골라줘요.");
assert.equal(spotlightTip(["SPAM", "대파"]), "여기를 눌러보세요. SPAM(이)랑 대파로 만들 요리를 바로 골라줘요."); // 한글이 아니면 (이)랑
assert.equal(spotlightTip(["두부 "]), "여기를 눌러보세요. 두부로 만들 요리를 바로 골라줘요.");
assert.equal(spotlightTip([]), "여기를 눌러보세요. 곧 먹어야 할 재료로 만들 요리를 바로 골라줘요.");

console.log("check-demo-guide: ok");
