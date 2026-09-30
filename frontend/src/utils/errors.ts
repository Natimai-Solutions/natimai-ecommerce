/**
 * Message lisible d'une erreur d'API (forme `AppError` du backend :
 * `{ error: { code, message } }`, ou `detail` FastAPI), sinon un repli selon le
 * statut HTTP. Remplace les copies locales de `extractError` des pages.
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
    const errorObj = (data as { error?: { message?: unknown } }).error;
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
