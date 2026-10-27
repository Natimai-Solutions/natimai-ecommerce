import type { components } from '@app/api-types';

type CategoryPublic = components['schemas']['CategoryPublic'];

/** Tuiles de catégories affichées sur l'accueil. */
const CATEGORY_TILES = 8;

/**
 * Catégories montrables : actives, non fusionnées, de premier niveau (une
 * sous-catégorie se découvre depuis son parent, dans le catalogue). L'API
 * publique les renvoie toutes ; celles qui portent une image passent devant,
 * puis l'ordre alphabétique du titre vitrine.
 */
export function pickCategoryTiles(all: CategoryPublic[]): CategoryPublic[] {
  const visible = all.filter((c) => c.is_active && c.is_admin_active && !c.merged_into_id);
  const ids = new Set(visible.map((c) => c.id));
  return visible
    .filter((c) => !c.parent_id || !ids.has(c.parent_id))
    .sort((a, b) => {
      const byImage = Number(Boolean(b.image_url)) - Number(Boolean(a.image_url));
      if (byImage !== 0) return byImage;
      return categoryTitle(a).localeCompare(categoryTitle(b), 'fr');
    })
    .slice(0, CATEGORY_TILES);
}

export function categoryTitle(category: CategoryPublic): string {
  return (category.display_name ?? '').trim() || category.name;
}

/** Séparateur des niveaux dans un chemin (« Réseau › WiFi »). */
export const CATEGORY_PATH_SEPARATOR = ' › ';

/** Profondeur maximale suivie (garde-fou contre une boucle, pas une limite). */
const MAX_DEPTH = 32;

type CategoryLike = Pick<CategoryPublic, 'id' | 'name' | 'display_name' | 'parent_id'>;

/**
 * La catégorie et ses parents, de la racine à elle : fil d'Ariane de la
 * fiche produit et du catalogue (« Réseau › WiFi › Point d'accès »). Un
 * parent inconnu (inactif, fusionné) arrête la remontée.
 */
export function categoryLineage<T extends CategoryLike>(all: T[], id: string | null): T[] {
  if (!id) return [];
  const byId = new Map(all.map((c) => [c.id, c]));
  const chain: T[] = [];
  const seen = new Set<string>();
  let current = byId.get(id);
  while (current && !seen.has(current.id) && chain.length < MAX_DEPTH) {
    seen.add(current.id);
    chain.unshift(current);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return chain;
}

/** Les sous-catégories directes de `parentId` (null : les catégories de premier niveau). */
export function categoryChildren<T extends CategoryLike>(all: T[], parentId: string | null): T[] {
  const ids = new Set(all.map((c) => c.id));
  return all.filter((c) =>
    parentId === null ? !c.parent_id || !ids.has(c.parent_id) : c.parent_id === parentId,
  );
}

/**
 * Les catégories à proposer dans le catalogue quand `selected` est choisie :
 * ses sous-catégories si elle en a, sinon ses sœurs (on change de rayon au
 * même niveau) ; sans sélection, le premier niveau.
 */
export function catalogueCategoryChoices<T extends CategoryLike>(
  all: T[],
  selected: string | null,
): T[] {
  if (!selected) return categoryChildren(all, null);
  const children = categoryChildren(all, selected);
  if (children.length) return children;
  const current = all.find((c) => c.id === selected);
  const siblings = categoryChildren(all, current?.parent_id ?? null);
  return siblings.length ? siblings : categoryChildren(all, null);
}
