import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { components } from '@app/api-types';
import {
  attachGuestCartEmail,
  clearGuestCart,
  clearMyCart,
  createGuestQuoteRequest,
  mergeGuestCart,
  reorderIntoCart,
  replaceGuestCartItems,
  replaceMyCartItems,
  type CartDetailPublic,
  type GuestQuoteRequestResponse,
} from '@/api/cart';
import { useAuthStore } from '@/stores/auth';
import { getProductById } from '@/api/products';
import { gt } from '@/i18n/global';

type ProductPublic = components['schemas']['ProductPublic'];

type LocalCartItem = {
  id: string;
  product_id: string;
  quantity: number;
  unit_price: string;
  line_total: string;
};

type LocalCart = {
  currency: string;
  total_amount: string;
  is_checked_out: boolean;
  items: LocalCartItem[];
};

type CartItemWithProduct = {
  item: LocalCartItem;
  product: ProductPublic | null;
};

const STORAGE_KEY = 'frontend.cart.v1';
/** The visitor's server-cart token (R8 / U9); removed once merged at sign-in. */
const TOKEN_KEY = 'frontend.cart.token.v1';
/** Debounce of the server mirror: one PUT per burst of clicks, not per click. */
const MIRROR_DELAY_MS = 1500;

export const useCartStore = defineStore('cart', () => {
  const cart = ref<LocalCart>(emptyCart());
  const productsById = ref<Record<string, ProductPublic>>({});
  const loading = ref(false);
  const mutating = ref(false);
  const quoteSubmitting = ref(false);
  const error = ref<string | null>(null);
  const requiresAuth = ref(false); // kept for UI compatibility; guest mode does not require auth
  const quoteMessage = ref<string | null>(null);
  const quoteEmailDelivered = ref<boolean | null>(null);

  const items = computed(() => cart.value.items);

  /**
   * Mirror the local cart into its server cart: the account's when logged
   * in, the visitor's (identified by a random token the browser keeps, R8 /
   * U9) otherwise.
   *
   * The cart lives in the browser; the server only saw it at checkout, so a
   * customer who added items and left was invisible to the abandoned-cart
   * reminder. Best effort and silent: a refused line (product gone) must not
   * disturb the local cart, the checkout re-validates everything anyway.
   */
  let mirrorTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleServerMirror() {
    if (typeof window === 'undefined') return;
    if (mirrorTimer !== null) clearTimeout(mirrorTimer);
    mirrorTimer = setTimeout(() => {
      mirrorTimer = null;
      void mirrorToServer();
    }, MIRROR_DELAY_MS);
  }
  async function mirrorToServer() {
    const auth = useAuthStore();
    const payload = {
      items: cart.value.items.map((item) => ({
        product_id: item.product_id,
        quantity: item.quantity,
      })),
    };
    try {
      if (auth.isAuthenticated) {
        if (payload.items.length === 0) await clearMyCart();
        else await replaceMyCartItems(payload);
        return;
      }
      // A visitor: no token and nothing to send means no server cart at all.
      const token = guestToken(payload.items.length > 0);
      if (!token) return;
      if (payload.items.length === 0) await clearGuestCart(token);
      else await replaceGuestCartItems(token, payload);
    } catch {
      // ignored on purpose: the local cart is the source of truth until checkout
    }
  }

  /**
   * At sign-in (R8 / U9): fold the visitor's server cart into the account's
   * and adopt the result — the account's lines from another device join the
   * ones added here. Silent on failure: the local cart then simply mirrors
   * itself as before.
   */
  async function mergeAfterLogin(): Promise<void> {
    const token = guestToken(false);
    if (!token) return;
    try {
      const merged = await mergeGuestCart(token);
      adoptServerCart(merged);
      forgetGuestToken();
    } catch {
      scheduleServerMirror();
    }
  }

  /**
   * « Re-commander » : the server adds the order's articles to the account's
   * cart (today's prices), which then becomes the local cart. Returns how
   * many articles came back and how many are no longer sold.
   */
  async function reorder(orderId: string): Promise<{ added: number; skipped: number }> {
    const result = await reorderIntoCart(orderId);
    adoptServerCart(result.cart);
    return { added: result.added, skipped: result.skipped };
  }

  /** The e-mail a visitor typed (stock alert, quote): kept on their server cart. */
  async function attachGuestEmail(email: string): Promise<void> {
    const auth = useAuthStore();
    if (auth.isAuthenticated || cart.value.items.length === 0) return;
    const token = guestToken(true);
    if (!token) return;
    try {
      await attachGuestCartEmail(token, email.trim().toLowerCase());
    } catch {
      // best effort: a reminder is a nicety, not a promise
    }
  }

  function adoptServerCart(detail: CartDetailPublic) {
    cart.value = {
      currency: detail.currency || cart.value.currency,
      total_amount: '0.00',
      is_checked_out: false,
      items: (detail.items ?? []).map((item) => ({
        id: item.product_id,
        product_id: item.product_id,
        quantity: item.quantity,
        unit_price: toMoneyString(parseMoney(item.unit_price)),
        line_total: toMoneyString(parseMoney(item.unit_price) * item.quantity),
      })),
    };
    recomputeTotals();
    persistCart(cart.value);
    void hydrateProducts(cart.value.items);
  }

  const totalItems = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0));

  const totalAmount = computed(() => {
    const raw = cart.value.total_amount;
    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) ? parsed : 0;
  });

  const detailedItems = computed<CartItemWithProduct[]>(() =>
    items.value.map((item) => ({
      item,
      product: productsById.value[item.product_id] ?? null,
    })),
  );

  function seedProduct(product: ProductPublic) {
    productsById.value[product.id] = product;
  }

  async function loadCart() {
    loading.value = true;
    error.value = null;
    try {
      cart.value = readPersistedCart();
      recomputeTotals();
      await hydrateProducts(cart.value.items);
      requiresAuth.value = false;
    } catch (err) {
      handleError(err, gt('stores.cart_load'));
    } finally {
      loading.value = false;
    }
  }

  async function addItem(productId: string, quantity = 1, seed?: ProductPublic) {
    mutating.value = true;
    error.value = null;
    quoteMessage.value = null;
    if (seed) seedProduct(seed);

    try {
      const normalizedQuantity = Math.max(1, Math.floor(quantity));
      let product = seed ?? productsById.value[productId] ?? null;
      if (!product) {
        product = await getProductById(productId);
      }
      seedProduct(product);

      const unitPrice = toMoneyString(parseMoney(product.base_price));
      const existing = cart.value.items.find((item) => item.product_id === productId);

      if (existing) {
        existing.quantity += normalizedQuantity;
        existing.unit_price = unitPrice;
      } else {
        cart.value.items.push({
          id: productId,
          product_id: productId,
          quantity: normalizedQuantity,
          unit_price: unitPrice,
          line_total: toMoneyString(parseMoney(unitPrice) * normalizedQuantity),
        });
      }

      recomputeTotals();
      persistCart(cart.value);
      scheduleServerMirror();
      requiresAuth.value = false;
      return true;
    } catch (err) {
      handleError(err, "Impossible d'ajouter au panier");
      return false;
    } finally {
      mutating.value = false;
    }
  }

  function updateItemQuantity(itemId: string, quantity: number) {
    mutating.value = true;
    error.value = null;
    quoteMessage.value = null;
    try {
      const nextQuantity = Math.max(1, Math.floor(quantity));
      const item = cart.value.items.find((entry) => entry.id === itemId);
      if (!item) {
        error.value = gt('stores.cart_item_missing');
        return false;
      }

      item.quantity = nextQuantity;
      recomputeTotals();
      persistCart(cart.value);
      scheduleServerMirror();
      requiresAuth.value = false;
      return true;
    } catch (err) {
      handleError(err, gt('stores.cart_qty'));
      return false;
    } finally {
      mutating.value = false;
    }
  }

  function removeItem(itemId: string) {
    mutating.value = true;
    error.value = null;
    quoteMessage.value = null;
    try {
      cart.value.items = cart.value.items.filter((entry) => entry.id !== itemId);
      recomputeTotals();
      persistCart(cart.value);
      scheduleServerMirror();
      requiresAuth.value = false;
      return true;
    } catch (err) {
      handleError(err, gt('stores.cart_remove'));
      return false;
    } finally {
      mutating.value = false;
    }
  }

  function clearCart() {
    mutating.value = true;
    error.value = null;
    quoteMessage.value = null;
    try {
      cart.value = emptyCart(cart.value.currency);
      persistCart(cart.value);
      scheduleServerMirror();
      requiresAuth.value = false;
      return true;
    } catch (err) {
      handleError(err, gt('stores.cart_clear'));
      return false;
    } finally {
      mutating.value = false;
    }
  }

  async function sendQuoteByEmail(payload: {
    customer_email: string;
    customer_name?: string | null;
    customer_phone?: string | null;
    shipping_address?: string | null;
    notes?: string | null;
    /** Captcha headers of the form (`useTurnstile().headers()`). */
    headers?: Record<string, string>;
  }): Promise<GuestQuoteRequestResponse | null> {
    quoteSubmitting.value = true;
    error.value = null;
    quoteMessage.value = null;
    quoteEmailDelivered.value = null;

    try {
      const customerEmail = payload.customer_email.trim().toLowerCase();
      if (!isValidEmail(customerEmail)) {
        error.value = gt('stores.cart_email');
        return null;
      }

      if (cart.value.items.length === 0) {
        error.value = gt('stores.cart_empty');
        return null;
      }

      const response = await createGuestQuoteRequest(
        {
          customer_email: customerEmail,
          customer_name: payload.customer_name ?? null,
          customer_phone: payload.customer_phone ?? null,
          shipping_address: payload.shipping_address ?? null,
          notes: payload.notes ?? null,
          currency: cart.value.currency,
          items: detailedItems.value.map((entry) => ({
            product_id: entry.item.product_id,
            product_name: entry.product?.name ?? `Produit ${entry.item.product_id.slice(0, 8)}`,
            product_image_url:
              entry.product?.image_url ?? entry.product?.supplier_image_url ?? null,
            quantity: entry.item.quantity,
            unit_price: entry.item.unit_price,
            line_total: entry.item.line_total,
          })),
        },
        payload.headers ?? {},
      );

      quoteMessage.value = response.message;
      quoteEmailDelivered.value = response.email_delivered;
      requiresAuth.value = false;
      void attachGuestEmail(customerEmail);
      return response;
    } catch (err) {
      handleError(err, "Impossible d'envoyer la demande de devis");
      return null;
    } finally {
      quoteSubmitting.value = false;
    }
  }

  function clearMessages() {
    error.value = null;
    quoteMessage.value = null;
    quoteEmailDelivered.value = null;
  }

  async function hydrateProducts(cartItems: LocalCartItem[]) {
    const missingIds = cartItems
      .map((item) => item.product_id)
      .filter((id) => !(id in productsById.value));

    if (missingIds.length === 0) return;

    const loaded = await Promise.all(
      missingIds.map(async (id) => {
        try {
          const product = await getProductById(id);
          return { id, product };
        } catch {
          return { id, product: null };
        }
      }),
    );

    for (const entry of loaded) {
      if (entry.product) {
        productsById.value[entry.id] = entry.product;
      }
    }
  }

  /**
   * Adopt the server's prices after a `cart.price.changed` checkout refusal.
   *
   * The local cart snapshots the price at the moment the line is added, but
   * the catalog moves under it (supplier sync, FX, customs). The backend
   * refuses to bill a stale price and returns the current one per line; the
   * customer must see that new price before confirming again.
   *
   * Returns true when at least one line actually moved.
   */
  function applyServerPrices(updates: { product_id: string; current_unit_price: string }[]) {
    let changed = false;
    for (const update of updates) {
      const item = cart.value.items.find((entry) => entry.product_id === update.product_id);
      if (!item) continue;
      const nextPrice = toMoneyString(parseMoney(update.current_unit_price));
      if (item.unit_price === nextPrice) continue;
      item.unit_price = nextPrice;
      changed = true;
    }
    if (changed) {
      recomputeTotals();
      persistCart(cart.value);
    }
    return changed;
  }

  function recomputeTotals() {
    for (const item of cart.value.items) {
      item.line_total = toMoneyString(parseMoney(item.unit_price) * item.quantity);
    }

    const subtotal = cart.value.items.reduce((sum, item) => sum + parseMoney(item.line_total), 0);
    cart.value.total_amount = toMoneyString(subtotal);
  }

  function handleError(err: unknown, fallback: string) {
    error.value = extractErrorMessage(err, fallback);
  }

  return {
    cart,
    loading,
    mutating,
    mergeAfterLogin,
    reorder,
    attachGuestEmail,
    quoteSubmitting,
    error,
    requiresAuth,
    quoteMessage,
    quoteEmailDelivered,
    items,
    detailedItems,
    totalItems,
    totalAmount,
    seedProduct,
    loadCart,
    addItem,
    updateItemQuantity,
    removeItem,
    clearCart,
    applyServerPrices,
    sendQuoteByEmail,
    clearMessages,
  };
});

/** The visitor's cart token, if they have a server cart (read only). */
export function currentGuestToken(): string | null {
  return guestToken(false);
}

/** The visitor's cart token; created on demand when `create` is true. */
function guestToken(create: boolean): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const existing = localStorage.getItem(TOKEN_KEY);
    if (existing) return existing;
    if (!create) return null;
    const token = `g-${crypto.randomUUID().replace(/-/g, '')}-${Date.now().toString(36)}`;
    localStorage.setItem(TOKEN_KEY, token);
    return token;
  } catch {
    return null;
  }
}

function forgetGuestToken(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable: nothing kept, nothing to forget
  }
}

function emptyCart(currency = 'XPF'): LocalCart {
  return {
    currency,
    total_amount: '0.00',
    is_checked_out: false,
    items: [],
  };
}

function readPersistedCart(): LocalCart {
  if (typeof window === 'undefined') return emptyCart();

  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return emptyCart();

  try {
    const parsed = JSON.parse(raw) as {
      currency?: unknown;
      items?: unknown;
    };

    const currency =
      typeof parsed.currency === 'string' && parsed.currency.trim().length > 0
        ? parsed.currency.trim().toUpperCase()
        : 'XPF';

    const items = Array.isArray(parsed.items)
      ? parsed.items
          .map((item) => toLocalCartItem(item))
          .filter((item): item is LocalCartItem => item !== null)
      : [];

    return {
      currency,
      total_amount: '0.00',
      is_checked_out: false,
      items,
    };
  } catch {
    return emptyCart();
  }
}

function persistCart(cart: LocalCart) {
  if (typeof window === 'undefined') return;

  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      currency: cart.currency,
      items: cart.items,
    }),
  );
}

function toLocalCartItem(value: unknown): LocalCartItem | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as {
    id?: unknown;
    product_id?: unknown;
    quantity?: unknown;
    unit_price?: unknown;
    line_total?: unknown;
  };

  if (typeof item.product_id !== 'string' || item.product_id.trim().length === 0) {
    return null;
  }

  const quantity = typeof item.quantity === 'number' ? Math.max(1, Math.floor(item.quantity)) : 1;

  const unitPrice = toMoneyString(parseMoney(item.unit_price));
  const lineTotal =
    typeof item.line_total === 'string'
      ? toMoneyString(parseMoney(item.line_total))
      : toMoneyString(parseMoney(unitPrice) * quantity);

  return {
    id: typeof item.id === 'string' && item.id.trim().length > 0 ? item.id : item.product_id,
    product_id: item.product_id,
    quantity,
    unit_price: unitPrice,
    line_total: lineTotal,
  };
}

function parseMoney(value: unknown): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === 'string') {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function toMoneyString(value: number): string {
  if (!Number.isFinite(value)) return '0.00';
  return value.toFixed(2);
}

function isValidEmail(value: string): boolean {
  return /^(?:[^\s@]+)@(?:[^\s@]+)\.[^\s@]+$/.test(value);
}

function extractErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const response = (err as { response?: { data?: unknown } }).response;
    const data = response?.data;

    if (typeof data === 'string' && data.trim().length > 0) {
      return data;
    }

    if (typeof data === 'object' && data !== null) {
      const payload = data as {
        detail?: unknown;
        message?: unknown;
        code?: unknown;
      };

      if (typeof payload.message === 'string' && payload.message.trim().length > 0) {
        return payload.message;
      }

      if (typeof payload.detail === 'string' && payload.detail.trim().length > 0) {
        return payload.detail;
      }

      if (typeof payload.detail === 'object' && payload.detail !== null) {
        const detailMessage = (payload.detail as { message?: unknown }).message;
        if (typeof detailMessage === 'string' && detailMessage.trim().length > 0) {
          return detailMessage;
        }
      }

      if (typeof payload.code === 'string' && payload.code.trim().length > 0) {
        return payload.code;
      }
    }
  }

  if (err instanceof Error && err.message.trim().length > 0) {
    return err.message;
  }

  return fallback;
}
