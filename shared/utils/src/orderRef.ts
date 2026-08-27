/**
 * Human reference for an order (M5).
 *
 * Mirrors `resolve_order_ref` in the backend email renderer: the sequential
 * number (`CMD-2026-00042`) when the order has one, otherwise the short-ref
 * derived from the UUID (`#e090fee1`) used before M5 existed.
 *
 * Both frontends go through this so an order never appears under two different
 * references depending on which screen — or which email — the customer reads.
 */
export function orderRef(
  orderNumber: string | null | undefined,
  orderId: string | null | undefined,
): string {
  const number = (orderNumber ?? '').trim()
  if (number) return number

  const id = (orderId ?? '').trim()
  if (!id) return '—'
  // Hyphens stripped so the fallback matches the backend, which shortens the
  // UUID's hex form: "e090fee1-2b5d-…" → "#e090fee1".
  return `#${id.replace(/-/g, '').slice(0, 8)}`
}
