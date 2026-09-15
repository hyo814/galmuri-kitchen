// 서비스 워커 미리 받을 목록 검사(4단계 계획 Task 7). `npm run check`
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fillServiceWorker, precacheList, writeServiceWorker } from "./sw-precache.mjs";

assert.deepEqual(
  precacheList(["sw.js", "index.html", "assets/index-abc.js", "assets/index-abc.js.map", "icon-192.png", "og.png", "manifest.webmanifest"]),
  ["/", "/assets/index-abc.js", "/icon-192.png", "/manifest.webmanifest"],
);

const template = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
const filled = fillServiceWorker(template, "abc123", ["/", "/assets/a.js"]);
assert.match(filled, /const VERSION = "abc123";/);
assert.match(filled, /const PRECACHE = \["\/","\/assets\/a.js"\];/);
assert.throws(() => fillServiceWorker("const X = 1;", "v", ["/"]));

// 실제 dist 모양: 내용이 바뀌면 버전도 바뀐다
const dir = mkdtempSync(join(tmpdir(), "sw-precache-"));
try {
  mkdirSync(join(dir, "assets"));
  writeFileSync(join(dir, "index.html"), "<html>");
  writeFileSync(join(dir, "assets", "index-1.js"), "a");
  const build = () => {
    writeFileSync(join(dir, "sw.js"), template);
    assert.deepEqual(writeServiceWorker(dir, "."), ["/", "/assets/index-1.js"]);
    return readFileSync(join(dir, "sw.js"), "utf8").match(/const VERSION = "(\w+)";/)[1];
  };
  const v1 = build();
  assert.equal(build(), v1);
  writeFileSync(join(dir, "index.html"), "<html lang=ko>");
  assert.notEqual(build(), v1);
} finally {
  rmSync(dir, { recursive: true, force: true });
}

console.log("sw precache ok");
