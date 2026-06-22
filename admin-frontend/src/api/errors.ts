/** Extract a human-readable message from a backend AppError / Axios error. */
export function extractApiError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { status?: number; data?: unknown } }).response
    const data = resp?.data
    if (typeof data === 'object' && data !== null) {
      // Backend AppError shape: { error: { message } }; OAuth2 default: { detail }
      const errorObj = (data as { error?: { message?: unknown } }).error
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
      const message = (data as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  }
  return null
}
