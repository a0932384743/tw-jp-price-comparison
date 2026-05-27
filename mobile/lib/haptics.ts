import { Platform } from 'react-native';
import * as Haptics from 'expo-haptics';

/**
 * Safe haptic feedback wrapper that only works on native platforms
 * Web platform will silently ignore haptic calls
 */

export const hapticSelection = () => {
  if (Platform.OS !== 'web') {
    Haptics.selectionAsync().catch(() => {});
  }
};

export const hapticImpact = (style: Haptics.ImpactFeedbackStyle = Haptics.ImpactFeedbackStyle.Medium) => {
  if (Platform.OS !== 'web') {
    Haptics.impactAsync(style).catch(() => {});
  }
};

export const hapticNotification = (type: Haptics.NotificationFeedbackType) => {
  if (Platform.OS !== 'web') {
    Haptics.notificationAsync(type).catch(() => {});
  }
};

