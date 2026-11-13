import type { LocationQuery } from 'vue-router';

const SPEC_KEY = /^[A-Za-z0-9_-]{1,50}$/;

/** A spec key read from the URL, or null when it is not one. */
export function specKey(raw: string): string | null {
  if (raw === '__proto__' || raw === 'constructor' || raw === 'prototype') return null;
  return SPEC_KEY.test(raw) ? raw : null;
}

function nonNegative(raw: string): number | null {
  if (raw.trim() === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/**
 * The specification filters of a catalogue URL: `f.<key>=a|b` (values) and
 * `min.<key>=n` (a minimum). The keys come from the URL, so only well-formed
 * spec keys are kept, in objects with no prototype — a `f.__proto__=…` link
 * must not reach Object.prototype (CodeQL, audit 2026-11 follow-up).
 */
export function specSelectionsFromQuery(query: LocationQuery): {
  enums: Record<string, string[]>;
  mins: Record<string, number | null>;
} {
  const enums: Record<string, string[]> = Object.create(null);
  const mins: Record<string, number | null> = Object.create(null);
  for (const [name, raw] of Object.entries(query)) {
    if (typeof raw !== 'string' || raw === '') continue;
    const enumKey = name.startsWith('f.') ? specKey(name.slice(2)) : null;
    if (enumKey) enums[enumKey] = raw.split('|').filter(Boolean);
    const minKey = name.startsWith('min.') ? specKey(name.slice(4)) : null;
    if (minKey) {
      const value = nonNegative(raw);
      if (value !== null) mins[minKey] = value;
    }
  }
  return { enums: { ...enums }, mins: { ...mins } };
}
