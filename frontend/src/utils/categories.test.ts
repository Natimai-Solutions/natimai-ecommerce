import { describe, expect, it } from 'vitest';
import type { components } from '@app/api-types';

import { categoryTitle, pickCategoryTiles } from './categories';

type CategoryPublic = components['schemas']['CategoryPublic'];

function category(overrides: Partial<CategoryPublic>): CategoryPublic {
  return {
    id: overrides.name ?? 'x',
    name: 'Catégorie',
    is_active: true,
    is_admin_active: true,
    ...overrides,
  } as CategoryPublic;
}

describe('pickCategoryTiles', () => {
  it('écarte les catégories inactives ou fusionnées', () => {
    const tiles = pickCategoryTiles([
      category({ name: 'Portables' }),
      category({ name: 'Ancienne', is_active: false }),
      category({ name: 'Masquée', is_admin_active: false }),
      category({ name: 'Doublon', merged_into_id: 'Portables' }),
    ]);
    expect(tiles.map((c) => c.name)).toEqual(['Portables']);
  });

  it("met d'abord les catégories illustrées, puis l'ordre alphabétique", () => {
    const tiles = pickCategoryTiles([
      category({ name: 'Écrans' }),
      category({ name: 'Accessoires' }),
      category({ name: 'Serveurs', image_url: 'https://img/serveurs.webp' }),
    ]);
    expect(tiles.map((c) => c.name)).toEqual(['Serveurs', 'Accessoires', 'Écrans']);
  });
});

describe('categoryTitle', () => {
  it('préfère le titre vitrine', () => {
    expect(
      categoryTitle(category({ name: 'Ordinateur Portable', display_name: 'Portables' })),
    ).toBe('Portables');
    expect(categoryTitle(category({ name: 'Écrans', display_name: '  ' }))).toBe('Écrans');
  });
});
