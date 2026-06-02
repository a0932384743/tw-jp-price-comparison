import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';

import { searchByImage, searchByText } from '../lib/api';
import { setLastResult } from '../lib/store';
import { addToHistory, clearHistory, getHistory, type HistoryItem } from '../lib/history';
import { getFavorites, removeFavorite, type FavoriteItem } from '../lib/favorites';
import LoadingOverlay from '../components/LoadingOverlay';
import { Colors } from '../constants/colors';
import { hapticImpact, hapticNotification, hapticSelection } from '../lib/haptics';

type Mode = 'text' | 'image';

const TRENDING: { label: string; icon: string }[] = [
  { label: 'Nintendo Switch OLED', icon: '🎮' },
  { label: 'AirPods Pro',          icon: '🎧' },
  { label: 'SK-II 神仙水',          icon: '✨' },
  { label: 'iPhone 16 Pro',        icon: '📱' },
  { label: 'Dyson V15',            icon: '🌀' },
  { label: 'Sony WH-1000XM5',     icon: '🎵' },
];

export default function SearchScreen() {
  const router = useRouter();
  const [mode, setMode]         = useState<Mode>('text');
  const [query, setQuery]       = useState('');
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageMime, setImageMime] = useState('image/jpeg');
  const [loading, setLoading]       = useState(false);
  const [coldStart, setColdStart]   = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [history, setHistory]       = useState<HistoryItem[]>([]);
  const [favorites, setFavorites]   = useState<FavoriteItem[]>([]);
  const coldStartTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setHistory(getHistory());
    setFavorites(getFavorites());
  }, []);

  const refreshHistory = useCallback(() => setHistory(getHistory()), []);
  const refreshFavorites = useCallback(() => setFavorites(getFavorites()), []);

  async function runSearch(fn: () => Promise<void>) {
    setLoading(true);
    setError(null);
    setColdStart(false);
    coldStartTimer.current = setTimeout(() => setColdStart(true), 6000);
    try {
      await fn();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      hapticNotification(Haptics.NotificationFeedbackType.Error);
    } finally {
      setLoading(false);
      setColdStart(false);
      if (coldStartTimer.current) clearTimeout(coldStartTimer.current);
    }
  }

  const handleTextSearch = (q?: string) => {
    const searchQuery = (q ?? query).trim();
    if (!searchQuery) return;
    runSearch(async () => {
      hapticImpact(Haptics.ImpactFeedbackStyle.Medium);
      const result = await searchByText(searchQuery);
      addToHistory(searchQuery, result.keyword_mapping?.category);
      refreshHistory();
      setLastResult(result);
      router.push('/results');
    });
  };

  const handleImageSearch = () =>
    runSearch(async () => {
      if (!imageUri) return;
      hapticImpact(Haptics.ImpactFeedbackStyle.Medium);
      const result = await searchByImage(imageUri, imageMime);
      setLastResult(result);
      router.push('/results');
    });

  const pickFromGallery = async () => {
    const { granted } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!granted) { Alert.alert('需要權限', '請在設定中允許存取相簿'); return; }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.85 });
    if (!res.canceled && res.assets[0]) {
      setImageUri(res.assets[0].uri);
      setImageMime(res.assets[0].mimeType ?? 'image/jpeg');
    }
  };

  const pickFromCamera = async () => {
    const { granted } = await ImagePicker.requestCameraPermissionsAsync();
    if (!granted) { Alert.alert('需要權限', '請在設定中允許使用相機'); return; }
    const res = await ImagePicker.launchCameraAsync({ quality: 0.85 });
    if (!res.canceled && res.assets[0]) {
      setImageUri(res.assets[0].uri);
      setImageMime(res.assets[0].mimeType ?? 'image/jpeg');
    }
  };

  const switchMode = (m: Mode) => { hapticSelection(); setMode(m); setError(null); };

  const handleClearHistory = () => {
    hapticSelection();
    clearHistory();
    refreshHistory();
  };

  const handleRemoveFavorite = (keyword: string) => {
    hapticSelection();
    removeFavorite(keyword);
    refreshFavorites();
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* ── Hero ─────────────────────────────────────────────────── */}
        <LinearGradient colors={['#0F172A', '#1E3A5F']} style={s.hero}>
          <View style={s.heroFlags}>
            <Text style={s.flagText}>🇹🇼</Text>
            <View style={s.heroArrow}>
              <Ionicons name="swap-horizontal" size={18} color="rgba(255,255,255,0.6)" />
            </View>
            <Text style={s.flagText}>🇯🇵</Text>
          </View>
          <Text style={s.heroTitle}>台日比價 AI 顧問</Text>
          <Text style={s.heroSub}>即時匯率 · 退稅試算 · AI 購買建議</Text>

          <View style={s.heroStats}>
            {[
              { icon: '🏬', label: '10+ 購物平台' },
              { icon: '💱', label: '即時匯率' },
              { icon: '🤖', label: 'AI 分析' },
            ].map((stat) => (
              <View key={stat.label} style={s.statItem}>
                <Text style={s.statIcon}>{stat.icon}</Text>
                <Text style={s.statLabel}>{stat.label}</Text>
              </View>
            ))}
          </View>

          <TouchableOpacity style={s.heroImgBtn} onPress={() => { hapticSelection(); switchMode('image'); }} activeOpacity={0.8}>
            <Ionicons name="camera" size={15} color="#fff" />
            <Text style={s.heroImgBtnText}>📸 拍照搜尋商品</Text>
            <Ionicons name="chevron-forward" size={13} color="rgba(255,255,255,0.6)" />
          </TouchableOpacity>
        </LinearGradient>

        {/* ── Mode tabs ────────────────────────────────────────────── */}
        <View style={s.tabBar}>
          {(['text', 'image'] as Mode[]).map((m) => (
            <TouchableOpacity
              key={m}
              style={[s.tab, mode === m && s.tabActive]}
              onPress={() => switchMode(m)}
              activeOpacity={0.8}
            >
              <Ionicons name={m === 'text' ? 'search' : 'camera'} size={16} color={mode === m ? Colors.primary : Colors.textSecondary} />
              <Text style={[s.tabLabel, mode === m && s.tabLabelActive]}>
                {m === 'text' ? '文字搜尋' : '圖片搜尋'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* ── Text mode ────────────────────────────────────────────── */}
        {mode === 'text' && (
          <View style={s.card}>
            <View style={s.inputRow}>
              <Ionicons name="search" size={20} color={Colors.textSecondary} />
              <TextInput
                style={s.input}
                placeholder="輸入商品名稱、型號…"
                placeholderTextColor={Colors.disabled}
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={() => handleTextSearch()}
                returnKeyType="search"
                autoCapitalize="none"
                autoCorrect={false}
              />
              {query.length > 0 && (
                <TouchableOpacity onPress={() => setQuery('')} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                  <Ionicons name="close-circle" size={20} color={Colors.disabled} />
                </TouchableOpacity>
              )}
            </View>

            <TouchableOpacity
              style={[s.btn, !query.trim() && s.btnDisabled]}
              onPress={() => handleTextSearch()}
              disabled={!query.trim()}
              activeOpacity={0.8}
            >
              <Ionicons name="analytics" size={18} color="#fff" />
              <Text style={s.btnText}>開始比價</Text>
            </TouchableOpacity>

            {/* Trending */}
            <View style={s.sectionRow}>
              <Text style={s.sectionLabel}>🔥 熱門搜尋</Text>
            </View>
            <View style={s.chips}>
              {TRENDING.map((item) => (
                <TouchableOpacity
                  key={item.label}
                  style={s.chip}
                  onPress={() => { hapticSelection(); handleTextSearch(item.label); }}
                  activeOpacity={0.7}
                >
                  <Text style={s.chipIcon}>{item.icon}</Text>
                  <Text style={s.chipText}>{item.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* ── Image mode ───────────────────────────────────────────── */}
        {mode === 'image' && (
          <View style={s.card}>
            <View style={s.imageBtns}>
              <TouchableOpacity style={s.imageBtn} onPress={pickFromCamera} activeOpacity={0.8}>
                <Ionicons name="camera" size={28} color={Colors.primary} />
                <Text style={s.imageBtnLabel}>拍照</Text>
              </TouchableOpacity>
              <View style={s.imageBtnDivider} />
              <TouchableOpacity style={s.imageBtn} onPress={pickFromGallery} activeOpacity={0.8}>
                <Ionicons name="images" size={28} color={Colors.primary} />
                <Text style={s.imageBtnLabel}>從相簿選取</Text>
              </TouchableOpacity>
            </View>

            {imageUri ? (
              <>
                <View style={s.previewWrapper}>
                  <Image source={{ uri: imageUri }} style={s.preview} resizeMode="cover" />
                  <TouchableOpacity style={s.previewClear} onPress={() => setImageUri(null)}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Ionicons name="close-circle" size={26} color="#fff" />
                  </TouchableOpacity>
                </View>
                <TouchableOpacity style={s.btn} onPress={handleImageSearch} activeOpacity={0.8}>
                  <Ionicons name="analytics" size={18} color="#fff" />
                  <Text style={s.btnText}>分析此圖片</Text>
                </TouchableOpacity>
              </>
            ) : (
              <View style={s.imagePlaceholder}>
                <Ionicons name="image-outline" size={52} color={Colors.border} />
                <Text style={s.imagePlaceholderText}>請拍照或從相簿選取商品圖片</Text>
                <Text style={s.imagePlaceholderHint}>支援 JPG / PNG / WEBP</Text>
              </View>
            )}
          </View>
        )}

        {/* ── Error ────────────────────────────────────────────────── */}
        {error && (
          <View style={s.errorBox}>
            <Ionicons name="alert-circle" size={18} color={Colors.error} />
            <Text style={s.errorText} selectable>{error}</Text>
          </View>
        )}

        {/* ── Favorites / Watchlist ────────────────────────────────── */}
        {favorites.length > 0 && (
          <View style={s.card}>
            <View style={s.sectionRow}>
              <Text style={s.sectionLabel}>❤️ 收藏清單</Text>
            </View>
            {favorites.map((item) => (
              <TouchableOpacity
                key={item.keyword + item.savedAt}
                style={s.historyItem}
                onPress={() => { setQuery(item.keyword); switchMode('text'); handleTextSearch(item.keyword); }}
                activeOpacity={0.7}
              >
                <Ionicons name="heart" size={16} color={Colors.jp} />
                <View style={s.historyContent}>
                  <Text style={s.historyQuery} numberOfLines={1}>{item.keyword}</Text>
                  {item.category && <Text style={s.historyCategory}>{item.category}</Text>}
                </View>
                <TouchableOpacity
                  onPress={() => handleRemoveFavorite(item.keyword)}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                  <Ionicons name="close" size={16} color={Colors.border} />
                </TouchableOpacity>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* ── Recent searches ──────────────────────────────────────── */}
        {history.length > 0 && (
          <View style={s.card}>
            <View style={s.sectionRow}>
              <Text style={s.sectionLabel}>🕐 最近搜尋</Text>
              <TouchableOpacity onPress={handleClearHistory} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Text style={s.clearBtn}>清除</Text>
              </TouchableOpacity>
            </View>
            {history.map((item) => (
              <TouchableOpacity
                key={item.query + item.timestamp}
                style={s.historyItem}
                onPress={() => { setQuery(item.query); switchMode('text'); handleTextSearch(item.query); }}
                activeOpacity={0.7}
              >
                <Ionicons name="time-outline" size={16} color={Colors.textSecondary} />
                <View style={s.historyContent}>
                  <Text style={s.historyQuery} numberOfLines={1}>{item.query}</Text>
                  {item.category && <Text style={s.historyCategory}>{item.category}</Text>}
                </View>
                <Ionicons name="chevron-forward" size={16} color={Colors.border} />
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* ── Tips ─────────────────────────────────────────────────── */}
        <View style={s.tipsCard}>
          <Text style={s.tipsTitle}>💡 使用說明</Text>
          {[
            ['🏬', '比較 8 個以上台日電商平台'],
            ['💱', '即時日圓匯率，退稅 10% 試算'],
            ['🤖', '支援文字搜尋與商品圖片辨識'],
            ['🚢', '比較結果納入運費參考試算'],
          ].map(([icon, text]) => (
            <View key={text} style={s.tipRow}>
              <Text style={s.tipIcon}>{icon}</Text>
              <Text style={s.tipText}>{text}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      {loading && <LoadingOverlay coldStart={coldStart} />}
    </KeyboardAvoidingView>
  );
}

/* ── styles ────────────────────────────────────────────────────────────── */
const s = StyleSheet.create({
  scroll:  { flex: 1, backgroundColor: Colors.background },
  content: { paddingBottom: 48 },

  /* hero */
  hero: { paddingTop: 28, paddingBottom: 24, paddingHorizontal: 24 },
  heroFlags: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 12 },
  flagText:  { fontSize: 32 },
  heroArrow: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center', justifyContent: 'center',
  },
  heroTitle: { fontSize: 26, fontWeight: '900', color: '#fff', textAlign: 'center', marginBottom: 6 },
  heroSub:   { fontSize: 13, color: 'rgba(255,255,255,0.75)', textAlign: 'center', marginBottom: 20 },
  heroStats: { flexDirection: 'row', justifyContent: 'center', gap: 20 },
  statItem:  { alignItems: 'center', gap: 4 },
  statIcon:  { fontSize: 18 },
  statLabel: { fontSize: 11, color: 'rgba(255,255,255,0.7)', fontWeight: '600' },

  /* hero image shortcut */
  heroImgBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    marginTop: 14, gap: 6,
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8,
    alignSelf: 'center',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
  },
  heroImgBtnText: { fontSize: 13, color: '#fff', fontWeight: '700' },

  /* tabs */
  tabBar: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginTop: 16,
    marginBottom: 4,
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 4,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  tab:            { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 10, gap: 6 },
  tabActive:      { backgroundColor: Colors.primaryLight },
  tabLabel:       { fontSize: 14, color: Colors.textSecondary, fontWeight: '600' },
  tabLabelActive: { color: Colors.primary },

  /* card */
  card: {
    backgroundColor: Colors.card,
    borderRadius: 16,
    margin: 16,
    padding: 16,
    shadowColor: Colors.shadowMd,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 8,
    elevation: 3,
    gap: 14,
  },

  /* input */
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.background,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: Platform.OS === 'ios' ? 13 : 8,
    gap: 8,
  },
  input: { flex: 1, fontSize: 15, color: Colors.text },

  /* button */
  btn:         { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.primary, borderRadius: 12, paddingVertical: 14, gap: 8 },
  btnDisabled: { backgroundColor: Colors.disabled },
  btnText:     { color: '#fff', fontSize: 16, fontWeight: '800' },

  /* section row */
  sectionRow:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionLabel:{ fontSize: 13, fontWeight: '700', color: Colors.text },
  clearBtn:    { fontSize: 12, color: Colors.textSecondary, fontWeight: '600' },

  /* trending chips */
  chips:     { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip:      { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.background, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7, gap: 5, borderWidth: 1, borderColor: Colors.borderLight },
  chipIcon:  { fontSize: 13 },
  chipText:  { fontSize: 12, color: Colors.text, fontWeight: '600' },

  /* image mode */
  imageBtns: { flexDirection: 'row', borderWidth: 1.5, borderColor: Colors.border, borderRadius: 12, overflow: 'hidden' },
  imageBtn:  { flex: 1, alignItems: 'center', paddingVertical: 20, gap: 8 },
  imageBtnDivider: { width: 1.5, backgroundColor: Colors.border },
  imageBtnLabel:   { fontSize: 13, fontWeight: '700', color: Colors.primary },
  imagePlaceholder: { alignItems: 'center', paddingVertical: 32, gap: 8, borderWidth: 2, borderStyle: 'dashed', borderColor: Colors.border, borderRadius: 12 },
  imagePlaceholderText: { fontSize: 13, color: Colors.textSecondary, textAlign: 'center' },
  imagePlaceholderHint: { fontSize: 11, color: Colors.textTertiary },
  previewWrapper: { position: 'relative' },
  preview:        { width: '100%', height: 220, borderRadius: 10 },
  previewClear:   { position: 'absolute', top: 8, right: 8, backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: 13 },

  /* error */
  errorBox:  { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: Colors.errorLight, borderRadius: 10, marginHorizontal: 16, padding: 12, gap: 8 },
  errorText: { flex: 1, fontSize: 13, color: Colors.error, lineHeight: 19 },

  /* history */
  historyItem: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: Colors.borderLight },
  historyContent: { flex: 1 },
  historyQuery:   { fontSize: 14, color: Colors.text, fontWeight: '500' },
  historyCategory:{ fontSize: 11, color: Colors.textTertiary, marginTop: 1 },

  /* tips */
  tipsCard:  { marginHorizontal: 16, marginTop: 4, backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 10, shadowColor: Colors.shadow, shadowOffset: { width: 0, height: 1 }, shadowOpacity: 1, shadowRadius: 4, elevation: 2 },
  tipsTitle: { fontSize: 14, fontWeight: '700', color: Colors.text, marginBottom: 2 },
  tipRow:    { flexDirection: 'row', alignItems: 'center', gap: 10 },
  tipIcon:   { fontSize: 16, width: 24 },
  tipText:   { fontSize: 13, color: Colors.textSecondary, flex: 1, lineHeight: 19 },
});
