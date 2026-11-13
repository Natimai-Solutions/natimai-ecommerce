/**
 * Garde-fou de l'interface (docs/GUIDE_INTERFACE.md), sur le modèle de
 * natimai-paie : les couleurs passent par les jetons --n-* (thème clair et
 * sombre), jamais par une couleur Material ni une valeur en dur ; pas de
 * surcharge !important ; des points de rupture Quasar seulement.
 *
 * Les jetons eux-mêmes (tokens.scss, quasar.variables.scss) sont la seule
 * source des valeurs : ils sont exclus des règles qui les définissent.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const REPO = join(__dirname, '../../..');
const ROOTS = ['frontend/src', 'admin-frontend/src', 'shared/ui/src'].map((dir) => join(REPO, dir));
const TOKEN_FILES = new Set(['tokens.scss', 'quasar.variables.scss']);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(vue|ts|scss)$/.test(entry) && !entry.endsWith('.test.ts')) out.push(full);
  }
  return out;
}

/** Commentaires retirés : une règle cite parfois ce qu'elle interdit. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

const MATERIAL =
  '(?:red|pink|purple|deep-purple|indigo|blue|light-blue|cyan|teal|green|light-green|lime|yellow|amber|orange|deep-orange|brown|grey|blue-grey)';

interface Rule {
  why: string;
  pattern: RegExp;
  /** Fichiers de jetons exclus : ils définissent les valeurs. */
  tokensExempt?: boolean;
}

const RULES: Rule[] = [
  {
    why: 'classe de couleur Material (bg-/text-<teinte>) : utiliser les jetons --n-* ou StatusTag',
    pattern: new RegExp(`\\b(?:bg|text)-${MATERIAL}(?:-\\d+)?\\b`),
  },
  {
    why: 'couleur Material passée à un composant ou renvoyée en JS : un ton StatusTag (ok, warn, danger, neutral) ou une couleur de marque (primary, accent…)',
    pattern: new RegExp(`(['"])${MATERIAL}(?:-\\d+)?\\1`),
  },
  {
    why: 'bg-white / bg-black : utiliser var(--n-surface) ou var(--n-paper)',
    pattern: /\bbg-(?:white|black)\b/,
  },
  {
    why: 'couleur choisie selon $q.dark : les jetons --n-* changent déjà avec le thème',
    pattern: /(?::class|:style|:color|:text-color)="[^"]*(?:\$q\.dark|Dark)\.isActive/,
  },
  {
    why: 'couleur en dur (#hex, rgb()) : la définir comme jeton dans tokens.scss',
    // Une valeur CSS : précédée de « : », d'un espace, de « ( », « , » ou
    // d'une apostrophe, suivie de « ; », « ) », « , », d'un blanc ou d'une
    // apostrophe. Ni un slot (`<template #add>`) ni une ancre (`href="#cafe"`).
    pattern: /(?:^|[\s:(,'])#[0-9a-fA-F]{3,8}(?=[;\s,)']|$)|\brgba?\(\s*\d/,
    tokensExempt: true,
  },
  {
    why: '!important : relever la spécificité ou changer la variable que lit Quasar',
    pattern: /!important/,
    tokensExempt: true,
  },
  {
    why: 'point de rupture hors échelle Quasar (599/600, 1023/1024, 1439/1440 px)',
    pattern: /@media[^{]*-width:\s*(?!(?:599|600|1023|1024|1439|1440)px)\d+px/,
  },
  {
    why: 'attribut statique qui contient $t( : le texte part tel quel (lecteur d\'écran compris) ; lier l\'attribut avec « : »',
    // `aria-label="$t('x')"` sans « : » : Vue ne l'évalue pas (audit 2026-11, U1).
    pattern: /(?:^|\s)(?!v-)[a-z][\w-]*="[^"]*\$t\(/,
  },
  {
    why: "message d'erreur brut (« Request failed with status code … ») : extractApiError / apiErrorMessage, puis un repli traduit",
    // Audit 2026-11, U2 : l'enveloppe { error: { message } } de l'API était ignorée.
    pattern: /instanceof Error \? \w+\.message :/,
  },
];

describe('interface : jetons, couleurs et points de rupture', () => {
  const files = ROOTS.flatMap((root) => walk(root));

  it('parcourt les deux applications et shared/ui', () => {
    expect(files.length).toBeGreaterThan(100);
  });

  for (const file of files) {
    const name = relative(REPO, file);
    const isTokens = TOKEN_FILES.has(file.split('/').pop() ?? '');
    it(name, () => {
      const source = code(readFileSync(file, 'utf8'));
      for (const rule of RULES) {
        if (rule.tokensExempt && isTokens) continue;
        const line = source.split('\n').findIndex((l) => rule.pattern.test(l));
        expect(line === -1 ? null : `${name}:${line + 1} — ${rule.why}`).toBeNull();
      }
    });
  }
});
