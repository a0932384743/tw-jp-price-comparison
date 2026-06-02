import React, { useState } from 'react';
import { Image, Linking, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../constants/colors';
import type { PriceListing } from '../types/api';

interface Props {
  listing: PriceListing;
  market: 'TW' | 'JP';
  exchangeRate: number;
  isCheapest?: boolean;
  thumbnailUrl?: string | null;
}

const PLATFORM_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  'momo購物網':          'storefront',
  '蝦皮購物':            'cart',
  'PChome 24h':         'cube',
  'Yahoo購物中心':       'storefront-outline',
  '燦坤':               'flash',
  '博客來':             'book',
  'Amazon Japan':       'logo-amazon',
  '楽天市場':           'gift',
  'Yahoo!ショッピング': 'pricetag',
  '価格.com':           'bar-chart',
  'ヨドバシカメラ':     'camera',
  'ビックカメラ':       'camera-outline',
};

function fmtTWD(n: number) { return `NT$${Math.round(n).toLocaleString('zh-TW')}`; }
function fmtJPY(n: number) { return `¥${Math.round(n).toLocaleString('ja-JP')}`; }

export default function PlatformCard({ listing, market, exchangeRate, isCheapest, thumbnailUrl }: Props) {
  const [imgError, setImgError] = useState(false);
  const iconName    = PLATFORM_ICONS[listing.platform] ?? 'cart-outline';
  const accentColor = market === 'TW' ? Colors.tw : Colors.jp;

  const jpTWD     = market === 'JP' ? listing.price * exchangeRate : null;
  const jpTaxFree = jpTWD != null ? jpTWD * 0.9 : null;

  const openLink = () => {
    if (listing.url) Linking.openURL(listing.url).catch(() => {});
  };

  // Priority: per-listing image → shared product thumbnail → thum.io screenshot of listing URL
  const screenshotUrl = listing.url
    ? `https://image.thum.io/get/width/160/crop/160/noanimate/${encodeURIComponent(listing.url)}`
    : null;
  const imageSource = listing.image_url || thumbnailUrl || screenshotUrl;
  const showImage = !!imageSource && !imgError;

  return (
    <View style={styles.card}>
      {/* Platform header */}
      <View style={[styles.header, { backgroundColor: accentColor }]}>
        <Ionicons name={iconName} size={13} color="#fff" />
        <Text style={styles.platform} numberOfLines={1}>{listing.platform}</Text>
        {isCheapest && (
          <View style={styles.cheapestBadge}>
            <Text style={styles.cheapestText}>最低價 🏅</Text>
          </View>
        )}
      </View>

      {/* Body */}
      <View style={styles.body}>
        <View style={styles.bodyRow}>
          {/* Thumbnail or placeholder icon */}
          {showImage ? (
            <Image
              source={{ uri: imageSource! }}
              style={styles.thumbnail}
              resizeMode="contain"
              onError={() => setImgError(true)}
            />
          ) : (
            <View style={[styles.thumbnailPlaceholder, { backgroundColor: accentColor + '18' }]}>
              <Ionicons name={iconName} size={26} color={accentColor} />
            </View>
          )}

          {/* Title + price */}
          <View style={styles.info}>
            <Text style={styles.title} numberOfLines={2}>{listing.title}</Text>

            <View style={styles.priceBlock}>
              <Text style={[styles.price, { color: accentColor }]}>
                {market === 'TW' ? fmtTWD(listing.price) : fmtJPY(listing.price)}
              </Text>
              {market === 'JP' && jpTWD != null && (
                <View style={styles.converted}>
                  <Text style={styles.convertedLabel}>≈ {fmtTWD(jpTWD)}</Text>
                  {jpTaxFree != null && (
                    <View style={styles.taxBadge}>
                      <Ionicons name="receipt-outline" size={11} color={Colors.gold} />
                      <Text style={styles.taxText}>退稅後 {fmtTWD(jpTaxFree)}</Text>
                    </View>
                  )}
                </View>
              )}
            </View>
          </View>
        </View>

        <TouchableOpacity
          style={[styles.linkBtn, { borderColor: accentColor }]}
          onPress={openLink}
          activeOpacity={0.7}
        >
          <Text style={[styles.linkText, { color: accentColor }]}>前往購買</Text>
          <Ionicons name="open-outline" size={13} color={accentColor} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const THUMB = 72;

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.card,
    borderRadius: 14,
    overflow: 'hidden',
    shadowColor: Colors.shadowMd,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 8,
    elevation: 3,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 7,
    gap: 6,
  },
  platform:      { fontSize: 12, color: '#fff', fontWeight: '600', flex: 1 },
  cheapestBadge: { backgroundColor: 'rgba(255,255,255,0.22)', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  cheapestText:  { fontSize: 11, color: '#fff', fontWeight: '700' },

  body:    { padding: 12, gap: 10 },
  bodyRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },

  thumbnail: {
    width: THUMB,
    height: THUMB,
    borderRadius: 8,
    backgroundColor: Colors.borderLight,
    flexShrink: 0,
  },
  thumbnailPlaceholder: {
    width: THUMB,
    height: THUMB,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },

  info:    { flex: 1, gap: 4 },
  title:   { fontSize: 12, color: Colors.text, lineHeight: 18 },

  priceBlock:     { gap: 2 },
  price:          { fontSize: 20, fontWeight: '900' },
  converted:      { gap: 3 },
  convertedLabel: { fontSize: 12, color: Colors.textSecondary },
  taxBadge: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
    backgroundColor: Colors.goldLight, borderRadius: 6,
    paddingHorizontal: 7, paddingVertical: 2, gap: 3,
  },
  taxText: { fontSize: 11, color: Colors.gold, fontWeight: '600' },

  linkBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    borderWidth: 1.5, borderRadius: 8, paddingVertical: 7, gap: 4,
  },
  linkText: { fontSize: 13, fontWeight: '700' },
});
