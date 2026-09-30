import { api } from '@/boot/api';

export interface Category {
  id: string;
  name: string;
  /** Titre vitrine choisi par l'admin (null → name). */
  display_name?: string | null;
  /** Résolu côté backend : display_name ?? name. */
  title?: string;
  description: string | null;
  default_tax_rate_id: string | null;
}

interface CategoriesResponse {
  data: Category[];
  count: number;
}

export async function listCategories(): Promise<Category[]> {
  const { data } = await api.get<CategoriesResponse>('/category/', {
    params: { limit: 500 },
  });
  return data.data;
}

/** Libellé à afficher dans les listes déroulantes admin. */
export function categoryLabel(c: Category): string {
  return c.title ?? c.display_name ?? c.name;
}

// --- Back-office des catégories (A17 / A12) --------------------------------

export interface AdminCategory {
  id: string;
  /** Clé de rapprochement de la sync fournisseur — jamais modifiable ici. */
  name: string;
  display_name: string | null;
  title: string;
  description: string | null;
  image_url: string | null;
  is_active: boolean;
  default_tax_rate_id: string | null;
  default_customs_rate_pct: string | null;
  /** Marge par défaut des articles (null = celle du groupe tarifaire). */
  default_margin_rate_pct: string | null;
  merged_into_id: string | null;
  merged_into_name: string | null;
  product_count: number;
}

export interface AdminCategoryUpdate {
  display_name?: string | null;
  description?: string | null;
  image_url?: string | null;
  is_active?: boolean;
  default_margin_rate_pct?: string | null;
}

export interface MergeResult {
  source: AdminCategory;
  target: AdminCategory;
  moved_products: number;
  moved_discounts: number;
}

export async function listAdminCategories(): Promise<AdminCategory[]> {
  const { data } = await api.get<{ data: AdminCategory[]; count: number }>('/admin/categories');
  return data.data;
}

export async function updateAdminCategory(
  id: string,
  payload: AdminCategoryUpdate,
): Promise<AdminCategory> {
  const { data } = await api.patch<AdminCategory>(`/admin/categories/${id}`, payload);
  return data;
}

export async function mergeCategory(sourceId: string, targetId: string): Promise<MergeResult> {
  const { data } = await api.post<MergeResult>(`/admin/categories/${sourceId}/merge`, {
    target_id: targetId,
  });
  return data;
}
