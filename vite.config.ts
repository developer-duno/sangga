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
    // ⚠️ 지도 키는 테스트에서 **항상 비운다.** vitest도 vite라 `.env.local`을 읽는데,
    //    그 파일은 개발자 PC에만 있고 CI에는 없다 — 비워 두지 않으면 내 PC에서만
    //    카카오 스크립트를 실제로 내려받으려 들어 결과가 환경마다 달라진다.
    //    키가 있는 상태가 필요한 테스트는 vi.stubEnv로 그 테스트 안에서만 켠다.
    env: { VITE_KAKAO_JS_KEY: '' },
  },
})
