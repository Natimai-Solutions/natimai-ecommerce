import { describe, expect, it } from 'vitest';

import { apiErrorCode, apiErrorMessage } from './errors';

describe('apiErrorMessage', () => {
  it("lit le message d'une AppError", () => {
    const err = { response: { status: 400, data: { error: { code: 'x.y', message: 'Refusé' } } } };
    expect(apiErrorMessage(err)).toBe('Refusé');
    expect(apiErrorCode(err)).toBe('x.y');
  });

  it('lit le detail FastAPI', () => {
    expect(apiErrorMessage({ response: { data: { detail: 'Non trouvé' } } })).toBe('Non trouvé');
  });

  it('retombe sur le message du statut HTTP', () => {
    const err = { response: { status: 404, data: {} } };
    expect(apiErrorMessage(err, { notFound: 'Introuvable' })).toBe('Introuvable');
    expect(apiErrorMessage(err)).toBeNull();
  });

  it("ignore ce qui n'est pas une erreur HTTP", () => {
    expect(apiErrorMessage(new Error('réseau'))).toBeNull();
    expect(apiErrorCode(null)).toBeNull();
  });
});
