/**
 * Text of an API error in the interface language.
 *
 * The API is language-agnostic (decision of 18/11/2026): an error is
 * `{ code, message, details }`, `message` being an English fallback. The
 * interfaces translate the `code` from this catalogue — the same file for the
 * storefront and the admin — with the `details` filling the `{placeholders}`.
 * A code missing here falls back on the server's message (see
 * `backend/app/tests/test_api_error_catalog.py`, which keeps the catalogue
 * complete).
 */
import en from "./en.json";
import fr from "./fr.json";

const FALLBACK: Record<string, string> = fr;
const CATALOGUES: Record<string, Record<string, string>> = { en, fr };
const PLACEHOLDER = /\{([a-z_][a-z0-9_]*)\}/g;

/** `{name}` replaced by `details.name` when it is there. */
export function fillPlaceholders(
  text: string,
  details: Record<string, unknown> = {},
): string {
  return text.replace(PLACEHOLDER, (whole, name: string) => {
    const value = details[name];
    return value === undefined || value === null ? whole : String(value);
  });
}

/**
 * The catalogue's text for `code` in `locale` (`fr`, `en`, `fr-FR`…), or
 * null when the code is not catalogued — or a placeholder has no value (the
 * server's fallback is then better than a text with a hole).
 */
export function apiErrorText(
  code: string | null | undefined,
  details: Record<string, unknown> | null | undefined,
  locale: string | null | undefined,
): string | null {
  if (!code) return null;
  const lang = (locale ?? "fr").slice(0, 2).toLowerCase();
  const catalogue = CATALOGUES[lang] ?? FALLBACK;
  // A refusal says why in `details.reason` (`checkout.discount.refused` +
  // `expired`): its own text when the catalogue has one.
  const reason = details?.reason;
  const text =
    (typeof reason === "string" ? catalogue[`${code}.${reason}`] : undefined) ??
    catalogue[code];
  if (!text) return null;
  const filled = fillPlaceholders(text, details ?? {});
  return PLACEHOLDER.test(filled) ? null : filled;
}

/** Every catalogued code (tests). */
export const API_ERROR_CODES: readonly string[] = Object.keys(en);
