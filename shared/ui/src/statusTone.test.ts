import { describe, expect, it } from 'vitest';

import { toneIcon, toneOf } from './statusTone';

describe('toneOf', () => {
  it('traduit les couleurs de statut en tons', () => {
    expect(toneOf('green')).toBe('ok');
    expect(toneOf('positive')).toBe('ok');
    expect(toneOf('orange')).toBe('warn');
    expect(toneOf('orange-2')).toBe('warn');
    expect(toneOf('negative')).toBe('danger');
    expect(toneOf('teal')).toBe('ok');
    expect(toneOf('deep-orange')).toBe('warn');
    expect(toneOf('amber-8')).toBe('warn');
    expect(toneOf('red-9')).toBe('danger');
  });

  it('reste neutre pour le reste', () => {
    expect(toneOf('primary')).toBe('neutral');
    expect(toneOf('grey-7')).toBe('neutral');
    expect(toneOf('blue')).toBe('neutral');
    expect(toneOf('blue-grey')).toBe('neutral');
    expect(toneOf('greyish')).toBe('neutral');
    expect(toneOf(undefined)).toBe('neutral');
  });
});

describe('toneIcon', () => {
  it('donne une icône Phosphor par ton', () => {
    expect(toneIcon('ok')).toBe('ph:check-circle');
    expect(toneIcon('danger')).toBe('ph:warning-circle');
  });
});
