// vite.config.ts가 타입 검사 때 읽는 선언(scripts/sw-precache.mjs)
export function precacheList(files: string[]): string[];
export function fillServiceWorker(source: string, version: string, urls: string[]): string;
export function writeServiceWorker(root: string, dist: string): string[];
