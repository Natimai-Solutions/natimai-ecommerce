/**
 * Garde-fou d'accessibilité (docs/GUIDE_INTERFACE.md, audit 2026-11) : un
 * bouton qui n'affiche qu'une icône porte un `aria-label`. L'infobulle seule
 * n'est lue ni par les lecteurs d'écran ni au toucher ; l'admin en comptait
 * une cinquantaine.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const REPO = join(__dirname, '../../..');
const ROOTS = ['frontend/src', 'admin-frontend/src', 'shared/ui/src'].map((dir) => join(REPO, dir));

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (entry.endsWith('.vue')) out.push(full);
  }
  return out;
}

/** `<q-btn …>` tags showing an icon and no text, without an accessible name. */
function unnamedIconButtons(source: string): number[] {
  const lines: number[] = [];
  for (const match of source.matchAll(/<q-btn\b([\s\S]*?)\/?>/g)) {
    const attrs = match[1] ?? '';
    if (!/(^|\s):?icon=/.test(attrs)) continue;
    if (/(^|\s):?label=|aria-label|aria-labelledby/.test(attrs)) continue;
    lines.push(source.slice(0, match.index).split('\n').length);
  }
  return lines;
}

describe('accessibilité : boutons icône nommés', () => {
  for (const file of ROOTS.flatMap((root) => walk(root))) {
    const name = relative(REPO, file);
    it(name, () => {
      const lines = unnamedIconButtons(readFileSync(file, 'utf8'));
      expect(
        lines.map((line) => `${name}:${line} — q-btn icône sans aria-label (ni label)`),
      ).toEqual([]);
    });
  }
});
