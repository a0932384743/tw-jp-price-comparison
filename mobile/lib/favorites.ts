/**
 * Favorites / watchlist – persists to AsyncStorage on native, localStorage on web.
 * Reads are synchronous (from in-memory cache). Writes return Promises.
 */

import { Platform } from 'react-native';

const STORAGE_KEY = 'tjpc_favorites';
const MAX_ITEMS = 50;

export interface FavoriteItem {
  keyword: string;
  category?: string;
  savedAt: number;
  image_url?: string;
  tw_min?: number;
  jp_min_twd?: number;
  best_deal?: 'Taiwan' | 'Japan' | 'Similar';
}

export interface FavoriteExtras {
  image_url?: string;
  tw_min?: number;
  jp_min_twd?: number;
  best_deal?: 'Taiwan' | 'Japan' | 'Similar';
}

let _items: FavoriteItem[] = [];
let _loaded = false;

// --- persistence helpers ---

async function persistAsync(items: FavoriteItem[]): Promise<void> {
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
 * Load favorites from storage into memory. Idempotent — subsequent calls
 * return the already-cached list without re-reading storage.
 */
export async function loadFavorites(): Promise<FavoriteItem[]> {
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
export function getFavorites(): FavoriteItem[] {
  return [..._items];
}

/** Synchronous read from in-memory cache. */
export function isFavorite(keyword: string): boolean {
  return _items.some(i => i.keyword.toLowerCase() === keyword.toLowerCase());
}

export async function addFavorite(
  keyword: string,
  category?: string,
  extras?: FavoriteExtras,
): Promise<void> {
  if (!isFavorite(keyword)) {
    _items = [
      { keyword, category, savedAt: Date.now(), ...extras },
      ..._items,
    ].slice(0, MAX_ITEMS);
    await persistAsync(_items);
  }
}

export async function removeFavorite(keyword: string): Promise<void> {
  _items = _items.filter(i => i.keyword.toLowerCase() !== keyword.toLowerCase());
  await persistAsync(_items);
}

export async function toggleFavorite(
  keyword: string,
  category?: string,
  extras?: FavoriteExtras,
): Promise<boolean> {
  if (isFavorite(keyword)) {
    await removeFavorite(keyword);
    return false;
  }
  await addFavorite(keyword, category, extras);
  return true;
}
