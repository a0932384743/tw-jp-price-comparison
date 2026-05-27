import { searchByText, searchByImage } from '../../lib/api';
import type { SearchResponse } from '../../types/api';

const mockResponse: SearchResponse = {
  keyword_mapping: {
    refined_tw_keyword: 'Sony WH-1000XM5',
    refined_jp_keyword: 'ソニー WH-1000XM5',
    category: '電子產品',
  },
  tw_listings: [
    { platform: 'momo購物網', title: 'Sony 耳機', price: 9900, currency: 'TWD', url: 'https://momo.example' },
  ],
  jp_listings: [
    { platform: 'Amazon Japan', title: 'Sony WH-1000XM5', price: 41800, currency: 'JPY', url: 'https://amazon.co.jp/example' },
  ],
  exchange_rate_jpy_twd: 0.218,
  advice: {
    price_comparison_summary: '日本退稅後較划算。',
    best_deal_location: 'Japan',
    tw_average_price_twd: 9900,
    jp_average_price_twd: 9112,
    jp_tax_free_price_twd: 8201,
    pros_cons: { pros: ['退稅優惠'], cons: ['需自行攜回'] },
    verdict: '建議在日本購買。',
  },
};

// ── fetch mock setup ───────────────────────────────────────────────────────

const mockFetch = jest.fn<Promise<Response>, [RequestInfo, RequestInit?]>();
global.fetch = mockFetch as typeof fetch;

function respondWith(body: unknown, ok = true, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok,
    status,
    json: async () => body,
  } as Response);
}

beforeEach(() => mockFetch.mockClear());

// ── searchByText ───────────────────────────────────────────────────────────

describe('searchByText', () => {
  it('POSTs to /api/search with FormData', async () => {
    respondWith(mockResponse);
    await searchByText('Sony WH-1000XM5');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(String(url)).toContain('/api/search');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
  });

  it('returns the parsed JSON response', async () => {
    respondWith(mockResponse);
    const result = await searchByText('Sony WH-1000XM5');
    expect(result).toEqual(mockResponse);
  });

  it('throws an Error when the server returns a non-ok status', async () => {
    respondWith({ detail: 'Pipeline error: timeout' }, false, 500);
    await expect(searchByText('test')).rejects.toThrow('Pipeline error: timeout');
  });

  it('falls back to "HTTP <status>" when the error body has no detail field', async () => {
    respondWith({}, false, 503);
    await expect(searchByText('test')).rejects.toThrow('HTTP 503');
  });
});

// ── searchByImage ──────────────────────────────────────────────────────────

describe('searchByImage', () => {
  it('POSTs to /api/search with FormData containing an image field', async () => {
    respondWith(mockResponse);
    await searchByImage('file:///tmp/product.jpg', 'image/jpeg');

    const [url, init] = mockFetch.mock.calls[0];
    expect(String(url)).toContain('/api/search');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
  });

  it('returns the parsed JSON response', async () => {
    respondWith(mockResponse);
    const result = await searchByImage('file:///tmp/product.jpg');
    expect(result).toEqual(mockResponse);
  });

  it('throws on HTTP error', async () => {
    respondWith({ detail: 'Image too large' }, false, 413);
    await expect(searchByImage('file:///tmp/big.jpg')).rejects.toThrow('Image too large');
  });
});
