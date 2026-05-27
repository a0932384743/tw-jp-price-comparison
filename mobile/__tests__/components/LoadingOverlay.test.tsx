import React from 'react';
import { act, render } from '@testing-library/react-native';
import LoadingOverlay from '../../components/LoadingOverlay';

// Prevent Animated.loop from firing outside act() by freezing timers
beforeEach(() => jest.useFakeTimers());
afterEach(() => {
  act(() => { jest.runOnlyPendingTimers(); });
  jest.useRealTimers();
});

describe('LoadingOverlay', () => {
  it('renders without crashing', () => {
    expect(() => render(<LoadingOverlay />)).not.toThrow();
  });

  it('displays the AI analysis heading', () => {
    const { getByText } = render(<LoadingOverlay />);
    expect(getByText('AI 正在分析中')).toBeTruthy();
  });

  it('displays the sub-description', () => {
    const { getByText } = render(<LoadingOverlay />);
    expect(getByText('識別商品、查詢台日價格')).toBeTruthy();
  });

  it('renders the robot emoji', () => {
    const { getByText } = render(<LoadingOverlay />);
    expect(getByText('🤖')).toBeTruthy();
  });

  it('covers the screen (absoluteFill overlay)', () => {
    const { toJSON } = render(<LoadingOverlay />);
    const tree = JSON.stringify(toJSON());
    // The overlay style includes position:absolute which manifests as absoluteFill
    expect(tree).toContain('absolute');
  });
});
