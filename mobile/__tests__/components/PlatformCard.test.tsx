import React from 'react';
import { Linking } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
import PlatformCard from '../../components/PlatformCard';
import type { PriceListing } from '../../types/api';

const RATE = 0.218;

const twListing: PriceListing = {
  platform: 'momo購物網',
  title:    'Sony WH-1000XM5 無線降噪耳機 台灣版',
  price:    9900,
  currency: 'TWD',
  url:      'https://www.momoshop.com.tw/product/123',
};

const jpListing: PriceListing = {
  platform: 'Amazon Japan',
  title:    'ソニー WH-1000XM5',
  price:    41800,
  currency: 'JPY',
  url:      'https://www.amazon.co.jp/dp/B0BXX1234',
};

// ── Taiwan card ───────────────────────────────────────────────────────────

describe('PlatformCard – Taiwan (TWD)', () => {
  it('shows the platform name', () => {
    const { getByText } = render(<PlatformCard listing={twListing} market="TW" exchangeRate={RATE} />);
    expect(getByText('momo購物網')).toBeTruthy();
  });

  it('shows the product title', () => {
    const { getByText } = render(<PlatformCard listing={twListing} market="TW" exchangeRate={RATE} />);
    expect(getByText(twListing.title)).toBeTruthy();
  });

  it('displays TWD price in NT$ format', () => {
    const { getByText } = render(<PlatformCard listing={twListing} market="TW" exchangeRate={RATE} />);
    expect(getByText('NT$9,900')).toBeTruthy();
  });

  it('does NOT show JPY or conversion text for TW card', () => {
    const { queryByText } = render(<PlatformCard listing={twListing} market="TW" exchangeRate={RATE} />);
    expect(queryByText(/¥/)).toBeNull();
    expect(queryByText(/退稅/)).toBeNull();
  });

  it('renders a "前往購買" button', () => {
    const { getByText } = render(<PlatformCard listing={twListing} market="TW" exchangeRate={RATE} />);
    expect(getByText('前往購買')).toBeTruthy();
  });

  it('pressing "前往購買" calls Linking.openURL with the listing URL', () => {
    const spy = jest.spyOn(Linking, 'openURL').mockResolvedValueOnce(undefined);
    const { getByText } = render(<PlatformCard listing={twListing} market="TW" exchangeRate={RATE} />);
    fireEvent.press(getByText('前往購買'));
    expect(spy).toHaveBeenCalledWith(twListing.url);
    spy.mockRestore();
  });
});

// ── Japan card ────────────────────────────────────────────────────────────

describe('PlatformCard – Japan (JPY)', () => {
  it('shows the platform name', () => {
    const { getByText } = render(<PlatformCard listing={jpListing} market="JP" exchangeRate={RATE} />);
    expect(getByText('Amazon Japan')).toBeTruthy();
  });

  it('displays JPY price in ¥ format', () => {
    const { getByText } = render(<PlatformCard listing={jpListing} market="JP" exchangeRate={RATE} />);
    expect(getByText('¥41,800')).toBeTruthy();
  });

  it('shows TWD conversion (price × rate)', () => {
    const { getByText } = render(<PlatformCard listing={jpListing} market="JP" exchangeRate={RATE} />);
    const converted = Math.round(jpListing.price * RATE);        // 9112
    expect(getByText(`≈ NT$${converted.toLocaleString('zh-TW')}`)).toBeTruthy();
  });

  it('shows the 退稅後 (tax-free) badge', () => {
    const { getByText } = render(<PlatformCard listing={jpListing} market="JP" exchangeRate={RATE} />);
    expect(getByText(/退稅後/)).toBeTruthy();
  });

  it('tax-free price is 90% of converted TWD price', () => {
    const { getByText } = render(<PlatformCard listing={jpListing} market="JP" exchangeRate={RATE} />);
    const taxFree = Math.round(jpListing.price * RATE * 0.9);    // 8201
    expect(getByText(new RegExp(taxFree.toLocaleString('zh-TW')))).toBeTruthy();
  });

  it('renders a "前往購買" button', () => {
    const { getByText } = render(<PlatformCard listing={jpListing} market="JP" exchangeRate={RATE} />);
    expect(getByText('前往購買')).toBeTruthy();
  });
});
