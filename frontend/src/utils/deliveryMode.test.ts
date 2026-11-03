import { describe, expect, it } from 'vitest';

import { deliveryModeLabel } from './deliveryMode';

const t = (key: string) => `[${key}]`;

describe('deliveryModeLabel', () => {
  it('translates the predefined modes', () => {
    expect(deliveryModeLabel('pickup', t)).toBe('[delivery_mode.pickup]');
    expect(deliveryModeLabel('home_delivery', t)).toBe('[delivery_mode.home_delivery]');
  });

  it('prettifies a custom code', () => {
    expect(deliveryModeLabel('pickup_taravao', t)).toBe('Pickup Taravao');
    expect(deliveryModeLabel('express-moorea', t)).toBe('Express Moorea');
  });
});
