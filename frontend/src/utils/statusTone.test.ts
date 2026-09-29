import { describe, expect, it } from 'vitest';

import { toneOf } from './statusTone';

describe('toneOf', () => {
  it('traduit les couleurs de statut en tons', () => {
    expect(toneOf('green')).toBe('ok');
    expect(toneOf('positive')).toBe('ok');
    expect(toneOf('orange')).toBe('warn');
    expect(toneOf('orange-2')).toBe('warn');
    expect(toneOf('negative')).toBe('danger');
  });

  it('reste neutre pour le reste', () => {
    expect(toneOf('primary')).toBe('neutral');
    expect(toneOf('grey-7')).toBe('neutral');
    expect(toneOf('blue')).toBe('neutral');
    expect(toneOf(undefined)).toBe('neutral');
  });
});
