import { describe, expect, it, vi } from 'vitest';

vi.mock('@/boot/api', () => ({ api: {} }));

import { fillCannedReply } from './messaging';

const reply = {
  id: 'r1',
  position: 1,
  channel: null,
  title: 'Suivi',
  body: 'Bonjour {prenom}, votre commande {commande} ({numero}) est en route.',
  translations: {
    en: { title: 'Tracking', body: 'Hello {prenom}, order {commande} is on its way.' },
  },
};

describe('prepared answers (MSG4)', () => {
  it('fills the variables in the customer language', () => {
    const values = { prenom: 'Hina', commande: 'CMD-2026-00042', numero: 'C-2026-00001' };
    expect(fillCannedReply(reply, 'fr', values)).toBe(
      'Bonjour Hina, votre commande CMD-2026-00042 (C-2026-00001) est en route.',
    );
    expect(fillCannedReply(reply, 'en', values)).toBe(
      'Hello Hina, order CMD-2026-00042 is on its way.',
    );
  });
});
