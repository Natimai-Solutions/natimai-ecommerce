import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  createPhosphorIconMapFn,
  MATERIAL_TO_PHOSPHOR,
  phosphorIconMapFn,
  resolvePhosphorName,
} from './icons';

const here = fileURLToPath(new URL('.', import.meta.url));
const repoRoot = join(here, '../../..');
const APPS = {
  vitrine: join(repoRoot, 'frontend/src'),
  admin: join(repoRoot, 'admin-frontend/src'),
} as const;
const phosphorCss = readFileSync(
  join(repoRoot, 'frontend/node_modules/@phosphor-icons/web/src/light/style.css'),
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

/** Noms d'icônes écrits en dur dans une app (attributs et helpers *Icon). */
function iconNamesInSource(srcDir: string): Map<string, string> {
  const found = new Map<string, string>();
  const add = (name: string, file: string) => {
    if (name) found.set(name, file.replace(srcDir, 'src'));
  };
  for (const file of sourceFiles(srcDir)) {
    const text = readFileSync(file, 'utf8');
    for (const m of text.matchAll(/<q-icon[^>]*?\sname="([a-z0-9_:-]+)"/g)) add(m[1] ?? '', file);
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

  // Garde-fou : le scan doit réellement trouver les icônes des pages. Les
  // pages refondues nomment Phosphor directement (`ph:…`) : ces noms-là sont
  // vérifiés aussi, une faute de frappe y donnerait un glyphe vide.
  it.each([
    ['vitrine', APPS.vitrine, ['ph:list', 'ph:map-pin']],
    ['admin', APPS.admin, ['ph:sign-out', 'ph:gear']],
  ] as const)('couvre toutes les icônes utilisées par %s', (_app, srcDir, sentinels) => {
    const used = iconNamesInSource(srcDir);
    expect(used.size).toBeGreaterThan(40);
    for (const sentinel of sentinels) expect(used.has(sentinel)).toBe(true);
    const missing = [...used].filter(([name]) => {
      const resolved = resolvePhosphorName(name);
      return resolved === null || !phosphorNames.has(resolved);
    });
    expect(missing).toEqual([]);
  });

  it("couvre le jeu d'icônes interne de Quasar (tables, éditeur, dates)", () => {
    const iconSet = readFileSync(
      join(repoRoot, 'admin-frontend/node_modules/quasar/icon-set/material-icons.js'),
      'utf8',
    );
    const names = new Set([...iconSet.matchAll(/'([a-z_]+)'/g)].map((m) => m[1] ?? ''));
    expect(names.size).toBeGreaterThan(50);
    expect([...names].filter((name) => !(name in MATERIAL_TO_PHOSPHOR))).toEqual([]);
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

  it('signale une seule fois chaque nom inconnu', () => {
    const missing: string[] = [];
    const mapFn = createPhosphorIconMapFn((name) => missing.push(name));
    mapFn('nope');
    mapFn('nope');
    mapFn('add');
    expect(missing).toEqual(['nope']);
  });
});
