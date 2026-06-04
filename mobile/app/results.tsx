import React, { useEffect, useMemo, useState } from 'react';
import {
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

import { getLastResult } from '../lib/store';
import { getPriceHistory } from '../lib/api';
import { isFavorite, toggleFavorite } from '../lib/favorites';
import PlatformCard from '../components/PlatformCard';
import AdviceCard from '../components/AdviceCard';
import { Colors } from '../constants/colors';
import type { BuyingAdvice, PriceHistoryPoint, SearchResponse } from '../types/api';

const LOCATION_LABELS: Record<string, string> = {
  Taiwan:  '🇹🇼 台灣較划算',
  Japan:   '🇯🇵 日本較划算',
  Similar: '🤝 兩地價格相近',
};
const LOCATION_COLOR: Record<string, string> = {
  Taiwan: Colors.tw,
  Japan:  Colors.jp,
  Similar: Colors.gold,
};
const LOCATION_BG: Record<string, string> = {
  Taiwan: Colors.twLight,
  Japan:  Colors.jpLight,
  Similar: Colors.goldLight,
};

function fmt(n: number | null) {
  if (n == null) return '—';
  return `NT$${Math.round(n).toLocaleString()}`;
}

/* ── Savings Banner ────────────────────────────────────────────────────────── */

function SavingsBanner({ advice }: { advice: BuyingAdvice }) {
  const color  = LOCATION_COLOR[advice.best_deal_location] ?? Colors.primary;
  const bg     = LOCATION_BG[advice.best_deal_location]    ?? Colors.card;
  const label  = LOCATION_LABELS[advice.best_deal_location] ?? advice.best_deal_location;

  const tw  = advice.tw_average_price_twd;
  const jp  = advice.jp_tax_free_price_twd;
  const savings = tw != null && jp != null ? Math.abs(tw - jp) : null;
  const max     = Math.max(tw ?? 0, jp ?? 0);
  const min     = Math.min(tw ?? Infinity, jp ?? Infinity);
  const savingsPct = savings != null && min > 0 ? Math.round((savings / max) * 100) : null;

  return (
    <View style={[s.banner, { backgroundColor: bg, borderColor: color }]}>
      {/* Header row */}
      <View style={s.bannerRow}>
        <Text style={[s.bannerLabel, { color }]}>{label}</Text>
        {savings != null && savings > 100 && (
          <View style={[s.savingsBadge, { backgroundColor: color }]}>
            <Text style={s.savingsText}>
              省 {fmt(savings)}{savingsPct != null && savingsPct >= 5 ? ` (${savingsPct}%)` : ''}
            </Text>
          </View>
        )}
      </View>

      {/* Price bar comparison */}
      {max > 0 && (
        <View style={s.bars}>
          {[
            { flag: '🇹🇼', label: '台灣均價', value: tw, barColor: Colors.tw },
            { flag: '🇯🇵', label: '日本退稅後', value: jp, barColor: Colors.jp },
          ].map((row) => (
            <View key={row.label} style={s.barRow}>
              <Text style={s.barFlag}>{row.flag}</Text>
              <View style={s.barTrack}>
                <View
                  style={[
                    s.barFill,
                    { width: `${(Math.max(row.value ?? 0, 0) / max) * 100}%`, backgroundColor: row.barColor },
                  ]}
                />
              </View>
              <Text style={[s.barValue, { color: row.barColor }]}>{fmt(row.value)}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Verdict */}
      <Text style={[s.verdict, { color }]} numberOfLines={3}>{advice.verdict}</Text>
    </View>
  );
}

/* ── Section Header ────────────────────────────────────────────────────────── */

function SectionHeader({ market, count }: { market: 'TW' | 'JP'; count: number }) {
  const isTW = market === 'TW';
  return (
    <View style={[s.sectionHeader, { borderLeftColor: isTW ? Colors.tw : Colors.jp }]}>
      <Text style={s.sectionFlag}>{isTW ? '🇹🇼' : '🇯🇵'}</Text>
      <Text style={s.sectionTitle}>{isTW ? '台灣價格' : '日本價格'}</Text>
      <View style={[s.countBadge, { backgroundColor: isTW ? Colors.twLight : Colors.jpLight }]}>
        <Text style={[s.countText, { color: isTW ? Colors.tw : Colors.jp }]}>{count} 筆</Text>
      </View>
      {!isTW && <Text style={s.taxNote}>含退稅試算</Text>}
    </View>
  );
}

/* ── Empty State ───────────────────────────────────────────────────────────── */

function EmptyState({ text }: { text: string }) {
  return (
    <View style={s.empty}>
      <Ionicons name="search-outline" size={28} color={Colors.border} />
      <Text style={s.emptyText}>{text}</Text>
    </View>
  );
}

/* ── Price History Chart ───────────────────────────────────────────────────── */

const BAR_MAX_H = 52;

function PriceHistoryChart({ keyword, market }: { keyword: string; market: 'TW' | 'JP'; rate: number }) {
  const [history, setHistory] = useState<PriceHistoryPoint[]>([]);

  useEffect(() => {
    getPriceHistory(keyword, market).then(setHistory).catch(() => {});
  }, [keyword, market]);

  if (history.length < 2) return null;

  const color = market === 'TW' ? Colors.tw : Colors.jp;
  const maxPrice = Math.max(...history.map(h => h.avg_price));
  const fmtPrice = (n: number) =>
    market === 'TW' ? `NT$${Math.round(n / 100) * 100}` : `¥${Math.round(n / 100) * 100}`;

  return (
    <View style={ph.container}>
      <View style={ph.header}>
        <Ionicons name="trending-up" size={15} color={color} />
        <Text style={[ph.title, { color }]}>{market === 'TW' ? '🇹🇼' : '🇯🇵'} 近 7 日均價走勢</Text>
      </View>
      <View style={ph.chart}>
        {history.map((point) => {
          const barH = Math.max(6, (point.avg_price / maxPrice) * BAR_MAX_H);
          return (
            <View key={point.date} style={ph.col}>
              <Text style={ph.priceLabel}>{fmtPrice(point.avg_price)}</Text>
              <View style={[ph.bar, { height: barH, backgroundColor: color }]} />
              <Text style={ph.dateLabel}>{point.date.slice(5)}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

/* ── Main Screen ───────────────────────────────────────────────────────────── */

export default function ResultsScreen() {
  const router = useRouter();
  const [data, setData] = useState<SearchResponse | null>(null);
  const [favorited, setFavorited] = useState(false);

  useEffect(() => {
    const result = getLastResult();
    if (!result) { router.replace('/'); return; }
    setData(result);
    setFavorited(isFavorite(result.keyword_mapping.refined_tw_keyword));
  }, [router]);

  const handleToggleFavorite = () => {
    if (!data) return;
    const nowFav = toggleFavorite(
      data.keyword_mapping.refined_tw_keyword,
      data.keyword_mapping.category,
    );
    setFavorited(nowFav);
  };

  const sortedTW = useMemo(
    () => [...(data?.tw_listings ?? [])].sort((a, b) => a.price - b.price),
    [data]
  );
  const sortedJP = useMemo(
    () => [...(data?.jp_listings ?? [])].sort((a, b) => a.price - b.price),
    [data]
  );

  if (!data) return null;

  const { keyword_mapping, exchange_rate_jpy_twd, advice, product_image_url, fetched_at } = data;

  const fetchedLabel = fetched_at
    ? (() => {
        const d = new Date(fetched_at);
        return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')} 抓取`;
      })()
    : null;

  return (
    <ScrollView
      style={s.scroll}
      contentContainerStyle={s.content}
      showsVerticalScrollIndicator={false}
    >
      {/* ── 1. Product header ── */}
      <LinearGradient colors={['#0F172A', '#1E3A5F']} style={s.productHeader}>
        <View style={s.headerTopRow}>
          <View style={s.categoryBadge}>
            <Ionicons name="pricetag" size={11} color="#fff" />
            <Text style={s.categoryText}>{keyword_mapping.category}</Text>
          </View>
          <TouchableOpacity onPress={handleToggleFavorite} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name={favorited ? 'heart' : 'heart-outline'} size={22} color={favorited ? '#F87171' : 'rgba(255,255,255,0.6)'} />
          </TouchableOpacity>
        </View>

        {/* Product image + names side by side */}
        <View style={s.headerMain}>
          {product_image_url && (
            <Image
              source={{ uri: product_image_url }}
              style={s.headerImage}
              resizeMode="contain"
            />
          )}
          <View style={s.headerText}>
            <Text style={s.productName}>{keyword_mapping.refined_tw_keyword}</Text>
            <Text style={s.jpKeyword}>🇯🇵 {keyword_mapping.refined_jp_keyword}</Text>
          </View>
        </View>

        <View style={s.headerBottomRow}>
          <View style={s.rateChip}>
            <Ionicons name="swap-horizontal" size={12} color="rgba(255,255,255,0.7)" />
            <Text style={s.rateText}>1 JPY = {exchange_rate_jpy_twd.toFixed(3)} TWD</Text>
          </View>
          {fetchedLabel && (
            <View style={s.fetchedChip}>
              <Ionicons name="time-outline" size={11} color="rgba(255,255,255,0.6)" />
              <Text style={s.fetchedText}>{fetchedLabel}</Text>
            </View>
          )}
        </View>
      </LinearGradient>

      {/* ── 2. Savings banner ── */}
      <View style={s.bannerWrapper}>
        <SavingsBanner advice={advice} />
      </View>

      {/* ── 3. Taiwan prices ── */}
      <SectionHeader market="TW" count={sortedTW.length} />
      <View style={s.listings}>
        {sortedTW.map((l, i) => (
          <PlatformCard key={i} listing={l} market="TW" exchangeRate={exchange_rate_jpy_twd} isCheapest={i === 0 && sortedTW.length > 1} thumbnailUrl={product_image_url} />
        ))}
        {sortedTW.length === 0 && <EmptyState text="未找到台灣價格資料" />}
      </View>

      {/* ── 4. Japan prices ── */}
      <SectionHeader market="JP" count={sortedJP.length} />
      <View style={s.listings}>
        {sortedJP.map((l, i) => (
          <PlatformCard key={i} listing={l} market="JP" exchangeRate={exchange_rate_jpy_twd} isCheapest={i === 0 && sortedJP.length > 1} thumbnailUrl={product_image_url} />
        ))}
        {sortedJP.length === 0 && <EmptyState text="未找到日本價格資料" />}
      </View>

      {/* ── 5. Price history charts ── */}
      <View style={s.historySection}>
        <PriceHistoryChart keyword={keyword_mapping.refined_tw_keyword} market="TW" rate={exchange_rate_jpy_twd} />
        <PriceHistoryChart keyword={keyword_mapping.refined_jp_keyword} market="JP" rate={exchange_rate_jpy_twd} />
      </View>

      {/* ── 6. Detailed AI analysis ── */}
      <View style={s.adviceSection}>
        <View style={s.adviceHeader}>
          <Ionicons name="sparkles" size={18} color={Colors.gold} />
          <Text style={s.adviceTitle}>詳細分析</Text>
        </View>
        <AdviceCard advice={advice} />
      </View>

      {/* ── 6. New search CTA ── */}
      <TouchableOpacity style={s.newSearchBtn} onPress={() => router.back()} activeOpacity={0.8}>
        <Ionicons name="search" size={16} color={Colors.primary} />
        <Text style={s.newSearchText}>搜尋其他商品</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  scroll:   { flex: 1, backgroundColor: Colors.background },
  content:  { paddingBottom: 56 },

  /* product header */
  productHeader: { padding: 16, paddingTop: 20, gap: 8 },
  headerTopRow:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerBottomRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 2 },
  headerMain:   { flexDirection: 'row', alignItems: 'center', gap: 14 },
  headerImage:  { width: 88, height: 88, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.1)', flexShrink: 0 },
  headerText:   { flex: 1, gap: 5 },
  categoryBadge: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 20,
    paddingHorizontal: 10, paddingVertical: 4, gap: 4,
  },
  categoryText: { fontSize: 11, fontWeight: '700', color: '#fff' },
  productName:  { fontSize: 18, fontWeight: '900', color: '#fff', lineHeight: 25 },
  jpKeyword:    { fontSize: 12, color: 'rgba(255,255,255,0.75)' },
  rateChip: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: 20,
    paddingHorizontal: 10, paddingVertical: 5, gap: 5,
  },
  rateText: { fontSize: 12, color: 'rgba(255,255,255,0.8)', fontWeight: '600' },
  fetchedChip: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 20,
    paddingHorizontal: 8, paddingVertical: 4, gap: 4,
  },
  fetchedText: { fontSize: 11, color: 'rgba(255,255,255,0.6)', fontWeight: '500' },

  /* price history */
  historySection: { marginHorizontal: 16, marginTop: 16, gap: 10 },

  /* savings banner */
  bannerWrapper: { marginHorizontal: 16, marginTop: 14 },
  banner: {
    borderWidth: 1.5,
    borderRadius: 16,
    padding: 16,
    gap: 12,
  },
  bannerRow:    { flexDirection: 'row', alignItems: 'center', gap: 10 },
  bannerLabel:  { fontSize: 17, fontWeight: '800', flex: 1 },
  savingsBadge: { borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 },
  savingsText:  { fontSize: 13, fontWeight: '800', color: '#fff' },

  bars:     { gap: 8 },
  barRow:   { flexDirection: 'row', alignItems: 'center', gap: 8 },
  barFlag:  { fontSize: 14, width: 22 },
  barTrack: { flex: 1, height: 8, backgroundColor: Colors.borderLight, borderRadius: 4, overflow: 'hidden' },
  barFill:  { height: 8, borderRadius: 4 },
  barValue: { fontSize: 12, fontWeight: '700', width: 80, textAlign: 'right' },

  verdict:  { fontSize: 13, lineHeight: 20 },

  /* section headers */
  sectionHeader: {
    flexDirection: 'row', alignItems: 'center',
    borderLeftWidth: 4, marginHorizontal: 16,
    marginTop: 20, marginBottom: 10, paddingLeft: 10, gap: 6,
  },
  sectionFlag:  { fontSize: 18 },
  sectionTitle: { fontSize: 16, fontWeight: '800', color: Colors.text },
  countBadge:   { borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  countText:    { fontSize: 11, fontWeight: '700' },
  taxNote:      { fontSize: 11, color: Colors.gold, fontWeight: '600', marginLeft: 'auto' },

  listings: { paddingHorizontal: 16, gap: 10 },

  /* advice */
  adviceSection: { marginHorizontal: 16, marginTop: 24, gap: 12 },
  adviceHeader:  { flexDirection: 'row', alignItems: 'center', gap: 8 },
  adviceTitle:   { fontSize: 17, fontWeight: '800', color: Colors.text },

  /* empty */
  empty:     { alignItems: 'center', paddingVertical: 28, backgroundColor: Colors.card, borderRadius: 12, gap: 8 },
  emptyText: { fontSize: 13, color: Colors.textSecondary },

  /* new search */
  newSearchBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    marginHorizontal: 16, marginTop: 24,
    borderWidth: 1.5, borderColor: Colors.primary,
    borderRadius: 12, paddingVertical: 13, gap: 8,
  },
  newSearchText: { fontSize: 15, fontWeight: '700', color: Colors.primary },
});

const ph = StyleSheet.create({
  container: {
    backgroundColor: Colors.card,
    borderRadius: 14,
    padding: 14,
    gap: 10,
    shadowColor: Colors.shadowMd,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 8,
    elevation: 3,
  },
  header:     { flexDirection: 'row', alignItems: 'center', gap: 6 },
  title:      { fontSize: 13, fontWeight: '700' },
  chart:      { flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: BAR_MAX_H + 32 },
  col:        { flex: 1, alignItems: 'center', justifyContent: 'flex-end', gap: 4 },
  bar:        { width: '100%', borderRadius: 4, minHeight: 6 },
  priceLabel: { fontSize: 9, color: Colors.textTertiary, textAlign: 'center' },
  dateLabel:  { fontSize: 9, color: Colors.textSecondary, textAlign: 'center' },
});
