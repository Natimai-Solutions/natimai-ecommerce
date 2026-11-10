import { describe, expect, it } from 'vitest';
import { createI18n } from 'vue-i18n';

import en from './en';
import fr from './fr';

type Tree = { [key: string]: string | Tree };

function leaves(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'string' ? [`${prefix}${key}`] : leaves(value, `${prefix}${key}.`),
  );
}

describe('admin messages', () => {
  it('has the same keys in French and English', () => {
    expect(leaves(en as Tree).sort()).toEqual(leaves(fr as Tree).sort());
  });

  it('holds no HTML entity (shown as is outside v-html)', () => {
    const entity = /&(amp|lt|gt|quot|nbsp|#\d+);/;
    const offenders = [fr, en].flatMap((tree) =>
      leaves(tree as Tree).filter((key) => {
        const text = key
          .split('.')
          .reduce<
            Tree | string | undefined
          >((node, part) => (typeof node === 'object' ? node[part] : undefined), tree as Tree);
        return typeof text === 'string' && entity.test(text);
      }),
    );
    expect(offenders).toEqual([]);
  });

  it.each(['fr', 'en'] as const)('compiles every %s message', (locale) => {
    const errors: string[] = [];
    const i18n = createI18n({
      legacy: false,
      locale,
      messages: { fr, en },
      missingWarn: false,
      fallbackWarn: false,
      warnHtmlMessage: false,
    });
    for (const key of leaves(fr)) {
      try {
        const text = i18n.global.t(key, { n: 2 }, { locale });
        if (!text || text === key) errors.push(key);
      } catch (err) {
        errors.push(`${key}: ${String(err)}`);
      }
    }
    expect(errors).toEqual([]);
  });
});
