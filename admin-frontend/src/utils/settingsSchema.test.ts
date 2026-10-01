import { describe, expect, it } from 'vitest';
import { fieldsFromSchema, fromFormValue, toFormValue } from './settingsSchema';

// Forme réelle d'un schéma Pydantic `X | None` (anyOf avec null).
const schema = {
  properties: {
    environment: {
      anyOf: [{ enum: ['sandbox', 'production'], type: 'string' }, { type: 'null' }],
      title: 'Environnement',
    },
    subcategory_allowlist: {
      anyOf: [{ type: 'array', items: { type: 'string' } }, { type: 'null' }],
      title: 'Sous-catégories autorisées',
      description: 'Vide : la liste de l’environnement.',
    },
    filter_rules: {
      anyOf: [{ type: 'array', items: { $ref: '#/$defs/ProductFilterRule' } }, { type: 'null' }],
    },
    sync_min_price: {
      anyOf: [{ type: 'number' }, { type: 'string' }, { type: 'null' }],
    },
    feed_url: { anyOf: [{ type: 'string' }, { type: 'null' }] },
  },
};

describe('fieldsFromSchema', () => {
  const fields = fieldsFromSchema(schema, { feed_url: 'Adresse du fichier' });
  const byKey = Object.fromEntries(fields.map((f) => [f.key, f]));

  it('reads kinds, choices and labels', () => {
    expect(byKey.environment).toMatchObject({ kind: 'choice', choices: ['sandbox', 'production'] });
    expect(byKey.subcategory_allowlist?.kind).toBe('list');
    expect(byKey.filter_rules?.kind).toBe('json');
    expect(byKey.sync_min_price?.kind).toBe('number');
    expect(byKey.feed_url).toMatchObject({ kind: 'text', label: 'Adresse du fichier' });
    expect(byKey.filter_rules?.label).toBe('filter_rules');
  });

  it('round-trips values through the form', () => {
    const list = byKey.subcategory_allowlist;
    expect(toFormValue(list, ['Laptops', 'Tablets'])).toBe('Laptops, Tablets');
    expect(fromFormValue(list, 'Laptops, Tablets\nPhones')).toEqual([
      'Laptops',
      'Tablets',
      'Phones',
    ]);
    expect(fromFormValue(list, '[]')).toEqual([]);
    expect(fromFormValue(list, '  ')).toBeUndefined();

    const rules = byKey.filter_rules;
    const value = [{ action: 'skip', field: 'name', contains: 'refurb' }];
    expect(fromFormValue(rules, toFormValue(rules, value))).toEqual(value);
    expect(() => fromFormValue(rules, '{oops')).toThrow(/JSON invalide/);
  });
});
