import type { WeightBand } from '@/api/logistics';

/** Ligne de grille éditée en chaînes (q-input). */
export interface BandRow {
  max_kg: string;
  price: string;
}

export function bandRows(bands: WeightBand[] | null | undefined): BandRow[] {
  return (bands ?? []).map((b) => ({ max_kg: b.max_kg ?? '', price: b.price }));
}

/** Lignes sans prix ignorées ; plafond vide = « et au-delà ». Vide → null. */
export function bandsPayload(rows: BandRow[]): WeightBand[] | null {
  const out = rows
    .filter((b) => b.price.trim() !== '')
    .map((b) => ({ max_kg: b.max_kg.trim() || null, price: b.price.trim() }));
  return out.length > 0 ? out : null;
}
