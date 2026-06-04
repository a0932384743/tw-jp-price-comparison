import React from 'react';
import { act, render } from '@testing-library/react-native';
import LoadingOverlay from '../../components/LoadingOverlay';

beforeEach(() => jest.useFakeTimers());
afterEach(() => {
  act(() => { jest.runOnlyPendingTimers(); });
  jest.useRealTimers();
});

describe('LoadingOverlay', () => {
  it('renders without crashing', () => {
    expect(() => render(<LoadingOverlay />)).not.toThrow();
  });

  it('shows the first step label on mount', () => {
    const { getByText } = render(<LoadingOverlay />);
    expect(getByText('AI 識別商品中…')).toBeTruthy();
  });

  it('shows the normal hint text by default', () => {
    const { getByText } = render(<LoadingOverlay />);
    expect(getByText('通常需要 10–20 秒')).toBeTruthy();
  });

  it('renders a dark overlay background', () => {
    const { toJSON } = render(<LoadingOverlay />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain('rgba(0,0,0,0.6)');
  });

  it('renders with a high zIndex to sit on top of content', () => {
    const { toJSON } = render(<LoadingOverlay />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain('"zIndex":999');
  });

  it('shows cold-start hint when coldStart=true', () => {
    const { getByText } = render(<LoadingOverlay coldStart />);
    expect(getByText('首次請求需喚醒後端，約 30 秒')).toBeTruthy();
  });

  it('shows the wake-up banner when coldStart=true', () => {
    const { getByText } = render(<LoadingOverlay coldStart />);
    expect(getByText('後端喚醒中，請稍候…')).toBeTruthy();
  });
});
