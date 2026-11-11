import { AsyncLocalStorage } from 'node:async_hooks';
import { afterAll, describe, expect, it } from 'vitest';
import { configureFormatting, formatContext, setFormatContextResolver } from '@app/utils';

import {
  REQUEST_SCOPE_KEY,
  currentRequestScope,
  requestFormatContext,
  type RequestScope,
} from './requestScope';

/**
 * Audit 2026-11, F1: two server renders interleaved at an `await` shared the
 * module-level language and formatting context.
 */
describe('one scope per server render', () => {
  const storage = new AsyncLocalStorage<RequestScope>();
  (globalThis as Record<symbol, unknown>)[REQUEST_SCOPE_KEY] = storage;
  setFormatContextResolver(requestFormatContext);

  afterAll(() => {
    setFormatContextResolver(null);
    delete (globalThis as Record<symbol, unknown>)[REQUEST_SCOPE_KEY];
  });

  const tick = () => new Promise((resolve) => setTimeout(resolve, 5));

  async function render(locale: string, timeZone: string) {
    return storage.run({}, async () => {
      currentRequestScope()!.locale = locale;
      configureFormatting({ locale, timeZone });
      await tick(); // the other render runs here
      return {
        locale: currentRequestScope()?.locale,
        format: { ...formatContext() },
      };
    });
  }

  it('keeps each request its own language and time zone', async () => {
    const [fr, en] = await Promise.all([
      render('fr', 'Pacific/Tahiti'),
      render('en', 'Europe/Paris'),
    ]);
    expect(fr).toEqual({ locale: 'fr', format: { locale: 'fr', timeZone: 'Pacific/Tahiti' } });
    expect(en).toEqual({ locale: 'en', format: { locale: 'en', timeZone: 'Europe/Paris' } });
  });

  it('leaves the module context alone outside a render', async () => {
    const before = { ...formatContext() };
    await render('en', 'Europe/Paris');
    expect(currentRequestScope()).toBeUndefined();
    expect(formatContext()).toEqual(before);
  });
});
