import messages from './index';
import type { Translate } from '../utils/availability';

/**
 * A plain translator over the bundled messages, outside any component (unit
 * tests, code that runs before the app). `{name}` placeholders are filled;
 * vue-i18n escapes (`{'@'}`) are resolved; plural forms are not chosen here.
 */
export function makeTranslate(locale: 'fr' | 'en' = 'fr'): Translate {
  return (key, named = {}) => {
    let node: unknown = messages[locale];
    for (const part of key.split('.')) {
      node = (node as Record<string, unknown> | undefined)?.[part];
    }
    if (typeof node !== 'string') return key;
    return node.replace(/\{'([^']*)'\}/g, '$1').replace(/\{(\w+)\}/g, (_, name: string) => {
      const value = named[name];
      return typeof value === 'string' || typeof value === 'number' ? String(value) : `{${name}}`;
    });
  };
}
