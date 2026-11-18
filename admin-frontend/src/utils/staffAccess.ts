/**
 * Screens a back-office team member reaches by role (lot ROLE). A superuser
 * reaches everything; the API checks the same allow-list on every route.
 */
export const ROLE_SCREENS: Record<string, string[]> = {
  customer_service: ['/messages', '/orders'],
  sales: ['/messages', '/orders', '/quote-requests'],
};

interface Access {
  is_superuser?: boolean;
  staff_role?: string | null;
}

/** Whether ``path`` is open to the signed-in person. */
export function canOpen(access: Access | null, path: string): boolean {
  if (!access || access.is_superuser) return true;
  const screens = ROLE_SCREENS[access.staff_role ?? ''] ?? [];
  const first = '/' + (path.split('/')[1] ?? '');
  return screens.includes(first);
}

/** Where a team member lands (their first screen). */
export function homeOf(access: Access | null): string {
  if (!access || access.is_superuser) return '/';
  return ROLE_SCREENS[access.staff_role ?? '']?.[0] ?? '/';
}
