import React, { useEffect, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { getLastResult } from '../lib/store';
import PlatformCard from '../components/PlatformCard';
import AdviceCard from '../components/AdviceCard';
import { Colors } from '../constants/colors';
import type { SearchResponse } from '../types/api';

export default function ResultsScreen() {
  const router = useRouter();
  const [data, setData] = useState<SearchResponse | null>(null);

  useEffect(() => {
    const result = getLastResult();
    if (!result) {
      router.replace('/');
    } else {
      setData(result);
    }
  }, [router]);

  if (!data) return null;

  const { keyword_mapping, tw_listings, jp_listings, exchange_rate_jpy_twd, advice } = data;

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      {/* Product header */}
      <View style={styles.productHeader}>
        <View style={styles.categoryBadge}>
          <Ionicons name="pricetag" size={11} color={Colors.primary} />
          <Text style={styles.categoryText}>{keyword_mapping.category}</Text>
        </View>
        <Text style={styles.productName}>{keyword_mapping.refined_tw_keyword}</Text>
        <Text style={styles.jpKeyword}>🇯🇵 {keyword_mapping.refined_jp_keyword}</Text>
        <View style={styles.rateChip}>
          <Ionicons name="swap-horizontal" size={13} color={Colors.textSecondary} />
          <Text style={styles.rateText}>
            1 JPY = {exchange_rate_jpy_twd.toFixed(3)} TWD
          </Text>
        </View>
      </View>

      {/* ── Taiwan prices ── */}
      <SectionHeader market="TW" count={tw_listings.length} />
      <View style={styles.listings}>
        {tw_listings.map((l, i) => (
          <PlatformCard key={i} listing={l} market="TW" exchangeRate={exchange_rate_jpy_twd} />
        ))}
        {tw_listings.length === 0 && <EmptyState text="未找到台灣價格資料" />}
      </View>

      {/* ── Japan prices ── */}
      <SectionHeader market="JP" count={jp_listings.length} />
      <View style={styles.listings}>
        {jp_listings.map((l, i) => (
          <PlatformCard key={i} listing={l} market="JP" exchangeRate={exchange_rate_jpy_twd} />
        ))}
        {jp_listings.length === 0 && <EmptyState text="未找到日本價格資料" />}
      </View>

      {/* ── AI Advice ── */}
      <View style={styles.adviceSection}>
        <View style={styles.adviceHeader}>
          <Ionicons name="sparkles" size={18} color={Colors.gold} />
          <Text style={styles.adviceTitle}>AI 購買建議</Text>
        </View>
        <AdviceCard advice={advice} />
      </View>
    </ScrollView>
  );
}

/* ── sub-components ──────────────────────────────────────────────────────── */

function SectionHeader({ market, count }: { market: 'TW' | 'JP'; count: number }) {
  const isTW = market === 'TW';
  return (
    <View style={[styles.sectionHeader, { borderLeftColor: isTW ? Colors.tw : Colors.jp }]}>
      <Text style={styles.sectionFlag}>{isTW ? '🇹🇼' : '🇯🇵'}</Text>
      <Text style={styles.sectionTitle}>{isTW ? '台灣價格' : '日本價格'}</Text>
      <View style={[styles.countBadge, { backgroundColor: isTW ? Colors.twLight : Colors.jpLight }]}>
        <Text style={[styles.countText, { color: isTW ? Colors.tw : Colors.jp }]}>{count} 筆</Text>
      </View>
      {market === 'JP' && (
        <Text style={styles.taxNote}>含退稅試算</Text>
      )}
    </View>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <View style={styles.empty}>
      <Ionicons name="search-outline" size={28} color={Colors.border} />
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

/* ── styles ──────────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
  scroll:  { flex: 1, backgroundColor: Colors.background },
  content: { paddingBottom: 48 },

  /* product header */
  productHeader: {
    backgroundColor: Colors.card,
    padding: 16,
    marginBottom: 8,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
    gap: 6,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#FDECEA',
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 4,
    gap: 4,
  },
  categoryText: { fontSize: 11, fontWeight: '700', color: Colors.primary },
  productName:  { fontSize: 18, fontWeight: '800', color: Colors.text, lineHeight: 25 },
  jpKeyword:    { fontSize: 13, color: Colors.textSecondary },
  rateChip: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: Colors.background,
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 5,
    gap: 5,
    marginTop: 2,
  },
  rateText: { fontSize: 12, color: Colors.textSecondary, fontWeight: '600' },

  /* section headers */
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    borderLeftWidth: 4,
    marginHorizontal: 16,
    marginTop: 16,
    marginBottom: 8,
    paddingLeft: 10,
    gap: 6,
  },
  sectionFlag:  { fontSize: 18 },
  sectionTitle: { fontSize: 16, fontWeight: '800', color: Colors.text },
  countBadge:   { borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  countText:    { fontSize: 11, fontWeight: '700' },
  taxNote:      { fontSize: 11, color: Colors.gold, fontWeight: '600', marginLeft: 'auto' },

  listings: { paddingHorizontal: 16 },

  /* AI advice */
  adviceSection: {
    marginHorizontal: 16,
    marginTop: 24,
    gap: 12,
  },
  adviceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  adviceTitle: { fontSize: 17, fontWeight: '800', color: Colors.text },

  /* empty */
  empty: {
    alignItems: 'center',
    paddingVertical: 24,
    backgroundColor: Colors.card,
    borderRadius: 12,
    gap: 8,
  },
  emptyText: { fontSize: 13, color: Colors.textSecondary },
});
