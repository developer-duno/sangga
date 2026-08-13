import { defineConfig, devices } from '@playwright/test';

/**
 * E2E(playwright) 설정 — "여러 조각이 실제로 이어 붙는가"만 본다.
 *
 * 단위 테스트(FloorStack.test.tsx·BuildingSearch.test.tsx)가 각 컴포넌트를 vi.mock으로
 * 격리해서 보는 것과 달리, 여기는 App.tsx가 실제로 렌더한 화면에서 검색→선택→층 스택
 * 렌더까지 브라우저로 붙여서 본다. 네트워크(Supabase REST)는 e2e/floor-stack.spec.ts가
 * page.route로 전부 가로채므로 라이브 DB·비밀값에 의존하지 않는다.
 *
 * `pnpm build`(프로덕션 번들)가 아니라 `pnpm dev`를 쓴다 — 이 테스트들은 DOM 배선만
 * 보므로 프로덕션 번들 차이가 무의미하고, CI web job의 기존 순서(lint→test→typecheck+build)
 * 를 건드리지 않아도 된다.
 */
// 여러 프로젝트가 한 PC에서 동시에 도는 환경이라 5173이 남의 서버일 수 있다(2026-08-14
// 실측 — reuseExistingServer가 다른 프로젝트 화면을 재사용해 6개 전부 타임아웃).
// E2E_PORT로 비켜 가고, strictPort로 vite가 말없이 옆 포트로 옮겨 앉는 것도 막는다.
const port = Number(process.env.E2E_PORT ?? 5173);

export default defineConfig({
  testDir: './e2e',
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  use: {
    baseURL: `http://localhost:${port}`,
  },
  webServer: {
    command: `pnpm dev --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
    env: {
      // src/lib/supabase.ts는 이 값이 없으면 모듈 로드 시 throw한다. 값 자체는 어디에도
      // 실제로 접속하지 않는다 — 모든 요청을 e2e/floor-stack.spec.ts가 가로챈다.
      VITE_SUPABASE_URL: 'https://e2e-test.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'e2e-test-anon-key',
    },
  },
});
