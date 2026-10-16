import { boundsOf, pointInGeometry, type Bounds } from './geo';
import { labelPointOf, showLabels } from './districtLabels';
import type { DistrictFeature } from '../types';

/**
 * 상권 지도의 **범위**에 따라 정하는 것들(결정 0039 Q4 · §4-12 · W1).
 *
 *  ⓪ **첫 범위** — 구 전체가 아니라 상권이 몰린 곳에 맞춘다(`coreBoundsOf`).
 *  ① **화면 밖 표지** — 지금 화면 밖에 있는 상권을 8방향으로 묶어 가장자리에 「↙ 이름 등 3곳」을 단다.
 *     첫 화면은 몰린 곳 상자(`coreBoundsOf`)에 맞추므로 그 밖으로 잘린 상권이 '사라진 것'처럼 보이지
 *     않게 한다. 사용자가 지도를 옮기면 따라 바뀐다.
 *  ② **멀리서는 점 + 이름** — 이름표가 꺼지는 배율(level > 5)에서 화면에서 작은 상권은 면이 점처럼
 *     뭉개져 안 보인다. 그런 상권만 점과 이름을 단다. 이름끼리 겹치면 뒤(면적 작은 쪽)의 이름을 뺀다.
 *
 * ⓘ 판정은 전부 여기(순수 함수)서 하고 화면(`DistrictMap.tsx`)은 부르기만 한다 — 카카오 지도를 띄우지
 *   않고 시험할 수 있어야 한다(E2E 에는 지도 키가 없어 지도가 안 그려진다).
 * ⚠️ 지금 범위·화면 크기는 카카오가 쥔다 — 배율별 '1px 이 몇 m'를 표로 박지 않고 지도가 멈출 때마다
 *    (`onIdle`) 지금 범위 ÷ 지도 칸 크기로 잰다.
 */

// ── ⓪ 첫 범위 = 몰린 곳 상자 ─────────────────────────────────────────────────

/**
 * 상권이 이만큼 이하인 구는 '몰린 곳'을 따로 고르지 않고 전부 담는다(결정 0039 Q4 · W1).
 * 대전 중구(30110)·대덕구(30230)는 상권이 3곳뿐이라 몇 곳을 잘라 내면 지도에 남는 것이 거의 없다.
 */
export const CORE_MIN_FEATURES = 5;

/** 격자 긴 변의 칸 수. 한 구(가장 넓은 강남도 약 10km)에서 칸 하나가 수십 m — 상권 하나보다 작다. */
const CORE_GRID_CELLS = 256;

/**
 * 몰린 곳 상자를 자를 누적 면적 비율 — 경도·위도 각각 **가운데 절반**(아래 25%·위 25% 를 잘라 낸다).
 * → 👤 재확인 2026-10-17(결정 0039 §7-5): 처음 정한 10~90% 로는 대전 서구가 넓은 화면 2km 그대로였다
 *   (30개 구 실측) — 전/후 사진을 보고 25~75% 로(서구 넓은 화면 500m · 휴대폰 1km · 서울 25구 전부 한 단계 이상 가까워짐 ·
 *   대신 27개 구에서 가장자리 표지가 1~6개 뜬다).
 */
const CORE_LOW = 0.25;
const CORE_HIGH = 0.75;

/**
 * 지도를 처음 맞출 **몰린 곳** 상자 — 그 구의 상권 면적이 경도·위도 각각 누적 25%~75%(가운데 절반)에 드는 구간
 * (결정 0039 Q4 · §4-12 · §7-5 · W1). 전부 담는 상자(`boundsOf`)는 외따로 떨어진 상권 하나 때문에 배율이
 * 크게 밀린다(대전 서구: 축척 4km — 둔산동이 손톱만 하게 보였다).
 *
 * 셈 = **격자 칠하기**: 구 전체 상자를 긴 변 기준 약 256칸으로 나누고, 상권마다 자기 상자 안 칸의
 * **가운데 점**이 그 상권 안이면 칸을 칠한다. 칠한 칸들을 경도 열·위도 줄로 더해 누적 25%·75% 칸을 고른다.
 *  ⛔ **겹친 면적은 한 번만 센다** — 칸은 몇 상권이 겹쳐도 1이다(같은 곳을 발달상권·골목상권이 함께
 *     덮는 일이 흔하다). 상권마다 따로 더하면 겹침이 많은 곳이 실제보다 무거워진다.
 *  ⓘ 칸보다 작아 한 칸도 못 칠한 상권은 그 이름표 점(`labelPointOf`)이 든 칸 하나를 칠한다 — 작다고
 *    셈에서 사라지면 작은 골목상권이 모인 동네가 통째로 빠진다.
 *  ⓘ 위도에 따라 경도 1° 의 실제 길이가 달라 칸 넓이도 조금씩 다르지만 무시한다(한 구 안의 위도 차는
 *    0.1° 안팎이라 칸 넓이 차가 1% 안팎이다).
 *  ⓘ 상권이 `CORE_MIN_FEATURES`(5) 곳 이하면 `boundsOf` 그대로 — 화면은 두 갈래를 몰라도 된다.
 *  ⓘ 결과는 언제나 `boundsOf` 상자 안이다(칸 가장자리를 전체 상자로 자른다).
 */
export function coreBoundsOf(features: DistrictFeature[]): Bounds | null {
  const full = boundsOf(features);
  if (full === null || features.length <= CORE_MIN_FEATURES) return full;

  const width = full.neLng - full.swLng;
  const height = full.neLat - full.swLat;
  const cell = Math.max(width, height) / CORE_GRID_CELLS;
  if (!(cell > 0)) return full;
  const nx = Math.max(1, Math.ceil(width / cell));
  const ny = Math.max(1, Math.ceil(height / cell));
  const colOf = (lng: number) => Math.min(nx - 1, Math.max(0, Math.floor((lng - full.swLng) / cell)));
  const rowOf = (lat: number) => Math.min(ny - 1, Math.max(0, Math.floor((lat - full.swLat) / cell)));

  const painted = new Uint8Array(nx * ny);
  for (const f of features) {
    const box = boundsOf([f]);
    if (box === null) continue;
    let hit = false;
    for (let i = colOf(box.swLng); i <= colOf(box.neLng); i += 1) {
      const lng = full.swLng + (i + 0.5) * cell;
      for (let j = rowOf(box.swLat); j <= rowOf(box.neLat); j += 1) {
        const lat = full.swLat + (j + 0.5) * cell;
        if (pointInGeometry(lng, lat, f.geometry)) {
          painted[j * nx + i] = 1;
          hit = true;
        }
      }
    }
    if (!hit) {
      const at = labelPointOf(f.geometry);
      if (at) painted[rowOf(at.lat) * nx + colOf(at.lng)] = 1;
    }
  }

  const cols = new Array<number>(nx).fill(0);
  const rows = new Array<number>(ny).fill(0);
  let total = 0;
  for (let j = 0; j < ny; j += 1) {
    for (let i = 0; i < nx; i += 1) {
      if (painted[j * nx + i]) {
        cols[i] += 1;
        rows[j] += 1;
        total += 1;
      }
    }
  }
  if (total === 0) return full;

  /** 누적이 처음으로 total × q 에 닿는 칸 번호. */
  const quantile = (sums: number[], q: number) => {
    let cum = 0;
    for (let k = 0; k < sums.length; k += 1) {
      cum += sums[k];
      if (cum >= total * q) return k;
    }
    return sums.length - 1;
  };
  const i0 = quantile(cols, CORE_LOW);
  const i1 = quantile(cols, CORE_HIGH);
  const j0 = quantile(rows, CORE_LOW);
  const j1 = quantile(rows, CORE_HIGH);
  return {
    swLng: full.swLng + i0 * cell,
    neLng: Math.min(full.neLng, full.swLng + (i1 + 1) * cell),
    swLat: full.swLat + j0 * cell,
    neLat: Math.min(full.neLat, full.swLat + (j1 + 1) * cell),
  };
}

// ── 지도 요약 ──────────────────────────────────────────────────────────────

/** 지도에 올릴 상권 한 곳의 요약 — 이름표 점·면적·자기 상자. */
export type MapItem = {
  id: string;
  nm: string;
  /** 이름표를 다는 점(`labelPointOf`) — 면 안이 보장된다. */
  at: { lat: number; lng: number };
  /** 면적(㎡). 자료에 없으면 0 — 이름 고르기에서 뒤로 밀릴 뿐이다. */
  area: number;
  /** 이 상권 하나를 담는 상자. */
  box: Bounds;
};

/** 지도가 멈췄을 때 잰 지금 화면. */
export type MapView = {
  bounds: Bounds;
  widthPx: number;
  heightPx: number;
  level: number;
};

/**
 * 상권 목록 → 지도 요약. 이름표 점을 못 잡는 도형은 빠진다(지금 이름표와 같은 규칙).
 * ⚠️ 구가 바뀔 때만 다시 센다(화면에서 `useMemo`) — 무게중심 계산이 상권 수만큼 돈다.
 */
export function mapItemsOf(features: DistrictFeature[]): MapItem[] {
  return features.flatMap((f) => {
    const at = labelPointOf(f.geometry);
    const box = boundsOf([f]);
    if (!at || !box) return [];
    return [
      {
        id: f.properties.district_id,
        nm: f.properties.district_nm || '(이름 없음)',
        at,
        area: f.properties.area_m2 ?? 0,
        box,
      },
    ];
  });
}

// ── ① 화면 밖 표지 ─────────────────────────────────────────────────────────

export type OffDir = 'nw' | 'n' | 'ne' | 'w' | 'e' | 'sw' | 's' | 'se';

/** 표지를 그리는 순서(위 줄 → 가운데 → 아래 줄) · 화살표 · 읽어 줄 말. */
export const OFF_DIRS: ReadonlyArray<{ dir: OffDir; arrow: string; word: string }> = [
  { dir: 'nw', arrow: '↖', word: '왼쪽 위' },
  { dir: 'n', arrow: '↑', word: '위' },
  { dir: 'ne', arrow: '↗', word: '오른쪽 위' },
  { dir: 'w', arrow: '←', word: '왼쪽' },
  { dir: 'e', arrow: '→', word: '오른쪽' },
  { dir: 'sw', arrow: '↙', word: '왼쪽 아래' },
  { dir: 's', arrow: '↓', word: '아래' },
  { dir: 'se', arrow: '↘', word: '오른쪽 아래' },
];

export type OffscreenGroup = {
  dir: OffDir;
  arrow: string;
  word: string;
  count: number;
  /** 그 방향에서 면적이 가장 큰 상권의 이름. */
  nm: string;
  /** 누르면 옮겨 갈 곳 — 그 묶음 이름표 점들을 담는 상자의 가운데. */
  center: { lat: number; lng: number };
};

/** 점 하나가 지금 범위의 어느 쪽 밖인가. 안(가장자리 포함)이면 null. */
function dirOf(at: { lat: number; lng: number }, view: Bounds): OffDir | null {
  const ns = at.lat > view.neLat ? 'n' : at.lat < view.swLat ? 's' : '';
  const ew = at.lng > view.neLng ? 'e' : at.lng < view.swLng ? 'w' : '';
  return ns || ew ? ((ns + ew) as OffDir) : null;
}

/**
 * 지금 범위 밖의 상권을 8방향으로 묶는다. 범위 안의 상권은 셈에 안 든다.
 * ⓘ 방향은 그 상권의 **이름표 점**으로 가른다 — 면이 반쯤 걸쳐 보여도 이름표 점이 안이면 안이다.
 * ⓘ 동 이름은 자료에 없어서 만들지 않는다(👤 결정 0039 Q4) — 이름은 그 방향에서 면적이 가장 큰 상권 하나.
 */
export function offscreenGroups(items: MapItem[], view: Bounds): OffscreenGroup[] {
  const byDir = new Map<OffDir, MapItem[]>();
  for (const it of items) {
    const d = dirOf(it.at, view);
    if (d) byDir.set(d, [...(byDir.get(d) ?? []), it]);
  }
  return OFF_DIRS.flatMap(({ dir, arrow, word }) => {
    const group = byDir.get(dir);
    if (!group) return [];
    let top = group[0];
    for (const it of group) if (it.area > top.area) top = it;
    const lats = group.map((g) => g.at.lat);
    const lngs = group.map((g) => g.at.lng);
    return [
      {
        dir,
        arrow,
        word,
        count: group.length,
        nm: top.nm,
        center: {
          lat: (Math.min(...lats) + Math.max(...lats)) / 2,
          lng: (Math.min(...lngs) + Math.max(...lngs)) / 2,
        },
      },
    ];
  });
}

// ── ② 멀리서는 점 + 이름 ───────────────────────────────────────────────────

/** 상권 상자의 긴 변이 화면에서 이보다 작으면 점으로 단다(px). */
export const FAR_DOT_MAX_PX = 16;

/*
  이름 상자 크기 **어림**(px) — 겹침 판정에만 쓴다. 실제 글자 폭은 글꼴·글자마다 달라 정확히 잴 수 없다.
  ⓘ 이름은 점 오른쪽에서 시작한다 — `styles.css` 의 `.dmap__far`(점 8px 의 가운데가 그 점 · 사이 4px)와 맞춘다.
  ⓘ 이름표(`.dmap__label`)는 최대 폭 116px(+ 테두리 2px)에서 말줄임이라 그보다 넓게 어림하지 않는다.
*/
const NAME_CHAR_PX = 11;
const NAME_PAD_PX = 8;
const NAME_MAX_PX = 118;
const NAME_H_PX = 18;
const NAME_OFFSET_PX = 8;

export type FarDot = {
  id: string;
  at: { lat: number; lng: number };
  /** 이름. 앞의 이름과 겹쳐 뺐으면 null(점은 남는다). */
  nm: string | null;
};

/**
 * 멀리서 점 + 이름을 달 상권. 이름표가 켜지는 배율(level ≤ 5)이면 빈 목록이다 — 이름표가 대신한다.
 * ⓘ 지금 화면 안(이름표 점 기준)의 상권만 — 화면 밖은 가장자리 표지가 맡는다.
 * ⓘ 이름 겹침은 면적 큰 순으로 놓아 가며 앞에 놓은 이름과 겹치면 뺀다(점은 남긴다).
 */
export function farDots(items: MapItem[], view: MapView): FarDot[] {
  if (showLabels(view.level)) return [];
  const { bounds, widthPx, heightPx } = view;
  const degX = (bounds.neLng - bounds.swLng) / widthPx;
  const degY = (bounds.neLat - bounds.swLat) / heightPx;
  // 지도 칸이 아직 크기를 못 잡았으면(0px) 화면 크기를 모른다 — 점을 달지 않는다.
  if (!(widthPx > 0 && heightPx > 0 && degX > 0 && degY > 0)) return [];

  const small = items
    .filter((it) => dirOf(it.at, bounds) === null)
    .filter((it) => {
      const w = (it.box.neLng - it.box.swLng) / degX;
      const h = (it.box.neLat - it.box.swLat) / degY;
      return Math.max(w, h) < FAR_DOT_MAX_PX;
    });
  // 면적 큰 순(같으면 들어온 순서 — 파일이 면적 내림차순이다).
  const order = small.map((it, i) => ({ it, i })).sort((a, b) => b.it.area - a.it.area || a.i - b.i);

  const placed: { x1: number; y1: number; x2: number; y2: number }[] = [];
  const named = new Set<string>();
  for (const { it } of order) {
    const x = (it.at.lng - bounds.swLng) / degX + NAME_OFFSET_PX;
    const y = (bounds.neLat - it.at.lat) / degY;
    const w = Math.min(NAME_MAX_PX, it.nm.length * NAME_CHAR_PX + NAME_PAD_PX);
    const r = { x1: x, y1: y - NAME_H_PX / 2, x2: x + w, y2: y + NAME_H_PX / 2 };
    if (placed.some((p) => r.x1 < p.x2 && p.x1 < r.x2 && r.y1 < p.y2 && p.y1 < r.y2)) continue;
    placed.push(r);
    named.add(it.id);
  }
  return small.map((it) => ({ id: it.id, at: it.at, nm: named.has(it.id) ? it.nm : null }));
}
