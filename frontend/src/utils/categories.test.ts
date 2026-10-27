import { describe, expect, it } from 'vitest';
import type { components } from '@app/api-types';

import {
  catalogueCategoryChoices,
  categoryChildren,
  categoryLineage,
  categoryTitle,
  pickCategoryTiles,
} from './categories';

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

describe('hiérarchie', () => {
  const tree = [
    category({ name: 'Réseau' }),
    category({ name: 'WiFi', parent_id: 'Réseau' }),
    category({ name: "Point d'accès", parent_id: 'WiFi' }),
    category({ name: 'Switch', parent_id: 'Réseau' }),
    category({ name: 'Écrans' }),
  ];

  it("l'accueil ne montre que le premier niveau", () => {
    expect(pickCategoryTiles(tree).map((c) => c.name)).toEqual(['Écrans', 'Réseau']);
  });

  it('remonte le fil des parents, de la racine à la catégorie', () => {
    expect(categoryLineage(tree, "Point d'accès").map((c) => c.name)).toEqual([
      'Réseau',
      'WiFi',
      "Point d'accès",
    ]);
    expect(categoryLineage(tree, null)).toEqual([]);
    expect(categoryLineage(tree, 'inconnue')).toEqual([]);
  });

  it('propose les sous-catégories, sinon les sœurs, sinon le premier niveau', () => {
    expect(catalogueCategoryChoices(tree, null).map((c) => c.name)).toEqual(['Réseau', 'Écrans']);
    expect(catalogueCategoryChoices(tree, 'Réseau').map((c) => c.name)).toEqual(['WiFi', 'Switch']);
    expect(catalogueCategoryChoices(tree, "Point d'accès").map((c) => c.name)).toEqual([
      "Point d'accès",
    ]);
    expect(catalogueCategoryChoices(tree, 'Écrans').map((c) => c.name)).toEqual([
      'Réseau',
      'Écrans',
    ]);
    expect(categoryChildren(tree, 'WiFi').map((c) => c.name)).toEqual(["Point d'accès"]);
  });

  it('ne boucle pas sur un parent inconnu ou circulaire', () => {
    const loop = [category({ name: 'A', parent_id: 'B' }), category({ name: 'B', parent_id: 'A' })];
    expect(categoryLineage(loop, 'A').map((c) => c.name)).toEqual(['B', 'A']);
    expect(pickCategoryTiles(loop)).toEqual([]);
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
