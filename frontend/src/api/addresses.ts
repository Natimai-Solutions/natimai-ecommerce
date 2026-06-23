import { api } from 'src/boot/api'

/** Allowed address types (backend `validate_address_type`). */
export type AddressType = 'billing' | 'shipping' | 'other'

/**
 * Address as returned by the backend (`AddressPublic`).
 *
 * `is_validated` is server-managed: a freshly created address starts at
 * `false` and is flipped by an admin before it can be selected at checkout.
 */
export interface Address {
  id: string
  user_id: string
  street: string
  city: string
  state: string | null
  postal_code: string
  country: string
  type: string
  is_validated: boolean
}

/** Create payload for `POST /address/users/me/addresses` (`AddressMeCreate`). */
export interface AddressInput {
  street: string
  city: string
  state?: string | null
  postal_code: string
  country: string
  type: AddressType
}

interface AddressesResponse {
  data: Address[]
  count: number
}

export async function listMyAddresses(): Promise<Address[]> {
  const { data } = await api.get<AddressesResponse>('/address/users/me/addresses')
  return data.data
}

export async function createMyAddress(payload: AddressInput): Promise<Address> {
  const { data } = await api.post<Address>('/address/users/me/addresses', payload)
  return data
}

export async function updateMyAddress(
  id: string,
  payload: Partial<AddressInput>,
): Promise<Address> {
  const { data } = await api.patch<Address>(`/address/users/me/addresses/${id}`, payload)
  return data
}

export async function deleteMyAddress(id: string): Promise<void> {
  await api.delete(`/address/users/me/addresses/${id}`)
}
