/**
 * Admin screens belonging to a switchable module (Admin → Modules).
 *
 * A screen whose module is off leaves the menu and its route sends back to
 * the dashboard; nothing is deleted, the screen returns with the module.
 */
export const ROUTE_MODULES: Record<string, string> = {
  '/suppliers': 'suppliers',
  '/supplier-orders': 'supplier_orders',
  '/spec-definitions': 'specs',
  '/customs-rates': 'customs',
  '/currency-rates': 'currencies',
  '/logistics-routes': 'logistics_multileg',
  '/grouped-departures': 'grouped_departures',
  '/quote-requests': 'quotes',
  '/group-upgrade-requests': 'price_groups',
  '/abandoned-carts': 'abandoned_carts',
};

/** The module a path belongs to (its first segment), if any. */
export function moduleOfPath(path: string): string | null {
  const first = '/' + (path.split('/')[1] ?? '');
  return ROUTE_MODULES[first] ?? null;
}
