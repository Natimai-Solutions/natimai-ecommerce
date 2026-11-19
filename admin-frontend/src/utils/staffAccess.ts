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

/**
 * Screens every back-office account reaches: the two-factor enrolment the
 * API demands before anything else (`auth.totp.enrollment_required`).
 */
export const COMMON_SCREENS: readonly string[] = ['/security'];

/** Whether ``path`` is open to the signed-in person. */
export function canOpen(access: Access | null, path: string): boolean {
  if (!access || access.is_superuser) return true;
  const screens = ROLE_SCREENS[access.staff_role ?? ''] ?? [];
  const first = '/' + (path.split('/')[1] ?? '');
  return COMMON_SCREENS.includes(first) || screens.includes(first);
}

/**
 * Where a team member lands: the first screen of their role that is open
 * (``isOn``: its module switched on), else the security screen — never `/`,
 * which would send them back here (a redirect loop).
 */
export function homeOf(
  access: Access | null,
  isOn: (path: string) => boolean = () => true,
): string {
  if (!access || access.is_superuser) return '/';
  const screens = ROLE_SCREENS[access.staff_role ?? ''] ?? [];
  return screens.find(isOn) ?? COMMON_SCREENS[0] ?? '/security';
}
