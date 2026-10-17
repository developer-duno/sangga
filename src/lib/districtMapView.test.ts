/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import {
  CORE_MIN_FEATURES,
  coreBoundsOf,
  FAR_DOT_MAX_PX,
  farDots,
  mapItemsOf,
  offscreenGroups,
  type MapItem,
  type MapView,
} from './districtMapView';
import { labelPointOf } from './districtLabels';
import { boundsOf, type Bounds } from './geo';
import type { DistrictFeature, DistrictGeometry, Ring } from '../types';

/**
 * 지도 보이는 범위 판정 시험(결정 0039 Q4 · W1).
 * ⓘ E2E 에는 카카오 키가 없어 지도가 안 그려진다 — 화면 밖 표지·점+이름의 가드는 여기와 `DistrictMap.test.tsx` 가 전부다.
 */

/** 지금 화면 — 경도 0~10 · 위도 0~10 을 1000×1000px 에(1px = 0.01°). */
const VIEW: Bounds = { swLng: 0, swLat: 0, neLng: 10, neLat: 10 };
const far = (level = 6): MapView => ({ bounds: VIEW, widthPx: 1000, heightPx: 1000, level });

function item(id: string, lng: number, lat: number, over: Partial<MapItem> = {}): MapItem {
  // 기본 상자 = 한 변 0.1°(화면에서 10px — 점으로 다는 크기).
  return {
    id,
    nm: id,
    at: { lat, lng },
    area: 1,
    box: { swLng: lng - 0.05, swLat: lat - 0.05, neLng: lng + 0.05, neLat: lat + 0.05 },
    ...over,
  };
}

describe('mapItemsOf — 상권 → 지도 요약', () => {
  it('이름표 점·상자·면적을 붙이고 이름이 비면 (이름 없음)', () => {
    const f: DistrictFeature = {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [box(1, 1, 3, 3)] },
      properties: {
        district_id: 'a',
        district_nm: '',
        district_type: '골목상권',
        source_nm: 's',
        sigungu_code: '30170',
        area_m2: null,
      },
    };
    expect(mapItemsOf([f])).toEqual([
      { id: 'a', nm: '(이름 없음)', at: { lat: 2, lng: 2 }, area: 0, box: { swLng: 1, swLat: 1, neLng: 3, neLat: 3 } },
    ]);
  });
});

describe('offscreenGroups — 화면 밖 표지', () => {
  it('8방향으로 묶는다 — 위 줄 → 가운데 → 아래 줄 순서', () => {
    const groups = offscreenGroups(
      [
        item('se', 11, -1),
        item('nw', -1, 11),
        item('n', 5, 11),
        item('ne', 11, 11),
        item('w', -1, 5),
        item('e', 11, 5),
        item('sw', -1, -1),
        item('s', 5, -1),
      ],
      VIEW,
    );
    expect(groups.map((g) => `${g.arrow}${g.dir}`)).toEqual(['↖nw', '↑n', '↗ne', '←w', '→e', '↙sw', '↓s', '↘se']);
    expect(groups.every((g) => g.count === 1)).toBe(true);
  });

  it('화면 안(가장자리 포함)은 셈에 안 든다', () => {
    expect(offscreenGroups([item('a', 5, 5), item('edge', 10, 0)], VIEW)).toEqual([]);
  });

  it('이름은 그 방향에서 면적이 가장 큰 상권 · 곳 수는 묶음 전부', () => {
    const [g] = offscreenGroups(
      [item('작은', -1, -1, { area: 5 }), item('가장큰', -3, -2, { area: 90 }), item('중간', -2, -3, { area: 40 })],
      VIEW,
    );
    expect(g).toMatchObject({ dir: 'sw', arrow: '↙', word: '왼쪽 아래', count: 3, nm: '가장큰' });
  });

  it('옮겨 갈 곳 = 그 묶음 이름표 점들을 담는 상자의 가운데', () => {
    const [g] = offscreenGroups([item('a', 12, 2), item('b', 14, 8), item('c', 13, 4)], VIEW);
    expect(g.dir).toBe('e');
    expect(g.center).toEqual({ lat: 5, lng: 13 });
  });
});

describe('farDots — 멀리서는 점 + 이름', () => {
  it(`화면에서 작은 상권(긴 변 ${FAR_DOT_MAX_PX}px 미만)만 점 — 큰 것은 점이 없다`, () => {
    const big = item('큰', 3, 3, { box: { swLng: 2.9, swLat: 2.9, neLng: 3.1, neLat: 3.1 } }); // 20px
    const edge = item('경계', 5, 5, { box: { swLng: 4.92, swLat: 4.92, neLng: 5.08, neLat: 5.08 } }); // 16px
    const small = item('작은', 7, 7); // 10px
    expect(farDots([big, edge, small], far()).map((d) => d.id)).toEqual(['작은']);
  });

  it('이름이 겹치면 면적 작은 쪽 이름만 빠지고 점은 남는다', () => {
    const a = item('가나다라', 5, 5, { area: 10 });
    const b = item('마바사아', 5.2, 5.05, { area: 50 }); // 오른쪽 20px · 위 5px — 이름 상자가 겹친다
    const c = item('자차카타', 8, 2, { area: 1 }); // 멀리 — 안 겹친다
    const dots = farDots([a, b, c], far());
    expect(dots).toEqual([
      { id: '가나다라', at: a.at, nm: null },
      { id: '마바사아', at: b.at, nm: '마바사아' },
      { id: '자차카타', at: c.at, nm: '자차카타' },
    ]);
  });

  it('겹치지 않을 만큼 떨어지면 둘 다 이름이 붙는다(양성 대조)', () => {
    const dots = farDots([item('가나다라', 5, 5), item('마바사아', 5.2, 5.5)], far());
    expect(dots.every((d) => d.nm !== null)).toBe(true);
  });

  it('이름표가 켜지는 배율(level ≤ 5)에서는 점이 없다 — 이름표가 대신한다', () => {
    expect(farDots([item('작은', 7, 7)], far(5))).toEqual([]);
    expect(farDots([item('작은', 7, 7)], far(6))).toHaveLength(1);
  });

  it('화면 밖 상권은 점이 아니라 가장자리 표지가 맡는다', () => {
    expect(farDots([item('밖', 12, 5)], far())).toEqual([]);
  });

  it('지도 칸 크기를 아직 모르면(0px) 점을 달지 않는다', () => {
    expect(farDots([item('작은', 7, 7)], { ...far(), widthPx: 0 })).toEqual([]);
  });
});

// ── 몰린 곳 상자 (결정 0039 Q4 · W1) ─────────────────────────────────────────

function box(west: number, south: number, east: number, north: number): Ring {
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ];
}

function area(id: string, geometry: DistrictGeometry): DistrictFeature {
  return {
    type: 'Feature',
    geometry,
    properties: {
      district_id: id,
      district_nm: id,
      district_type: '골목상권',
      source_nm: '테스트 출처',
      sigungu_code: '30170',
      area_m2: 1,
    },
  };
}

const poly = (id: string, r: Ring) => area(id, { type: 'Polygon', coordinates: [r] });

describe('coreBoundsOf — 몰린 곳 상자', () => {
  /*
    서쪽에 같은 네모 넷이 **겹쳐** 있고(X), 그 옆에 좁은 Y, 멀리 동쪽 끝에 작은 Z.
    겹침을 한 번만 세면 X:Y:Z ≈ 1 : 0.5 : 0.1 이라 75% 지점이 Y 에 닿아 Y 까지 담는다(Z 는 빠진다).
    겹침을 두 번 이상 세면 X 가 2~4 가 되어 75% 지점이 X 안에서 끝나 **Y 가 빠진다** — 그래서 '한 번만'을 실제로 가른다.
    (구간 = 가운데 절반 25~75% — 👤 재확인 2026-10-17 · 결정 0039 §7-5)
  */
  const STACK = [
    poly('X1', box(0, 0, 1, 1)),
    poly('X2', box(0, 0, 1, 1)),
    poly('X3', box(0, 0, 1, 1)),
    poly('X4', box(0, 0, 1, 1)),
    poly('Y', box(2, 0, 2.5, 1)),
    poly('Z', box(10, 0, 10.1, 1)),
  ];

  it('ⓐ 겹친 면적은 한 번만 센다 — 옆의 Y 는 담고 멀리 떨어진 Z 는 뺀다', () => {
    const core = coreBoundsOf(STACK)!;
    // 서쪽 끝은 X 안(아래 25% 를 잘라 X 의 왼쪽이 깎인다) · 동쪽 끝은 Y 안(X 는 lng 1 에서 끝난다).
    expect(core.swLng).toBeGreaterThanOrEqual(0);
    expect(core.swLng).toBeLessThan(1);
    expect(core.neLng).toBeGreaterThan(2);
    expect(core.neLng).toBeLessThan(3);
    // 전부 담는 상자는 Z 까지 간다 — 몰린 곳 상자는 그보다 훨씬 좁다.
    expect(boundsOf(STACK)!.neLng).toBe(10.1);
  });

  it(`ⓑ 상권이 ${CORE_MIN_FEATURES}곳 이하면 전부 담는 상자 그대로 — ${CORE_MIN_FEATURES + 1}곳부터 잘라 낸다`, () => {
    const five = STACK.slice(1); // X2·X3·X4·Y·Z — 5곳
    expect(five).toHaveLength(5);
    expect(coreBoundsOf(five)).toEqual(boundsOf(five));
    expect(STACK).toHaveLength(6);
    expect(coreBoundsOf(STACK)).not.toEqual(boundsOf(STACK));
  });

  it('ⓒ 칸보다 작은 상권도 셈에 든다 — 이름표 점이 든 칸 하나를 칠한다', () => {
    // A 는 2×2 칸쯤, 동쪽 끝의 작은 상권 다섯은 칸 가운데를 하나도 못 품는다(0.001° — 칸은 약 0.039°).
    // 작은 것을 빼면 A 만 남아 상자가 서쪽 끝(약 0.08°)에 붙는다 — 세면 9칸 중 5칸이 동쪽이라 75% 지점이 동쪽까지 간다.
    const tiny = [0.1, 0.3, 0.5, 0.7, 0.9].map((lat, k) => poly(`t${k}`, box(9.9, lat, 9.901, lat + 0.001)));
    const core = coreBoundsOf([poly('A', box(0, 0, 0.08, 0.08)), ...tiny])!;
    expect(core.neLng).toBeGreaterThan(9);
    expect(core.neLat).toBeGreaterThan(0.5);
  });

  it('ⓓ MultiPolygon 은 조각을 전부 센다 — 떨어진 두 Polygon 으로 나눈 것과 같다', () => {
    const rest = STACK.slice(0, 4);
    // 둘째 조각이 Y 다 — 첫 조각만 세면 Y 가 빠져 상자가 X 에서 끝난다.
    const multi = area('ZY', { type: 'MultiPolygon', coordinates: [[box(10, 0, 10.1, 1)], [box(2, 0, 2.5, 1)]] });
    const extra = poly('W', box(0.2, 0.2, 0.4, 0.4));
    const core = coreBoundsOf([...rest, multi, extra])!;
    expect(core).toEqual(
      coreBoundsOf([...rest, poly('Y', box(2, 0, 2.5, 1)), poly('Z', box(10, 0, 10.1, 1)), extra]),
    );
    expect(core.neLng).toBeGreaterThan(2);
  });

  it('ⓔ 상권이 없으면 null — 지도를 어디로 맞출지 모른다', () => {
    expect(coreBoundsOf([])).toBeNull();
  });
});

describe('coreBoundsOf — 실자료 30개 구(public/districts.geojson)', () => {
  const HERE = dirname(fileURLToPath(import.meta.url));
  const all = (
    JSON.parse(readFileSync(resolve(HERE, '../../public/districts.geojson'), 'utf-8')) as {
      features: DistrictFeature[];
    }
  ).features;
  const byGu = new Map<string, DistrictFeature[]>();
  for (const f of all) byGu.set(f.properties.sigungu_code, [...(byGu.get(f.properties.sigungu_code) ?? []), f]);

  /** 상자 긴 변(km) — 경도 1° 는 위도에 따라 짧아진다. */
  const longKm = (b: Bounds) => {
    const lat = ((b.swLat + b.neLat) / 2) * (Math.PI / 180);
    return Math.max((b.neLng - b.swLng) * 111.32 * Math.cos(lat), (b.neLat - b.swLat) * 110.57);
  };
  const inside = (b: Bounds, inner: Bounds) =>
    inner.swLng >= b.swLng && inner.neLng <= b.neLng && inner.swLat >= b.swLat && inner.neLat <= b.neLat;

  it('30개 구가 다 있다', () => {
    expect(byGu.size).toBe(30);
  });

  it('모든 구에서 몰린 곳 상자는 전부 담는 상자 안이다', () => {
    for (const [, fs] of byGu) {
      const full = boundsOf(fs)!;
      const core = coreBoundsOf(fs)!;
      expect(inside(full, core)).toBe(true);
    }
  });

  it(`상권 ${CORE_MIN_FEATURES}곳 이하인 대전 동구(30110)·대덕구(30230)는 전부 담는다`, () => {
    for (const gu of ['30110', '30230']) {
      const fs = byGu.get(gu)!;
      expect(fs.length).toBeLessThanOrEqual(CORE_MIN_FEATURES);
      expect(coreBoundsOf(fs)).toEqual(boundsOf(fs));
    }
  });

  it('대전 서구(30170)는 상자가 줄고 둔산동(시청역6번 출구·대전둔산초등학교)이 그 안에 든다', () => {
    const fs = byGu.get('30170')!;
    const full = boundsOf(fs)!;
    const core = coreBoundsOf(fs)!;
    expect(longKm(core)).toBeLessThan(longKm(full));
    // 가운데 절반(25~75%)의 실측 = 긴 변 2.18km(전체 8.10km). 처음 정한 10~90% 면 6.14km 로 넓은 화면이 2km 축척 그대로였다
    // (👤 재확인 2026-10-17 · 결정 0039 §7-5) — 구간이 되돌아가면 여기서 빨강.
    expect(longKm(core)).toBeLessThan(3);
    for (const nm of ['시청역6번 출구', '대전둔산초등학교']) {
      const f = fs.find((x) => x.properties.district_nm === nm);
      expect(f, nm).toBeTruthy();
      const at = labelPointOf(f!.geometry)!;
      expect(at.lng >= core.swLng && at.lng <= core.neLng && at.lat >= core.swLat && at.lat <= core.neLat, nm).toBe(
        true,
      );
    }
  });
});
