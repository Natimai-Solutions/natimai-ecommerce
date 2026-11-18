import { apiErrorText } from '@app/utils';

import { currentLocale } from '@/i18n/global';

/**
 * Message lisible d'une erreur d'API (forme `AppError` du backend :
 * `{ error: { code, message, details } }`, ou `detail` FastAPI), sinon un
 * repli selon le statut HTTP. Le code est traduit depuis le catalogue partagé
 * (`@app/utils`, `apiErrors/{en,fr}.json`) dans la langue de l'interface ; le
 * message du serveur (anglais) n'est qu'un repli pour un code non catalogué.
 */
export interface ApiErrorFallbacks {
  /** Message pour une réponse 404. */
  notFound?: string;
  /** Message pour une réponse 403. */
  forbidden?: string;
}

interface ErrorResponseShape {
  response?: { status?: number; data?: unknown };
}

export function apiErrorMessage(err: unknown, fallbacks: ApiErrorFallbacks = {}): string | null {
  if (typeof err !== 'object' || err === null || !('response' in err)) return null;
  const response = (err as ErrorResponseShape).response;
  const data = response?.data;
  if (typeof data === 'object' && data !== null) {
    const errorObj = (data as { error?: { code?: unknown; message?: unknown; details?: unknown } })
      .error;
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
    if (errorObj && typeof errorObj.message === 'string' && errorObj.message) {
      return errorObj.message;
    }
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail) return detail;
  }
  if (response?.status === 404 && fallbacks.notFound) return fallbacks.notFound;
  if (response?.status === 403 && fallbacks.forbidden) return fallbacks.forbidden;
  return null;
}

/** Code stable d'une erreur `AppError` (`user.password.invalid_current`…). */
export function apiErrorCode(err: unknown): string | null {
  if (typeof err !== 'object' || err === null || !('response' in err)) return null;
  const data = (err as ErrorResponseShape).response?.data;
  if (typeof data !== 'object' || data === null) return null;
  const code = (data as { error?: { code?: unknown } }).error?.code;
  return typeof code === 'string' ? code : null;
}
