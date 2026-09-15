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

assert.equal(guideText(demo).join(""), "냉장고를 미리 채워뒀어요. 그런데 두부가 내일까지예요! 두부로 뭘 만들 수 있을지 같이 볼까요?");
assert.equal(guideText(demo)[1], "두부가 내일까지예요!");
assert.equal(guideText([item("양상추", 0)])[1], "양상추가 오늘까지예요!");
assert.equal(guideText([item("당근", 3)]).join(""), "냉장고를 미리 채워뒀어요. 그런데 당근이 3일 남았어요! 당근으로 뭘 만들 수 있을지 같이 볼까요?");
assert.deepEqual(guideText([item("우유", 6, "ok")]), ["냉장고를 미리 채워뒀어요. 곧 먹어야 할 재료로 뭘 만들 수 있을지 같이 볼까요?", "", ""]);

assert.equal(spotlightTip(["두부", "대파"], 5), "여기를 눌러보세요. 두부랑 대파부터 쓰는 요리 3가지를 바로 만들어줘요. 체험은 하루 5번까지 돼요.");
assert.match(spotlightTip(["김치", "두부", "대파"], 5), /^여기를 눌러보세요\. 김치랑 두부부터 쓰는/); // 앞 두 개만
assert.match(spotlightTip(["당근", "대파"], 5), / 당근이랑 대파부터 쓰는 /); // 받침 있으면 이랑
assert.equal(spotlightTip(["두부"], 3), "여기를 눌러보세요. 두부부터 쓰는 요리 3가지를 바로 만들어줘요. 체험은 하루 3번까지 돼요.");
assert.equal(spotlightTip([], 5), "여기를 눌러보세요. 곧 먹어야 할 재료부터 쓰는 요리 3가지를 바로 만들어줘요. 체험은 하루 5번까지 돼요.");

console.log("check-demo-guide: ok");
