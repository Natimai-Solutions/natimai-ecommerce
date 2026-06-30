import { api } from 'src/boot/api';

/**
 * User preferences (storefront self-service).
 *
 * Mirrors the backend `UserPreferencePublic` schema exposed by
 * `GET/PUT /users/me/preferences`. All enum-like fields are nullable: a null
 * value means "no explicit preference, fall back to system defaults".
 */
export interface UserPreferences {
  user_id: string;
  notification_email_enabled: boolean;
  notification_shipping_steps: boolean;
  /** Checkout fallback: fastest | cheapest | eco_friendly */
  default_shipping_preference: string | null;
  /** UI language: fr | en */
  locale: string | null;
  /** Display currency: XPF | USD | EUR */
  currency_pref: string | null;
  /** Import freight level of service: rapide | economique | ecologique */
  preferred_shipping_mode: string | null;
}

/** Partial update — every field is optional (PUT is an upsert/patch). */
export type UserPreferencesUpdate = Partial<Omit<UserPreferences, 'user_id'>>;

export async function getMyPreferences(): Promise<UserPreferences> {
  const { data } = await api.get<UserPreferences>('/users/me/preferences');
  return data;
}

export async function updateMyPreferences(
  payload: UserPreferencesUpdate,
): Promise<UserPreferences> {
  const { data } = await api.put<UserPreferences>('/users/me/preferences', payload);
  return data;
}
