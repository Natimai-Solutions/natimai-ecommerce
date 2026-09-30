import type { components } from '@app/api-types';

type CategoryPublic = components['schemas']['CategoryPublic'];

/** Tuiles de catégories affichées sur l'accueil. */
const CATEGORY_TILES = 8;

/**
 * Catégories montrables : actives, non fusionnées. L'API publique les renvoie
 * toutes ; celles qui portent une image passent devant, puis l'ordre
 * alphabétique du titre vitrine.
 */
export function pickCategoryTiles(all: CategoryPublic[]): CategoryPublic[] {
  return all
    .filter((c) => c.is_active && c.is_admin_active && !c.merged_into_id)
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
