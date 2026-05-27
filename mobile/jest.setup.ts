import '@testing-library/react-native/extend-expect';
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

jest.mock('react-native/Libraries/Linking/Linking', () => ({
  openURL:          jest.fn().mockResolvedValue(undefined),
  canOpenURL:       jest.fn().mockResolvedValue(true),
  addEventListener: jest.fn(),
}));
