import { labels } from '@/i18n/global';
import { api } from '@/boot/api';

/** A payment awaiting manual/document validation (chèque, virement, BC). */
export interface PendingPayment {
  payment_id: string;
  provider_code: string;
  provider_reference: string | null;
  amount: number;
  currency: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  order_id: string | null;
  /** Numéro lisible (CMD-…) de la commande, quand elle en a un. */
  order_number?: string | null;
  /** True for document-validated providers (purchase order / BC). */
  is_document: boolean;
  /** Σ of the instalments already received on this payment. */
  received_amount?: number;
}

export interface PaymentAttachment {
  id: string;
  payment_id: string;
  filename: string;
  mimetype: string;
  size: number | null;
  document_type: string;
  av_scanned: boolean;
  av_clean: boolean | null;
  av_signature: string | null;
}

interface AttachmentDownload {
  download_url: string;
  expires_in: number;
}

/**
 * Document-validated providers expose an uploaded purchase order. Prefer the
 * server-provided `is_document` flag; this string fallback also covers the
 * `po_*` codes (e.g. `po_public`) and any future `document*` codes.
 */
export function isDocumentProvider(providerCode: string): boolean {
  return providerCode.startsWith('document') || providerCode.startsWith('po_');
}

export async function listPendingValidation(): Promise<PendingPayment[]> {
  const { data } = await api.get<PendingPayment[]>('/admin/payments/pending-validation');
  return data;
}

export async function approvePayment(
  paymentId: string,
  payload: { reference?: string | null; comment?: string | null },
): Promise<void> {
  await api.post(`/admin/payments/${paymentId}/approve`, payload);
}

export async function rejectPayment(paymentId: string, reason: string): Promise<void> {
  await api.post(`/admin/payments/${paymentId}/reject`, { reason });
}

export interface RefundResult {
  payment_id: string;
  fully_refunded: boolean;
  message: string | null;
}

/** Refund a payment — full when `amount` is omitted, partial otherwise. */
export async function refundPayment(
  paymentId: string,
  payload: { amount?: number | null; reason?: string | null },
): Promise<RefundResult> {
  const { data } = await api.post<RefundResult>(`/admin/payments/${paymentId}/refund`, payload);
  return data;
}

export interface CaptureResult {
  payment_id: string;
  payment_status_id: string | null;
  message: string | null;
}

/** Capture an authorised card payment (deferred debit, e.g. at shipment). */
export async function capturePayment(paymentId: string): Promise<CaptureResult> {
  const { data } = await api.post<CaptureResult>(`/admin/payments/${paymentId}/capture`);
  return data;
}

export async function listPaymentAttachments(paymentId: string): Promise<PaymentAttachment[]> {
  const { data } = await api.get<PaymentAttachment[]>(`/admin/payments/${paymentId}/attachments`);
  return data;
}

/**
 * Presigned download URL for an attachment. With LocalFileStorage the URL is
 * built server-side from FRONTEND_HOST (wrong host in a multi-origin setup), so
 * we rebuild it against VITE_API_URL when it targets the internal storage
 * endpoint; S3 presigned URLs are returned verbatim.
 */
export async function getAttachmentDownloadUrl(
  paymentId: string,
  attachmentId: string,
): Promise<string> {
  const { data } = await api.get<AttachmentDownload>(
    `/admin/payments/${paymentId}/attachments/${attachmentId}/download`,
  );
  return resolveStorageUrl(data.download_url);
}

function resolveStorageUrl(url: string): string {
  try {
    const parsed = new URL(url);
    if (parsed.pathname.includes('/internal/storage/')) {
      const base = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');
      return `${base}${parsed.pathname}${parsed.search}`;
    }
  } catch {
    // Relative/invalid URL — return as-is.
  }
  return url;
}

// --- Versements reçus sur un paiement manuel (espèces, chèque, virement) ---

export type ReceiptMethod = 'cash' | 'check' | 'transfer' | 'card' | 'other';

export const RECEIPT_METHOD_LABELS: Record<ReceiptMethod, string> = labels({
  cash: 'api.receipt_method.cash',
  check: 'api.receipt_method.check',
  transfer: 'api.receipt_method.transfer',
  card: 'api.receipt_method.card',
  other: 'api.receipt_method.other',
});

export interface PaymentReceipt {
  id: string;
  payment_id: string;
  order_id: string | null;
  amount: string;
  currency: string;
  received_at: string;
  method: ReceiptMethod;
  reference: string | null;
  note: string | null;
  is_active: boolean;
  cancelled_at: string | null;
  cancel_reason: string | null;
}

export interface ReceiptInput {
  amount: number;
  received_at?: string | null;
  method?: ReceiptMethod | null;
  reference?: string | null;
  note?: string | null;
}

export interface ReceiptResult {
  receipt: PaymentReceipt;
  payment_id: string;
  received_amount: string;
  remaining_amount: string;
  payment_settled: boolean;
}

/** Record an instalment; the one that reaches the amount settles the payment. */
export async function recordReceipt(
  paymentId: string,
  input: ReceiptInput,
): Promise<ReceiptResult> {
  const { data } = await api.post<ReceiptResult>(`/admin/payments/${paymentId}/receipts`, input);
  return data;
}

/** Cancel an instalment of a pending payment (bounced cheque, cash handed back). */
export async function cancelReceipt(receiptId: string, reason: string): Promise<PaymentReceipt> {
  const { data } = await api.post<PaymentReceipt>(`/admin/payments/receipts/${receiptId}/cancel`, {
    reason,
  });
  return data;
}

/** Money handed over at the office for the part of the order now due. */
export async function recordCounterPayment(
  orderId: string,
  input: ReceiptInput & { method: 'cash' | 'check' | 'transfer' },
): Promise<ReceiptResult> {
  const { data } = await api.post<ReceiptResult>(`/admin/orders/${orderId}/payments`, input);
  return data;
}
