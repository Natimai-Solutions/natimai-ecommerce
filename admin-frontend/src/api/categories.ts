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
  /** Catégorie parente (« Réseau » pour « WiFi »), null = premier niveau. */
  parent_id?: string | null;
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
export function categoryLabel(c: Pick<Category, 'name' | 'display_name' | 'title'>): string {
  return c.title ?? c.display_name ?? c.name;
}

/** Séparateur des niveaux dans un chemin de catégorie (« Réseau › WiFi »). */
export const CATEGORY_PATH_SEPARATOR = ' › ';

/**
 * Chemin complet de chaque catégorie (« Réseau › WiFi › Point d'accès »),
 * pour les listes déroulantes : deux « Accessoires » sous des parents
 * différents restent distinguables. Un parent inconnu ou une boucle arrête
 * la remontée.
 */
export function categoryPathLabels(
  categories: Pick<Category, 'id' | 'name' | 'display_name' | 'title' | 'parent_id'>[],
): Map<string, string> {
  const byId = new Map(categories.map((c) => [c.id, c]));
  const out = new Map<string, string>();
  for (const category of categories) {
    const parts: string[] = [];
    const seen = new Set<string>();
    let current: typeof category | undefined = category;
    while (current && !seen.has(current.id) && parts.length < 32) {
      seen.add(current.id);
      parts.unshift(categoryLabel(current));
      current = current.parent_id ? byId.get(current.parent_id) : undefined;
    }
    out.set(category.id, parts.join(CATEGORY_PATH_SEPARATOR));
  }
  return out;
}

/** Options « chemin complet » triées, pour un sélecteur de catégorie. */
export function categoryPathOptions(
  categories: Pick<Category, 'id' | 'name' | 'display_name' | 'title' | 'parent_id'>[],
): { label: string; value: string }[] {
  const labels = categoryPathLabels(categories);
  return categories
    .map((c) => ({ label: labels.get(c.id) ?? categoryLabel(c), value: c.id }))
    .sort((a, b) => a.label.localeCompare(b.label, 'fr'));
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
  /** Translated display_name / description per language (R9 / T3). */
  translations: Record<string, Record<string, unknown>>;
  translation_status: Record<string, string>;
  /** Categories suggested from this one's products (R9 / T7), in order. */
  suggested_category_ids: string[];
  /** Supplier couples mapped to this category (« Ingram : Computers / Notebooks »). */
  supplier_sources: string[];
  /** Hiérarchie : parent, chemin depuis la racine, niveau (0 = racine), sous-catégories directes. */
  parent_id: string | null;
  parent_name: string | null;
  path: string[];
  depth: number;
  children_count: number;
  /** Valeurs en vigueur (propre, sinon héritée) et la catégorie dont elles viennent (null = propre). */
  inherited_tax_rate_id: string | null;
  inherited_tax_rate_from: string | null;
  inherited_customs_rate_pct: string | null;
  inherited_customs_rate_from: string | null;
  inherited_margin_rate_pct: string | null;
  inherited_margin_rate_from: string | null;
}

export interface AdminCategoryUpdate {
  display_name?: string | null;
  description?: string | null;
  image_url?: string | null;
  is_active?: boolean;
  default_margin_rate_pct?: string | null;
  translations?: Record<string, Record<string, unknown>>;
  suggested_category_ids?: string[];
  /** Catégorie parente ; null = remonter au premier niveau. */
  parent_id?: string | null;
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

export async function createAdminCategory(payload: {
  name: string;
  display_name?: string | null;
  description?: string | null;
  parent_id?: string | null;
}): Promise<AdminCategory> {
  const { data } = await api.post<AdminCategory>('/admin/categories', payload);
  return data;
}
