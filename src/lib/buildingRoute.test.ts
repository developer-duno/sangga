import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { buildingRewriteTarget } from './buildingRoute';

const BLD = '1168010600109420015_10241100257870';
const HERE = dirname(fileURLToPath(import.meta.url));

describe('buildingRewriteTarget — middleware 판정(결정 0037)', () => {
  it('bld 가 건물 번호 꼴이면 /api/building 으로 · sgg·bld 를 넘긴다', () => {
    expect(buildingRewriteTarget(`https://sangga-one.vercel.app/?sgg=11680&bld=${BLD}`)).toBe(
      `https://sangga-one.vercel.app/api/building?sgg=11680&bld=${BLD}`,
    );
    expect(buildingRewriteTarget(`https://x.vercel.app/?bld=${BLD}`)).toBe(`https://x.vercel.app/api/building?bld=${BLD}`);
  });

  it('sgg·bld 두 값만 다시 조립한다 — 낯선 인자는 사라지고 순서는 sgg 먼저', () => {
    expect(buildingRewriteTarget(`https://sangga-one.vercel.app/?x=123&bld=${BLD}&utm_source=a&sgg=11680`)).toBe(
      `https://sangga-one.vercel.app/api/building?sgg=11680&bld=${BLD}`,
    );
    // sgg 꼴이 틀리면 빼고 bld 만(캐시 열쇠를 늘리지 않는다)
    expect(buildingRewriteTarget(`https://sangga-one.vercel.app/?sgg=abc&bld=${BLD}`)).toBe(
      `https://sangga-one.vercel.app/api/building?bld=${BLD}`,
    );
    // 같은 bld 를 두 번 적어도 첫 값 하나만
    expect(buildingRewriteTarget(`https://sangga-one.vercel.app/?bld=${BLD}&bld=${BLD}9`)).toBe(
      `https://sangga-one.vercel.app/api/building?bld=${BLD}`,
    );
  });

  it('bld 가 없으면 null', () => {
    expect(buildingRewriteTarget('https://sangga-one.vercel.app/')).toBeNull();
    expect(buildingRewriteTarget('https://sangga-one.vercel.app/?sgg=11680')).toBeNull();
  });

  it('bld 꼴이 틀리면 null', () => {
    for (const bad of ['1168010600109420015', 'abc', `${BLD}x`, '', `${'1'.repeat(19)}_${'1'.repeat(33)}`]) {
      expect(buildingRewriteTarget(`https://sangga-one.vercel.app/?bld=${encodeURIComponent(bad)}`), bad).toBeNull();
    }
  });

  it('다른 경로는 bld 가 있어도 null(정적 파일·함수 주소를 안 건드린다)', () => {
    for (const p of ['/index.html', '/districts.geojson', '/api/building', '/assets/index-x.js']) {
      expect(buildingRewriteTarget(`https://sangga-one.vercel.app${p}?bld=${BLD}`), p).toBeNull();
    }
  });

  it('건물 번호 꼴은 화면 urlState.ts 의 BLD_RE 와 같은 글자다(buildingHead.ts 대조)', () => {
    const re = (file: string) => readFileSync(resolve(HERE, file), 'utf-8').match(/const BLD_RE = (\/.*\/);/)?.[1];
    expect(re('urlState.ts')).toBeDefined();
    expect(re('buildingHead.ts')).toBe(re('urlState.ts'));
  });

  // ⓘ 2026-10-09 두 단계 배포: PR① 은 함수만 → PR② 가 middleware.ts 를 더하며 이 skip 을 지운다.
  it.skipIf(!existsSync(resolve(HERE, '../../middleware.ts')))('middleware.ts 는 matcher "/" · 이 판정을 .js 확장자로 부른다', () => {
    const src = readFileSync(resolve(HERE, '../../middleware.ts'), 'utf-8');
    expect(src).toContain("matcher: '/'");
    expect(src).toContain("from './src/lib/buildingRoute.js'");
  });
});
