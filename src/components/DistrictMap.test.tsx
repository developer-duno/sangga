/// <reference types="node" />
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { useState } from 'react';
import type { BuildingHit, DistrictFeature, DistrictGeoJson, Ring } from '../types';

/**
 * 상권 지도 테스트 (결정 0010 Track B).
 *
 * 카카오 SDK 는 통째로 흉내 낸다 — 지도를 진짜로 띄우는 것은 이 테스트의 관심사가 아니고,
 * 띄우려면 바깥 스크립트를 내려받아야 해서 CI 가 네트워크에 매이게 된다. 여기서 지키는 것은
 * **우리가 정한 규칙 넷**이다:
 *  ① 키가 없으면 스크립트를 부르지 않고 안내만 한다(CI·E2E 요건)
 *  ② 고른 구의 면만 그리고, **파일 순서를 건드리지 않는다**(면적 내림차순 = 겹침 규칙)
 *  ③ 누른 자리에 걸친 상권을 **전부** 나열한다
 *  ④ 출처는 자료(source_nm)에서 읽는다 — 화면에 박지 않는다
 */

const kakao = vi.hoisted(() => ({
  /** `<Map>` 이 마지막으로 받은 props. 클릭·확대 이벤트를 여기서 직접 쏜다. */
  mapProps: null as {
    onClick?: (m: unknown, e: unknown) => void;
    onZoomChanged?: (m: { getLevel: () => number }) => void;
    onIdle?: (m: unknown) => void;
  } | null,
  setBounds: vi.fn(),
  panTo: vi.fn(),
  setLevel: vi.fn(),
  /** 지도 칸 크기를 바꾼 뒤 부르는 것(W4b — 숨겼다 보일 때 · 판 단계가 바뀐 뒤). */
  relayout: vi.fn(),
  /** 다시 보일 때 마지막으로 잰 중심을 되돌린다(W4b 보완 B2). */
  setCenter: vi.fn(),
  /** 지금 보이는 범위 — 누른 자리가 화면 안인지(`contain`) 볼 때 쓴다(W4b 보완 B3). */
  getBounds: vi.fn(),
  map: null as unknown,
}));
kakao.map = {
  setBounds: kakao.setBounds,
  panTo: kakao.panTo,
  setLevel: kakao.setLevel,
  relayout: kakao.relayout,
  setCenter: kakao.setCenter,
  getBounds: kakao.getBounds,
};

vi.mock('react-kakao-maps-sdk', async () => {
  const { useEffect } = await import('react');
  return {
    useKakaoLoader: () => [false, undefined],
    // ⓘ 진짜 SDK 처럼 **같은 지도 객체**를 돌려준다 — 부를 때마다 새 객체면 `[map, bounds]` effect 가 매 렌더 다시 돌아
    //   "구를 바꿀 때만 다시 맞춘다"를 셀 수 없다(결정 0039 W1).
    useMap: () => kakao.map,
    Map: (props: {
      children?: React.ReactNode;
      onClick?: (m: unknown, e: unknown) => void;
      onZoomChanged?: (m: { getLevel: () => number }) => void;
      onIdle?: (m: unknown) => void;
      onCreate?: (m: unknown) => void;
    }) => {
      kakao.mapProps = props;
      // 진짜 SDK 처럼 지도를 만든 뒤 한 번 `onCreate` 로 지도 객체를 건넨다(W4b relayout 시험).
      const { onCreate } = props;
      useEffect(() => {
        onCreate?.(kakao.map);
      }, [onCreate]);
      return <div data-testid="map">{props.children}</div>;
    },
    // 이름표가 타는 오버레이. **클릭을 막는 스위치(clickable)** 를 볼 수 있게 그대로 내건다.
    CustomOverlayMap: (props: {
      children?: React.ReactNode;
      clickable?: boolean;
      position: { lat: number; lng: number };
    }) => (
      <div data-testid="label" data-clickable={String(props.clickable)} data-lat={props.position.lat}>
        {props.children}
      </div>
    ),
    Polygon: (props: { fillColor?: string }) => <div data-testid="polygon" data-fill={props.fillColor} />,
    MapMarker: (props: { position: { lat: number; lng: number } }) => (
      <div data-testid="marker" data-lat={props.position.lat} data-lng={props.position.lng} />
    ),
  };
});

// 지도 시점 맞추기가 쓰는 전역. 값은 안 쓰고 "불렸는지"만 본다.
vi.stubGlobal('kakao', {
  maps: {
    LatLng: class {
      constructor(lat: number, lng: number) {
        Object.assign(this, { lat, lng });
      }
    },
    LatLngBounds: class {
      constructor(sw: unknown, ne: unknown) {
        Object.assign(this, { sw, ne });
      }
    },
  },
});

// ── 자료 ────────────────────────────────────────────────────────────────

function ring(west: number, south: number, east: number, north: number): Ring {
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ];
}

function feature(over: {
  id: string;
  nm: string;
  type: string;
  gu: string;
  source: string;
  ring: Ring;
}): DistrictFeature {
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [over.ring] },
    properties: {
      district_id: over.id,
      district_nm: over.nm,
      district_type: over.type,
      source_nm: over.source,
      sigungu_code: over.gu,
      area_m2: 1,
    },
  };
}

/** 넓은 발달상권 안에 좁은 골목상권이 겹쳐 있고, 다른 구에도 하나 있다(면적 내림차순). */
function geojson(): DistrictGeoJson {
  return {
    type: 'FeatureCollection',
    meta: { district_cnt: 3, max_computed_at: '2026-08-13T23:18:22.882729Z' },
    features: [
      feature({
        id: 'big',
        nm: '역삼역',
        type: '발달상권',
        gu: '11680',
        source: '서울특별시 상권분석서비스',
        ring: ring(127.0, 37.5, 127.1, 37.6),
      }),
      feature({
        id: 'small',
        nm: '역삼골목',
        type: '골목상권',
        gu: '11680',
        source: '서울특별시 상권분석서비스',
        ring: ring(127.04, 37.54, 127.06, 37.56),
      }),
      feature({
        id: 'daejeon',
        nm: '둔산',
        type: '주요상권',
        gu: '30170',
        source: '소상공인시장진흥공단',
        ring: ring(127.3, 36.3, 127.4, 36.4),
      }),
    ],
  };
}

function building(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: '1168010100-1',
    pnu: '1168010100100010000',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 1,
    min_floor: 1,
    max_floor: 1,
    has_roof: false,
    ...over,
  };
}

// ── 준비 ────────────────────────────────────────────────────────────────

/**
 * 상권 이름을 누르면 그 안의 건물을 서버에 묻는다(DistrictBuildings).
 * 여기서는 **연결부**만 보므로 답은 한 줄이면 충분하다 — 목록 자체의 규칙은
 * `DistrictBuildings.test.tsx` 가 지킨다.
 */
const landRows = [
  {
    pnu: '1168010100107070034',
    store_cnt: 12,
    bld_cnt_in_pnu: 1,
    bld_id: 'B-1',
    bld_nm: '역삼빌딩',
    road_addr: '서울특별시 강남구 테헤란로 1',
    jibun_addr: '서울특별시 강남구 역삼동 707-34',
    lat: 37.5,
    lng: 127.05,
    floor_cnt: 10,
    min_floor: -2,
    max_floor: 8,
    has_roof: false,
    total_parcel_cnt: 1,
    total_bld_cnt: 1,
  },
];

/** 상권 목록 rpc 의 인자 — 지도가 칩을 목록까지 넘기는지 본다(2026-10-11a · 물결 2-2b). */
const rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];
/** 이 시험만의 답 — 있으면 기본 답(landRows) 대신 쓴다. 칩마다 다른 답·영영 안 오는 답을 만든다. */
const rpcPlan: { answer: ((args: Record<string, unknown>) => Promise<unknown>) | null } = { answer: null };

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: Record<string, unknown>) => {
      rpcCalls.push({ fn, args: args ?? {} });
      if (rpcPlan.answer) return rpcPlan.answer(args ?? {});
      return Promise.resolve({ data: landRows, error: null });
    },
  },
}));

const fetchMock = vi.fn();

/**
 * ⚠️ 매번 모듈을 새로 들여온다 — 경계 파일 캐시(lib/districts.ts)가 모듈 안에 있어서,
 *    안 지우면 앞 테스트가 받아 둔 자료를 뒷 테스트가 물려받아 fetch 횟수를 못 센다.
 */
async function load() {
  vi.resetModules();
  return (await import('./DistrictMap')).DistrictMap;
}

function okJson(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

beforeEach(() => {
  rpcPlan.answer = null;
  kakao.mapProps = null;
  kakao.setBounds.mockReset();
  kakao.panTo.mockReset();
  kakao.setLevel.mockReset();
  kakao.relayout.mockReset();
  kakao.setCenter.mockReset();
  kakao.getBounds.mockReset();
  kakao.getBounds.mockImplementation(() => ({ contain: () => true }));
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => okJson(geojson()));
  vi.stubGlobal('fetch', fetchMock);
  // 기본은 "키 있음". 키 없는 상태는 그 테스트에서 따로 지운다.
  vi.stubEnv('VITE_KAKAO_JS_KEY', 'test-js-key');
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

/** 지도가 자료를 받아 실제로 그려질 때까지 기다린다. */
async function renderMap(props: Partial<Parameters<typeof import('./DistrictMap').DistrictMap>[0]> = {}) {
  const DistrictMap = await load();
  render(<DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} {...props} />);
  return DistrictMap;
}

// ── 키가 없을 때 (CI·E2E 요건) ──────────────────────────────────────────

describe('DistrictMap — 지도 키가 없을 때', () => {
  it('스크립트를 부르지 않고 안내만 한다', async () => {
    vi.stubEnv('VITE_KAKAO_JS_KEY', '');
    const DistrictMap = await load();
    render(<DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} />);

    expect(screen.getByText(/지도 키가 설정되지 않았습니다/)).toBeTruthy();
    expect(screen.queryByTestId('map')).toBeNull();
    // 지도를 못 그리는데 1.13MB 를 받아 오는 것은 순수한 낭비다.
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

// ── 구를 안 골랐을 때 ───────────────────────────────────────────────────

describe('DistrictMap — 구를 안 골랐을 때', () => {
  it('아무것도 그리지 않는다 — 어디를 비출지 정해지지 않았다', async () => {
    const DistrictMap = await load();
    const { container } = render(<DistrictMap sigungu={null} sigunguName={null} selected={null} onSelectBuilding={() => {}} />);
    expect(container.innerHTML).toBe('');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

// ── 고른 구의 면만 그린다 ───────────────────────────────────────────────

describe('DistrictMap — 그리기', () => {
  it('고른 구의 상권만 파일 순서 그대로 그린다', async () => {
    await renderMap();

    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    const drawn = screen.getAllByTestId('polygon');
    // 대전(30170)은 빠지고 강남(11680) 둘만 그려진다.
    expect(drawn).toHaveLength(2);
    // ⛔ 순서가 뒤집히면 좁은 골목상권이 넓은 발달상권에 덮여 보이지도, 눌리지도 않는다.
    //    파일이 면적 내림차순이므로 발달상권(넓음)이 먼저, 골목상권(좁음)이 나중이어야 한다.
    //    ⚠️ 색을 다시 계산해 비교하면 같은 식을 두 번 쓰는 동어반복이 된다 — 값을 못박는다.
    expect(drawn.map((d) => d.getAttribute('data-fill'))).toEqual(['#c4452d', '#2f5fd0']);
  });

  it('범례는 실제로 그린 유형에서 만든다 — 다른 구의 유형은 안 뜬다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByText('발달상권')).toBeTruthy());
    expect(screen.getByText('골목상권')).toBeTruthy();
    expect(screen.queryByText('주요상권')).toBeNull();
  });

  it('출처는 자료에서 읽는다 — 안 쓴 출처는 안 붙인다', async () => {
    // 공공누리 1유형(출처표시) 의무. 대전 자료(소진공)는 지금 화면에 안 그렸으므로 출처도 아니다.
    await renderMap();
    await waitFor(() => expect(screen.getByText(/출처: 서울특별시 상권분석서비스/)).toBeTruthy());
    expect(screen.queryByText(/소상공인시장진흥공단/)).toBeNull();
  });

  it('상권이 하나도 없는 구는 빈 지도 대신 그렇다고 말한다', async () => {
    await renderMap({ sigungu: '11110', sigunguName: '종로구' });
    await waitFor(() => expect(screen.getByText(/상권 경계 자료가 없습니다/)).toBeTruthy());
    expect(screen.queryByTestId('map')).toBeNull();
  });

  it('경계 파일을 못 받으면 이유를 말한다 — 검색·층 스택은 멀쩡하다', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    fetchMock.mockImplementation(() => Promise.resolve({ ok: false, status: 404 }));
    await renderMap();
    await waitFor(() => expect(screen.getByText(/불러오지 못했습니다/)).toBeTruthy());
    warn.mockRestore();
  });
});

// ── 클릭 판정 — 겹치면 전부 ─────────────────────────────────────────────

describe('DistrictMap — 누른 자리의 상권', () => {
  /** `<Map>` 의 onClick 을 카카오가 주는 모양 그대로 흉내 내 쏜다. */
  async function clickAt(lng: number, lat: number) {
    await act(async () => {
      kakao.mapProps?.onClick?.(null, { latLng: { getLat: () => lat, getLng: () => lng } });
    });
  }

  it('처음에는 눌러 보라고 안내한다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.getByText(/지도를 누르면/)).toBeTruthy();
  });

  it('겹친 자리를 누르면 걸친 상권을 전부 나열한다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    await clickAt(127.05, 37.55); // 발달상권 · 골목상권이 겹치는 자리

    expect(screen.getByText(/누른 자리 \(2곳\)/)).toBeTruthy();
    expect(screen.getByText('역삼역')).toBeTruthy();
    expect(screen.getByText('역삼골목')).toBeTruthy();
  });

  it('겹치지 않는 자리는 하나만 나온다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    await clickAt(127.09, 37.59); // 발달상권 안, 골목상권 밖

    expect(screen.getByText(/누른 자리 \(1곳\)/)).toBeTruthy();
    expect(screen.queryByText('역삼골목')).toBeNull();
  });

  it('경계 밖은 "없음"이 정상이다 — 오류가 아니다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    await clickAt(128.5, 38.5);

    expect(screen.getByText(/어느 상권 경계에도 들지 않는/)).toBeTruthy();
  });
});

// ── 상권 이름표 ─────────────────────────────────────────────────────────

describe('DistrictMap — 상권 이름을 누르면 그 안의 건물', () => {
  /*
    이 조각이 고치는 것은 **막다른 길**이다. 여태 지도는 누른 자리의 상권 이름을 알려주고
    끝났는데, 창업자는 건물 이름을 모르므로 거기서 더 갈 데가 없었다.
  */
  async function clickAt(lng: number, lat: number) {
    await act(async () => {
      kakao.mapProps?.onClick?.(null, { latLng: { getLat: () => lat, getLng: () => lng } });
    });
  }

  it('상권 이름이 **누를 수 있는 것**이다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);

    const btn = screen.getByRole('button', { name: /역삼역/ });
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  it('누르면 그 상권의 건물 목록이 열린다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);

    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    expect(await screen.findByText('역삼빌딩')).toBeTruthy();
    expect(screen.getByRole('button', { name: /역삼역/ }).getAttribute('aria-expanded')).toBe(
      'true',
    );
  });

  it('한 번 더 누르면 접힌다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);

    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await screen.findByText('역삼빌딩');
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await waitFor(() => expect(screen.queryByText('역삼빌딩')).toBeNull());
  });

  it('⛔ 지도를 다시 누르면 목록이 닫힌다 — 새 자리 아래 옛 상권의 건물이 서면 안 된다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await screen.findByText('역삼빌딩');

    await clickAt(127.05, 37.55); // 다른 자리(두 상권이 겹치는 곳)
    await waitFor(() => expect(screen.queryByText('역삼빌딩')).toBeNull());
  });

  it('창업자 칩을 받으면 상권 목록이 그 업종 코드로 묻는다 — 없으면 업종 인자를 안 보낸다', async () => {
    rpcCalls.length = 0;
    await renderMap({ chip: '카페' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await screen.findByText('역삼빌딩');
    const withChip = rpcCalls.filter((c) => c.fn === 'list_district_buildings');
    expect(withChip.at(-1)?.args.p_cat_m).toEqual(['I212']);

    cleanup();
    rpcCalls.length = 0;
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await screen.findByText('역삼빌딩');
    const noChip = rpcCalls.filter((c) => c.fn === 'list_district_buildings');
    expect(noChip.length).toBeGreaterThan(0);
    expect(noChip.at(-1)?.args).not.toHaveProperty('p_cat_m');
  });

  it('★ 목록이 열린 채 칩만 바꾼 첫 렌더에도 옛 칩의 숫자가 새 칩 이름표로 그려지지 않는다', async () => {
    // 카페는 바로 3곳 · 한식은 답이 영영 안 온다 — 그 사이에 한 번이라도 「고른 업종(한식) 3곳」이 붙으면 깜빡임이다.
    rpcPlan.answer = (args) => {
      const codes = args.p_cat_m as string[] | undefined;
      if (codes?.includes('I201')) return new Promise(() => {});
      return Promise.resolve({ data: [{ ...landRows[0], cat_store_cnt: 3 }], error: null });
    };
    const DistrictMap = await load();
    const view = (chip: '카페' | '한식') => (
      <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} chip={chip} />
    );
    const { container, rerender } = render(view('카페'));
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    expect(await screen.findByText(/고른 업종\(카페\) 3곳/)).toBeTruthy();

    // 최종 화면만 보면 effect 가 이미 비운 뒤라 못 본다 → 붙은·떨어진·바뀐 마디를 전부 기록한다
    // (IndustryMixSection.test 의 같은 꼴).
    const seen: string[] = [];
    const keep = (recs: MutationRecord[]) => {
      for (const r of recs) {
        r.addedNodes.forEach((n) => seen.push(n.textContent ?? ''));
        r.removedNodes.forEach((n) => seen.push(n.textContent ?? ''));
        if (r.type === 'characterData') seen.push(r.target.textContent ?? '');
      }
    };
    const obs = new MutationObserver(keep);
    obs.observe(container, { childList: true, subtree: true, characterData: true });
    rerender(view('한식'));
    expect(await screen.findByText(/불러오는 중/)).toBeTruthy();
    keep(obs.takeRecords());
    obs.disconnect();
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.some((t) => t.includes('고른 업종(한식)'))).toBe(false);
    expect(screen.queryByText(/고른 업종\(카페\)/)).toBeNull();
  });
});

describe('DistrictMap — 상권 이름표', () => {
  /** 카카오가 배율을 바꿨을 때 주는 이벤트를 그대로 흉내 낸다(인자는 지도 객체다). */
  async function zoomTo(level: number) {
    await act(async () => {
      kakao.mapProps?.onZoomChanged?.({ getLevel: () => level });
    });
  }

  it('처음 배율에서는 이름표를 안 켠다 — 한 구에 수십 개가 겹쳐 글자 죽이 된다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.queryAllByTestId('label')).toHaveLength(0);
  });

  it('한 단계 확대하면 그린 면마다 이름이 붙는다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    await zoomTo(5);

    // 그린 면과 같은 수다 — 다른 구(대전)는 애초에 안 그렸으니 이름도 없다.
    expect(screen.getAllByTestId('label')).toHaveLength(2);
    expect(screen.getByText('역삼역')).toBeTruthy();
    expect(screen.getByText('역삼골목')).toBeTruthy();
    expect(screen.queryByText('둔산')).toBeNull();
  });

  it('다시 넓게 보면 이름표가 걷힌다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    await zoomTo(4);
    expect(screen.getAllByTestId('label')).toHaveLength(2);

    await zoomTo(6);
    expect(screen.queryAllByTestId('label')).toHaveLength(0);
  });

  it('이름표는 카카오 쪽 클릭 차단을 켜지 않는다', async () => {
    // ⛔ `clickable`이 true 가 되면 카카오가 이름표 위 클릭에서 지도 이벤트를 막는다
    //    (kakao.maps.d.ts `CustomOverlayOptions`). 그러면 상권 이름 위 — 가장 누르고 싶은
    //    자리 — 를 눌렀을 때 "누른 자리 상권"이 아무 답도 안 한다.
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await zoomTo(5);

    for (const label of screen.getAllByTestId('label')) {
      expect(label.getAttribute('data-clickable')).toBe('false');
    }
  });

  it('이름표는 브라우저 쪽에서도 클릭 대상이 아니다(pointer-events: none)', async () => {
    // 위 시험과 짝이다 — 차단 장치가 둘이라 하나가 사라져도 나머지가 남는다.
    // ⚠️ jsdom 은 CSS 를 실제로 적용하지 않으므로 **규칙 자체**가 살아 있는지를 본다.
    // ⚠️ `import '…styles.css?raw'` 로는 못 읽는다 — vitest 는 CSS 를 아예 처리하지 않아
    //    **빈 문자열**이 온다(실측). 빈 문자열은 어떤 정규식에도 안 맞아 시험이 조용히
    //    "규칙이 없다"고 말하게 되므로, 파일을 직접 연다(경로는 프로젝트 뿌리 기준).
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    const block = css.slice(css.indexOf('.dmap__label {'));
    expect(block.slice(0, block.indexOf('}'))).toMatch(/pointer-events:\s*none/);
  });

  it('이름표가 떠 있어도 누른 자리 판정은 그대로다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await zoomTo(5);

    await act(async () => {
      kakao.mapProps?.onClick?.(null, {
        latLng: { getLat: () => 37.55, getLng: () => 127.05 },
      });
    });

    expect(screen.getByText(/누른 자리 \(2곳\)/)).toBeTruthy();
  });
});

// ── 건물 마커 ───────────────────────────────────────────────────────────

describe('DistrictMap — 건물 마커', () => {
  it('좌표가 있으면 그 자리에 찍는다', async () => {
    await renderMap({ selected: building({ lat: 37.55, lng: 127.05 }) });
    await waitFor(() => expect(screen.getByTestId('marker')).toBeTruthy());
    expect(screen.getByTestId('marker').getAttribute('data-lat')).toBe('37.55');
    // panTo 는 MapFocus 의 effect(지도 객체가 잡힌 뒤)에서 불린다 — 마커가 먼저 그려질 수 있어
    // 기다린다(2026-10-06 CI 러너에서 1회 빨강 · 아래 setLevel 시험과 같은 꼴).
    await waitFor(() => expect(kakao.panTo).toHaveBeenCalled());
  });

  it('건물을 고르면 그 주변이 보이게 확대한다 — 구 전체 배율로 두지 않는다', async () => {
    // 2026-08-17 사장님 지적: 종로구에서 건물을 골랐는데 축척 2km(서울 절반)로 남아
    // 건물이 점으로만 보였다. setBounds 가 구의 상권 전체를 담느라 넓게 잡아 둔 배율을
    // 그대로 쓰고 위치만 옮겼기 때문이다.
    await renderMap({ selected: building({ lat: 37.55, lng: 127.05 }) });
    await waitFor(() => expect(kakao.setLevel).toHaveBeenCalled());
    const level = kakao.setLevel.mock.calls[0]?.[0];
    // 카카오 ROADMAP 은 숫자가 작을수록 확대다. 6 이상이면 건물이 다시 점이 된다.
    expect(typeof level).toBe('number');
    expect(level).toBeLessThanOrEqual(5);
    expect(level).toBeGreaterThanOrEqual(1);
  });

  it('좌표가 없으면 배율도 건드리지 않는다 — 옮길 곳이 없으면 화면을 흔들지 않는다', async () => {
    await renderMap({ selected: building() });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(kakao.setLevel).not.toHaveBeenCalled();
  });

  it('좌표가 없으면 마커를 안 찍는다 — 없는 좌표를 0,0 으로 채우지 않는다', async () => {
    // 마이그레이션(2026-08-14e)이 라이브에 적용되기 전에는 서버가 이 칸을 안 준다.
    await renderMap({ selected: building() });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.queryByTestId('marker')).toBeNull();
    expect(kakao.panTo).not.toHaveBeenCalled();
  });
});

// ── 접기·펴기, 파일 한 번만 받기 ────────────────────────────────────────

describe('DistrictMap — 접기와 캐시', () => {
  it('접으면 지도를 치우고, 다시 펴면 되돌아온다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '지도 접기' }));
    expect(screen.queryByTestId('map')).toBeNull();
    expect(screen.getByText(/접어 두었습니다/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '지도 펴기' }));
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
  });

  it('경계 파일은 한 번만 받는다 — 구를 바꿔도 다시 받지 않는다', async () => {
    const DistrictMap = await load();
    const { rerender } = render(
      <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} />,
    );
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    rerender(<DistrictMap sigungu="30170" sigunguName="서구" selected={null} onSelectBuilding={() => {}} />);
    await waitFor(() => expect(screen.getByText(/출처: 소상공인시장진흥공단/)).toBeTruthy());

    // 파일 하나에 전국이 다 들어 있다 — 구별로 거르기만 하면 된다.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

/**
 * CSS 를 주석 빼고 `@media` 묶음 밖(기본 규칙)과 안으로 갈라 규칙 목록(선택자 · 본문 · 묶음 머리)으로 편다.
 * ⓘ 이 파일의 CSS 가드 셋이 같은 함수를 지난다 — 양성 대조도 같은 함수로 본다.
 * 못 보는 것: `@media` 안의 또 다른 `@media`·`@supports` 겹 묶음(이 파일에 없다) · 문자열 안의 중괄호.
 */
function cssRules(css: string): { sel: string[]; body: string; media: string | null }[] {
  const src = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const out: { sel: string[]; body: string; media: string | null }[] = [];
  const take = (chunk: string, media: string | null) => {
    for (const m of chunk.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      out.push({ sel: m[1].split(',').map((x) => x.trim()), body: m[2], media });
    }
  };
  let i = 0;
  let plain = '';
  while (i < src.length) {
    const at = src.indexOf('@media', i);
    if (at < 0) {
      plain += src.slice(i);
      break;
    }
    plain += src.slice(i, at);
    const open = src.indexOf('{', at);
    let depth = 1;
    let j = open + 1;
    while (j < src.length && depth > 0) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') depth -= 1;
      j += 1;
    }
    take(src.slice(open + 1, j - 1), src.slice(at, open).trim());
    i = j;
  }
  take(plain, null);
  return out;
}

// ── 지도 배율 — 몰린 곳에 맞추기 (결정 0039 W1) ──────────────────────────────────────────────
// ⓘ E2E 에는 지도 키가 없어 지도가 안 그려진다 — 첫 범위·화면 밖 표지·멀리서의 점+이름의 화면 가드는 여기가 전부다.
describe('DistrictMap — 지도 배율(결정 0039 W1)', () => {
  /** `setBounds` 로 받은 LatLngBounds 흉내(위 stub — {sw, ne})를 숫자로 편다. */
  function fitted(call: unknown[]) {
    const b = call[0] as { sw: { lat: number; lng: number }; ne: { lat: number; lng: number } };
    return { swLat: b.sw.lat, swLng: b.sw.lng, neLat: b.ne.lat, neLng: b.ne.lng };
  }

  /** 카카오가 멈춤(idle) 때 주는 지도 객체 흉내 — 지금 범위·지도 칸 크기·배율. */
  async function idleAt(view: { swLat: number; swLng: number; neLat: number; neLng: number }, level = 6) {
    await act(async () => {
      kakao.mapProps?.onIdle?.({
        getBounds: () => ({
          getSouthWest: () => ({ getLat: () => view.swLat, getLng: () => view.swLng }),
          getNorthEast: () => ({ getLat: () => view.neLat, getLng: () => view.neLng }),
        }),
        getNode: () => ({ clientWidth: 1000, clientHeight: 1000 }),
        getLevel: () => level,
        getCenter: () => ({ lat: (view.swLat + view.neLat) / 2, lng: (view.swLng + view.neLng) / 2 }),
      });
    });
  }

  /** 서구(30170)에 상권 여섯 — 서쪽에 겹친 넷 + 옆에 하나 + 멀리 동쪽에 작은 하나. */
  function sixGeo(): DistrictGeoJson {
    const at = (id: string, r: Ring) =>
      feature({ id, nm: id, type: '골목상권', gu: '30170', source: '소상공인시장진흥공단', ring: r });
    return {
      type: 'FeatureCollection',
      meta: { district_cnt: 6, max_computed_at: '2026-08-13T23:18:22.882729Z' },
      features: [
        at('X1', ring(127.3, 36.3, 127.31, 36.31)),
        at('X2', ring(127.3, 36.3, 127.31, 36.31)),
        at('X3', ring(127.3, 36.3, 127.31, 36.31)),
        at('X4', ring(127.3, 36.3, 127.31, 36.31)),
        at('Y', ring(127.32, 36.3, 127.323, 36.31)),
        at('Z', ring(127.4, 36.3, 127.401, 36.31)),
      ],
    };
  }

  it('첫 범위는 여백 네 개(위·오른쪽·아래·왼쪽)와 함께 맞춘다', async () => {
    await renderMap();
    await waitFor(() => expect(kakao.setBounds).toHaveBeenCalled());
    const call = kakao.setBounds.mock.calls[0];
    expect(call).toHaveLength(5);
    const pads = call.slice(1) as number[];
    // 카카오 기본(32)보다 넓게 — 가장자리 표지가 몰린 곳을 가리지 않게.
    expect(pads.every((p) => typeof p === 'number' && p > 32)).toBe(true);
    expect(new Set(pads).size).toBe(1);
  });

  it('상권 5곳 이하 구는 전부 담는 상자로 맞춘다', async () => {
    await renderMap(); // 강남 2곳
    await waitFor(() => expect(kakao.setBounds).toHaveBeenCalled());
    expect(fitted(kakao.setBounds.mock.calls[0])).toEqual({ swLat: 37.5, swLng: 127.0, neLat: 37.6, neLng: 127.1 });
  });

  it('6곳부터는 몰린 곳 상자 — 멀리 떨어진 작은 상권 쪽으로 넓히지 않는다', async () => {
    fetchMock.mockImplementation(() => okJson(sixGeo()));
    await renderMap({ sigungu: '30170', sigunguName: '서구' });
    await waitFor(() => expect(kakao.setBounds).toHaveBeenCalled());
    const b = fitted(kakao.setBounds.mock.calls[0]);
    expect(b.swLng).toBeGreaterThanOrEqual(127.3);
    expect(b.neLng).toBeLessThan(127.33); // 전부 담으면 127.401
  });

  it('구를 바꾸면 사용자가 배율을 바꾼 뒤라도 새 구의 상자로 다시 맞춘다', async () => {
    const DistrictMap = await load();
    const { rerender } = render(
      <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} />,
    );
    await waitFor(() => expect(kakao.setBounds).toHaveBeenCalledTimes(1));
    await act(async () => {
      kakao.mapProps?.onZoomChanged?.({ getLevel: () => 3 });
    });
    rerender(<DistrictMap sigungu="30170" sigunguName="서구" selected={null} onSelectBuilding={() => {}} />);
    await waitFor(() => expect(kakao.setBounds).toHaveBeenCalledTimes(2));
    expect(fitted(kakao.setBounds.mock.calls[1])).toEqual({ swLat: 36.3, swLng: 127.3, neLat: 36.4, neLng: 127.4 });
  });

  it('멈춘 뒤 화면 밖 상권이 있으면 가장자리 표지가 서고, 누르면 그쪽으로 옮긴다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.queryByRole('button', { name: /화면 밖 상권/ })).toBeNull();

    // 지금 화면 = 강남 상권 둘보다 서쪽 → 둘 다 오른쪽 밖.
    await idleAt({ swLat: 37.5, swLng: 126.8, neLat: 37.6, neLng: 126.9 });
    const btn = screen.getByRole('button', { name: /화면 밖 상권/ });
    // 접근 이름에 방향·곳 수·면적 큰 이름(파일 첫째 = 역삼역 — 시험 자료는 면적이 같아 앞의 것).
    expect(btn.getAttribute('aria-label')).toBe('오른쪽 화면 밖 상권 2곳(역삼역 등) — 그쪽으로 옮기기');
    expect(btn.className).toContain('dmap__off--e');
    expect(btn.textContent).toBe('→역삼역등2곳');

    fireEvent.click(btn);
    expect(kakao.panTo).toHaveBeenCalledTimes(1);
    const to = kakao.panTo.mock.calls[0][0] as { lat: number; lng: number };
    expect(to.lat).toBeCloseTo(37.55, 6);
    expect(to.lng).toBeCloseTo(127.05, 6);
  });

  it('화면 안에 다 들면 표지가 없다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await idleAt({ swLat: 37.4, swLng: 126.9, neLat: 37.7, neLng: 127.2 });
    expect(screen.queryByRole('button', { name: /화면 밖 상권/ })).toBeNull();
  });

  it('⛔ 다른 구에서 잰 화면으로는 표지를 세지 않는다 — 구를 바꾼 직후 전부 화면 밖으로 그려지지 않는다', async () => {
    const DistrictMap = await load();
    const { rerender } = render(
      <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} />,
    );
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await idleAt({ swLat: 37.4, swLng: 126.9, neLat: 37.7, neLng: 127.2 });
    rerender(<DistrictMap sigungu="30170" sigunguName="서구" selected={null} onSelectBuilding={() => {}} />);
    await waitFor(() => expect(screen.getByText(/출처: 소상공인시장진흥공단/)).toBeTruthy());
    expect(screen.queryByRole('button', { name: /화면 밖 상권/ })).toBeNull();
  });

  it('멀리(level 6)에서는 화면에서 작은 상권만 점 + 이름 — 누르기를 넘기고(clickable false), 확대하면 이름표가 대신한다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    // 1000px 에 2° → 1px = 0.002°. 역삼역(0.1° = 50px)은 면이 보이고, 역삼골목(0.02° = 10px)만 점이다.
    await idleAt({ swLat: 36.5, swLng: 126.0, neLat: 38.5, neLng: 128.0 }, 6);
    const fars = document.querySelectorAll('.dmap__far');
    expect(fars).toHaveLength(1);
    expect(fars[0].textContent).toBe('역삼골목');
    expect(fars[0].parentElement?.getAttribute('data-clickable')).toBe('false');

    await act(async () => {
      kakao.mapProps?.onZoomChanged?.({ getLevel: () => 5 });
    });
    expect(document.querySelectorAll('.dmap__far')).toHaveLength(0);
    expect(screen.getAllByTestId('label')).toHaveLength(2);
  });

  it('점은 브라우저 쪽에서도 클릭 대상이 아니다(pointer-events: none)', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    const block = css.slice(css.indexOf('.dmap__far {'));
    expect(block.slice(0, block.indexOf('}'))).toMatch(/pointer-events:\s*none/);
  });

  it('화면 밖 표지는 종이에서 빠지고, 휴대폰 꼴(이름 숨김)은 화면 720 묶음 안에만 있다', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    const print = css.slice(css.indexOf('@media print {'));
    expect(print.slice(0, print.indexOf('display: none !important;'))).toMatch(/\.dmap__off,/);
    // 휴대폰 규칙이 든 묶음의 머리가 `@media screen and (max-width: 720px)` 인지 — 기본 규칙이면 종이·넓은 화면까지 바뀐다.
    const at = css.indexOf('.dmap__off-nm,\n  .dmap__off-etc {\n    display: none;');
    const at2 = at >= 0 ? at : css.indexOf('.dmap__off-nm,\r\n  .dmap__off-etc {\r\n    display: none;');
    expect(at2).toBeGreaterThan(0);
    const head = css.lastIndexOf('@media', at2);
    expect(css.slice(head, css.indexOf('{', head))).toBe('@media screen and (max-width: 720px) ');
  });

  it('⛔ 아래 줄 표지(↙ ↓ ↘)는 카카오 로고·축척 막대(약 25~30px) 위에 뜬다', async () => {
    const { readFileSync } = await import('node:fs');
    const rules = cssRules(readFileSync('src/styles.css', 'utf8'));
    for (const dir of ['sw', 's', 'se']) {
      const bottoms = rules
        .filter((r) => r.media === null && r.sel.includes(`.dmap__off--${dir}`))
        .flatMap((r) => [...r.body.matchAll(/bottom:\s*(\d+)px/g)].map((m) => Number(m[1])));
      expect(bottoms, dir).toHaveLength(1);
      expect(bottoms[0], dir).toBeGreaterThanOrEqual(30);
      // 화면 묶음에서 다시 낮추지 않는다.
      const lowered = rules.filter((r) => r.media !== null && r.sel.includes(`.dmap__off--${dir}`) && /bottom:/.test(r.body));
      expect(lowered, dir).toHaveLength(0);
    }
  });

  it('표지는 화면 전체의 「누르는 것은 44px 이상」 목록에 든다', async () => {
    const { readFileSync } = await import('node:fs');
    const rules = cssRules(readFileSync('src/styles.css', 'utf8'));
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body));
    expect(tall.some((r) => r.sel.includes('.dmap__off'))).toBe(true);
  });

  it('넓은 화면에서는 표지 이름이 보인다 — 기본 규칙(모든 @media 밖)에서 이름을 숨기지 않는다', async () => {
    const { readFileSync } = await import('node:fs');
    const hides = (css: string) =>
      cssRules(css).some(
        (r) =>
          r.media === null &&
          (r.sel.includes('.dmap__off-nm') || r.sel.includes('.dmap__off-etc')) &&
          /display:\s*none|visibility:\s*hidden/.test(r.body),
      );
    const css = readFileSync('src/styles.css', 'utf8');
    expect(hides(css)).toBe(false);
    // 양성 대조 — 흔한 꼴(이름 하나) + 변형 꼴(선택자 목록 · 줄바꿈 다른 꼴)을 실제로 잡는다.
    expect(hides(`${css}\n.dmap__off-nm { display: none; }`)).toBe(true);
    expect(hides(`${css}\r\n.x,\r\n.dmap__off-etc {\r\n  display:none;\r\n}`)).toBe(true);
    // 720 묶음 안의 숨김은 기본 규칙이 아니다(지금 저장소가 그 꼴이다).
    expect(hides('@media screen and (max-width: 720px) { .dmap__off-nm { display: none; } }')).toBe(false);
  });
});

// ── 다시 그려져도 누른 상권·목록 되살리기 (👤 2026-10-15 G1) ─────────────────────────────
// 입구가 접히면(S1) 지도는 안 그려진다. App 이 기억(`pick`)을 쥐고 넘기면, 다시 그릴 때 아까 누른 상권과 펼친 건물
// 목록이 그대로 선다. ⓘ E2E 는 지도 키가 비어 알맹이가 안 그려지므로 이 가짜 SDK 시험이 대신한다.
describe('DistrictMap — 다시 그려져도 누른 상권·목록 되살리기 (G1)', () => {
  async function clickAt(lng: number, lat: number) {
    await act(async () => {
      kakao.mapProps?.onClick?.(null, { latLng: { getLat: () => lat, getLng: () => lng } });
    });
  }

  it('★ 위가 기억을 쥐면, 지도를 치웠다 다시 그려도 누른 상권과 펼친 건물 목록이 그대로 선다', async () => {
    const DistrictMap = await load();
    const { EMPTY_MAP_PICK } = await import('../lib/districtMapPick');
    type Pick = typeof EMPTY_MAP_PICK;
    const seen: Pick[] = [];
    function Host({ show }: { show: boolean }) {
      const [pick, setPick] = useState<Pick>(EMPTY_MAP_PICK);
      return show ? (
        <DistrictMap
          sigungu="11680"
          sigunguName="강남구"
          selected={null}
          onSelectBuilding={() => {}}
          pick={pick}
          onPickChange={(next) => {
            seen.push(next);
            setPick(next);
          }}
        />
      ) : null;
    }
    const { rerender } = render(<Host show />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await screen.findByText('역삼빌딩');
    // 기억에는 구와 상권 **번호**만 실린다.
    expect(seen.at(-1)).toEqual({ sigungu: '11680', pickedIds: ['big'], openId: 'big' });

    rerender(<Host show={false} />);
    expect(screen.queryByTestId('map')).toBeNull();
    rerender(<Host show />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.getByRole('button', { name: /역삼역/ }).getAttribute('aria-expanded')).toBe('true');
    expect(await screen.findByText('역삼빌딩')).toBeTruthy();
  });

  it('양성 대조 — 기억을 안 넘기면(스스로 쥐면) 다시 그릴 때 처음부터다', async () => {
    const DistrictMap = await load();
    function Host({ show }: { show: boolean }) {
      return show ? (
        <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} />
      ) : null;
    }
    const { rerender } = render(<Host show />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.09, 37.59);
    expect(screen.getByRole('button', { name: /역삼역/ })).toBeTruthy();
    rerender(<Host show={false} />);
    rerender(<Host show />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.queryByRole('button', { name: /역삼역/ })).toBeNull();
    expect(screen.getByText(/지도를 누르면 그 자리의 상권을 알려드립니다/)).toBeTruthy();
  });

  it('⛔ 다른 구에서 누른 기억은 쓰지 않는다 — 처음 안내가 선다', async () => {
    await renderMap({
      pick: { sigungu: '30170', pickedIds: ['big'], openId: 'big' },
      onPickChange: () => {},
    });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(screen.queryByRole('button', { name: /역삼역/ })).toBeNull();
    expect(screen.queryByText('역삼빌딩')).toBeNull();
    expect(screen.getByText(/지도를 누르면 그 자리의 상권을 알려드립니다/)).toBeTruthy();
  });
});

// ── 휴대폰 지도 가득 · 끌어올리는 상권 판 · relayout (👤 2026-10-19 결정 0039 W4b) ─────────────────────────────
// ⓘ E2E 에는 카카오 키가 없어 지도 칸은 안내 글뿐이다 — 판·relayout 의 배선은 이 가짜 SDK 시험이 본다(판 자체는 E2E BT 도 본다).
describe('DistrictMap — 휴대폰 지도 가득(결정 0039 W4b)', () => {
  async function clickAt(lng: number, lat: number) {
    await act(async () => {
      kakao.mapProps?.onClick?.(null, { latLng: { getLat: () => lat, getLng: () => lng } });
    });
  }
  const sheet = () => document.querySelector('.dsheet');
  const handle = () => document.querySelector<HTMLButtonElement>('.dsheet__handle')!;
  const stageOf = () => /dsheet--(\w+)/.exec(sheet()!.className)![1];

  it('★ full 꼴 — 제목·접기 단추 없이 지도 칸 + 엿보기 글(구 이름 · 상권 수) · 카드 꼴엔 판이 없다', async () => {
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(document.querySelector('.dmap__toggle')).toBeNull();
    expect(document.querySelector('.dmap__title')).toBeNull();
    expect(document.querySelector('section.dmap')!.classList.contains('dmap--full')).toBe(true);
    expect(sheet()!.querySelector('.dsheet__title')!.textContent).toBe('강남구 상권 2곳');
    expect(sheet()!.querySelector('.dsheet__hint')!.textContent).toBe('지도를 누르면 그 자리 상권');
    expect(stageOf()).toBe('peek');
    cleanup();

    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(sheet()).toBeNull();
    expect(document.querySelector('.dmap__toggle')).not.toBeNull();
    expect(document.querySelector('section.dmap')!.classList.contains('dmap--full')).toBe(false);
  });

  it('★ 손잡이는 단추 — 이름과 펼침이 단계마다 바뀌며 엿보기 → 반 → 가득 → 엿보기 · 「접기」는 반·가득에서만 → 엿보기', async () => {
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(sheet()).not.toBeNull());
    const seen: [string, string | null, string | null][] = [];
    for (let i = 0; i < 4; i += 1) {
      seen.push([stageOf(), handle().getAttribute('aria-label'), handle().getAttribute('aria-expanded')]);
      if (i < 3) fireEvent.click(handle());
    }
    expect(seen).toEqual([
      ['peek', '상권 판 펼치기', 'false'],
      ['half', '상권 판 더 펼치기', 'true'],
      ['full', '상권 판 접기', 'true'],
      ['peek', '상권 판 펼치기', 'false'],
    ]);
    expect(screen.queryByRole('button', { name: '접기' })).toBeNull();
    fireEvent.click(handle());
    fireEvent.click(screen.getByRole('button', { name: '접기' }));
    expect(stageOf()).toBe('peek');
    fireEvent.click(handle());
    fireEvent.click(handle());
    fireEvent.click(screen.getByRole('button', { name: '접기' }));
    expect(stageOf()).toBe('peek');
  });

  it('★ 손가락 끌기 — 30px 넘게 올리면 한 단계 위 · 내리면 한 단계 아래 · 그만큼 안 움직이면 그대로(끈 뒤 따라오는 click 은 안 먹는다)', async () => {
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(sheet()).not.toBeNull());
    const bar = () => document.querySelector('.dsheet__bar')!;
    const drag = (from: number, to: number) => {
      fireEvent.pointerDown(bar(), { pointerId: 1, clientY: from });
      fireEvent.pointerMove(bar(), { pointerId: 1, clientY: to });
      fireEvent.pointerUp(bar(), { pointerId: 1, clientY: to });
    };
    drag(500, 490); // 10px — 단계 그대로
    expect(stageOf()).toBe('peek');
    drag(500, 450); // 위로 50px
    expect(stageOf()).toBe('half');
    fireEvent.click(handle()); // 끈 뒤 따라오는 click — 한 번 더 돌리지 않는다
    expect(stageOf()).toBe('half');
    drag(300, 250);
    expect(stageOf()).toBe('full');
    drag(100, 160); // 아래로
    expect(stageOf()).toBe('half');
    drag(100, 160);
    expect(stageOf()).toBe('peek');
    fireEvent.click(handle()); // 끈 뒤 click 은 버림
    fireEvent.click(handle()); // 그다음 누름은 먹는다
    expect(stageOf()).toBe('half');
  });

  it('★ 지도를 누르면 그 자리 상권 + 판이 반으로(엿보기일 때만 — 반·가득이면 그대로) · 머리 글은 지금 누른 자리 글 그대로', async () => {
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(sheet()).not.toBeNull());
    await clickAt(127.05, 37.55);
    expect(stageOf()).toBe('half');
    expect(sheet()!.querySelector('.dsheet__title')!.textContent).toBe('누른 자리 (2곳):');
    expect(screen.getByRole('button', { name: /역삼골목/ })).toBeTruthy();
    fireEvent.click(handle()); // 가득
    await clickAt(126.0, 30.0); // 경계 밖
    expect(stageOf()).toBe('full');
    expect(sheet()!.querySelector('.dsheet__title')!.textContent).toBe('어느 상권 경계에도 들지 않는 위치입니다.');
    fireEvent.click(screen.getByRole('button', { name: '접기' }));
    fireEvent.click(handle()); // 반
    await clickAt(127.05, 37.55);
    expect(stageOf()).toBe('half');
  });

  it('★ 구가 바뀌면 판은 엿보기로', async () => {
    const DistrictMap = await load();
    const { rerender } = render(
      <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} onSelectBuilding={() => {}} layout="full" />,
    );
    await waitFor(() => expect(sheet()).not.toBeNull());
    fireEvent.click(handle());
    fireEvent.click(handle());
    expect(stageOf()).toBe('full');
    rerender(<DistrictMap sigungu="30170" sigunguName="서구" selected={null} onSelectBuilding={() => {}} layout="full" />);
    await waitFor(() => expect(sheet()!.querySelector('.dsheet__title')!.textContent).toBe('서구 상권 1곳'));
    expect(stageOf()).toBe('peek');
  });

  it('★ 판 안 차례 = 범례 → 누른 자리 상권 → 건물 목록 → 출처(지금 카드 아래 것 그대로)', async () => {
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(sheet()).not.toBeNull());
    await clickAt(127.09, 37.59);
    fireEvent.click(screen.getByRole('button', { name: /역삼역/ }));
    await screen.findByText('역삼빌딩');
    const body = sheet()!.querySelector('.dsheet__body')!;
    const order = [...body.children].map((c) => c.className.split(' ')[0]);
    expect(order).toEqual(['dmap__legend', 'dmap__picked', 'dbld', 'dmap__src']);
    // 판 바깥에는 범례·출처가 없다.
    expect(document.querySelectorAll('.dmap__legend')).toHaveLength(1);
  });

  it('★ 숨겼다 다시 보이면 relayout 한 번(true→true 는 0 · 양성/음성) · 판 단계가 바뀐 뒤에도 한 번', async () => {
    const DistrictMap = await load();
    const props = {
      sigungu: '11680',
      sigunguName: '강남구',
      selected: null,
      onSelectBuilding: () => {},
      layout: 'full' as const,
    };
    const { rerender } = render(<DistrictMap {...props} visible />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    rerender(<DistrictMap {...props} visible />);
    expect(kakao.relayout).not.toHaveBeenCalled();
    rerender(<DistrictMap {...props} visible={false} />);
    expect(document.querySelector('section.dmap')!.hasAttribute('hidden')).toBe(true);
    expect(kakao.relayout).not.toHaveBeenCalled();
    rerender(<DistrictMap {...props} visible />);
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
    // 같은 지도 — 다시 맞추지 않았다(첫 범위 한 번뿐 · 확대·이동이 그대로).
    expect(kakao.setBounds).toHaveBeenCalledTimes(1);
    fireEvent.click(handle());
    expect(kakao.relayout).toHaveBeenCalledTimes(2);
  });

  it('★ 카드 꼴도 숨겼다 보이면 relayout 을 받는다(중개사 지도) · 기본은 숨김 속성 없음', async () => {
    const DistrictMap = await load();
    const props = { sigungu: '11680', sigunguName: '강남구', selected: null, onSelectBuilding: () => {} };
    const { rerender } = render(<DistrictMap {...props} />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(document.querySelector('section.dmap')!.hasAttribute('hidden')).toBe(false);
    rerender(<DistrictMap {...props} visible={false} />);
    rerender(<DistrictMap {...props} visible />);
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
  });

  it('★ 키가 없어도 full 꼴은 판이 선다(지도 칸에는 키 안내 글) — 카드 꼴은 지금처럼 파일을 안 받는다(위 「키가 없을 때」)', async () => {
    vi.stubEnv('VITE_KAKAO_JS_KEY', '');
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(sheet()).not.toBeNull());
    expect(document.querySelector('.dmap__canvas')!.textContent).toMatch(/지도 키가 설정되지 않았습니다/);
    expect(sheet()!.querySelector('.dsheet__title')!.textContent).toBe('강남구 상권 2곳');
    fireEvent.click(handle());
    expect(screen.getByText(/출처: 서울특별시 상권분석서비스/)).toBeTruthy();
    expect(screen.queryByTestId('map')).toBeNull();
  });

  it('판 규칙은 전부 휴대폰 화면 묶음 안 · 종이에서 빠진다 · 손잡이·접기는 44px 목록 · 엿보기는 안 굴린다', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    const medias = (src: string) =>
      cssRules(src)
        .filter((r) => r.media !== '@media print' && r.sel.some((s) => /\.dsheet|\.dmap--full/.test(s)))
        .filter((r) => !(r.media === '@media screen' && /min-height:\s*44px/.test(r.body)))
        .map((r) => r.media);
    expect(medias(css).length).toBeGreaterThan(10);
    expect(new Set(medias(css))).toEqual(new Set(['@media screen and (max-width: 720px)']));
    // 양성 대조 — 기본 규칙 꼴 + 다른 묶음 속 선택자 목록 꼴(줄바꿈 다른 꼴).
    expect(medias(`${css}\n.dsheet { position: fixed; }`)).toContain(null);
    expect(medias(`${css}\n@media (max-width: 720px) {\r\n  .a,\r\n  .dsheet--half { height: 1px; }\r\n}`)).toContain(
      '@media (max-width: 720px)',
    );
    const rules = cssRules(css);
    const hide = rules.filter((r) => r.media === '@media print' && /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    // 종이에서는 손잡이·「접기」·안내만 빠진다 — 판 통째는 남는다(W4b 보완 A3 · 아래 「종이」 시험).
    for (const s of ['.dsheet__handle', '.dsheet__fold', '.dsheet__hint']) expect(hide, s).toContain(s);
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.dsheet__handle', '.dsheet__fold']) expect(tall, s).toContain(s);
    expect(
      rules.some(
        (r) =>
          r.media === '@media screen and (max-width: 720px)' &&
          r.sel.includes('.dsheet--peek .dsheet__body') &&
          /display:\s*none/.test(r.body),
      ),
    ).toBe(true);
  });
});

// ── W4b 보완 1 — 검사관 3인 + 메인 실사진(겹침·두 번 쓴 글·종이 출처·숨은 지도의 안전·inert) ──────────────────────
describe('DistrictMap — 휴대폰 지도 가득 보완(W4b 보완 1)', () => {
  const PHONE = '@media screen and (max-width: 720px)';
  const base = {
    sigungu: '11680',
    sigunguName: '강남구',
    selected: null,
    onSelectBuilding: () => {},
    layout: 'full' as const,
  };
  async function clickAt(lng: number, lat: number) {
    await act(async () => {
      kakao.mapProps?.onClick?.(null, { latLng: { getLat: () => lat, getLng: () => lng } });
    });
  }
  /** 카카오 멈춤(idle) 흉내 — 칸 크기·배율·중심을 고른다(숨은 칸 = 0×0). */
  async function idle(
    view: { swLat: number; swLng: number; neLat: number; neLng: number },
    size: { w: number; h: number },
    level = 6,
    center: unknown = { lat: (view.swLat + view.neLat) / 2, lng: (view.swLng + view.neLng) / 2 },
  ) {
    await act(async () => {
      kakao.mapProps?.onIdle?.({
        getBounds: () => ({
          getSouthWest: () => ({ getLat: () => view.swLat, getLng: () => view.swLng }),
          getNorthEast: () => ({ getLat: () => view.neLat, getLng: () => view.neLng }),
        }),
        getNode: () => ({ clientWidth: size.w, clientHeight: size.h }),
        getLevel: () => level,
        getCenter: () => center,
      });
    });
  }
  /** 상권(127.0~127.1 · 37.5~37.6)이 하나도 안 드는 먼 화면 — 표지가 서야 하는 범위. */
  const FAR = { swLat: 37.0, swLng: 126.0, neLat: 37.01, neLng: 126.01 };
  const sheet = () => document.querySelector('.dsheet');
  const handle = () => document.querySelector<HTMLButtonElement>('.dsheet__handle')!;
  const stageOf = () => /dsheet--(\w+)/.exec(sheet()!.className)![1];

  /**
   * 판이 화면 밖 표지 위에 오나(A1) — 휴대폰 묶음의 판 규칙(`.dsheet`·`.dsheet--단계`) z-index 가 전부 표지(`.dmap__off`) 보다 크고
   * 띠(19) 보다 작은가. 가드 본체와 양성 대조가 이 함수를 같이 지난다.
   * 못 보는 것: 같은 선택자가 뒤 규칙에서 z-index 없이 덮이는 꼴 · `.dsheet` 를 다른 이름표 조합(`.x .dsheet`)으로 고친 꼴.
   */
  function sheetAboveBadge(src: string): boolean {
    const rules = cssRules(src);
    const z = (body: string) => Number(/z-index:\s*(-?\d+)/.exec(body)![1]);
    const badge = rules.filter((r) => r.sel.includes('.dmap__off') && /z-index/.test(r.body)).map((r) => z(r.body));
    const sheets = rules
      .filter((r) => r.media === PHONE && r.sel.some((s) => /^\.dsheet(--\w+)?$/.test(s)) && /z-index/.test(r.body))
      .map((r) => z(r.body));
    if (badge.length === 0 || sheets.length === 0) return false;
    return sheets.every((s) => s > Math.max(...badge) && s < 19);
  }

  it('A1 판(엿보기·반·가득)의 층이 화면 밖 표지보다 위 · 띠보다 아래 · 양성 대조(되돌린 꼴 · 띠를 넘는 꼴 · 표지를 올린 꼴)', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    expect(sheetAboveBadge(css)).toBe(true);
    expect(sheetAboveBadge(`${css}\n${PHONE} {\n  .dsheet { z-index: 2; }\n}`)).toBe(false);
    expect(sheetAboveBadge(`${css}\n${PHONE} {\r\n  .a,\r\n  .dsheet--full { z-index: 25; }\r\n}`)).toBe(false);
    expect(sheetAboveBadge(`${css}\n.dmap__off { z-index: 30; }`)).toBe(false);
  });

  it('★ A2 판 안에서는 「누른 자리」·「경계 밖」 글이 한 번(판 머리만) — 카드 꼴은 지금 그대로(목록 머리 · 양성 대조)', async () => {
    const count = (re: RegExp) => (document.body.textContent!.match(re) ?? []).length;
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.05, 37.55);
    expect(stageOf()).toBe('half');
    expect(count(/누른 자리/g)).toBe(1);
    expect(sheet()!.querySelector('.dsheet__title')!.textContent).toBe('누른 자리 (2곳):');
    expect(document.querySelector('.dmap__picked-key')).toBeNull();
    // 이름 단추(건물 목록 열기)는 그대로 판 안에 있다.
    expect(screen.getByRole('button', { name: /역삼골목/ })).toBeTruthy();
    await clickAt(126.0, 30.0);
    expect(count(/어느 상권 경계에도 들지 않는 위치입니다/g)).toBe(1);
    cleanup();

    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.05, 37.55);
    expect(document.querySelector('.dmap__picked-key')!.textContent).toBe('누른 자리 (2곳):');
    expect(count(/누른 자리/g)).toBe(1);
    await clickAt(126.0, 30.0);
    expect(document.querySelector('.dmap__picked-key')!.textContent).toBe('누른 자리:');
    expect(count(/어느 상권 경계에도 들지 않는 위치입니다/g)).toBe(1);
  });

  it('A3 종이 — 판 통째·범례·출처는 남고 손잡이·「접기」·안내만 빠진다 · 판은 흐름(static)', async () => {
    const { readFileSync } = await import('node:fs');
    const print = cssRules(readFileSync('src/styles.css', 'utf8')).filter((r) => r.media === '@media print');
    const hide = print.filter((r) => /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.dsheet__handle', '.dsheet__fold', '.dsheet__hint']) expect(hide, s).toContain(s);
    for (const s of ['.dsheet', '.dsheet__body', '.dsheet__head', '.dmap__legend', '.dmap__src', '.dmap--full']) {
      expect(hide, s).not.toContain(s);
    }
    expect(print.some((r) => r.sel.includes('.dsheet') && /position:\s*static/.test(r.body))).toBe(true);
  });

  it('★ B1 숨은 채 태어나면 지도를 만들지 않는다(자료·판은 받는다) — 처음 보일 때 하나 만들고 첫 범위 한 번 · 다시 숨겨도 치우지 않는다', async () => {
    const DistrictMap = await load();
    const { rerender } = render(<DistrictMap {...base} visible={false} />);
    await waitFor(() => expect(sheet()).not.toBeNull());
    expect(screen.queryByTestId('map')).toBeNull();
    expect(kakao.setBounds).not.toHaveBeenCalled();
    rerender(<DistrictMap {...base} visible />);
    await waitFor(() => expect(screen.getAllByTestId('map')).toHaveLength(1));
    expect(kakao.setBounds).toHaveBeenCalledTimes(1);
    // 보이는 칸에서 태어났다 — 되맞출 것이 없다.
    expect(kakao.relayout).not.toHaveBeenCalled();
    rerender(<DistrictMap {...base} visible={false} />);
    expect(screen.getAllByTestId('map')).toHaveLength(1);
    expect(kakao.setBounds).toHaveBeenCalledTimes(1);
  });

  it('★ B2 숨은(0×0) 칸의 멈춤은 버린다 — 표지도 안 세고 되돌릴 중심도 안 적는다 · 양성 대조(제 크기면 표지가 선다)', async () => {
    const DistrictMap = await load();
    const { rerender } = render(<DistrictMap {...base} visible />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await idle(FAR, { w: 0, h: 0 });
    expect(document.querySelectorAll('.dmap__off')).toHaveLength(0);
    await idle(FAR, { w: 412, h: 0 });
    expect(document.querySelectorAll('.dmap__off')).toHaveLength(0);
    rerender(<DistrictMap {...base} visible={false} />);
    rerender(<DistrictMap {...base} visible />);
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
    expect(kakao.setLevel).not.toHaveBeenCalled();
    expect(kakao.setCenter).not.toHaveBeenCalled();
    await idle(FAR, { w: 412, h: 600 });
    expect(document.querySelectorAll('.dmap__off').length).toBeGreaterThan(0);
  });

  it('★ B2 숨었다 다시 보이면 relayout → 배율 → 중심 차례로 「마지막으로 제대로 잰」 값을 되돌린다(0×0 멈춤은 안 덮는다)', async () => {
    const DistrictMap = await load();
    const { rerender } = render(<DistrictMap {...base} visible />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    const good = { tag: '제대로 잰 중심' };
    await idle(FAR, { w: 412, h: 600 }, 4, good);
    rerender(<DistrictMap {...base} visible={false} />);
    await idle(FAR, { w: 0, h: 0 }, 9, { tag: '숨은 칸 중심' });
    rerender(<DistrictMap {...base} visible />);
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
    expect(kakao.setLevel).toHaveBeenCalledTimes(1);
    expect(kakao.setLevel).toHaveBeenCalledWith(4);
    expect(kakao.setCenter).toHaveBeenCalledTimes(1);
    expect(kakao.setCenter.mock.calls[0][0]).toBe(good);
    const order = [kakao.relayout, kakao.setLevel, kakao.setCenter].map((f) => f.mock.invocationCallOrder[0]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it('★ B3 지도를 눌러 판이 반으로 오른 뒤 — 누른 자리가 줄어든 화면 밖이면 relayout 다음에 그쪽으로 한 번 옮긴다', async () => {
    kakao.getBounds.mockImplementation(() => ({ contain: () => false }));
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.05, 37.55);
    expect(stageOf()).toBe('half');
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
    expect(kakao.panTo).toHaveBeenCalledTimes(1);
    const at = kakao.panTo.mock.calls[0][0] as { getLat: () => number; getLng: () => number };
    expect([at.getLat(), at.getLng()]).toEqual([37.55, 127.05]);
    expect(kakao.relayout.mock.invocationCallOrder[0]).toBeLessThan(kakao.panTo.mock.invocationCallOrder[0]);
  });

  it('★ B3 누른 자리가 화면 안이면 옮기지 않는다(음성) · 아직 안 눌렀으면 단계를 바꿔도 옮기지 않는다', async () => {
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    fireEvent.click(handle()); // 반 — 누른 자리 없음
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
    expect(kakao.getBounds).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '접기' }));
    await clickAt(127.05, 37.55); // 기본 = 화면 안(contain true)
    expect(stageOf()).toBe('half');
    expect(kakao.relayout).toHaveBeenCalledTimes(3);
    expect(kakao.getBounds).toHaveBeenCalled();
    expect(kakao.panTo).not.toHaveBeenCalled();
  });

  it('★ B3 누른 자리는 한 번만 쓴다 — 그 뒤 판 단계를 바꿔도(사용자가 지도를 옮겼어도) 옛 누른 자리로 다시 옮기지 않는다(재검사 🟠)', async () => {
    kakao.getBounds.mockImplementation(() => ({ contain: () => false }));
    await renderMap({ layout: 'full' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await clickAt(127.05, 37.55);
    expect(stageOf()).toBe('half');
    expect(kakao.panTo).toHaveBeenCalledTimes(1);
    fireEvent.click(handle()); // 가득 — 화면 밖(contain false)이어도 옛 누른 자리로는 안 간다
    expect(stageOf()).toBe('full');
    expect(kakao.panTo).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '접기' }));
    expect(kakao.panTo).toHaveBeenCalledTimes(1);
    // 다시 누르면 다시 한 번(양성 대조).
    await clickAt(127.06, 37.56);
    expect(kakao.panTo).toHaveBeenCalledTimes(2);
  });

  it('★ C2 판이 가득이면 칩 줄·지도 칸은 inert(판 자체는 아님) — 엿보기·반에서는 아니다', async () => {
    await renderMap({ layout: 'full', headExtra: <span>칩 줄</span> });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    const inert = () =>
      ['.dmap__head', '.dmap__canvas'].map((s) => document.querySelector(s)!.hasAttribute('inert'));
    expect(inert()).toEqual([false, false]);
    fireEvent.click(handle()); // 반
    expect(inert()).toEqual([false, false]);
    fireEvent.click(handle()); // 가득
    expect(stageOf()).toBe('full');
    expect(inert()).toEqual([true, true]);
    expect(sheet()!.closest('[inert]')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '접기' }));
    expect(inert()).toEqual([false, false]);
  });
});

// ── PC 두 칸 보완(결정 0039 W5 보완 1 · F3 종이 지도 폭 · F7 relayout 안 쌓임) ─────────────────────────────
describe('DistrictMap — PC 두 칸 보완(W5 보완 1)', () => {
  const base = { sigungu: '11680', sigunguName: '강남구', selected: null, onSelectBuilding: () => {} };
  const VIEW = { swLat: 37.5, swLng: 127.0, neLat: 37.6, neLng: 127.1 };
  async function idleAt(w: number, h: number) {
    await act(async () => {
      kakao.mapProps?.onIdle?.({
        getBounds: () => ({
          getSouthWest: () => ({ getLat: () => VIEW.swLat, getLng: () => VIEW.swLng }),
          getNorthEast: () => ({ getLat: () => VIEW.neLat, getLng: () => VIEW.neLng }),
        }),
        getNode: () => ({ clientWidth: w, clientHeight: h }),
        getLevel: () => 6,
        getCenter: () => ({ lat: 37.55, lng: 127.05 }),
      });
    });
  }
  const canvas = () => document.querySelector<HTMLElement>('.dmap__canvas')!;

  it('★ F3 화면에서 잰 지도 칸 폭을 `--dmap-w` 로 남긴다(카드 꼴) · 못 잰(0×0) 멈춤은 안 적는다 · 휴대폰 가득 꼴은 안 적는다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    expect(canvas().style.getPropertyValue('--dmap-w')).toBe('');
    // 숨은 칸(0×0)의 멈춤 — 버린다(양성 대조의 반대편).
    await idleAt(0, 0);
    expect(canvas().style.getPropertyValue('--dmap-w')).toBe('');
    await idleAt(367, 300);
    expect(canvas().style.getPropertyValue('--dmap-w')).toBe('367px');
    // 칸이 넓어진 뒤 다시 멈추면 새 폭.
    await idleAt(405, 300);
    expect(canvas().style.getPropertyValue('--dmap-w')).toBe('405px');
    // 높이도 같은 자리(👤 2026-10-22 방법 나 R5 — 두 칸 지도 칸 높이가 창 높이를 따른다 · 종이는 그린 높이).
    expect(canvas().style.getPropertyValue('--dmap-h')).toBe('300px');
    await idleAt(405, 540);
    expect(canvas().style.getPropertyValue('--dmap-h')).toBe('540px');
    cleanup();

    await renderMap({ layout: 'full' });
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    await idleAt(412, 600);
    expect(canvas().style.getPropertyValue('--dmap-w')).toBe('');
    expect(canvas().style.getPropertyValue('--dmap-h')).toBe('');
  });

  it('★ F3 종이 — 「상권 지도 넣기」 종이의 지도 칸 폭 = `var(--dmap-w` (가운데) · 인쇄 묶음 안 · 양성 대조(갈래를 지운 꼴)', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync('src/styles.css', 'utf8');
    const has = (src: string) =>
      cssRules(src).some(
        (r) =>
          r.media === '@media print' &&
          r.sel.includes('.app--printmap .dmap__canvas') &&
          /width:\s*var\(--dmap-w/.test(r.body) &&
          /margin-left:\s*auto/.test(r.body),
      );
    expect(has(css)).toBe(true);
    const cut = css.replace(/\.app--printmap \.dmap__canvas\s*\{[^}]*\}/, '');
    expect(cut).not.toBe(css);
    expect(has(cut)).toBe(false);
    // 화면 묶음으로 옮긴 꼴도 못 지난다.
    expect(has(`${cut}\n@media screen {\n  .app--printmap .dmap__canvas { width: var(--dmap-w); margin-left: auto; }\n}`)).toBe(false);
  });

  it('★ 보완 3 창 크기가 바뀌면 relayout 을 직접 부른다 — 디바운스 하나(여러 번 → 멈춘 뒤 한 번) · 숨은(크기 0) 칸은 안 부름 · 사라지면 듣기를 멈춘다', async () => {
    await renderMap();
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    // 가짜 SDK 가 지도 객체를 effect 로 건넨 뒤의 다시 그리기까지 마친다(그래야 창 크기를 듣기 시작한다).
    await act(async () => {});
    kakao.relayout.mockClear();
    vi.useFakeTimers();
    try {
      // jsdom 의 칸 크기는 늘 0 — 숨은 칸과 같다 → 안 부른다.
      window.dispatchEvent(new Event('resize'));
      vi.advanceTimersByTime(200);
      expect(kakao.relayout).not.toHaveBeenCalled();
      // 보이는 칸(400×500)에서 창을 끌어 세 번 바꾼다 — 멈춘 뒤 한 번만.
      Object.defineProperty(canvas(), 'clientWidth', { value: 400, configurable: true });
      Object.defineProperty(canvas(), 'clientHeight', { value: 500, configurable: true });
      for (let i = 0; i < 3; i += 1) {
        window.dispatchEvent(new Event('resize'));
        vi.advanceTimersByTime(50);
      }
      expect(kakao.relayout).not.toHaveBeenCalled();
      vi.advanceTimersByTime(200);
      expect(kakao.relayout).toHaveBeenCalledTimes(1);
      // 사라진 뒤의 창 크기 변화는 안 듣는다.
      cleanup();
      window.dispatchEvent(new Event('resize'));
      vi.advanceTimersByTime(200);
      expect(kakao.relayout).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('★ F7 숨은 채(왼쪽 칸 접힘) 건물을 여러 번 바꿔도 relayout 0 — 다시 보일 때 한 번', async () => {
    const DistrictMap = await load();
    const { rerender } = render(<DistrictMap {...base} visible />);
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());
    rerender(<DistrictMap {...base} visible={false} />);
    for (const [lat, lng, n] of [
      [37.55, 127.05, '1'],
      [37.56, 127.06, '2'],
      [37.57, 127.07, '3'],
    ] as const) {
      rerender(<DistrictMap {...base} visible={false} selected={building({ lat, lng, bld_id: `b${n}` })} />);
    }
    expect(kakao.relayout).not.toHaveBeenCalled();
    rerender(<DistrictMap {...base} visible selected={building({ lat: 37.57, lng: 127.07, bld_id: 'b3' })} />);
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
    // 보이는 채로 건물을 바꿔도 더 안 부른다(칸 크기가 안 바뀐다).
    rerender(<DistrictMap {...base} visible selected={building({ lat: 37.58, lng: 127.08, bld_id: 'b4' })} />);
    expect(kakao.relayout).toHaveBeenCalledTimes(1);
  });
});
