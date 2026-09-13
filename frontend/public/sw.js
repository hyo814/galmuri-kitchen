// ponytail: 이 SW는 앱 셸(/) 하나만 캐시한다. 재료·장보기 목록 오프라인 지원(spec §19)은
// phase 4에서 이 위에 확장한다.
const CACHE = "galmuri-shell-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add("/")));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("galmuri-shell-") && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // /api, /auth, POST 등, 다른 오리진 요청은 절대 가로채지 않는다 — 네트워크로 그대로 보낸다.
  if (request.method !== "GET" || request.mode !== "navigate" || new URL(request.url).origin !== self.location.origin) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) caches.open(CACHE).then((cache) => cache.put("/", response.clone()));
        return response;
      })
      .catch(() => caches.match("/")),
  );
});
