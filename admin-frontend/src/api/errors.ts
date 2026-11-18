import { apiErrorText } from '@app/utils';

import { currentLocale } from '@/i18n/global';

/**
 * Readable text of an API error. The backend is language-agnostic: its
 * `{ error: { code, message, details } }` is translated here from the shared
 * catalogue (`@app/utils`, `apiErrors/{en,fr}.json`); the server's English
 * `message` is only the fallback of an uncatalogued code.
 */
export function extractApiError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { status?: number; data?: unknown } }).response;
    const data = resp?.data;
    if (typeof data === 'object' && data !== null) {
      // Backend AppError shape: { error: { code, message, details } }; OAuth2 default: { detail }
      const errorObj = (
        data as { error?: { code?: unknown; message?: unknown; details?: unknown } }
      ).error;
      if (errorObj) {
        const translated = apiErrorText(
          typeof errorObj.code === 'string' ? errorObj.code : null,
          typeof errorObj.details === 'object' && errorObj.details !== null
            ? (errorObj.details as Record<string, unknown>)
            : null,
          currentLocale(),
        );
        if (translated) return translated;
      }
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
      const message = (data as { message?: unknown }).message;
      if (typeof message === 'string') return message;
    }
  }
  return null;
}
