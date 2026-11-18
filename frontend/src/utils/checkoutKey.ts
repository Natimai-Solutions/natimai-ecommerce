/**
 * Idempotency key of an order submission (`CheckoutRequest.idempotency_key`).
 *
 * One key per submission: every retry of the same cart sends it again, so a
 * checkout whose response was lost (a timeout, a dropped connection) gets
 * its order back instead of creating a second one. A cart that changed is a
 * new submission and gets a new key. Kept in sessionStorage so a reload of
 * the page after a timeout still retries with the same key.
 */

const STORAGE_KEY = 'checkout.idempotency_key';

interface StoredKey {
  signature: string;
  key: string;
}

export interface SubmittedLine {
  product_id: string;
  quantity: number;
  import_service_level?: string | null;
}

/** What makes two submissions « the same »: the lines and the quote. */
export function submissionSignature(
  lines: readonly SubmittedLine[],
  quoteRequestId: string | null,
): string {
  const parts = lines
    .map((l) => `${l.product_id}:${l.quantity}:${l.import_service_level ?? ''}`)
    .sort();
  return `${quoteRequestId ?? ''}|${parts.join(',')}`;
}

function newKey(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
  // Old browsers: still 128 random-looking bits, enough to tell submissions apart.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

function read(): StoredKey | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredKey>;
    return typeof parsed.key === 'string' && typeof parsed.signature === 'string'
      ? { key: parsed.key, signature: parsed.signature }
      : null;
  } catch {
    return null;
  }
}

/** The key of this submission: the stored one when the cart is unchanged. */
export function checkoutKeyFor(signature: string): string {
  const stored = read();
  if (stored && stored.signature === signature) return stored.key;
  const key = newKey();
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ signature, key }));
  } catch {
    // Private mode / storage blocked: the key still covers retries on this page.
  }
  return key;
}

/** The order exists: the next submission is a new one. */
export function forgetCheckoutKey(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // nothing stored
  }
}
