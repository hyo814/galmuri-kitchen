// 갈무리부엌 서비스 워커(스펙 19·28절). 화면 파일만 캐시한다 — /api·/auth 데이터는 화면이 IndexedDB로 보관한다.
// 빌드 때 vite.config.ts(scripts/sw-precache.mjs)가 아래 두 줄을 dist 파일 목록·내용 해시로 바꾼다. 개발 서버에서는 그대로(/만 캐시).
const VERSION = "dev";
const PRECACHE = [];

const SHELL = `galmuri-shell-${VERSION}`;
// 글꼴 캐시는 배포와 상관없이 남긴다(Google Fonts 주소는 배포마다 바뀌지 않는다)
const FONTS = "galmuri-fonts-v1";
// ponytail: 글꼴 캐시 개수 상한(한글은 unicode-range 조각이 굵기마다 100개 안팎). 넘으면 먼저 넣은 것부터 지운다.
const FONTS_MAX = 200;

self.addEventListener("install", (event) => {
  // cache: "reload" — HTTP 캐시의 옛 index.html이 새 해시 목록과 섞이지 않게
  const urls = PRECACHE.length ? PRECACHE : ["/"];
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(urls.map((url) => new Request(url, { cache: "reload" })))));
});

// 새 버전은 화면이 보내는 SKIP_WAITING(앱을 떠날 때, main.tsx)이나 탭이 모두 닫힐 때 바뀐다
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("galmuri-shell-") && key !== SHELL).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

/** 네트워크에서 받아 글꼴 캐시에 넣는다. crossorigin 없이 불린 opaque 응답(status 0)도 넣는다.
 *  stored: 캐시에 다 넣었을 때 끝나는 약속(waitUntil용, 실패해도 조용히 끝남) */
function fetchFont(request) {
  const response = fetch(request);
  const stored = response
    .then(async (res) => {
      if (!res.ok && res.type !== "opaque") return;
      const copy = res.clone(); // 화면이 본문을 읽기 전에 복사한다(await 뒤에는 이미 읽혀 clone이 실패한다)
      const cache = await caches.open(FONTS);
      await cache.put(request, copy);
      const keys = await cache.keys();
      await Promise.all(keys.slice(0, Math.max(0, keys.length - FONTS_MAX)).map((key) => cache.delete(key)));
    })
    .catch(() => {});
  return { response, stored };
}

/** 화면 이동을 이만큼 기다려도 응답이 없으면 캐시한 화면을 준다(마트 지하처럼 연결이 거의 끊긴 곳) */
const NAVIGATE_TIMEOUT_MS = 3000;

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin === self.location.origin) {
    // /api·/auth(로그인 리다이렉트)는 가로채지 않는다
    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/")) return;
    if (request.mode === "navigate") {
      // 네트워크 우선, 실패하거나 3초 안에 안 오면 캐시한 index.html(해시 파일과 같은 버전). 캐시도 없으면 네트워크를 끝까지 기다린다
      const network = fetch(request);
      network.catch(() => {});
      const timeout = new Promise((resolve) => setTimeout(resolve, NAVIGATE_TIMEOUT_MS));
      event.respondWith(
        Promise.race([network, timeout])
          .catch(() => undefined)
          .then((res) => res || caches.match("/", { cacheName: SHELL }).then((cached) => cached || network))
          .catch(() => Response.error()),
      );
    } else if (PRECACHE.includes(url.pathname)) {
      event.respondWith(caches.match(url.pathname, { cacheName: SHELL }).then((cached) => cached || fetch(request)));
    }
    return;
  }

  const cached = () => caches.match(request, { cacheName: FONTS });
  if (url.origin === "https://fonts.googleapis.com") {
    // CSS: 캐시가 있으면 바로 주고 뒤에서 새로 받는다(stale-while-revalidate)
    const { response, stored } = fetchFont(request);
    response.catch(() => {});
    event.waitUntil(stored);
    event.respondWith(cached().then((hit) => hit || response));
  } else if (url.origin === "https://fonts.gstatic.com") {
    // 글꼴 파일: 주소에 버전이 있어 바뀌지 않으니 캐시 우선. waitUntil은 이벤트 안에서 바로 걸고, 받았으면 캐시에 넣을 때까지 기다린다
    const result = cached().then((hit) => (hit ? { response: hit, stored: null } : fetchFont(request)));
    event.waitUntil(result.then((r) => r.stored).catch(() => {}));
    event.respondWith(result.then((r) => r.response));
  }
});
