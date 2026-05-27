import React, { useState } from 'react';
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
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
import LoadingOverlay from '../components/LoadingOverlay';
import { Colors } from '../constants/colors';

type Mode = 'text' | 'image';

const EXAMPLES = ['Sony WH-1000XM5', 'SK-II 神仙水', 'Nintendo Switch', 'Dyson V15', '資生堂防曬乳'];

export default function SearchScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('text');
  const [query, setQuery] = useState('');
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageMime, setImageMime] = useState('image/jpeg');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* ── helpers ─────────────────────────────────────────────────────────── */

  async function runSearch(fn: () => Promise<void>) {
    setLoading(true);
    setError(null);
    try {
      await fn();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setLoading(false);
    }
  }

  const handleTextSearch = () =>
    runSearch(async () => {
      if (!query.trim()) return;
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      const result = await searchByText(query.trim());
      setLastResult(result);
      router.push('/results');
    });

  const handleImageSearch = () =>
    runSearch(async () => {
      if (!imageUri) return;
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      const result = await searchByImage(imageUri, imageMime);
      setLastResult(result);
      router.push('/results');
    });

  const pickFromGallery = async () => {
    const { granted } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!granted) { Alert.alert('需要權限', '請在設定中允許存取相簿'); return; }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
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

  const switchMode = (m: Mode) => {
    Haptics.selectionAsync();
    setMode(m);
    setError(null);
  };

  /* ── render ──────────────────────────────────────────────────────────── */

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Hero gradient */}
        <LinearGradient colors={['#7B241C', '#C0392B']} style={styles.hero}>
          <Text style={styles.heroFlags}>🇹🇼  ↔  🇯🇵</Text>
          <Text style={styles.heroTitle}>台日比價 AI 顧問</Text>
          <Text style={styles.heroSub}>
            輸入商品或上傳圖片，AI 即時分析{'\n'}匯率、退稅、運費，找到最划算選擇
          </Text>
        </LinearGradient>

        {/* Mode tabs */}
        <View style={styles.tabBar}>
          {(['text', 'image'] as Mode[]).map((m) => (
            <TouchableOpacity
              key={m}
              style={[styles.tab, mode === m && styles.tabActive]}
              onPress={() => switchMode(m)}
              activeOpacity={0.8}
            >
              <Ionicons
                name={m === 'text' ? 'text' : 'camera'}
                size={16}
                color={mode === m ? Colors.primary : Colors.textSecondary}
              />
              <Text style={[styles.tabLabel, mode === m && styles.tabLabelActive]}>
                {m === 'text' ? '文字搜尋' : '圖片搜尋'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* ── Text mode ──────────────────────────────────────────────── */}
        {mode === 'text' && (
          <View style={styles.card}>
            <View style={styles.inputRow}>
              <Ionicons name="search" size={20} color={Colors.textSecondary} />
              <TextInput
                style={styles.input}
                placeholder="輸入商品名稱、型號…"
                placeholderTextColor={Colors.disabled}
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={handleTextSearch}
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
              style={[styles.btn, !query.trim() && styles.btnDisabled]}
              onPress={handleTextSearch}
              disabled={!query.trim()}
              activeOpacity={0.8}
            >
              <Ionicons name="analytics" size={18} color="#fff" />
              <Text style={styles.btnText}>開始比價</Text>
            </TouchableOpacity>

            {/* Quick examples */}
            <Text style={styles.examplesLabel}>熱門搜尋</Text>
            <View style={styles.chips}>
              {EXAMPLES.map((ex) => (
                <TouchableOpacity
                  key={ex}
                  style={styles.chip}
                  onPress={() => { setQuery(ex); Haptics.selectionAsync(); }}
                >
                  <Text style={styles.chipText}>{ex}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* ── Image mode ─────────────────────────────────────────────── */}
        {mode === 'image' && (
          <View style={styles.card}>
            <View style={styles.imageBtns}>
              <TouchableOpacity style={styles.imageBtn} onPress={pickFromCamera} activeOpacity={0.8}>
                <Ionicons name="camera" size={28} color={Colors.primary} />
                <Text style={styles.imageBtnLabel}>拍照</Text>
              </TouchableOpacity>
              <View style={styles.imageBtnDivider} />
              <TouchableOpacity style={styles.imageBtn} onPress={pickFromGallery} activeOpacity={0.8}>
                <Ionicons name="images" size={28} color={Colors.primary} />
                <Text style={styles.imageBtnLabel}>從相簿選取</Text>
              </TouchableOpacity>
            </View>

            {imageUri ? (
              <>
                <View style={styles.previewWrapper}>
                  <Image source={{ uri: imageUri }} style={styles.preview} resizeMode="cover" />
                  <TouchableOpacity
                    style={styles.previewClear}
                    onPress={() => setImageUri(null)}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Ionicons name="close-circle" size={26} color="#fff" />
                  </TouchableOpacity>
                </View>
                <TouchableOpacity style={styles.btn} onPress={handleImageSearch} activeOpacity={0.8}>
                  <Ionicons name="analytics" size={18} color="#fff" />
                  <Text style={styles.btnText}>分析此圖片</Text>
                </TouchableOpacity>
              </>
            ) : (
              <View style={styles.imagePlaceholder}>
                <Ionicons name="image-outline" size={52} color={Colors.border} />
                <Text style={styles.imagePlaceholderText}>請拍照或從相簿選取商品圖片</Text>
              </View>
            )}
          </View>
        )}

        {/* Error */}
        {error && (
          <View style={styles.errorBox}>
            <Ionicons name="alert-circle" size={18} color={Colors.error} />
            <Text style={styles.errorText} selectable>{error}</Text>
          </View>
        )}

        {/* Tips */}
        <View style={styles.tips}>
          <Text style={styles.tipsTitle}>💡 使用說明</Text>
          {[
            '支援電子、美妝、食品、服飾等各類商品',
            '日本退稅 10% 僅適用於實體門市購買',
            '比較結果已納入國際運費試算參考',
            '圖片搜尋請確保畫面清晰、有商品包裝文字',
          ].map((t, i) => (
            <Text key={i} style={styles.tipItem}>• {t}</Text>
          ))}
        </View>
      </ScrollView>

      {loading && <LoadingOverlay />}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll:   { flex: 1, backgroundColor: Colors.background },
  content:  { paddingBottom: 48 },

  /* hero */
  hero: {
    paddingTop: 32,
    paddingBottom: 28,
    paddingHorizontal: 24,
    alignItems: 'center',
  },
  heroFlags: { fontSize: 28, marginBottom: 8 },
  heroTitle: { fontSize: 24, fontWeight: '900', color: '#fff', marginBottom: 8, textAlign: 'center' },
  heroSub:   { fontSize: 13, color: 'rgba(255,255,255,0.85)', textAlign: 'center', lineHeight: 20 },

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
  tab:           { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 10, gap: 6 },
  tabActive:     { backgroundColor: '#FDECEA' },
  tabLabel:      { fontSize: 14, color: Colors.textSecondary, fontWeight: '600' },
  tabLabelActive:{ color: Colors.primary },

  /* card */
  card: {
    backgroundColor: Colors.card,
    borderRadius: 16,
    margin: 16,
    padding: 16,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 8,
    elevation: 3,
    gap: 14,
  },

  /* text input */
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
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.primary,
    borderRadius: 12,
    paddingVertical: 14,
    gap: 8,
  },
  btnDisabled: { backgroundColor: Colors.disabled },
  btnText:     { color: '#fff', fontSize: 16, fontWeight: '800' },

  /* quick examples */
  examplesLabel: { fontSize: 12, color: Colors.textSecondary, fontWeight: '600' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip:  { backgroundColor: Colors.background, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6 },
  chipText: { fontSize: 12, color: Colors.text, fontWeight: '600' },

  /* image mode */
  imageBtns: {
    flexDirection: 'row',
    borderWidth: 1.5,
    borderColor: Colors.border,
    borderRadius: 12,
    overflow: 'hidden',
  },
  imageBtn: { flex: 1, alignItems: 'center', paddingVertical: 20, gap: 8 },
  imageBtnDivider: { width: 1.5, backgroundColor: Colors.border },
  imageBtnLabel: { fontSize: 13, fontWeight: '700', color: Colors.primary },
  imagePlaceholder: {
    alignItems: 'center',
    paddingVertical: 32,
    gap: 10,
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: Colors.border,
    borderRadius: 12,
  },
  imagePlaceholderText: { fontSize: 13, color: Colors.textSecondary, textAlign: 'center' },
  previewWrapper: { position: 'relative' },
  preview: { width: '100%', height: 220, borderRadius: 10 },
  previewClear: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: 13,
  },

  /* error */
  errorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#FDECEA',
    borderRadius: 10,
    marginHorizontal: 16,
    padding: 12,
    gap: 8,
  },
  errorText: { flex: 1, fontSize: 13, color: Colors.error, lineHeight: 19 },

  /* tips */
  tips: {
    marginHorizontal: 16,
    marginTop: 4,
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 16,
    gap: 6,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  tipsTitle: { fontSize: 14, fontWeight: '700', color: Colors.text, marginBottom: 2 },
  tipItem:   { fontSize: 13, color: Colors.textSecondary, lineHeight: 20 },
});
