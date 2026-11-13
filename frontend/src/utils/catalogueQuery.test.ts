import { describe, expect, it } from 'vitest';

import { specSelectionsFromQuery } from './catalogueQuery';

describe('specification filters read from the URL', () => {
  it('keeps well-formed keys', () => {
    expect(specSelectionsFromQuery({ 'f.memory_gb': '8|16', 'min.screen-in': '13' })).toEqual({
      enums: { memory_gb: ['8', '16'] },
      mins: { 'screen-in': 13 },
    });
  });

  it('never writes a prototype key', () => {
    const { enums, mins } = specSelectionsFromQuery({
      'f.__proto__': 'polluted',
      'f.constructor': 'x',
      'min.prototype': '1',
      'f.bad key': 'x',
    });
    expect(Object.keys(enums)).toEqual([]);
    expect(Object.keys(mins)).toEqual([]);
    expect(({} as Record<string, unknown>)['polluted']).toBeUndefined();
    expect(Object.getPrototypeOf(enums)).toBe(Object.prototype);
  });
});
