import type { components } from '@app/api-types';
import { api } from '@/boot/api';

/** Invoice metadata as returned by `GET /admin/invoices` (`InvoicePublic`). */
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

export async function listInvoices(params?: {
  fiscal_year?: number;
  skip?: number;
  limit?: number;
}): Promise<InvoicesResponse> {
  const { data } = await api.get<InvoicesResponse>('/admin/invoices', { params });
  return data;
}

/**
 * Fetch a blob from an authenticated endpoint and save it as a file.
 *
 * A plain `<a href>` would not carry the bearer token, hence the blob +
 * temporary object URL dance.
 */
async function downloadBlob(url: string, filename: string, params?: object): Promise<void> {
  const response = await api.get<Blob>(url, { responseType: 'blob', params });
  const objectUrl = URL.createObjectURL(response.data);
  try {
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function downloadInvoicePdf(invoice: Invoice): Promise<void> {
  await downloadBlob(`/admin/invoices/${invoice.id}/pdf`, `${invoice.invoice_number}.pdf`);
}

/** Accounting export (CSV), optionally restricted to one fiscal year. */
export async function downloadInvoicesCsv(fiscalYear: number | null): Promise<void> {
  const filename = fiscalYear ? `factures-${fiscalYear}.csv` : 'factures.csv';
  await downloadBlob(
    '/admin/invoices/export.csv',
    filename,
    fiscalYear ? { fiscal_year: fiscalYear } : undefined,
  );
}

export type IntegrityReport = components['schemas']['IntegrityReportPublic'];

/** Recompute the integrity chain of every invoice and credit note. */
export async function checkInvoicesIntegrity(): Promise<IntegrityReport> {
  const { data } = await api.get<IntegrityReport>('/admin/invoices/integrity');
  return data;
}
