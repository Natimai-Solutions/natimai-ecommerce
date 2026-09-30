import { api } from '@/boot/api';
import type { ProductPublic } from '@/stores/products';

/** Méthode d'approvisionnement d'un fournisseur (voir backend `SupplierKind`). */
export type SupplierKind = 'manual' | 'file' | 'api';

export const SUPPLIER_KIND_LABELS: Record<SupplierKind, string> = {
  manual: 'Générique (saisie manuelle)',
  file: 'Fichier CSV / Excel',
  api: 'API (intégration)',
};

export interface Supplier {
  id: string;
  /** Clé de rapprochement (Product.supplier_name) — immuable après création. */
  code: string;
  name: string;
  kind: SupplierKind;
  adapter_key: string | null;
  origin_place_id: string | null;
  is_domestic: boolean;
  sync_enabled: boolean;
  sync_interval_hours: number;
  default_categories: string[] | null;
  price_currency: string | null;
  column_mapping: Record<string, string> | null;
  /** Références suivies chez ce fournisseur (null / vide = tout le catalogue synchronisé). */
  sku_allowlist: string[] | null;
  /** Les nouveaux articles de ce fournisseur arrivent en brouillon (publiés par l'admin). */
  import_as_draft: boolean;
  /** Sort des articles dont la catégorie fournisseur n'a pas de règle. */
  unmapped_category_action: UnmappedCategoryAction;
  /** Commande fournisseur passée automatiquement à l'encaissement (intégration qui sait commander). */
  auto_purchase_order: boolean;
  /** Des identifiants (flux fichier) sont enregistrés, chiffrés — jamais renvoyés. */
  has_credentials?: boolean;
  /** Import fichier : quantité minimale d'une ligne (null = pas de seuil). */
  min_quantity: string | null;
  /** Import fichier : prix d'achat minimal, dans la devise du fichier (null = pas de seuil). */
  min_price: string | null;
  settings: Record<string, unknown> | null;
  contact_email: string | null;
  contact_phone: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /** kind=api : l'intégration existe et ses identifiants sont présents. */
  configured: boolean;
  /** Réponse de la désactivation : articles retirés (stock à zéro / masqués). */
  products_withdrawn?: number | null;
}

export interface SupplierCreate {
  code: string;
  name: string;
  kind: SupplierKind;
  adapter_key?: string | null;
  origin_place_id?: string | null;
  is_domestic?: boolean;
  sync_enabled?: boolean;
  sync_interval_hours?: number;
  default_categories?: string[] | null;
  price_currency?: string | null;
  column_mapping?: Record<string, string> | null;
  unmapped_category_action?: UnmappedCategoryAction;
  auto_purchase_order?: boolean;
  min_quantity?: number | null;
  min_price?: number | null;
  import_as_draft?: boolean;
  settings?: Record<string, unknown> | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  notes?: string | null;
}

export type SupplierUpdate = Partial<Omit<SupplierCreate, 'code'>> & { is_active?: boolean };

export interface AdapterDescriptor {
  key: string;
  display_name: string;
  configured: boolean;
  settings_keys: string[];
  /** L'intégration sait passer une commande fournisseur. */
  supports_purchase_orders?: boolean;
}

export interface FileInspectResponse {
  filename: string;
  headers: string[];
  sample_rows: Record<string, string>[];
  total_rows: number;
  mapping_targets: string[];
  required_targets: string[];
  mapping_problems: string[];
}

export interface FileImportRowError {
  row_number: number;
  message: string;
}

export type ImportResolutionAction = 'new' | 'updated' | 'adopted' | 'ambiguous' | 'skipped';
export type ImportMatchKey = 'mapping' | 'supplier_sku' | 'gtin' | 'manufacturer_part';

/** Comment une ligne lisible a été (ou serait) rapprochée du catalogue. */
export interface FileImportResolutionRow {
  supplier_sku: string;
  name: string;
  action: ImportResolutionAction;
  match_key: ImportMatchKey | null;
  product_id: string | null;
  product_name: string | null;
  message: string | null;
}

export const MATCH_KEY_LABELS: Record<ImportMatchKey, string> = {
  mapping: 'référence (déjà liée)',
  supplier_sku: 'référence fournisseur',
  gtin: 'code-barres EAN/UPC',
  manufacturer_part: 'marque + réf. fabricant',
};

export const RESOLUTION_ACTION_LABELS: Record<ImportResolutionAction, string> = {
  new: 'Nouveau',
  updated: 'Mise à jour',
  adopted: 'Adopté (article saisi à la main)',
  ambiguous: 'Ambigu — non traité',
  skipped: 'Ignoré',
};

export interface FileImportResponse {
  supplier_name: string;
  filename: string;
  dry_run: boolean;
  total_rows: number;
  parsed_products: number;
  rejected_rows: number;
  row_errors: FileImportRowError[];
  statistics: Record<string, number>;
  sync_errors: { sku: string; error: string }[];
  sync_log_id: string | null;
  /** Les articles créés / adoptés ont été publiés tels que le fichier les décrit. */
  published_new: boolean;
  /** Fichier volumineux : stocké et confié au worker ; suivre `sync_log_id` via getImportStatus. */
  queued: boolean;
  job_id: string | null;
  message: string | null;
  sample: Record<string, unknown>[];
  /** Simulation : compteurs de la reconnaissance (new / updated / adopted / ambiguous / skipped, matched_by_*). */
  resolution: Record<string, number>;
  sample_resolutions: FileImportResolutionRow[];
  /** Simulation d'un gros fichier : seules les N premières lignes ont été rapprochées. */
  resolution_limited_to: number | null;
  /** Simulation : chaque couple (catégorie, sous-catégorie) du fichier et son sort. */
  category_pairs?: ObservedCategory[];
}

export type ImportStatus = 'pending' | 'running' | 'success' | 'partial' | 'failed';

/** Avancement et résultat d'un import (son journal de synchronisation). */
export interface FileImportStatus {
  sync_log_id: string;
  supplier_name: string;
  status: ImportStatus;
  filename: string | null;
  total_rows: number | null;
  parsed_products: number | null;
  rejected_rows: number | null;
  row_errors: FileImportRowError[];
  statistics: Record<string, number>;
  sync_errors: { sku: string; error: string }[];
  published_new: boolean;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface SyncResponse {
  job_id: string;
  supplier_name: string;
  status: string;
  message: string;
  timestamp: string;
}

export interface HealthResponse {
  supplier_name: string;
  status: string;
  api_responsive: boolean;
  configuration_valid: boolean;
  last_sync: string | null;
  message: string;
}

/** Libellés des champs internes qu'un mapping de colonnes peut viser. */
export const MAPPING_TARGET_LABELS: Record<string, string> = {
  supplier_sku: 'Référence fournisseur (SKU) *',
  name: 'Désignation *',
  description: 'Description',
  manufacturer: 'Marque / fabricant',
  vendor_part_number: 'Référence fabricant',
  category: 'Catégorie fournisseur',
  subcategory: 'Sous-catégorie (→ catégorie interne)',
  price: 'Prix d’achat (coût)',
  currency: 'Devise du prix',
  quantity: 'Stock disponible',
  weight: 'Poids (kg)',
  image_url: 'URL image',
  spec_url: 'URL fiche technique',
  upc: 'UPC',
  ean: 'EAN',
};

export async function listSuppliers(): Promise<Supplier[]> {
  const { data } = await api.get<{ data: Supplier[]; count: number }>('/admin/suppliers');
  return data.data;
}

export async function listAdapters(): Promise<AdapterDescriptor[]> {
  const { data } = await api.get<AdapterDescriptor[]>('/admin/suppliers/adapters');
  return data;
}

export async function createSupplier(payload: SupplierCreate): Promise<Supplier> {
  const { data } = await api.post<Supplier>('/admin/suppliers', payload);
  return data;
}

export async function updateSupplier(code: string, payload: SupplierUpdate): Promise<Supplier> {
  const { data } = await api.patch<Supplier>(`/admin/suppliers/${code}`, payload);
  return data;
}

/** Sort des articles d'un fournisseur désactivé. */
export type SupplierWithdrawal = 'keep' | 'zero_stock' | 'hide';

export async function deactivateSupplier(
  code: string,
  products: SupplierWithdrawal = 'keep',
): Promise<Supplier> {
  const { data } = await api.delete<Supplier>(`/admin/suppliers/${code}`, {
    params: { products },
  });
  return data;
}

/** Une référence de la liste blanche et l'article qu'elle désigne, s'il existe déjà. */
export interface AllowlistEntry {
  supplier_sku: string;
  product_id: string | null;
  product_name: string | null;
  is_active: boolean | null;
}

export interface AllowlistView {
  supplier_name: string;
  entries: AllowlistEntry[];
  /** Références déjà au catalogue. */
  known: number;
  /** Références que la prochaine synchronisation catalogue créera. */
  unknown: string[];
  /** Articles gérés par ce fournisseur hors liste (retirés de la vitrine). */
  outside: number;
  /** Articles retirés de la vitrine par le dernier enregistrement. */
  deactivated: number;
}

export async function getSkuAllowlist(code: string): Promise<AllowlistView> {
  const { data } = await api.get<AllowlistView>(`/admin/suppliers/${code}/sku-allowlist`);
  return data;
}

/** Remplace la liste (vide = tout le catalogue) ; les articles hors liste quittent la vitrine. */
export async function saveSkuAllowlist(code: string, skus: string[]): Promise<AllowlistView> {
  const { data } = await api.put<AllowlistView>(`/admin/suppliers/${code}/sku-allowlist`, {
    skus,
  });
  return data;
}

export async function inspectCatalogFile(code: string, file: File): Promise<FileInspectResponse> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post<FileInspectResponse>(
    `/suppliers/${code}/import-file/inspect`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function importCatalogFile(
  code: string,
  file: File,
  options: {
    mapping?: Record<string, string> | null;
    dryRun?: boolean;
    publishNew?: boolean;
    /** Seuils de cet import ; absents = ceux du fournisseur, 0 = aucun. */
    minQuantity?: number | null;
    minPrice?: number | null;
    /** Catégorie boutique des lignes que les règles ne placent pas. */
    defaultCategoryId?: string | null;
  },
): Promise<FileImportResponse> {
  const form = new FormData();
  form.append('file', file);
  if (options.mapping) form.append('mapping', JSON.stringify(options.mapping));
  form.append('publish_new', options.publishNew === false ? 'false' : 'true');
  if (options.minQuantity != null) form.append('min_quantity', String(options.minQuantity));
  if (options.minPrice != null) form.append('min_price', String(options.minPrice));
  if (options.defaultCategoryId) form.append('default_category_id', options.defaultCategoryId);
  const { data } = await api.post<FileImportResponse>(`/suppliers/${code}/import-file`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: { dry_run: options.dryRun ? 'true' : 'false' },
  });
  return data;
}

export async function getImportStatus(code: string, syncLogId: string): Promise<FileImportStatus> {
  const { data } = await api.get<FileImportStatus>(`/suppliers/${code}/import-file/${syncLogId}`);
  return data;
}

export async function triggerProductSync(code: string): Promise<SyncResponse> {
  const { data } = await api.post<SyncResponse>(`/suppliers/${code}/sync/products`, {});
  return data;
}

export async function triggerInventorySync(code: string): Promise<SyncResponse> {
  const { data } = await api.post<SyncResponse>(`/suppliers/${code}/sync/inventory`, {});
  return data;
}

export async function checkSupplierHealth(code: string): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>(`/suppliers/${code}/health`);
  return data;
}

/** « Rattacher maintenant » : `adopted` = coût et stock repris ; `pending` = au prochain import. */
export interface SupplierAttachResponse {
  status: 'adopted' | 'pending';
  message: string;
  product: ProductPublic;
}

export async function attachProductToSupplier(
  productId: string,
  payload: { supplier_name?: string | null; supplier_sku?: string | null },
): Promise<SupplierAttachResponse> {
  const { data } = await api.post<SupplierAttachResponse>(
    `/admin/products/${productId}/attach-supplier`,
    payload,
  );
  return data;
}

/** « Détacher » : l'article redevient manuel (verrous conservés, stock fournisseur à 0). */
export async function detachProductFromSupplier(productId: string): Promise<ProductPublic> {
  const { data } = await api.post<ProductPublic>(`/admin/products/${productId}/detach-supplier`);
  return data;
}

// --- Mappage des catégories fournisseur → boutique (R4 / S5) ---------------

export type CategoryMappingAction = 'import' | 'draft' | 'deactivate' | 'skip';
export type UnmappedCategoryAction = 'auto' | 'draft' | 'deactivate' | 'skip';

export const CATEGORY_ACTION_LABELS: Record<CategoryMappingAction, string> = {
  import: 'Importer',
  draft: 'Nouveaux en brouillon',
  deactivate: 'Importer hors vitrine',
  skip: 'Ignorer',
};

export const UNMAPPED_ACTION_LABELS: Record<UnmappedCategoryAction, string> = {
  auto: 'Catégorie au nom de la sous-catégorie (automatique)',
  draft: 'Idem, nouveaux articles en brouillon',
  deactivate: 'Idem, articles hors vitrine',
  skip: 'Ignorer (ni créés ni mis à jour)',
};

/** Ce que l'import fera d'un couple (import | draft | deactivate | skip | filtered). */
export const CATEGORY_EFFECT_LABELS: Record<string, string> = {
  import: 'Importé',
  draft: 'Brouillon',
  deactivate: 'Hors vitrine',
  skip: 'Ignoré',
  filtered: 'Écarté (filtre global)',
};

export interface CategoryMapping {
  id: string;
  source_category: string | null;
  source_subcategory: string | null;
  /** Catégorie boutique ; null = au nom de la source (créée au besoin). */
  category_id: string | null;
  category_name: string | null;
  action: CategoryMappingAction;
  updated_at: string;
}

export interface CategoryMappingWrite {
  source_category: string | null;
  source_subcategory: string | null;
  category_id: string | null;
  action: CategoryMappingAction;
}

export interface ObservedCategory {
  source_category: string | null;
  source_subcategory: string | null;
  count: number;
  mapping: CategoryMapping | null;
  resolved_category_name: string | null;
  effect: string;
}

export async function listCategoryMappings(code: string): Promise<CategoryMapping[]> {
  const { data } = await api.get<CategoryMapping[]>(`/admin/suppliers/${code}/category-mappings`);
  return data;
}

export async function saveCategoryMappings(
  code: string,
  rules: CategoryMappingWrite[],
): Promise<CategoryMapping[]> {
  const { data } = await api.put<CategoryMapping[]>(
    `/admin/suppliers/${code}/category-mappings`,
    rules,
  );
  return data;
}

export async function deleteCategoryMapping(code: string, mappingId: string): Promise<void> {
  await api.delete(`/admin/suppliers/${code}/category-mappings/${mappingId}`);
}

export async function reapplyCategoryMappings(
  code: string,
): Promise<{ moved: number; deactivated: number }> {
  const { data } = await api.post<{ moved: number; deactivated: number }>(
    `/admin/suppliers/${code}/category-mappings/reapply`,
  );
  return data;
}

export async function listObservedCategories(code: string): Promise<ObservedCategory[]> {
  const { data } = await api.get<ObservedCategory[]>(
    `/admin/suppliers/${code}/observed-categories`,
  );
  return data;
}

// --- Fichier en ligne (R4 / S3) ---------------------------------------------

export const FEED_ADAPTER_KEY = 'file_feed';

export async function saveSupplierCredentials(
  code: string,
  credentials: { username: string; password: string },
): Promise<Supplier> {
  const { data } = await api.put<Supplier>(`/admin/suppliers/${code}/credentials`, credentials);
  return data;
}

export async function deleteSupplierCredentials(code: string): Promise<Supplier> {
  const { data } = await api.delete<Supplier>(`/admin/suppliers/${code}/credentials`);
  return data;
}

/** Télécharge le flux du fournisseur et renvoie ses en-têtes (même forme qu'un fichier). */
export async function inspectSupplierFeed(code: string): Promise<FileInspectResponse> {
  const { data } = await api.post<FileInspectResponse>(`/admin/suppliers/${code}/feed/inspect`);
  return data;
}
