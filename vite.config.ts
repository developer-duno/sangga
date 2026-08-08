import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 프론트 테스트. 예전에는 러너 자체가 없어서 화면 로직 버그가 CI를 그대로 통과했다
  // (지하만 있는 건물의 층 표기가 "지하 5층 ~ -1층"으로 나온 것 등, 2026-08-08 적대검증).
  test: {
    // 컴포넌트 렌더링 테스트에 DOM이 필요하다.
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
