import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { buildingRewriteTarget } from './buildingRoute';

const BLD = '1168010600109420015_10241100257870';
const HERE = dirname(fileURLToPath(import.meta.url));

describe('buildingRewriteTarget — middleware 판정(결정 0037)', () => {
  it('bld 가 건물 번호 꼴이면 /api/building 으로 · query 그대로', () => {
    expect(buildingRewriteTarget(`https://sangga-one.vercel.app/?sgg=11680&bld=${BLD}`)).toBe(
      `https://sangga-one.vercel.app/api/building?sgg=11680&bld=${BLD}`,
    );
    expect(buildingRewriteTarget(`https://x.vercel.app/?bld=${BLD}`)).toBe(`https://x.vercel.app/api/building?bld=${BLD}`);
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

  it('middleware.ts 는 matcher "/" · 이 판정을 .js 확장자로 부른다', () => {
    const src = readFileSync(resolve(HERE, '../../middleware.ts'), 'utf-8');
    expect(src).toContain("matcher: '/'");
    expect(src).toContain("from './src/lib/buildingRoute.js'");
  });
});
