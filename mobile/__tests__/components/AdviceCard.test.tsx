import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import AdviceCard from '../../components/AdviceCard';
import type { BuyingAdvice } from '../../types/api';

const makeTWAdvice = (): BuyingAdvice => ({
  price_comparison_summary: '台灣平均售價 NT$9,900，日本換算後約 NT$9,112，退稅後約 NT$8,201。',
  best_deal_location: 'Taiwan',
  tw_average_price_twd: 9900,
  jp_average_price_twd: 9112,
  jp_tax_free_price_twd: 8201,
  pros_cons: {
    pros: ['台灣本地保固', '快速到貨'],
    cons: ['無退稅優惠'],
  },
  verdict: '建議在台灣購買，享受完整本地服務。',
});

const makeJPAdvice = (): BuyingAdvice => ({
  price_comparison_summary: '日本退稅後省約 NT$1,700。',
  best_deal_location: 'Japan',
  tw_average_price_twd: 9900,
  jp_average_price_twd: 9112,
  jp_tax_free_price_twd: 8201,
  pros_cons: {
    pros: ['退稅後省 NT$1,700'],
    cons: ['需加計運費 NT$400', '保固限制'],
  },
  verdict: '赴日時於實體門市退稅購買最划算。',
});

const makeSimilarAdvice = (): BuyingAdvice => ({
  ...makeTWAdvice(),
  best_deal_location: 'Similar',
  verdict: '兩地價格相近，就近購買即可。',
});

// ── Summary ───────────────────────────────────────────────────────────────

describe('AdviceCard – summary', () => {
  it('shows the price_comparison_summary', () => {
    const advice = makeTWAdvice();
    const { getByText } = render(<AdviceCard advice={advice} />);
    expect(getByText(advice.price_comparison_summary)).toBeTruthy();
  });

  it('shows the 📊 比價摘要 section title', () => {
    const { getByText } = render(<AdviceCard advice={makeTWAdvice()} />);
    expect(getByText('📊 比價摘要')).toBeTruthy();
  });
});

// ── Verdict ───────────────────────────────────────────────────────────────

describe('AdviceCard – verdict', () => {
  it('shows the verdict text', () => {
    const advice = makeTWAdvice();
    const { getByText } = render(<AdviceCard advice={advice} />);
    expect(getByText(advice.verdict)).toBeTruthy();
  });

  it('shows the verdict for Japan advice', () => {
    const advice = makeJPAdvice();
    const { getByText } = render(<AdviceCard advice={advice} />);
    expect(getByText(advice.verdict)).toBeTruthy();
  });

  it('shows the verdict for Similar advice', () => {
    const advice = makeSimilarAdvice();
    const { getByText } = render(<AdviceCard advice={advice} />);
    expect(getByText(advice.verdict)).toBeTruthy();
  });
});

// ── Pros / Cons accordion ─────────────────────────────────────────────────

describe('AdviceCard – pros/cons accordion', () => {
  it('hides pros/cons items by default', () => {
    const { queryByText } = render(<AdviceCard advice={makeTWAdvice()} />);
    expect(queryByText(/台灣本地保固/)).toBeNull();
    expect(queryByText(/無退稅優惠/)).toBeNull();
  });

  it('reveals pros after pressing 優缺點分析', () => {
    const { getByText, queryByText } = render(<AdviceCard advice={makeTWAdvice()} />);
    fireEvent.press(getByText('優缺點分析'));
    expect(queryByText(/台灣本地保固/)).toBeTruthy();
  });

  it('reveals cons after pressing 優缺點分析', () => {
    const { getByText, queryByText } = render(<AdviceCard advice={makeTWAdvice()} />);
    fireEvent.press(getByText('優缺點分析'));
    expect(queryByText(/無退稅優惠/)).toBeTruthy();
  });

  it('collapses on second press', () => {
    const { getByText, queryByText } = render(<AdviceCard advice={makeTWAdvice()} />);
    fireEvent.press(getByText('優缺點分析'));
    fireEvent.press(getByText('優缺點分析'));
    expect(queryByText(/台灣本地保固/)).toBeNull();
  });

  it('shows multiple pros and cons for Japan advice', () => {
    const advice = makeJPAdvice();
    const { getByText, queryAllByText, queryByText } = render(<AdviceCard advice={advice} />);
    fireEvent.press(getByText('優缺點分析'));
    expect(queryAllByText(/退稅後省/).length).toBeGreaterThan(0);
    expect(queryByText(/需加計運費/)).toBeTruthy();
    expect(queryByText(/保固限制/)).toBeTruthy();
  });
});
