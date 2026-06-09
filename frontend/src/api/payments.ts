import { api } from 'src/boot/api'

export interface PaymentMethod {
  id: string
  name: string
  description: string | null
  fee: string
  provider_code: string
  requires_admin_validation: boolean
  requires_document_upload: boolean
  sort_order: number
}

export interface PaymentMethodsResponse {
  data: PaymentMethod[]
  count: number
}

export interface InitiatePaymentRequest {
  payment_method_id: string
  amount: string
  currency: string
  order_id?: string | null
  return_url?: string | null
}

export interface InitiatePaymentResponse {
  payment_id: string
  provider_code: string
  provider_reference: string | null
  form_token: string | null
  server_url: string | null
  public_key: string | null
  redirect_url: string | null
  instructions: string | null
}

export interface PaymentStatusResponse {
  payment_id: string
  status_name: string | null
  is_terminal: boolean
  provider_code: string | null
  amount: string
  currency: string
  order_id: string | null
}

export async function listPaymentMethods(): Promise<PaymentMethod[]> {
  const response = await api.get<PaymentMethodsResponse>('/payment_method')
  return response.data.data
}

/**
 * Payment methods eligible for the authenticated user, filtered by their price
 * group and (optionally) the current cart total against each method's
 * `max_amount`. Requires authentication. Returns a bare array.
 */
export async function listMyPaymentMethods(cartTotal?: number): Promise<PaymentMethod[]> {
  const response = await api.get<PaymentMethod[]>('/payments/me/methods', {
    params: cartTotal != null ? { cart_total: cartTotal } : {},
  })
  return response.data
}

export async function initiatePayment(
  data: InitiatePaymentRequest,
): Promise<InitiatePaymentResponse> {
  const response = await api.post<InitiatePaymentResponse>('/payments/initiate', data)
  return response.data
}

export async function getMyPaymentStatus(paymentId: string): Promise<PaymentStatusResponse> {
  const response = await api.get<PaymentStatusResponse>(`/payments/me/${paymentId}`)
  return response.data
}
