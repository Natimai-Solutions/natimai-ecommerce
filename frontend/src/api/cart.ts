import type { components } from '@app/api-types'
import { api } from 'src/boot/api'

type CartDetailPublic = components['schemas']['CartDetailPublic']
type CartItemAddRequest = components['schemas']['CartItemAddRequest']
type CartItemQuantityUpdateRequest = components['schemas']['CartItemQuantityUpdateRequest']
type QuoteRequestSubmit = components['schemas']['QuoteRequestSubmit']
type QuoteRequestResponse = components['schemas']['QuoteRequestResponse']

export interface GuestQuoteRequestItem {
  product_id?: string | null
  product_name: string
  product_image_url?: string | null
  quantity: number
  unit_price: string
  line_total: string
}

export interface GuestQuoteRequestSubmit {
  customer_email: string
  customer_name?: string | null
  customer_phone?: string | null
  shipping_address?: string | null
  notes?: string | null
  currency?: string
  items: GuestQuoteRequestItem[]
}

export interface GuestQuoteRequestResponse {
  email_delivered: boolean
  message: string
}

export async function getMyCart(): Promise<CartDetailPublic> {
  const { data } = await api.get<CartDetailPublic>('/cart/me')
  return data
}

export async function addCartItem(payload: CartItemAddRequest): Promise<CartDetailPublic> {
  const { data } = await api.post<CartDetailPublic>('/cart/items', payload)
  return data
}

export async function updateCartItemQuantity(
  itemId: string,
  payload: CartItemQuantityUpdateRequest,
): Promise<CartDetailPublic> {
  const { data } = await api.patch<CartDetailPublic>(`/cart/items/${itemId}`, payload)
  return data
}

export async function removeCartItem(itemId: string): Promise<CartDetailPublic> {
  const { data } = await api.delete<CartDetailPublic>(`/cart/items/${itemId}`)
  return data
}

export async function clearMyCart(): Promise<CartDetailPublic> {
  const { data } = await api.delete<CartDetailPublic>('/cart/items')
  return data
}

export async function createQuoteRequest(
  payload: QuoteRequestSubmit,
): Promise<QuoteRequestResponse> {
  const { data } = await api.post<QuoteRequestResponse>('/cart/quote-request', payload)
  return data
}

export async function createGuestQuoteRequest(
  payload: GuestQuoteRequestSubmit,
): Promise<GuestQuoteRequestResponse> {
  const { data } = await api.post<GuestQuoteRequestResponse>('/cart/guest-quote-request', payload)
  return data
}
