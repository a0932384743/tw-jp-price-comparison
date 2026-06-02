import { Colors } from '../../constants/colors';

const HEX_RE = /^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/;

const REQUIRED_KEYS = [
  'primary', 'primaryLight',
  'tw', 'twLight',
  'jp', 'jpLight',
  'gold', 'goldLight',
  'background', 'card', 'border', 'disabled', 'shadow',
  'text', 'textSecondary',
  'error',
] as const;

describe('Colors palette', () => {
  it('exports all required keys', () => {
    for (const key of REQUIRED_KEYS) {
      expect(Colors).toHaveProperty(key);
    }
  });

  it('every value is a valid hex colour string', () => {
    for (const [key, value] of Object.entries(Colors)) {
      expect(value).toMatch(HEX_RE), `Colors.${key} = "${value}" is not a valid hex colour`;
    }
  });

  it('TW and JP accent colours are distinct', () => {
    expect(Colors.tw).not.toBe(Colors.jp);
    expect(Colors.twLight).not.toBe(Colors.jpLight);
  });

  it('primary is darker than primaryLight', () => {
    // A simple luminance heuristic: primary has lower sum of RGB channels
    const parse = (hex: string) =>
      [1, 3, 5].reduce((sum, i) => sum + parseInt(hex.slice(i, i + 2), 16), 0);
    expect(parse(Colors.primary)).toBeLessThan(parse(Colors.primaryLight));
  });
});
