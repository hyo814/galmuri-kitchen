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
  const url = new URL(request.url);
  // 같은 오리진의 화면 이동(GET)만 다룬다. /api·/auth(로그인 리다이렉트), POST, 다른 오리진은 가로채지 않고 네트워크로 그대로 보낸다.
  if (request.method !== "GET" || request.mode !== "navigate" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/")) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) caches.open(CACHE).then((cache) => cache.put("/", response.clone()));
        return response;
      })
      .catch(() => caches.match("/")),
  );
});
