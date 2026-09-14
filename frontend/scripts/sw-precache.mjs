// 빌드한 dist 파일 목록·내용 해시를 서비스 워커(public/sw.js → dist/sw.js)에 넣는다(스펙 19·28절). vite.config.ts가 빌드 끝에 부른다.
// 검사: scripts/check-sw-precache.mjs
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

/** dist 안 모든 파일 → 서비스 워커가 미리 받을 주소(index.html은 "/"). sw.js·소스맵은 뺀다. 정렬해서 돌려준다 */
export function precacheList(files) {
  return files
    .filter((f) => f !== "sw.js" && !f.endsWith(".map"))
    .map((f) => (f === "index.html" ? "/" : `/${f}`))
    .sort();
}

/** sw.js 원본의 VERSION·PRECACHE 두 줄을 바꾼다. 줄이 없으면 빌드를 멈춘다(조용히 오프라인이 깨지지 않게) */
export function fillServiceWorker(source, version, urls) {
  const out = source
    .replace('const VERSION = "dev";', `const VERSION = ${JSON.stringify(version)};`)
    .replace("const PRECACHE = [];", `const PRECACHE = ${JSON.stringify(urls)};`);
  if (out === source || !out.includes(JSON.stringify(urls))) throw new Error("sw.js에서 VERSION·PRECACHE 줄을 찾지 못했어요");
  return out;
}

/** dist/sw.js를 채운다. 버전은 파일 이름·내용 해시라 무엇이든 바뀌면 새 캐시가 된다 */
export function writeServiceWorker(root, dist) {
  const outDir = resolve(root, dist);
  const files = readdirSync(outDir, { recursive: true, withFileTypes: true })
    .filter((d) => d.isFile())
    .map((d) => join(d.parentPath, d.name).slice(outDir.length + 1).split("\\").join("/"));
  const urls = precacheList(files);
  const hash = createHash("sha256");
  for (const f of files.filter((f) => f !== "sw.js").sort()) hash.update(f).update(readFileSync(join(outDir, f)));
  const swPath = join(outDir, "sw.js");
  writeFileSync(swPath, fillServiceWorker(readFileSync(swPath, "utf8"), hash.digest("hex").slice(0, 12), urls));
  return urls;
}
