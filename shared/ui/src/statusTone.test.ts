import { describe, expect, it } from 'vitest';

import { toneIcon } from './statusTone';

describe('toneIcon', () => {
  it('donne une icône Phosphor par ton', () => {
    expect(toneIcon('ok')).toBe('ph:check-circle');
    expect(toneIcon('danger')).toBe('ph:warning-circle');
  });
});
