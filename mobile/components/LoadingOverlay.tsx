import React, { useEffect, useRef } from 'react';
import {
  Animated,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Colors } from '../constants/colors';

const DOT_COUNT = 3;
const DURATION = 600;

export default function LoadingOverlay() {
  const anims = useRef(Array.from({ length: DOT_COUNT }, () => new Animated.Value(0))).current;

  useEffect(() => {
    const animations = anims.map((anim, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * (DURATION / DOT_COUNT)),
          Animated.timing(anim, { toValue: 1, duration: DURATION / 2, useNativeDriver: true }),
          Animated.timing(anim, { toValue: 0, duration: DURATION / 2, useNativeDriver: true }),
        ])
      )
    );
    animations.forEach((a) => a.start());
    return () => animations.forEach((a) => a.stop());
  }, [anims]);

  return (
    <View style={styles.overlay}>
      <View style={styles.box}>
        <Text style={styles.emoji}>🤖</Text>
        <Text style={styles.title}>AI 正在分析中</Text>
        <Text style={styles.sub}>識別商品、查詢台日價格</Text>
        <View style={styles.dots}>
          {anims.map((anim, i) => (
            <Animated.View
              key={i}
              style={[
                styles.dot,
                {
                  opacity: anim,
                  transform: [{ translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [0, -8] }) }],
                },
              ]}
            />
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 999,
  },
  box: {
    backgroundColor: Colors.card,
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    width: 240,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 10,
  },
  emoji:  { fontSize: 40, marginBottom: 12 },
  title:  { fontSize: 17, fontWeight: '700', color: Colors.text, marginBottom: 6 },
  sub:    { fontSize: 13, color: Colors.textSecondary, textAlign: 'center' },
  dots:   { flexDirection: 'row', marginTop: 20, gap: 8 },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: Colors.primary,
  },
});
