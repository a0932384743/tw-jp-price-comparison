import React, { useState } from 'react';
import { LayoutAnimation, Platform, StyleSheet, Text, TouchableOpacity, UIManager, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../constants/colors';
import type { BuyingAdvice } from '../types/api';

if (Platform.OS === 'android') {
  UIManager.setLayoutAnimationEnabledExperimental?.(true);
}

interface Props {
  advice: BuyingAdvice;
}

const LOCATION_LABELS: Record<string, string> = {
  Taiwan:  '🇹🇼 台灣較划算',
  Japan:   '🇯🇵 日本較划算',
  Similar: '🤝 兩地價格相近',
};

const LOCATION_COLORS: Record<string, string> = {
  Taiwan:  Colors.tw,
  Japan:   Colors.jp,
  Similar: Colors.gold,
};

const LOCATION_BG: Record<string, string> = {
  Taiwan:  Colors.twLight,
  Japan:   Colors.jpLight,
  Similar: Colors.goldLight,
};

function formatTWD(n: number | null) {
  if (n == null) return '—';
  return `NT$${Math.round(n).toLocaleString('zh-TW')}`;
}

export default function AdviceCard({ advice }: Props) {
  const [prosCons, setProsCons] = useState(false);
  const accent = LOCATION_COLORS[advice.best_deal_location] ?? Colors.primary;
  const bg     = LOCATION_BG[advice.best_deal_location]     ?? Colors.card;

  const toggleProsCons = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setProsCons((v) => !v);
  };

  return (
    <View style={styles.wrapper}>
      {/* Best deal banner */}
      <View style={[styles.banner, { backgroundColor: bg, borderColor: accent }]}>
        <Text style={[styles.bannerText, { color: accent }]}>
          {LOCATION_LABELS[advice.best_deal_location] ?? advice.best_deal_location}
        </Text>
      </View>

      {/* Price summary table */}
      <View style={styles.table}>
        <View style={styles.tableRow}>
          <Text style={styles.tableLabel}>🇹🇼 台灣均價</Text>
          <Text style={[styles.tableValue, { color: Colors.tw }]}>{formatTWD(advice.tw_average_price_twd)}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.tableRow}>
          <Text style={styles.tableLabel}>🇯🇵 日本均價（換算後）</Text>
          <Text style={[styles.tableValue, { color: Colors.jp }]}>{formatTWD(advice.jp_average_price_twd)}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.tableRow}>
          <Text style={styles.tableLabel}>🇯🇵 日本退稅後（實體）</Text>
          <Text style={[styles.tableValue, { color: Colors.gold, fontWeight: '800' }]}>
            {formatTWD(advice.jp_tax_free_price_twd)}
          </Text>
        </View>
      </View>

      {/* Summary */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>📊 比價摘要</Text>
        <Text style={styles.body}>{advice.price_comparison_summary}</Text>
      </View>

      {/* Pros / Cons accordion */}
      <TouchableOpacity style={styles.accordionHeader} onPress={toggleProsCons} activeOpacity={0.7}>
        <Text style={styles.sectionTitle}>優缺點分析</Text>
        <Ionicons name={prosCons ? 'chevron-up' : 'chevron-down'} size={18} color={Colors.textSecondary} />
      </TouchableOpacity>
      {prosCons && (
        <View style={styles.prosConsBlock}>
          {advice.pros_cons.pros.length > 0 && (
            <View style={styles.prosBlock}>
              <Text style={styles.prosTitle}>✅ 優點</Text>
              {advice.pros_cons.pros.map((p, i) => (
                <Text key={i} style={styles.listItem}>• {p}</Text>
              ))}
            </View>
          )}
          {advice.pros_cons.cons.length > 0 && (
            <View style={styles.consBlock}>
              <Text style={styles.consTitle}>⚠️ 缺點 / 注意事項</Text>
              {advice.pros_cons.cons.map((c, i) => (
                <Text key={i} style={styles.listItem}>• {c}</Text>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Verdict */}
      <View style={[styles.verdict, { borderLeftColor: accent }]}>
        <Text style={styles.verdictLabel}>💡 AI 建議</Text>
        <Text style={styles.verdictText}>{advice.verdict}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: 12 },
  banner: {
    borderWidth: 2,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
  },
  bannerText: { fontSize: 18, fontWeight: '800' },

  table: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 13,
  },
  tableLabel: { fontSize: 13, color: Colors.text },
  tableValue: { fontSize: 16, fontWeight: '700' },
  divider:    { height: StyleSheet.hairlineWidth, backgroundColor: Colors.border, marginHorizontal: 16 },

  section: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 16,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: Colors.text, marginBottom: 6 },
  body:         { fontSize: 14, color: Colors.textSecondary, lineHeight: 21 },

  accordionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: Colors.card,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 13,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  prosConsBlock: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 16,
    gap: 12,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  prosBlock:  { gap: 4 },
  consBlock:  { gap: 4 },
  prosTitle:  { fontSize: 13, fontWeight: '700', color: Colors.tw,   marginBottom: 4 },
  consTitle:  { fontSize: 13, fontWeight: '700', color: Colors.gold, marginBottom: 4 },
  listItem:   { fontSize: 13, color: Colors.textSecondary, lineHeight: 20 },

  verdict: {
    backgroundColor: Colors.card,
    borderLeftWidth: 4,
    borderRadius: 12,
    padding: 16,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  verdictLabel: { fontSize: 13, fontWeight: '700', color: Colors.text, marginBottom: 6 },
  verdictText:  { fontSize: 15, color: Colors.text, lineHeight: 22, fontWeight: '500' },
});
