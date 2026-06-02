import React, { useState } from 'react';
import { LayoutAnimation, Platform, StyleSheet, Text, TouchableOpacity, UIManager, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../constants/colors';
import type { BuyingAdvice } from '../types/api';

if (Platform.OS === 'android') {
  UIManager.setLayoutAnimationEnabledExperimental?.(true);
}

const ACCENT: Record<string, string> = {
  Taiwan:  Colors.tw,
  Japan:   Colors.jp,
  Similar: Colors.gold,
};

export default function AdviceCard({ advice }: { advice: BuyingAdvice }) {
  const [open, setOpen] = useState(false);
  const accent = ACCENT[advice.best_deal_location] ?? Colors.primary;

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((v) => !v);
  };

  return (
    <View style={s.wrapper}>
      {/* Summary */}
      <View style={s.section}>
        <Text style={s.sectionTitle}>📊 比價摘要</Text>
        <Text style={s.body}>{advice.price_comparison_summary}</Text>
      </View>

      {/* Pros / Cons accordion */}
      <TouchableOpacity style={s.accordionBtn} onPress={toggle} activeOpacity={0.7}>
        <Text style={s.sectionTitle}>優缺點分析</Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={Colors.textSecondary} />
      </TouchableOpacity>

      {open && (
        <View style={s.prosConsBlock}>
          {advice.pros_cons.pros.length > 0 && (
            <View style={s.group}>
              <Text style={[s.groupTitle, { color: Colors.success }]}>✅ 優點</Text>
              {advice.pros_cons.pros.map((p, i) => (
                <View key={i} style={s.listRow}>
                  <Text style={s.bullet}>•</Text>
                  <Text style={s.listItem}>{p}</Text>
                </View>
              ))}
            </View>
          )}
          {advice.pros_cons.cons.length > 0 && (
            <View style={s.group}>
              <Text style={[s.groupTitle, { color: Colors.gold }]}>⚠️ 注意事項</Text>
              {advice.pros_cons.cons.map((c, i) => (
                <View key={i} style={s.listRow}>
                  <Text style={s.bullet}>•</Text>
                  <Text style={s.listItem}>{c}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Verdict */}
      <View style={[s.verdict, { borderLeftColor: accent }]}>
        <Text style={s.verdictLabel}>💡 AI 購買建議</Text>
        <Text style={s.verdictText}>{advice.verdict}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrapper: { gap: 10 },

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
  body:         { fontSize: 14, color: Colors.textSecondary, lineHeight: 22 },

  accordionBtn: {
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
    gap: 14,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  group:      { gap: 6 },
  groupTitle: { fontSize: 13, fontWeight: '700', marginBottom: 4 },
  listRow:    { flexDirection: 'row', gap: 6 },
  bullet:     { fontSize: 13, color: Colors.textSecondary, lineHeight: 20 },
  listItem:   { flex: 1, fontSize: 13, color: Colors.textSecondary, lineHeight: 20 },

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
  verdictText:  { fontSize: 15, color: Colors.text, lineHeight: 23, fontWeight: '500' },
});
