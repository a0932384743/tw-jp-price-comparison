/**
 * Search history – persists to AsyncStorage on native, localStorage on web.
 * Reads are synchronous (from in-memory cache). Writes return Promises.
 */

import { Platform } from 'react-native';

const STORAGE_KEY = 'tjpc_search_history';
const MAX_ITEMS = 30;

export interface HistoryItem {
  query: string;
  keyword?: string;
  category?: string;
  timestamp: number;
  tw_min?: number;
  jp_min_twd?: number;
  best_deal?: 'Taiwan' | 'Japan' | 'Similar';
}

export interface HistoryAddOpts {
  keyword?: string;
  category?: string;
  tw_min?: number;
  jp_min_twd?: number;
  best_deal?: 'Taiwan' | 'Japan' | 'Similar';
}

let _items: HistoryItem[] = [];
let _loaded = false;

// --- persistence helpers ---

async function persistAsync(items: HistoryItem[]): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
      }
    } catch {}
  } else {
    try {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {}
  }
}

// --- public API ---

/**
 * Load history from storage into memory. Idempotent — subsequent calls
 * return the already-cached list without re-reading storage.
 */
export async function loadHistory(): Promise<HistoryItem[]> {
  if (_loaded) return [..._items];

  try {
    if (Platform.OS === 'web') {
      if (typeof localStorage !== 'undefined') {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) _items = JSON.parse(raw);
      }
    } else {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) _items = JSON.parse(raw);
    }
  } catch {}

  _loaded = true;
  return [..._items];
}

/** Synchronous read from in-memory cache. */
export function getHistory(): HistoryItem[] {
  return [..._items];
}

export async function addToHistory(query: string, opts?: HistoryAddOpts): Promise<void> {
  _items = [
    { query, timestamp: Date.now(), ...opts },
    ..._items.filter(i => i.query.toLowerCase() !== query.toLowerCase()),
  ].slice(0, MAX_ITEMS);
  await persistAsync(_items);
}

export async function clearHistory(): Promise<void> {
  _items = [];
  await persistAsync(_items);
}

export async function removeFromHistory(query: string): Promise<void> {
  _items = _items.filter(i => i.query !== query);
  await persistAsync(_items);
}
