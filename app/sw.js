/* 오프라인 — 한 번 본 화면과 지도 칸은 인터넷이 없어도 열린다.
   껍데기(화면 파일)는 받아 두고, 지도 칸은 본 것만 쌓되 80개까지만 둔다(용량 폭주 방지).
   카카오 지도는 남의 서버라 저장할 수 없다 → 오프라인에서는 목록·상세만 된다(앱이 이미 그렇게 견딘다). */
const SHELL = 'shell-v1';
const TILES = 'tiles-v1';
const KEEP = 80;
const FILES = ['./', 'index.html', 'style.css', 'app.js', 'hours.js', 'detail.js', 'mapview.js',
  'icon.svg', 'icon-180.png', 'icon-192.png', 'manifest.webmanifest',
  'img/bg_day_blue_1080.webp', 'img/bg_evening_1080.webp', 'img/bg_night_1080.webp',
  'data/index.json', 'data/holidays.json', 'data/gov_sites.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== SHELL && k !== TILES).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function trim(cache) {
  const keys = await cache.keys();
  for (const k of keys.slice(0, Math.max(0, keys.length - KEEP))) await cache.delete(k);
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;   // 카카오 등 남의 서버는 건드리지 않는다

  if (url.pathname.includes('/data/t/')) {                                     // 지도 칸: 저장본 먼저, 없으면 받아서 저장
    e.respondWith(caches.open(TILES).then(async (c) => {
      const hit = await c.match(e.request);
      if (hit) return hit;
      const res = await fetch(e.request);
      if (res.ok) { c.put(e.request, res.clone()); trim(c); }
      return res;
    }));
    return;
  }
  // 화면 파일: 저장본 먼저(주소에 내용 해시가 붙어 있어 새 파일이면 주소가 달라진다)
  e.respondWith(caches.open(SHELL).then(async (c) => {
    const hit = await c.match(e.request, { ignoreSearch: url.pathname.endsWith('.html') || url.pathname === '/' });
    const net = fetch(e.request).then((res) => { if (res.ok) c.put(e.request, res.clone()); return res; }).catch(() => hit);
    return hit || net;
  }));
});
