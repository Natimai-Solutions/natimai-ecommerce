import type { components } from '@app/api-types';
import { api } from 'src/boot/api';

export type CartDetailPublic = components['schemas']['CartDetailPublic'];
type CartItemAddRequest = components['schemas']['CartItemAddRequest'];
type CartItemQuantityUpdateRequest = components['schemas']['CartItemQuantityUpdateRequest'];
type CartReplaceRequest = components['schemas']['CartReplaceRequest'];
type QuoteRequestSubmit = components['schemas']['QuoteRequestSubmit'];
type QuoteRequestResponse = components['schemas']['QuoteRequestResponse'];
// The generated schema lags the backend additions for the single-payment flow
// (payment_method_id/return_url on the request; provider fields on the response).
// Omit the fields we widen so these overrides win over the generated (narrower)
// declarations instead of being intersected with them.
type CheckoutRequest = Omit<
  components['schemas']['CheckoutRequest'],
  'payment_method_id' | 'return_url' | 'delivery_type'
> & {
  /** Initiate this method's provider in the same call (single-payment flow). */
  payment_method_id?: string | null;
  return_url?: string | null;
  /** Last-leg delivery mode: pickup | home_delivery | air_freight. */
  delivery_type?: string | null;
  /** Id of the saved shipping address to link (avoids duplicate creation). */
  shipping_address_id?: string | null;
  /** full | deposit (see DepositTerms). */
  payment_plan?: string | null;
  /** Order an issued quote at its prices and delivery fee. */
  quote_request_id?: string | null;
};
type CheckoutResponse = components['schemas']['CheckoutResponse'] & {
  provider_code?: string | null;
  provider_reference?: string | null;
  form_token?: string | null;
  server_url?: string | null;
  public_key?: string | null;
  redirect_url?: string | null;
  instructions?: string | null;
};

export interface GuestQuoteRequestItem {
  product_id?: string | null;
  product_name: string;
  product_image_url?: string | null;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface GuestQuoteRequestSubmit {
  customer_email: string;
  customer_name?: string | null;
  customer_phone?: string | null;
  shipping_address?: string | null;
  notes?: string | null;
  currency?: string;
  items: GuestQuoteRequestItem[];
}

export interface GuestQuoteRequestResponse {
  email_delivered: boolean;
  message: string;
}

export async function getMyCart(): Promise<CartDetailPublic> {
  const { data } = await api.get<CartDetailPublic>('/cart/me');
  return data;
}

export async function addCartItem(payload: CartItemAddRequest): Promise<CartDetailPublic> {
  const { data } = await api.post<CartDetailPublic>('/cart/items', payload);
  return data;
}

export async function updateCartItemQuantity(
  itemId: string,
  payload: CartItemQuantityUpdateRequest,
): Promise<CartDetailPublic> {
  const { data } = await api.patch<CartDetailPublic>(`/cart/items/${itemId}`, payload);
  return data;
}

export async function removeCartItem(itemId: string): Promise<CartDetailPublic> {
  const { data } = await api.delete<CartDetailPublic>(`/cart/items/${itemId}`);
  return data;
}

/**
 * Install the whole cart content in one transaction.
 *
 * Replaces the old clear-then-add-each-line sequence, which was not atomic:
 * a failure midway left a truncated backend cart that the checkout then
 * ordered as if it were complete.
 */
export async function replaceMyCartItems(payload: CartReplaceRequest): Promise<CartDetailPublic> {
  const { data } = await api.put<CartDetailPublic>('/cart/items', payload);
  return data;
}

export async function clearMyCart(): Promise<CartDetailPublic> {
  const { data } = await api.delete<CartDetailPublic>('/cart/items');
  return data;
}

/**
 * Turn the authenticated user's backend cart into an order (creates the order +
 * order lines + a pending payment, and empties the backend cart). The storefront
 * cart is client-side, so its items must be synced to the backend first.
 */
export async function checkoutMyCart(payload: CheckoutRequest): Promise<CheckoutResponse> {
  const { data } = await api.post<CheckoutResponse>('/cart/checkout', payload);
  return data;
}

export interface LastLegOption {
  delivery_type: string;
  /** Customer-facing label (route's customer_label); falls back to the mode key. */
  label: string | null;
  amount: string;
  currency: string;
  eta_days: number | null;
  route_name: string | null;
}
interface LastLegOptionsResponse {
  currency: string;
  options: LastLegOption[];
  /** Frais de dédouanement facturés une fois par expédition ('0' si aucun). */
  customs_declaration_fee: string;
}

/** Priced last-leg delivery options for the current cart (shown at checkout).
 *
 * `addressId` filters the modes to those serving the address' destination
 * (île → archipel → pays) — always-available modes (retrait boutique) are
 * returned in every case.
 */
export async function getLastLegOptions(
  addressId?: string | null,
): Promise<LastLegOptionsResponse> {
  const { data } = await api.get<LastLegOptionsResponse>('/cart/me/last-leg-options', {
    params: addressId ? { address_id: addressId } : {},
  });
  return data;
}

/** Deposit part of a quote / checkout response (`DepositTerms`). */
export interface DepositTerms {
  /** full | deposit — the plan the backend settled on. */
  payment_plan: string;
  deposit_available: boolean;
  deposit_required: boolean;
  deposit_pct: string | null;
  deposit_fee_amount: string;
  /** Charged now on a deposit order. */
  deposit_amount: string;
  /** Asked for at reception. */
  balance_amount: string;
}

export interface CheckoutQuote extends DepositTerms {
  currency: string;
  subtotal_amount: string;
  /** Livraison (tronçon choisi) + frais de dédouanement. */
  shipping_fee_amount: string;
  customs_declaration_fee: string;
  payment_fee_amount: string;
  total_fees_amount: string;
  /** Montant qui sera débité — la seule source de vérité du récapitulatif. */
  total_amount: string;
  delivery_type: string | null;
  shipping_eta_days: number | null;
  free_shipping_applied: boolean;
}

/** What POST /cart/checkout will bill for the backend cart and these choices.
 *
 * Same computation as the checkout: the recap shows the amount debited. The
 * backend cart must be in sync (see replaceMyCartItems) for the quote to
 * cover the storefront cart.
 */
export async function getCheckoutQuote(params: {
  addressId?: string | null;
  deliveryType?: string | null;
  paymentMethodId?: string | null;
  paymentPlan?: string | null;
  quoteRequestId?: string | null;
}): Promise<CheckoutQuote> {
  const query: Record<string, string> = {};
  if (params.addressId) query.address_id = params.addressId;
  if (params.deliveryType) query.delivery_type = params.deliveryType;
  if (params.paymentMethodId) query.payment_method_id = params.paymentMethodId;
  if (params.paymentPlan) query.payment_plan = params.paymentPlan;
  if (params.quoteRequestId) query.quote_request_id = params.quoteRequestId;
  const { data } = await api.get<CheckoutQuote>('/cart/me/checkout-quote', { params: query });
  return data;
}

export async function createQuoteRequest(
  payload: QuoteRequestSubmit,
): Promise<QuoteRequestResponse> {
  const { data } = await api.post<QuoteRequestResponse>('/cart/quote-request', payload);
  return data;
}

export async function createGuestQuoteRequest(
  payload: GuestQuoteRequestSubmit,
): Promise<GuestQuoteRequestResponse> {
  const { data } = await api.post<GuestQuoteRequestResponse>('/cart/guest-quote-request', payload);
  return data;
}
