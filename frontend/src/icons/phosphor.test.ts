import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { MATERIAL_TO_PHOSPHOR, phosphorIconMapFn, resolvePhosphorName } from './phosphor';

const here = fileURLToPath(new URL('.', import.meta.url));
const srcDir = join(here, '..');
const phosphorCss = readFileSync(
  join(here, '../../node_modules/@phosphor-icons/web/src/light/style.css'),
  'utf8',
);
const phosphorNames = new Set(
  [...phosphorCss.matchAll(/\.ph-light\.ph-([a-z0-9-]+):before/g)].map((m) => m[1] ?? ''),
);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(vue|ts)$/.test(entry) && !entry.endsWith('.test.ts') ? [path] : [];
  });
}

/** Noms d'icônes écrits en dur dans la vitrine (attributs et helpers *Icon). */
function iconNamesInSource(): Map<string, string> {
  const found = new Map<string, string>();
  const add = (name: string, file: string) => {
    if (name) found.set(name, file.replace(srcDir, 'src'));
  };
  for (const file of sourceFiles(srcDir)) {
    const text = readFileSync(file, 'utf8');
    for (const m of text.matchAll(/<q-icon[^>]*?\sname="([a-z0-9_]+)"/g)) add(m[1] ?? '', file);
    for (const m of text.matchAll(/\s(?:icon|icon-right)="([a-z0-9_:-]+)"/g)) add(m[1] ?? '', file);
    for (const m of text.matchAll(
      /:(?:icon|name)="[^"]*\?\s*'([a-z0-9_:-]+)'\s*:\s*'([a-z0-9_:-]+)'/g,
    )) {
      add(m[1] ?? '', file);
      add(m[2] ?? '', file);
    }
    for (const m of text.matchAll(/\bicon: '([a-z0-9_:-]+)'/g)) add(m[1] ?? '', file);
    for (const fn of text.matchAll(/function \w*Icon\([^)]*\)[^{]*\{([\s\S]*?)\n\}/g)) {
      for (const r of (fn[1] ?? '').matchAll(/return '([a-z0-9_:-]+)'/g)) add(r[1] ?? '', file);
    }
  }
  return found;
}

describe('MATERIAL_TO_PHOSPHOR', () => {
  it('ne pointe que vers des glyphes Phosphor existants', () => {
    const unknown = Object.entries(MATERIAL_TO_PHOSPHOR).filter(([, ph]) => !phosphorNames.has(ph));
    expect(unknown).toEqual([]);
  });

  it('couvre toutes les icônes utilisées par la vitrine', () => {
    const used = iconNamesInSource();
    // Garde-fou : le scan doit réellement trouver les icônes des pages.
    expect(used.size).toBeGreaterThan(40);
    expect(used.has('local_shipping')).toBe(true);
    const missing = [...used].filter(([name]) => {
      const resolved = resolvePhosphorName(name);
      return resolved === null || !phosphorNames.has(resolved);
    });
    expect(missing).toEqual([]);
  });
});

describe('phosphorIconMapFn', () => {
  it('traduit un nom Material vers la classe Phosphor light', () => {
    expect(phosphorIconMapFn('shopping_cart')).toEqual({ cls: 'ph-light ph-shopping-bag' });
  });

  it('accepte un nom Phosphor préfixé', () => {
    expect(phosphorIconMapFn('ph:magnifying-glass')).toEqual({
      cls: 'ph-light ph-magnifying-glass',
    });
  });

  it('laisse Quasar gérer les images et les tracés SVG', () => {
    expect(phosphorIconMapFn('img:https://example.test/logo.svg')).toBeUndefined();
    expect(phosphorIconMapFn('M0 0h24v24H0z')).toBeUndefined();
  });

  it('retombe sur un glyphe neutre pour un nom inconnu', () => {
    expect(phosphorIconMapFn('definitely_not_an_icon')).toEqual({ cls: 'ph-light ph-question' });
  });
});
