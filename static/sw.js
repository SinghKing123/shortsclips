// Service worker for PWA — minimal, just enables "Add to Home Screen"
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
self.addEventListener('fetch', (e) => e.respondWith(fetch(e.request)));
