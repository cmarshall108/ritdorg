/* RITDorg service worker — chapter + assets caching for offline reading. */
const CACHE_STATIC = 'ritd-static-v1';
const CACHE_CHAPTERS = 'ritd-chapters-v1';
const CACHE_TTS = 'ritd-tts-v1';
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/userdata.js',
    '/static/js/study.js',
];

self.addEventListener('install', (e) => {
    e.waitUntil(caches.open(CACHE_STATIC).then((c) => c.addAll(STATIC_ASSETS).catch(()=>{})));
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);

    // Cache-first for static assets.
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(req).then((hit) => hit || fetch(req).then((r) => {
                const copy = r.clone();
                caches.open(CACHE_STATIC).then((c) => c.put(req, copy)).catch(()=>{});
                return r;
            }).catch(() => hit)),
        );
        return;
    }
    // Cache-first for cached Bible chapter JSON in /static/data/bible/.
    // (Already covered above.)
    // Stale-while-revalidate for /api/words/* (small JSON, useful offline).
    if (url.pathname.startsWith('/api/words/') || url.pathname.startsWith('/api/crossrefs/') ||
        url.pathname.startsWith('/api/timeline') || url.pathname.startsWith('/api/plans')) {
        event.respondWith(
            caches.open(CACHE_CHAPTERS).then(async (c) => {
                const hit = await c.match(req);
                const network = fetch(req).then((r) => { c.put(req, r.clone()).catch(()=>{}); return r; }).catch(() => hit);
                return hit || network;
            }),
        );
        return;
    }
    if (url.pathname === '/api/tts') {
        event.respondWith(
            caches.open(CACHE_TTS).then(async (c) => {
                const hit = await c.match(req);
                if (hit) return hit;
                const r = await fetch(req);
                if (r.ok) c.put(req, r.clone()).catch(()=>{});
                return r;
            }),
        );
    }
});
