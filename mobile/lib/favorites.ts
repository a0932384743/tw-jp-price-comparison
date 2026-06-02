/**
 * Favorites / watchlist – persists to localStorage on web, in-memory on native.
 */

const STORAGE_KEY = 'tjpc_favorites';
const MAX_ITEMS = 20;

export interface FavoriteItem {
  keyword: string;
  category?: string;
  savedAt: number;
}

let _items: FavoriteItem[] = [];

try {
  if (typeof localStorage !== 'undefined') {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) _items = JSON.parse(raw);
  }
} catch {}

function persist() {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(_items));
    }
  } catch {}
}

export function getFavorites(): FavoriteItem[] {
  return [..._items];
}

export function isFavorite(keyword: string): boolean {
  return _items.some(i => i.keyword.toLowerCase() === keyword.toLowerCase());
}

export function addFavorite(keyword: string, category?: string): void {
  if (!isFavorite(keyword)) {
    _items = [{ keyword, category, savedAt: Date.now() }, ..._items].slice(0, MAX_ITEMS);
    persist();
  }
}

export function removeFavorite(keyword: string): void {
  _items = _items.filter(i => i.keyword.toLowerCase() !== keyword.toLowerCase());
  persist();
}

export function toggleFavorite(keyword: string, category?: string): boolean {
  if (isFavorite(keyword)) {
    removeFavorite(keyword);
    return false;
  }
  addFavorite(keyword, category);
  return true;
}
