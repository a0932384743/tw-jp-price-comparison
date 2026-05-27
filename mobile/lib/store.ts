/**
 * Minimal in-memory store to pass search results between screens
 * without URL serialisation overhead.
 */
import type { SearchResponse } from '../types/api';

let _result: SearchResponse | null = null;

export function setLastResult(result: SearchResponse): void {
  _result = result;
}

export function getLastResult(): SearchResponse | null {
  return _result;
}
