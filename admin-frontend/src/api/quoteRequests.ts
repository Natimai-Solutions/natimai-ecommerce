import { api } from '@/boot/api';

/** Cycle de vie d'une demande, aligné sur QuoteRequestStatus côté backend. */
export type QuoteRequestStatus =
  'requested' | 'email_failed' | 'in_progress' | 'quoted' | 'won' | 'lost' | 'cancelled';

export interface AdminQuoteRequestListItem {
  quote_request_id: string;
  created_at: string | null;
  email: string;
  full_name: string | null;
  phone: string | null;
  status: QuoteRequestStatus;
  /** Faux pour un visiteur non connecté — il n'a pas de compte à rappeler. */
  is_registered_customer: boolean;
  item_count: number;
  currency: string | null;
  subtotal_amount: string | null;
  handled_at: string | null;
  /** DEV-AAAA-NNNNN une fois le devis émis. */
  quote_number: string | null;
}

/** Une ligne du panier figé au moment de la demande. */
export interface QuoteRequestItem {
  product_name?: string | null;
  quantity?: string | null;
  unit_price?: string | null;
  line_total?: string | null;
  image_url?: string | null;
}

/** Une ligne du devis émis (ou proposée pour l'émission). */
export interface QuoteLine {
  product_id: string | null;
  product_name: string;
  quantity: number;
  unit_price: string;
}

export interface AdminQuoteRequestDetail extends AdminQuoteRequestListItem {
  shipping_address: string | null;
  notes: string | null;
  admin_comment: string | null;
  items: QuoteRequestItem[];
  quoted_at: string | null;
  valid_until: string | null;
  /** Commande créée depuis le devis (statut won). */
  order_id: string | null;
  /** Le devis émis, figé (lignes, livraison, totaux, message). */
  quote_snapshot: {
    lines: QuoteLine[];
    shipping_fee_amount: string;
    subtotal_amount: string;
    total_amount: string;
    customer_message: string;
    valid_until: string;
  } | null;
  /** Lignes pré-remplies : celles du devis émis, sinon le panier de la demande. */
  proposed_lines: QuoteLine[];
}

export interface QuoteIssueBody {
  lines: QuoteLine[];
  shipping_fee_amount: string;
  valid_until?: string | null;
  customer_message?: string | null;
  send_email: boolean;
}

export interface QuoteIssueResponse extends AdminQuoteRequestDetail {
  email_sent: boolean;
}

/** Émettre (ou ré-émettre) le devis : numéro DEV, PDF, e-mail au client. */
export async function issueQuote(id: string, body: QuoteIssueBody): Promise<QuoteIssueResponse> {
  const { data } = await api.post<QuoteIssueResponse>(`/admin/quote-requests/${id}/issue`, body);
  return data;
}

export async function downloadQuotePdf(id: string, quoteNumber: string | null): Promise<void> {
  const { data } = await api.get<Blob>(`/admin/quote-requests/${id}/pdf`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${quoteNumber ?? 'devis'}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

export interface QuoteRequestFilters {
  status?: QuoteRequestStatus | undefined;
  search?: string | undefined;
  openOnly?: boolean | undefined;
}

export async function listQuoteRequests(
  filters: QuoteRequestFilters = {},
): Promise<AdminQuoteRequestListItem[]> {
  const params: Record<string, string | boolean> = {};
  if (filters.status) params.status = filters.status;
  const search = filters.search?.trim();
  if (search) params.search = search;
  if (filters.openOnly) params.open_only = true;

  const { data } = await api.get<AdminQuoteRequestListItem[]>('/admin/quote-requests', {
    params,
  });
  return data;
}

export async function getQuoteRequest(id: string): Promise<AdminQuoteRequestDetail> {
  const { data } = await api.get<AdminQuoteRequestDetail>(`/admin/quote-requests/${id}`);
  return data;
}

export async function updateQuoteRequest(
  id: string,
  body: { status?: QuoteRequestStatus; admin_comment?: string },
): Promise<AdminQuoteRequestDetail> {
  const { data } = await api.patch<AdminQuoteRequestDetail>(`/admin/quote-requests/${id}`, body);
  return data;
}

const STATUS_LABELS: Record<QuoteRequestStatus, string> = {
  requested: 'Reçue',
  email_failed: 'Email non transmis',
  in_progress: 'En cours',
  quoted: 'Devis envoyé',
  won: 'Gagnée',
  lost: 'Perdue',
  cancelled: 'Annulée',
};

export function quoteStatusLabel(status: QuoteRequestStatus): string {
  return STATUS_LABELS[status] ?? status;
}

export function quoteStatusColor(status: QuoteRequestStatus): string {
  // `email_failed` en rouge : c'est la demande que personne n'a vue passer,
  // celle qu'il faut rattraper en priorité.
  if (status === 'email_failed') return 'negative';
  if (status === 'won') return 'positive';
  if (status === 'lost' || status === 'cancelled') return 'grey-7';
  if (status === 'quoted') return 'primary';
  return 'orange';
}

/** Statuts proposés dans le sélecteur de suivi. */
export const QUOTE_STATUS_OPTIONS: { label: string; value: QuoteRequestStatus }[] = (
  Object.keys(STATUS_LABELS) as QuoteRequestStatus[]
).map((value) => ({ label: STATUS_LABELS[value], value }));
