import { api } from 'src/boot/api';

/** Cycle de vie d'une demande, aligné sur QuoteRequestStatus côté backend. */
export type QuoteRequestStatus =
  | 'requested'
  | 'email_failed'
  | 'in_progress'
  | 'quoted'
  | 'won'
  | 'lost'
  | 'cancelled';

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
}

/** Une ligne du panier figé au moment de la demande. */
export interface QuoteRequestItem {
  product_name?: string | null;
  quantity?: string | null;
  unit_price?: string | null;
  line_total?: string | null;
  image_url?: string | null;
}

export interface AdminQuoteRequestDetail extends AdminQuoteRequestListItem {
  shipping_address: string | null;
  notes: string | null;
  admin_comment: string | null;
  items: QuoteRequestItem[];
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
