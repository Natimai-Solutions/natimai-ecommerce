import { api } from 'src/boot/api';

/** Invoice metadata as returned by `GET /invoices/me` (`InvoicePublic`). */
export interface Invoice {
  id: string;
  invoice_number: string;
  fiscal_year: number;
  order_id: string;
  issued_at: string;
  currency: string;
  total_excl_tax: string;
  total_tax: string;
  total_incl_tax: string;
  /** Human-readable order reference (CMD-2026-00042), null for pre-M5 orders. */
  order_number: string | null;
}

interface InvoicesResponse {
  data: Invoice[];
  count: number;
}

/** Invoices issued for the authenticated customer, most recent first. */
export async function listMyInvoices(): Promise<Invoice[]> {
  const response = await api.get<InvoicesResponse>('/invoices/me');
  return response.data.data;
}

/**
 * Download an invoice PDF and hand it to the browser as a file.
 *
 * The endpoint is authenticated, so a plain `<a href>` would not carry the
 * bearer token: the PDF is fetched as a blob and saved through a temporary
 * object URL.
 */
export async function downloadInvoicePdf(invoice: Invoice): Promise<void> {
  const response = await api.get<Blob>(`/invoices/me/${invoice.id}/pdf`, {
    responseType: 'blob',
  });

  const url = URL.createObjectURL(response.data);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${invoice.invoice_number}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
