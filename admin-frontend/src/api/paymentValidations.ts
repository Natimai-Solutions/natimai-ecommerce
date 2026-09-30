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
  /** True for document-validated providers (purchase order / BC). */
  is_document: boolean;
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
