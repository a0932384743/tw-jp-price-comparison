import React, { useEffect } from 'react';
import { Share, TouchableOpacity } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { getLastResult } from '../lib/store';
import { loadFavorites } from '../lib/favorites';
import { loadHistory } from '../lib/history';

function ShareButton() {
  const handleShare = async () => {
    const result = getLastResult();
    if (!result) return;

    const { keyword_mapping, tw_listings, jp_listings, advice, exchange_rate_jpy_twd } = result;

    const twMin = tw_listings.length > 0 ? Math.min(...tw_listings.map((l) => l.price)) : null;
    const jpMin = jp_listings.length > 0  ? Math.min(...jp_listings.map((l) => l.price)) : null;
    const jpMinTwd = jpMin != null ? Math.round(jpMin * exchange_rate_jpy_twd) : null;

    const lines = [
      `📊 台日比價結果：${keyword_mapping.refined_tw_keyword}`,
      '',
      twMin  != null ? `🇹🇼 台灣最低價：NT$${Math.round(twMin).toLocaleString()}` : '🇹🇼 台灣：無資料',
      jpMinTwd != null ? `🇯🇵 日本最低價（換算）：NT$${jpMinTwd.toLocaleString()}` : '🇯🇵 日本：無資料',
      '',
      `💡 ${advice.verdict}`,
      '',
      '— 台日比價 AI 顧問',
    ];

    try {
      await Share.share({ message: lines.join('\n') });
    } catch {}
  };

  return (
    <TouchableOpacity onPress={handleShare} style={{ marginRight: 8 }} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
      <Ionicons name="share-outline" size={22} color="#fff" />
    </TouchableOpacity>
  );
}

export default function RootLayout() {
  useEffect(() => {
    loadFavorites();
    loadHistory();
  }, []);

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle:      { backgroundColor: '#0F172A' },
          headerTintColor:  '#fff',
          headerTitleStyle: { fontWeight: '700', fontSize: 17 },
          headerBackTitle:  '搜尋',
          animation:        'slide_from_right',
          contentStyle:     { backgroundColor: '#F9FAFB' },
        }}
      >
        <Stack.Screen
          name="index"
          options={{ title: '台日比價 AI 顧問', headerLargeTitle: false }}
        />
        <Stack.Screen
          name="results"
          options={{
            title: '比價結果',
            headerRight: () => <ShareButton />,
          }}
        />
      </Stack>
    </>
  );
}
