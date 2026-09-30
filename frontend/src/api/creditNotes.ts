import { api } from '@/boot/api';

/** Credit note metadata as returned by `GET /invoices/me/credit-notes` (`CreditNotePublic`). */
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
  order_number: string | null;
  invoice_number: string | null;
}

/** Credit notes issued for the authenticated customer, most recent first. */
export async function listMyCreditNotes(): Promise<CreditNote[]> {
  const response = await api.get<CreditNote[]>('/invoices/me/credit-notes');
  return response.data;
}

/**
 * Download a credit note PDF and hand it to the browser as a file (blob +
 * temporary object URL, so the bearer token travels with the request).
 */
export async function downloadCreditNotePdf(note: CreditNote): Promise<void> {
  const response = await api.get<Blob>(`/invoices/me/credit-notes/${note.id}/pdf`, {
    responseType: 'blob',
  });

  const url = URL.createObjectURL(response.data);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${note.credit_note_number}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
