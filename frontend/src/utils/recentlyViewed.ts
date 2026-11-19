/**
 * « Vus récemment » (lot A5 / R9): the last products this browser opened,
 * kept in `localStorage` only — no history on the server, nothing personal
 * sent anywhere. Unavailable storage (private window) = no section.
 */
const KEY = 'recently-viewed';
export const RECENTLY_VIEWED_MAX = 12;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function readRecentlyViewed(): string[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? '[]') as unknown;
    return Array.isArray(raw)
      ? raw.filter((id): id is string => typeof id === 'string' && UUID.test(id))
      : [];
  } catch {
    return [];
  }
}

/** The product goes first; the list keeps the last twelve, each once. */
export function rememberViewed(productId: string): void {
  if (!UUID.test(productId)) return;
  const ids = [productId, ...readRecentlyViewed().filter((id) => id !== productId)];
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ids.slice(0, RECENTLY_VIEWED_MAX)));
  } catch {
    // Storage full or blocked: the section simply stays empty.
  }
}
