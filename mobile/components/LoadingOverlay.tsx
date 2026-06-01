import React, { useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';
import { Colors } from '../constants/colors';

interface Step { emoji: string; label: string; durationMs: number; }

const STEPS: Step[] = [
  { emoji: '🔍', label: 'AI 識別商品中…',     durationMs: 2500 },
  { emoji: '🇹🇼', label: '搜尋台灣電商價格…', durationMs: 5000 },
  { emoji: '🇯🇵', label: '搜尋日本電商價格…', durationMs: 5000 },
  { emoji: '✨', label: 'AI 生成購買建議…',    durationMs: 99999 },
];

export default function LoadingOverlay() {
  const [stepIdx, setStepIdx] = useState(0);
  const fadeAnim = useRef(new Animated.Value(1)).current;
  const barAnim  = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let cancelled = false;
    let idx = 0;
    const advance = () => {
      if (cancelled || idx >= STEPS.length - 1) return;
      Animated.timing(fadeAnim, { toValue: 0, duration: 250, useNativeDriver: true }).start(() => {
        if (cancelled) return;
        idx += 1;
        setStepIdx(idx);
        Animated.timing(fadeAnim, { toValue: 1, duration: 300, useNativeDriver: true }).start();
        setTimeout(advance, STEPS[idx].durationMs);
      });
    };
    setTimeout(advance, STEPS[0].durationMs);
    return () => { cancelled = true; };
  }, [fadeAnim]);

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(barAnim, { toValue: 1, duration: 1600, useNativeDriver: false }),
        Animated.timing(barAnim, { toValue: 0, duration: 0,    useNativeDriver: false }),
      ])
    ).start();
  }, [barAnim]);

  const barWidth = barAnim.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });
  const step = STEPS[stepIdx];

  return (
    <View style={s.overlay}>
      <View style={s.box}>
        <View style={s.dots}>
          {STEPS.map((_, i) => (
            <View key={i} style={[s.dot, i < stepIdx && s.dotDone, i === stepIdx && s.dotActive]} />
          ))}
        </View>

        <Animated.View style={[s.stepContent, { opacity: fadeAnim }]}>
          <Text style={s.emoji}>{step.emoji}</Text>
          <Text style={s.label}>{step.label}</Text>
        </Animated.View>

        <View style={s.trackOuter}>
          <Animated.View style={[s.trackFill, { width: barWidth }]} />
        </View>

        <Text style={s.hint}>通常需要 10–20 秒</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 999,
  },
  box: {
    backgroundColor: Colors.card,
    borderRadius: 24,
    padding: 28,
    alignItems: 'center',
    width: 260,
    gap: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 16,
    elevation: 12,
  },
  dots:      { flexDirection: 'row', gap: 8 },
  dot:       { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.border },
  dotDone:   { backgroundColor: Colors.success },
  dotActive: { backgroundColor: Colors.primary, width: 24 },
  stepContent: { alignItems: 'center', gap: 8 },
  emoji:     { fontSize: 38 },
  label:     { fontSize: 15, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  trackOuter: { width: '100%', height: 4, backgroundColor: Colors.border, borderRadius: 2, overflow: 'hidden' },
  trackFill:  { height: 4, backgroundColor: Colors.primary, borderRadius: 2 },
  hint:      { fontSize: 11, color: Colors.textTertiary },
});
