import { Platform } from 'react-native';
import type { PriceHistoryPoint, SearchResponse } from '../types/api';

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

async function handleResponse(res: Response): Promise<SearchResponse> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      if (json.detail) message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

/** Build a backend-proxied thumbnail URL for a website screenshot.
 *  The /api/thumbnail endpoint fetches via mshots server-side, so the
 *  browser receives the image from our own origin with CORS headers. */
export function thumbnailProxyUrl(pageUrl: string): string {
  return `${API_URL}/api/thumbnail?url=${encodeURIComponent(pageUrl)}`;
}

export async function searchByText(query: string): Promise<SearchResponse> {
  const form = new FormData();
  form.append('query', query);
  const res = await fetch(`${API_URL}/api/search`, { method: 'POST', body: form });
  return handleResponse(res);
}

export async function getPriceHistory(keyword: string, market: string): Promise<PriceHistoryPoint[]> {
  try {
    const res = await fetch(
      `${API_URL}/api/price-history?keyword=${encodeURIComponent(keyword)}&market=${encodeURIComponent(market)}`
    );
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function searchByImage(uri: string, mimeType = 'image/jpeg'): Promise<SearchResponse> {
  const form = new FormData();

  if (Platform.OS === 'web') {
    // On web, the URI is a blob: or data: URL — fetch it to get the actual Blob,
    // then wrap in a File so FormData sends proper multipart binary data.
    const fetched = await fetch(uri);
    const blob = await fetched.blob();
    form.append('image', new File([blob], 'product.jpg', { type: blob.type || mimeType }));
  } else {
    // React Native native fetch understands the { uri, type, name } shorthand.
    form.append('image', { uri, type: mimeType, name: 'product.jpg' } as unknown as Blob);
  }

  const res = await fetch(`${API_URL}/api/search`, { method: 'POST', body: form });
  return handleResponse(res);
}
