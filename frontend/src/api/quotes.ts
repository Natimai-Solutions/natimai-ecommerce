import { api } from 'src/boot/api';
import type { CartDetailPublic } from 'src/api/cart';

/** A quote request / issued quote of the customer (`MyQuoteItem`). */
export interface MyQuote {
  id: string;
  /** DEV-AAAA-NNNNN once issued, null while the request is being handled. */
  quote_number: string | null;
  status: string;
  created_at: string | null;
  quoted_at: string | null;
  valid_until: string | null;
  currency: string | null;
  total_amount: string | null;
  /** The order created from the quote, once ordered. */
  order_id: string | null;
  /** Issued, in date, not converted, made of catalogue products. */
  can_order: boolean;
}

export const QUOTE_STATUS_LABELS: Record<string, string> = {
  requested: 'Demande reçue',
  email_failed: 'Demande reçue',
  in_progress: 'En cours de traitement',
  quoted: 'Devis émis',
  won: 'Commandé',
  lost: 'Sans suite',
  cancelled: 'Annulé',
};

export async function listMyQuotes(): Promise<MyQuote[]> {
  const { data } = await api.get<MyQuote[]>('/cart/quote-requests/me');
  return data;
}

export async function downloadMyQuotePdf(quote: MyQuote): Promise<void> {
  const response = await api.get<Blob>(`/cart/quote-requests/me/${quote.id}/pdf`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(response.data);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${quote.quote_number ?? 'devis'}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Load the quote into the backend cart at the quoted prices. */
export async function acceptMyQuote(quoteId: string): Promise<CartDetailPublic> {
  const { data } = await api.post<CartDetailPublic>(`/cart/quote-requests/me/${quoteId}/accept`);
  return data;
}
