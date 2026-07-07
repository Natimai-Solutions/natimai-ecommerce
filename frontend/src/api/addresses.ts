import { api } from 'src/boot/api';

/** Allowed address types (backend `validate_address_type`). */
export type AddressType = 'billing' | 'shipping' | 'other';

/**
 * Address as returned by the backend (`AddressPublic`).
 *
 * `is_validated` is server-managed: a freshly created address starts at
 * `false` and is flipped by an admin before it can be selected at checkout.
 */
export interface Address {
  id: string;
  user_id: string;
  street: string;
  city: string;
  state: string | null;
  postal_code: string;
  country: string;
  type: string;
  place_id: string | null;
  is_validated: boolean;
}

/** Create payload for `POST /address/users/me/addresses` (`AddressMeCreate`). */
export interface AddressInput {
  street: string;
  city: string;
  state?: string | null;
  postal_code: string;
  country: string;
  type: AddressType;
  /**
   * Geographic zone (island…) of the address. Omit to let the backend deduce
   * it from country + postal code; set it only for an explicit manual choice.
   */
  place_id?: string | null;
}

interface AddressesResponse {
  data: Address[];
  count: number;
}

export async function listMyAddresses(): Promise<Address[]> {
  const { data } = await api.get<AddressesResponse>('/address/users/me/addresses');
  return data.data;
}

export async function createMyAddress(payload: AddressInput): Promise<Address> {
  const { data } = await api.post<Address>('/address/users/me/addresses', payload);
  return data;
}

export async function updateMyAddress(
  id: string,
  payload: Partial<AddressInput>,
): Promise<Address> {
  const { data } = await api.patch<Address>(`/address/users/me/addresses/${id}`, payload);
  return data;
}

export async function deleteMyAddress(id: string): Promise<void> {
  await api.delete(`/address/users/me/addresses/${id}`);
}

// ---------------------------------------------------------------------------
// Geographic zones (island deduction from postal code, manual fallback)
// ---------------------------------------------------------------------------

export interface PlaceSummary {
  id: string;
  name: string;
  type: string;
  code: string | null;
}

export interface ResolvePostalResponse {
  place: PlaceSummary | null;
  /** Parent chain of the resolved place, nearest first (île → archipel → pays). */
  ancestors: PlaceSummary[];
}

/** Deduce the delivery zone (island…) from an exact postal code. */
export async function resolvePostalZone(
  country: string,
  postalCode: string,
): Promise<ResolvePostalResponse> {
  const { data } = await api.get<ResolvePostalResponse>('/place/geo/resolve-postal', {
    params: { country, postal_code: postalCode },
  });
  return data;
}

export interface PlaceTreeNode {
  id: string;
  name: string;
  type: string;
  code: string | null;
  children: PlaceTreeNode[];
}

/** Geographic zone tree of a country (empty when none is defined). */
export async function getGeoTree(country: string): Promise<PlaceTreeNode[]> {
  const { data } = await api.get<{ roots: PlaceTreeNode[] }>('/place/geo/tree', {
    params: { country },
  });
  return data.roots;
}
