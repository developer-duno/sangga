import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
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
  /** `<Map>` 이 마지막으로 받은 props. 클릭 이벤트를 여기서 직접 쏜다. */
  mapProps: null as { onClick?: (m: unknown, e: unknown) => void } | null,
  setBounds: vi.fn(),
  panTo: vi.fn(),
  setLevel: vi.fn(),
}));

vi.mock('react-kakao-maps-sdk', () => ({
  useKakaoLoader: () => [false, undefined],
  useMap: () => ({ setBounds: kakao.setBounds, panTo: kakao.panTo, setLevel: kakao.setLevel }),
  Map: (props: { children?: React.ReactNode; onClick?: (m: unknown, e: unknown) => void }) => {
    kakao.mapProps = props;
    return <div data-testid="map">{props.children}</div>;
  },
  Polygon: (props: { fillColor?: string }) => <div data-testid="polygon" data-fill={props.fillColor} />,
  MapMarker: (props: { position: { lat: number; lng: number } }) => (
    <div data-testid="marker" data-lat={props.position.lat} data-lng={props.position.lng} />
  ),
}));

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
  kakao.mapProps = null;
  kakao.setBounds.mockReset();
  kakao.panTo.mockReset();
  kakao.setLevel.mockReset();
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
  render(<DistrictMap sigungu="11680" sigunguName="강남구" selected={null} {...props} />);
  return DistrictMap;
}

// ── 키가 없을 때 (CI·E2E 요건) ──────────────────────────────────────────

describe('DistrictMap — 지도 키가 없을 때', () => {
  it('스크립트를 부르지 않고 안내만 한다', async () => {
    vi.stubEnv('VITE_KAKAO_JS_KEY', '');
    const DistrictMap = await load();
    render(<DistrictMap sigungu="11680" sigunguName="강남구" selected={null} />);

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
    const { container } = render(<DistrictMap sigungu={null} sigunguName={null} selected={null} />);
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

// ── 건물 마커 ───────────────────────────────────────────────────────────

describe('DistrictMap — 건물 마커', () => {
  it('좌표가 있으면 그 자리에 찍는다', async () => {
    await renderMap({ selected: building({ lat: 37.55, lng: 127.05 }) });
    await waitFor(() => expect(screen.getByTestId('marker')).toBeTruthy());
    expect(screen.getByTestId('marker').getAttribute('data-lat')).toBe('37.55');
    expect(kakao.panTo).toHaveBeenCalled();
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
      <DistrictMap sigungu="11680" sigunguName="강남구" selected={null} />,
    );
    await waitFor(() => expect(screen.getByTestId('map')).toBeTruthy());

    rerender(<DistrictMap sigungu="30170" sigunguName="서구" selected={null} />);
    await waitFor(() => expect(screen.getByText(/출처: 소상공인시장진흥공단/)).toBeTruthy());

    // 파일 하나에 전국이 다 들어 있다 — 구별로 거르기만 하면 된다.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
