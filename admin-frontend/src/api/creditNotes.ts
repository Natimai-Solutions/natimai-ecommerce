import { api } from 'src/boot/api';

/** Credit note metadata as returned by `GET /admin/credit-notes` (`CreditNotePublic`). */
export interface CreditNote {
  id: string;
  credit_note_number: string;
  fiscal_year: number;
  invoice_id: string;
  order_id: string;
  issued_at: string;
  currency: string;
  total_excl_tax: string;
  total_tax: string;
  total_incl_tax: string;
  reason: string | null;
  /** Human-readable references read from the frozen snapshot; null on legacy documents. */
  order_number: string | null;
  invoice_number: string | null;
}

export async function listCreditNotes(params?: {
  fiscal_year?: number;
  skip?: number;
  limit?: number;
}): Promise<CreditNote[]> {
  const { data } = await api.get<CreditNote[]>('/admin/credit-notes', { params });
  return data;
}

/** Same blob + object-URL dance as the invoices: a plain link would not carry the token. */
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

export async function downloadCreditNotePdf(note: CreditNote): Promise<void> {
  await downloadBlob(`/admin/credit-notes/${note.id}/pdf`, `${note.credit_note_number}.pdf`);
}

/** Accounting export (CSV), optionally restricted to one fiscal year. */
export async function downloadCreditNotesCsv(fiscalYear: number | null): Promise<void> {
  const filename = fiscalYear ? `avoirs-${fiscalYear}.csv` : 'avoirs.csv';
  await downloadBlob(
    '/admin/credit-notes/export.csv',
    filename,
    fiscalYear ? { fiscal_year: fiscalYear } : undefined,
  );
}
