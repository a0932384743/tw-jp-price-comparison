import React from 'react';
import {
  Linking,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../constants/colors';
import type { PriceListing } from '../types/api';

interface Props {
  listing: PriceListing;
  market: 'TW' | 'JP';
  exchangeRate: number;
}

const PLATFORM_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  'momo購物網':         'storefront',
  '蝦皮購物 (Shopee TW)': 'cart',
  'PChome 24h':        'cube',
  'Amazon Japan':      'logo-amazon',
  '楽天市場 (Rakuten)': 'gift',
  'Yahoo!ショッピング':  'pricetag',
};

function formatTWD(n: number) {
  return `NT$${Math.round(n).toLocaleString('zh-TW')}`;
}
function formatJPY(n: number) {
  return `¥${Math.round(n).toLocaleString('ja-JP')}`;
}

export default function PlatformCard({ listing, market, exchangeRate }: Props) {
  const iconName = PLATFORM_ICONS[listing.platform] ?? 'cart-outline';
  const accentColor = market === 'TW' ? Colors.tw : Colors.jp;

  const jpConvertedTWD = market === 'JP' ? listing.price * exchangeRate : null;
  const jpTaxFree      = jpConvertedTWD !== null ? jpConvertedTWD * 0.9 : null;

  return (
    <View style={styles.card}>
      {/* Platform header */}
      <View style={[styles.header, { backgroundColor: accentColor }]}>
        <Ionicons name={iconName} size={14} color="#fff" />
        <Text style={styles.platform} numberOfLines={1}>{listing.platform}</Text>
      </View>

      {/* Body */}
      <View style={styles.body}>
        <Text style={styles.title} numberOfLines={2}>{listing.title}</Text>

        <View style={styles.priceRow}>
          <Text style={[styles.price, { color: accentColor }]}>
            {market === 'TW' ? formatTWD(listing.price) : formatJPY(listing.price)}
          </Text>
          {market === 'JP' && jpConvertedTWD !== null && (
            <View style={styles.converted}>
              <Text style={styles.convertedLabel}>≈ {formatTWD(jpConvertedTWD)}</Text>
              {jpTaxFree !== null && (
                <View style={styles.taxBadge}>
                  <Text style={styles.taxText}>退稅後 {formatTWD(jpTaxFree)}</Text>
                </View>
              )}
            </View>
          )}
        </View>

        <TouchableOpacity
          style={[styles.linkBtn, { borderColor: accentColor }]}
          onPress={() => Linking.openURL(listing.url)}
          activeOpacity={0.7}
        >
          <Text style={[styles.linkText, { color: accentColor }]}>前往購買</Text>
          <Ionicons name="open-outline" size={13} color={accentColor} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    marginBottom: 10,
    overflow: 'hidden',
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 6,
    elevation: 3,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    gap: 6,
  },
  platform: { fontSize: 12, color: '#fff', fontWeight: '600', flex: 1 },
  body:     { padding: 12 },
  title:    { fontSize: 14, color: Colors.text, lineHeight: 20, marginBottom: 8 },
  priceRow: { marginBottom: 10 },
  price:    { fontSize: 22, fontWeight: '800' },
  converted:    { marginTop: 4, gap: 4 },
  convertedLabel: { fontSize: 13, color: Colors.textSecondary },
  taxBadge: {
    alignSelf: 'flex-start',
    backgroundColor: Colors.goldLight,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  taxText: { fontSize: 12, color: Colors.gold, fontWeight: '600' },
  linkBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderRadius: 8,
    paddingVertical: 8,
    gap: 4,
  },
  linkText: { fontSize: 13, fontWeight: '700' },
});
