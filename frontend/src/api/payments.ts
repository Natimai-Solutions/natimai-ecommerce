import { api } from '@/boot/api';

export interface PaymentMethod {
  id: string;
  name: string;
  description: string | null;
  fee: string;
  provider_code: string;
  requires_admin_validation: boolean;
  requires_document_upload: boolean;
  sort_order: number;
  /** false = cannot pay a deposit (the balance stays open to every method). */
  deposit_allowed?: boolean;
}

export interface PaymentMethodsResponse {
  data: PaymentMethod[];
  count: number;
}

export interface InitiatePaymentRequest {
  payment_method_id: string;
  amount: string;
  currency: string;
  order_id?: string | null;
  return_url?: string | null;
}

export interface InitiatePaymentResponse {
  payment_id: string;
  provider_code: string;
  provider_reference: string | null;
  form_token: string | null;
  server_url: string | null;
  public_key: string | null;
  redirect_url: string | null;
  instructions: string | null;
}

export interface PaymentStatusResponse {
  payment_id: string;
  status_name: string | null;
  is_terminal: boolean;
  provider_code: string | null;
  amount: string;
  currency: string;
  order_id: string | null;
}

export async function listPaymentMethods(): Promise<PaymentMethod[]> {
  const response = await api.get<PaymentMethodsResponse>('/payment_method/');
  return response.data.data;
}

/**
 * Payment methods eligible for the authenticated user, filtered by their price
 * group and (optionally) the current cart total against each method's
 * `max_amount`. Requires authentication. Returns a bare array.
 */
export async function listMyPaymentMethods(cartTotal?: number): Promise<PaymentMethod[]> {
  const response = await api.get<PaymentMethod[]>('/payments/me/methods', {
    params: cartTotal != null ? { cart_total: cartTotal } : {},
  });
  return response.data;
}

export async function initiatePayment(
  data: InitiatePaymentRequest,
): Promise<InitiatePaymentResponse> {
  const response = await api.post<InitiatePaymentResponse>('/payments/initiate', data);
  return response.data;
}

export async function getMyPaymentStatus(paymentId: string): Promise<PaymentStatusResponse> {
  const response = await api.get<PaymentStatusResponse>(`/payments/me/${paymentId}`);
  return response.data;
}

/**
 * Finish a payment the customer approved on the provider's page (PayPal): the
 * shop captures it server-side. Idempotent.
 */
export async function confirmMyPayment(paymentId: string): Promise<PaymentStatusResponse> {
  const response = await api.post<PaymentStatusResponse>(`/payments/me/${paymentId}/confirm`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Document-validated payments (Bon de commande): presigned upload flow
// ---------------------------------------------------------------------------

export interface UploadDocumentResponse {
  payment_id: string;
  file_key: string;
  upload_url: string;
  upload_method: string;
  upload_headers: Record<string, string>;
  expires_in: number;
  max_bytes: number;
  allowed_mime: string[];
}

export interface DocumentUploadedResponse {
  payment_id: string;
  attachment_id: string;
  payment_status_id: string | null;
  av_scan: string;
}

/** Step 1: request a presigned URL to upload the purchase-order document. */
export async function issueDocumentUploadUrl(
  paymentId: string,
  payload: { filename: string; mimetype: string; documentType?: string },
): Promise<UploadDocumentResponse> {
  const { data } = await api.post<UploadDocumentResponse>(
    `/payments/${paymentId}/upload-document`,
    {
      filename: payload.filename,
      mimetype: payload.mimetype,
      document_type: payload.documentType ?? 'purchase_order',
    },
  );
  return data;
}

/**
 * Step 2: PUT the raw file bytes to the presigned URL (bypasses the axios
 * client — it's a direct upload to S3 or the local storage endpoint).
 *
 * With the LocalFileStorage backend the URL is built server-side from
 * FRONTEND_HOST, which is the wrong host in a multi-origin deployment. When the
 * URL targets the internal storage endpoint we rebuild it against VITE_API_URL
 * (the correct API host); S3 presigned URLs are used verbatim.
 */
export async function uploadFileToPresignedUrl(
  intent: UploadDocumentResponse,
  file: File,
): Promise<void> {
  let url = intent.upload_url;
  try {
    const parsed = new URL(intent.upload_url);
    if (parsed.pathname.includes('/internal/storage/')) {
      const base = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');
      url = `${base}${parsed.pathname}${parsed.search}`;
    }
  } catch {
    // Relative/invalid URL — use as returned.
  }
  const response = await fetch(url, {
    method: intent.upload_method,
    headers: intent.upload_headers,
    body: file,
  });
  if (!response.ok) {
    throw new Error(`Upload failed (${response.status})`);
  }
}

/** Step 3: confirm the upload so the backend records the attachment + AV scan. */
export async function confirmDocumentUploaded(
  paymentId: string,
  payload: {
    fileKey: string;
    filename: string;
    mimetype: string;
    documentType?: string;
  },
): Promise<DocumentUploadedResponse> {
  const { data } = await api.post<DocumentUploadedResponse>(
    `/payments/${paymentId}/document-uploaded`,
    {
      file_key: payload.fileKey,
      filename: payload.filename,
      mimetype: payload.mimetype,
      document_type: payload.documentType ?? 'purchase_order',
    },
  );
  return data;
}
