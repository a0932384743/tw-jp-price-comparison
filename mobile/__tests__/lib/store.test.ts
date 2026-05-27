import type { SearchResponse } from '../../types/api';

// Re-import the module fresh each test suite via jest module registry
let setLastResult: (r: SearchResponse) => void;
let getLastResult: () => SearchResponse | null;

beforeEach(() => {
  jest.resetModules();
  ({ setLastResult, getLastResult } = require('../../lib/store'));
});

const makeResult = (id: string): SearchResponse => ({
  keyword_mapping: { refined_tw_keyword: id, refined_jp_keyword: id, category: '電子產品' },
  tw_listings: [],
  jp_listings: [],
  exchange_rate_jpy_twd: 0.218,
  advice: {
    price_comparison_summary: 'summary',
    best_deal_location: 'Taiwan',
    tw_average_price_twd: 1000,
    jp_average_price_twd: 1200,
    jp_tax_free_price_twd: 1080,
    pros_cons: { pros: [], cons: [] },
    verdict: 'verdict',
  },
});

describe('store', () => {
  it('returns null before any result is stored', () => {
    expect(getLastResult()).toBeNull();
  });

  it('stores and retrieves a result', () => {
    const result = makeResult('test-1');
    setLastResult(result);
    expect(getLastResult()).toBe(result);
  });

  it('overwrites the previous result', () => {
    const first  = makeResult('first');
    const second = makeResult('second');
    setLastResult(first);
    setLastResult(second);
    expect(getLastResult()).toBe(second);
  });

  it('retrieved reference is identical to what was stored', () => {
    const result = makeResult('same-ref');
    setLastResult(result);
    expect(getLastResult()).toStrictEqual(result);
  });
});
