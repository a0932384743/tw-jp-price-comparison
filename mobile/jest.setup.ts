// @testing-library/react-native v13+ auto-registers matchers — no extend-expect import needed
import { UIManager } from 'react-native';

UIManager.setLayoutAnimationEnabledExperimental = jest.fn();

// ── Expo module mocks ──────────────────────────────────────────────────────

jest.mock('@expo/vector-icons', () => {
  // Must return a real React element, not a plain function call
  const React = require('react');
  const { Text } = require('react-native');
  return {
    Ionicons: (props: { name: string; [key: string]: unknown }) =>
      React.createElement(Text, { testID: `icon-${props.name}` }, props.name),
  };
});

jest.mock('expo-linear-gradient', () => {
  const { View } = require('react-native');
  return { LinearGradient: View };
});

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  selectionAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle:      { Light: 'Light', Medium: 'Medium', Heavy: 'Heavy' },
  NotificationFeedbackType: { Error: 'Error', Success: 'Success', Warning: 'Warning' },
}));

jest.mock('expo-image-picker', () => ({
  requestMediaLibraryPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  requestCameraPermissionsAsync:       jest.fn().mockResolvedValue({ granted: true }),
  launchImageLibraryAsync: jest.fn().mockResolvedValue({ canceled: true, assets: [] }),
  launchCameraAsync:       jest.fn().mockResolvedValue({ canceled: true, assets: [] }),
  MediaTypeOptions: { Images: 'Images' },
}));

jest.mock('expo-router', () => ({
  useRouter:            jest.fn(() => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() })),
  useLocalSearchParams: jest.fn(() => ({})),
  Stack: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));

// Linking is tested via jest.spyOn(Linking, 'openURL') in PlatformCard.test.tsx
// Avoid mocking the internal path here – it changed in React Native 0.85+.
