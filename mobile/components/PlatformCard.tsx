import React, { useState } from 'react';
import { Image, Linking, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../constants/colors';
import { thumbnailProxyUrl } from '../lib/api';
import type { PriceListing } from '../types/api';

interface Props {
  listing: PriceListing;
  market: 'TW' | 'JP';
  exchangeRate: number;
  isCheapest?: boolean;
  thumbnailUrl?: string | null;
}

const PLATFORM_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  'momo':               'storefront',
  '蝦皮':               'cart',
  'shopee':             'cart',
  'pchome':             'cube',
  'yahoo':              'pricetag',
  '露天':               'pricetags',
  '博客來':             'book',
  'uniqlo':             'shirt-outline',
  'gu ':                'shirt',
  ' gu':                'shirt',
  'nike':               'footsteps',
  'adidas':             'walk',
  'amazon':             'logo-amazon',
  '楽天':               'gift',
  'rakuten':            'gift',
  'kakaku':             'bar-chart',
  '価格':               'bar-chart',
  'apple':              'logo-apple',
  'google shopping':    'search',
};

function _icon(platform: string): keyof typeof Ionicons.glyphMap {
  const pl = platform.toLowerCase();
  for (const [key, icon] of Object.entries(PLATFORM_ICONS)) {
    if (pl.includes(key.trim().toLowerCase())) return icon;
  }
  return 'cart-outline';
}

function fmtTWD(n: number) { return `NT$${Math.round(n).toLocaleString('zh-TW')}`; }
function fmtJPY(n: number) { return `¥${Math.round(n).toLocaleString('ja-JP')}`; }

export default function PlatformCard({ listing, market, exchangeRate, isCheapest, thumbnailUrl }: Props) {
  const [imgError,   setImgError]   = useState(false);
  const [imgLoaded,  setImgLoaded]  = useState(false);
  const iconName    = _icon(listing.platform);
  const accentColor = market === 'TW' ? Colors.tw : Colors.jp;

  const jpTWD     = market === 'JP' ? listing.price * exchangeRate : null;
  const jpTaxFree = jpTWD != null ? jpTWD * 0.9 : null;

  const openLink = () => {
    if (listing.url) Linking.openURL(listing.url).catch(() => {});
  };

  // Priority 1: scraped product image (per-listing)
  // Priority 2: backend search-level thumbnail (Bing/DDG/Wikipedia)
  // Priority 3: backend proxy screenshot – the /api/thumbnail endpoint fetches
  //   a mshots website screenshot server-side and returns it with CORS headers,
  //   so the browser never has to reach a third-party domain directly.
  const screenshotUrl = listing.url ? thumbnailProxyUrl(listing.url) : null;
  const imageSource = listing.image_url || thumbnailUrl || screenshotUrl;
  // Show placeholder icon while image is loading; hide on error
  const showImage = !!imageSource && !imgError;

  return (
    <View style={styles.card}>
      {/* Platform header */}
      <View style={[styles.header, { backgroundColor: accentColor }]}>
        <Ionicons name={iconName} size={13} color="#fff" />
        <Text style={styles.platform} numberOfLines={1}>{listing.platform}</Text>
        {listing.data_source === 'ai_estimated' ? (
          <View style={styles.aiBadge}>
            <Ionicons name="sparkles" size={9} color={Colors.gold} />
            <Text style={styles.aiText}>AI 估算</Text>
          </View>
        ) : isCheapest ? (
          <View style={styles.cheapestBadge}>
            <Text style={styles.cheapestText}>電商最低價 🏅</Text>
          </View>
        ) : null}
      </View>

      {/* Body */}
      <View style={styles.body}>
        <View style={styles.bodyRow}>
          {/* Thumbnail or placeholder icon */}
          <View style={styles.thumbnailWrap}>
            {/* Always show icon; hide it once image loads successfully */}
            {(!showImage || !imgLoaded) && (
              <View style={[styles.thumbnailPlaceholder, { backgroundColor: `${accentColor}18` }]}>
                <Ionicons name={iconName} size={26} color={accentColor} />
              </View>
            )}
            {showImage && (
              <Image
                source={{ uri: imageSource! }}
                style={[styles.thumbnail, !imgLoaded && styles.hidden]}
                resizeMode="cover"
                onLoad={() => setImgLoaded(true)}
                onError={() => setImgError(true)}
              />
            )}
          </View>

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
  aiBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: Colors.goldLight, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 },
  aiText:  { fontSize: 10, color: Colors.gold, fontWeight: '700' },

  body:    { padding: 12, gap: 10 },
  bodyRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },

  thumbnailWrap: {
    width: THUMB,
    height: THUMB,
    borderRadius: 8,
    overflow: 'hidden',
    flexShrink: 0,
  },
  thumbnail: {
    position: 'absolute',
    top: 0, left: 0,
    width: THUMB,
    height: THUMB,
    borderRadius: 8,
  },
  thumbnailPlaceholder: {
    width: THUMB,
    height: THUMB,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hidden: { opacity: 0 },

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
