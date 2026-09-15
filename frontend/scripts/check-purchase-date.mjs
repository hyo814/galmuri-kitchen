// 재고 구입일 칩 순수 로직 검사(시안 docs/design/scan-multi). `npm run check`
import assert from "node:assert/strict";
import { detectedPick, ownDateText, pickDate, pickedText } from "../src/purchaseDate.ts";

const today = "2026-09-15";
assert.equal(pickDate({ chip: "today", date: "" }, today), "2026-09-15");
assert.equal(pickDate({ chip: "yesterday", date: "" }, today), "2026-09-14");
assert.equal(pickDate({ chip: "3days", date: "" }, today), "2026-09-12");
assert.equal(pickDate({ chip: "week", date: "" }, today), "2026-09-08");
assert.equal(pickDate({ chip: "week", date: "" }, "2026-03-03"), "2026-02-24"); // 달 넘김
assert.equal(pickDate({ chip: "date", date: "2026-09-03" }, today), "2026-09-03");
assert.equal(pickDate({ chip: "unknown", date: "2026-09-03" }, today), null);

// 영수증·주문 날짜 → 처음 칩
assert.deepEqual(detectedPick(null, today), { chip: "today", date: "" });
assert.deepEqual(detectedPick("2026-09-15", today), { chip: "today", date: "" });
assert.deepEqual(detectedPick("2026-09-14", today), { chip: "yesterday", date: "" });
assert.deepEqual(detectedPick("2026-09-12", today), { chip: "date", date: "2026-09-12" });

assert.equal(pickedText("2026-09-12"), "9월 12일 (토) 구입으로 넣어요");
assert.equal(pickedText(null), "구입일 없이 넣어요");

assert.equal(ownDateText(null, today), "구입일 모름");
assert.equal(ownDateText("2026-09-15", today), "오늘 구입");
assert.equal(ownDateText("2026-09-14", today), "어제 구입");
assert.equal(ownDateText(`${new Date().getFullYear()}-09-03`, today), "9월 3일 구입");
console.log("check-purchase-date: ok");
