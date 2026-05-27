import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle:      { backgroundColor: '#C0392B' },
          headerTintColor:  '#fff',
          headerTitleStyle: { fontWeight: '800', fontSize: 17 },
          headerBackTitle:  '返回',
          animation:        'slide_from_right',
          contentStyle:     { backgroundColor: '#F2F2F7' },
        }}
      >
        <Stack.Screen
          name="index"
          options={{ title: '台日比價 AI 顧問', headerLargeTitle: false }}
        />
        <Stack.Screen
          name="results"
          options={{ title: '比價結果' }}
        />
      </Stack>
    </>
  );
}
