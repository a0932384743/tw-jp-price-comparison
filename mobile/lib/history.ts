/**
 * Search history – persists to localStorage on web, in-memory on native.
 */

const STORAGE_KEY = 'tjpc_search_history';
const MAX_ITEMS = 8;

export interface HistoryItem {
  query: string;
  category?: string;
  timestamp: number;
}

let _items: HistoryItem[] = [];

// Hydrate from localStorage (web only)
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

export function addToHistory(query: string, category?: string): void {
  _items = [
    { query, category, timestamp: Date.now() },
    ..._items.filter((i) => i.query.toLowerCase() !== query.toLowerCase()),
  ].slice(0, MAX_ITEMS);
  persist();
}

export function getHistory(): HistoryItem[] {
  return _items;
}

export function clearHistory(): void {
  _items = [];
  persist();
}

export function removeFromHistory(query: string): void {
  _items = _items.filter((i) => i.query !== query);
  persist();
}
