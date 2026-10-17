import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  CustomOverlayMap,
  Map,
  MapMarker,
  Polygon,
  useKakaoLoader,
  useMap,
} from 'react-kakao-maps-sdk';
import { loadDistricts } from '../lib/districts';
import { showLabels } from '../lib/districtLabels';
import { pointInGeometry, polygonsOf, ringsToPath, type Bounds } from '../lib/geo';
import {
  coreBoundsOf,
  farDots,
  mapItemsOf,
  offscreenGroups,
  type MapView,
  type OffscreenGroup,
} from '../lib/districtMapView';
import { FOUNDER_CHIP_ALL, type FounderChip } from '../lib/founderChips';
import { EMPTY_MAP_PICK, type DistrictMapPick } from '../lib/districtMapPick';
import type { BuildingHit, DistrictFeature } from '../types';
import { DistrictBuildings } from './DistrictBuildings';

/**
 * 상권 지도 — 고른 구의 상권 경계를 면으로 그린다(결정 0010).
 *
 * 세 가지가 이 화면의 규칙이다:
 *  ① **그리는 순서를 건드리지 않는다.** 파일이 면적 내림차순으로 구워져 있어서, 그 순서
 *     그대로 그리면 넓은 상권이 아래·좁은 골목상권이 위로 온다. 정렬을 다시 하면 골목상권이
 *     발달상권 밑에 깔려 보이지 않는다.
 *  ② **겹치면 전부 나열한다.** 클릭 판정을 카카오 Polygon 이벤트가 아니라 우리가 직접
 *     한다(lib/geo.ts 머리말) — 그래야 #51 의 "속한 상권"과 같은 규칙이 된다.
 *  ③ **출처는 자료에서 읽는다.** 서울시·소상공인시장진흥공단 둘이라 문구를 박으면 한쪽에
 *     거짓말이 된다(공공누리 1유형 출처표시 의무).
 */

type Props = {
  /** 지금 고른 시군구 코드. 없으면 지도를 아예 그리지 않는다. */
  sigungu: string | null;
  /** 고른 시군구 이름(제목용). */
  sigunguName: string | null;
  /** 지금 고른 건물. 좌표가 있을 때만 마커를 찍는다. */
  selected: BuildingHit | null;
  /**
   * 상권 안의 건물 목록에서 하나를 고르면 부른다.
   *
   * ⓘ 검색 결과를 골랐을 때와 **같은 handler** 를 받는다 — 들어온 길이 달라도 그 뒤는
   *   똑같아야 주소 남기기·인쇄 머리글·지도 마커가 저절로 따라온다.
   */
  onSelectBuilding: (hit: BuildingHit) => void;
  /**
   * 제목 줄에 함께 얹을 것 — 창업자의 업종 칩 줄(👤 결정 0036 결정 18 ④). 없으면 지금 머리 그대로.
   * ⓘ 칩 줄을 그리는 일은 App 몫이다 — 지도는 고른 칩 값(`chip`)만 받아 상권 목록에 넘긴다.
   */
  headExtra?: ReactNode;
  /**
   * 창업자가 고른 업종 칩(App 의 `activeChip` — 다른 역할은 늘 '전체'). 상권 목록(`DistrictBuildings`)이
   * 그 업종 기준으로 거르고 줄 세운다(2026-10-11a · 물결 2-2b · 결정 18 ⑨·㉒). 지도 면은 안 바뀐다.
   */
  chip?: FounderChip;
  /**
   * 누른 자리의 상권·펼친 상권 목록(👤 2026-10-15 G1 「다시 펴면 그대로 되살리기」). 주면 그 값을 쓰고 바뀌면 알린다 —
   * App 이 쥐어, 입구가 접혀 지도가 안 그려졌다가(S1) 다시 그려져도 아까 누른 상권과 건물 목록이 그대로 선다.
   * 안 주면 지도가 스스로 쥔다(다시 그려지면 처음부터).
   * ⛔ 화면 상태만 — 이 기기 저장·주소·의견함에 싣지 않는다 · 구가 다르면 없는 것으로 본다.
   */
  pick?: DistrictMapPick;
  onPickChange?: (next: DistrictMapPick) => void;
};

/**
 * 건물을 골랐을 때 맞출 지도 확대 수준.
 *
 * 카카오 ROADMAP 은 1~14 이고 **숫자가 작을수록 확대**다(kakao.maps.d.ts Map.setLevel 주석).
 * 4 는 축척 약 100m — 건물과 맞닿은 골목·옆 블록이 함께 보이는 정도다. 더 당기면(3 이하)
 * 상권 면이 화면 밖으로 밀려 무엇에 속한 건물인지 안 보이고, 더 밀면(6 이상) 지금처럼
 * 건물이 점이 된다.
 */
const FOCUS_LEVEL = 4;

/**
 * 지도를 처음 그릴 때의 확대 수준.
 *
 * 이 값에서는 상권 이름표를 켜지 않는다 — 한 구에 상권이 수십~수백 개라 이름이 서로 겹쳐
 * 글자 죽이 된다(`lib/districtLabels.ts`). 한 단계 확대하면(5) 그때부터 이름이 붙는다.
 */
const INITIAL_LEVEL = 6;

/**
 * 첫 범위를 맞출 때 사방 여백(px) — 카카오 `setBounds` 기본은 32(kakao.maps.d.ts).
 * 화면 밖 표지(「↙ 3곳」)가 지도 가장자리에 앉으므로 그만큼 조금 더 비워, 몰린 곳의 가장자리 상권이
 * 표지 밑에 깔리지 않게 한다(결정 0039 Q4 · W1).
 */
const MAP_PADDING_PX = 40;

/**
 * 유형별 색. 자료에 있는 5종(골목·발달·전통시장·관광특구·주요)을 여기서 색으로만 잇는다.
 *
 * ⚠️ 이 표는 "무엇이 있는가"의 목록이 아니다 — 범례는 **실제로 그려진 면들의 유형**에서
 *    만든다. 새 유형이 자료에 생기면 회색으로 그려지고 범례에도 그대로 나온다.
 */
const TYPE_COLORS: Record<string, string> = {
  골목상권: '#2f5fd0',
  발달상권: '#c4452d',
  전통시장: '#2e8b57',
  관광특구: '#7a4fc0',
  주요상권: '#b8860b',
};
const FALLBACK_COLOR = '#6b6d76';

function colorOf(type: string | null): string {
  return (type && TYPE_COLORS[type]) || FALLBACK_COLOR;
}

/** 지도를 가리지 않을 만큼만 칠한다 — 겹친 면이 서로 비쳐 보여야 겹침이 눈에 띈다. */
const FILL_OPACITY = 0.18;

export function DistrictMap({
  sigungu,
  sigunguName,
  selected,
  onSelectBuilding,
  headExtra,
  chip = FOUNDER_CHIP_ALL,
  pick,
  onPickChange,
}: Props) {
  const [open, setOpen] = useState(true);

  if (!sigungu) return null;

  // ⚠️ 키를 모듈 바깥이 아니라 여기서 읽는다 — 없는 상태를 테스트로 재현할 수 있어야 한다.
  const appkey = import.meta.env.VITE_KAKAO_JS_KEY;

  return (
    <section className="dmap">
      <header className="dmap__head">
        <h2 className="dmap__title">{sigunguName ?? '고른 지역'} 상권 지도</h2>
        <button type="button" className="dmap__toggle" onClick={() => setOpen(!open)}>
          {open ? '지도 접기' : '지도 펴기'}
        </button>
        {headExtra}
      </header>

      {!open ? (
        <p className="dmap__folded">지도를 접어 두었습니다.</p>
      ) : !appkey ? (
        <p className="msg">
          지도 키가 설정되지 않았습니다. <code>python scripts/make_env_local.py</code>를 실행하면{' '}
          <code>.env</code>에서 만들어집니다.
        </p>
      ) : (
        <DistrictMapBody
          appkey={appkey}
          sigungu={sigungu}
          selected={selected}
          onSelectBuilding={onSelectBuilding}
          chip={chip}
          pick={pick}
          onPickChange={onPickChange}
        />
      )}
    </section>
  );
}

/**
 * 키가 있을 때만 그려지는 알맹이.
 *
 * ⚠️ 컴포넌트를 굳이 나눈 이유: `useKakaoLoader`는 부르는 순간 카카오 스크립트를 내려받는다.
 *    키가 없을 때 그 훅을 부르면(훅은 조건부로 못 부른다) 빈 키로 요청이 나간다. 컴포넌트
 *    자체를 안 그리면 훅도 안 불린다 — CI·E2E 처럼 키가 없는 환경에서 바깥 요청이 0이다.
 */
function DistrictMapBody({
  appkey,
  sigungu,
  selected,
  onSelectBuilding,
  chip,
  pick: pickProp,
  onPickChange,
}: {
  appkey: string;
  sigungu: string;
  selected: BuildingHit | null;
  onSelectBuilding: (hit: BuildingHit) => void;
  chip: FounderChip;
  pick?: DistrictMapPick;
  onPickChange?: (next: DistrictMapPick) => void;
}) {
  const [kakaoLoading, kakaoError] = useKakaoLoader({ appkey });
  const [features, setFeatures] = useState<DistrictFeature[] | null>(null);
  const [fileError, setFileError] = useState(false);
  /*
    누른 자리·펼친 상권(`DistrictMapPick`). 위(App)가 주면 그것을, 안 주면 스스로 쥔다.
    ⛔ 다른 구에서 누른 기억은 없는 것으로 본다 — 안 그러면 다른 구의 상권이 그대로 남는다.
  */
  const [ownPick, setOwnPick] = useState<DistrictMapPick>(EMPTY_MAP_PICK);
  const pickNow = pickProp ?? ownPick;
  const setPick = onPickChange ?? setOwnPick;
  const mine = pickNow.sigungu === sigungu ? pickNow : EMPTY_MAP_PICK;
  /**
   * 지금 확대 수준. 이름표를 켤지 말지에만 쓴다.
   *
   * ⚠️ 이 값을 `<Map level>`로 되먹이지 **않는다.** 지도가 실제로 몇 배율인지는 카카오가
   *    쥐고 있고(사용자 휠·`setBounds`·`setLevel`이 다 바꾼다), 우리는 그 결과를
   *    `onZoomChanged`로 **받아 적기만** 한다. 되먹이면 우리가 적은 값이 다시 지도를
   *    밀어 사용자가 맞춘 배율과 다투게 된다.
   */
  const [level, setLevel] = useState(INITIAL_LEVEL);

  useEffect(() => {
    let cancelled = false;
    loadDistricts()
      .then((json) => {
        if (!cancelled) setFeatures(json.features);
      })
      .catch((err) => {
        if (cancelled) return;
        // 지도는 이 화면의 보조 자료다 — 못 읽어도 검색·층 스택은 멀쩡하다.
        console.warn('상권 경계 파일을 불러오지 못했습니다', err);
        setFileError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ⛔ 정렬하지 않는다. 파일 순서(면적 내림차순)가 곧 겹침 규칙이다.
  const shown = useMemo(
    () => (features ?? []).filter((f) => f.properties.sigungu_code === sigungu),
    [features, sigungu],
  );
  /*
    첫 범위 = **몰린 곳** 상자(결정 0039 Q4 · W1). 상권 5곳 이하 구는 전부 담는 상자 — 그 갈래는
    `coreBoundsOf` 안에 있다. ⓘ 구가 바뀌면 이 값이 바뀌어 `MapFocus` 가 사용자가 옮긴 배율과 상관없이 다시 맞춘다.
  */
  const bounds = useMemo(() => coreBoundsOf(shown), [shown]);
  /** 마지막으로 누른 자리에 걸친 상권들. null이면 아직 아무 데도 안 눌렀다는 뜻이다. */
  const picked = useMemo(
    () =>
      mine.pickedIds === null
        ? null
        : mine.pickedIds.flatMap((id) => shown.filter((f) => f.properties.district_id === id)),
    [mine.pickedIds, shown],
  );
  /**
   * 건물 목록을 펼쳐 둔 상권. 누른 자리에 여럿이 걸치면 그중 **하나만** 연다.
   *
   * ⛔ 지도를 다시 누르면 비운다 — 안 비우면 새로 누른 자리 아래에 **옛 상권의 건물들**이
   *    그대로 서 있어, 방금 누른 곳의 목록으로 읽힌다.
   */
  const openDistrict =
    mine.openId === null ? null : (shown.find((f) => f.properties.district_id === mine.openId) ?? null);
  /** 그려진 면들의 출처만 모은다 — 안 쓴 출처를 덧붙이는 것은 지어낸 출처다(2026-08-14d와 같은 규칙). */
  const sources = useMemo(
    () => [...new Set(shown.map((f) => f.properties.source_nm).filter(Boolean))],
    [shown],
  );
  const legend = useMemo(
    () => [...new Set(shown.map((f) => f.properties.district_type ?? '기타'))],
    [shown],
  );
  /**
   * 이름표를 놓을 자리 — 면 하나에 한 곳. 자리를 못 잡는 도형은 아예 빠진다.
   *
   * ⚠️ **`shown`이 바뀔 때만** 다시 센다. 배율이 바뀔 때마다 수백 개의 무게중심을 다시
   *    세면 확대·축소가 그만큼 뻑뻑해진다(이름표를 켜고 끄는 것은 계산이 아니라 그리기다).
   */
  const labels = useMemo(() => mapItemsOf(shown), [shown]);
  /*
    지도가 멈췄을 때 잰 지금 화면(`onIdle`) — 화면 밖 표지와 멀리서의 점+이름을 정한다(결정 0039 W1).
    ⛔ 다른 구에서 잰 화면은 없는 것으로 본다 — 구를 바꾼 직후 새 범위를 맞추기 전에 옛 화면으로 세면
       새 구의 상권이 전부 '화면 밖'으로 한 번 그려진다.
  */
  const [measured, setMeasured] = useState<(MapView & { sigungu: string }) | null>(null);
  const view = measured?.sigungu === sigungu ? measured : null;
  const offscreen = useMemo(() => (view ? offscreenGroups(labels, view.bounds) : []), [labels, view]);
  // 배율은 `onZoomChanged` 로 받은 값(`level`)을 쓴다 — 멈춤(`onIdle`)보다 먼저 와서, 이름표와 점이 한꺼번에 서는 틈이 없다.
  const dots = useMemo(() => (view ? farDots(labels, { ...view, level }) : []), [labels, view, level]);

  const focusLat = selected?.lat ?? null;
  const focusLng = selected?.lng ?? null;

  if (kakaoError) return <p className="msg msg--error">지도를 불러오지 못했습니다.</p>;
  if (fileError) return <p className="msg msg--error">상권 경계 자료를 불러오지 못했습니다.</p>;
  if (features === null || kakaoLoading) return <p className="msg">지도를 불러오는 중…</p>;
  if (bounds === null) {
    // 상권이 0개인 구는 실제로 있다(대전은 5개 구에 37개가 흩어져 있다). 빈 지도를 띄우고
    // "왜 아무것도 없지?" 하게 두는 대신, 자료가 없다고 말한다.
    return <p className="msg">이 구에는 아직 상권 경계 자료가 없습니다.</p>;
  }

  return (
    <>
      <div className="dmap__canvas">
        <Map
          center={{ lat: (bounds.swLat + bounds.neLat) / 2, lng: (bounds.swLng + bounds.neLng) / 2 }}
          style={{ width: '100%', height: '100%' }}
          level={INITIAL_LEVEL}
          onClick={(_map, mouseEvent) => {
            const lat = mouseEvent.latLng.getLat();
            const lng = mouseEvent.latLng.getLng();
            setPick({
              sigungu,
              pickedIds: shown
                .filter((f) => pointInGeometry(lng, lat, f.geometry))
                .map((f) => f.properties.district_id),
              openId: null,
            });
          }}
          onZoomChanged={(map) => setLevel(map.getLevel())}
          onIdle={(map) => {
            // 지도가 멈출 때마다 지금 범위와 지도 칸 크기를 잰다(배율별 표를 박지 않는다).
            const b = map.getBounds();
            const sw = b.getSouthWest();
            const ne = b.getNorthEast();
            const node = map.getNode();
            setMeasured({
              sigungu,
              bounds: { swLat: sw.getLat(), swLng: sw.getLng(), neLat: ne.getLat(), neLng: ne.getLng() },
              widthPx: node.clientWidth,
              heightPx: node.clientHeight,
              level: map.getLevel(),
            });
          }}
        >
          <MapFocus bounds={bounds} focusLat={focusLat} focusLng={focusLng} />

          {shown.map((f) =>
            polygonsOf(f.geometry).map((rings, i) => (
              <Polygon
                key={`${f.properties.district_id}-${i}`}
                path={ringsToPath(rings)}
                fillColor={colorOf(f.properties.district_type)}
                fillOpacity={FILL_OPACITY}
                strokeColor={colorOf(f.properties.district_type)}
                strokeOpacity={0.7}
                strokeWeight={1}
              />
            )),
          )}

          {/*
            상권 이름표 — 한 단계 확대(level ≤ 5)부터만 켠다.

            ⛔ **클릭을 가로채면 안 된다.** 이 화면의 "누른 자리 상권"은 지도 클릭 한 번을
               받아 우리가 직접 판정한다(lib/geo.ts 머리말). 이름표가 그 클릭을 삼키면
               상권 위를 눌렀는데 아무 일도 안 일어난다.
               막는 장치는 둘이고, 둘 다 필요하다:
                ① `clickable={false}` — 카카오가 "컨텐츠를 클릭하면 지도 이벤트를 막는" 것은
                   **`clickable: true`일 때뿐**이다(kakao.maps.d.ts `CustomOverlayOptions`).
                   그래서 끈 채로 둔다. ⚠️ 값을 안 주면 기본값에 기대게 되므로 **적어 둔다.**
                ② `styles.css`의 `.dmap__label { pointer-events: none }` — 브라우저 수준에서
                   이름표 자체를 클릭 대상에서 빼, 클릭이 지도에 그대로 닿는다.
          */}
          {showLabels(level) &&
            labels.map((l) => (
              <CustomOverlayMap key={`label-${l.id}`} position={l.at} clickable={false}>
                <span className="dmap__label">{l.nm}</span>
              </CustomOverlayMap>
            ))}

          {/*
            멀리서는 점 + 이름(결정 0039 W1) — 이름표가 꺼진 배율에서 화면에서 작은 상권만.
            ⛔ 위 이름표와 같은 두 겹으로 **누르기를 넘긴다**: `clickable={false}` + `.dmap__far { pointer-events: none }`.
            ⓘ 점의 가운데가 그 점에 오도록 왼쪽 끝에 붙인다(xAnchor 0) — 이름은 점 오른쪽(`farDots` 의 겹침 어림과 같은 꼴).
          */}
          {dots.map((d) => (
            <CustomOverlayMap
              key={`far-${d.id}`}
              position={d.at}
              clickable={false}
              xAnchor={0}
              yAnchor={0.5}
            >
              <span className="dmap__far">
                <span className="dmap__dot" />
                {d.nm && <span className="dmap__label">{d.nm}</span>}
              </span>
            </CustomOverlayMap>
          ))}

          <OffscreenBadges groups={offscreen} />

          {focusLat != null && focusLng != null && (
            <MapMarker
              position={{ lat: focusLat, lng: focusLng }}
              title={selected?.bld_nm ?? undefined}
            />
          )}
        </Map>
      </div>

      <ul className="dmap__legend">
        {legend.map((t) => (
          <li key={t}>
            <span className="dmap__swatch" style={{ background: colorOf(t) }} />
            {t}
          </li>
        ))}
      </ul>

      <PickedList
        picked={picked}
        openId={openDistrict?.properties.district_id ?? null}
        onPick={(f) =>
          setPick({
            ...mine,
            sigungu,
            openId: mine.openId === f.properties.district_id ? null : f.properties.district_id,
          })
        }
      />

      {openDistrict && (
        /*
          ⛔ key 에 상권과 칩을 함께 둔다(2026-10-11 적대 검사 🟡). 같은 조각을 그대로 두고 칩만 바꾸면
             effect 가 옛 목록을 비우기 **전 첫 렌더**에 옛 칩의 숫자가 새 칩 이름표로 한 번 그려진다
             (카페 → 한식 때 「고른 업종(한식) 3곳」). 새로 태어나면 처음부터 '불러오는 중'이다.
        */
        <DistrictBuildings
          key={`${openDistrict.properties.district_id}|${chip}`}
          districtId={openDistrict.properties.district_id}
          districtNm={openDistrict.properties.district_nm || '(이름 없음)'}
          onSelect={onSelectBuilding}
          selectedBldId={selected?.bld_id ?? null}
          chip={chip}
        />
      )}

      {/* 공공누리 1유형(출처표시) 의무. 문구가 아니라 자료(source_nm)에서 온다. */}
      {sources.length > 0 && <p className="dmap__src">출처: {sources.join(' · ')}</p>}
    </>
  );
}

/**
 * 지도 시점 맞추기.
 *
 * 지도 객체를 직접 만져야 하는 두 가지(범위 맞추기·선택 건물로 이동)만 여기서 한다 —
 * `useMap()`은 `Map` 안에서만 쓸 수 있어서 자식 컴포넌트로 뺐다.
 */
function MapFocus({
  bounds,
  focusLat,
  focusLng,
}: {
  bounds: Bounds;
  focusLat: number | null;
  focusLng: number | null;
}) {
  const map = useMap();

  useEffect(() => {
    map.setBounds(
      new kakao.maps.LatLngBounds(
        new kakao.maps.LatLng(bounds.swLat, bounds.swLng),
        new kakao.maps.LatLng(bounds.neLat, bounds.neLng),
      ),
      MAP_PADDING_PX,
      MAP_PADDING_PX,
      MAP_PADDING_PX,
      MAP_PADDING_PX,
    );
  }, [map, bounds]);

  // 건물을 고르면 그 건물 **주변이 보이도록** 옮기고 확대한다.
  //
  // ⚠️ 예전에는 위치만 옮기고(panTo) 배율은 그대로 뒀다 — "사용자가 맞춘 배율을 되돌리지
  //    않는다"는 뜻이었는데, 첫 선택에서 정반대로 작동했다. 위 setBounds 가 구의 상권 전체를
  //    담느라 배율을 아주 넓게(축척 2km — 서울 절반이 보이는 수준) 잡아 두기 때문에, 건물을
  //    골라도 점 하나로만 보였다(2026-08-17 사장님 지적, 종로구에서 실제로 그랬다).
  //    배율을 맞추는 것은 **건물이 새로 선택될 때뿐**이라(이 effect 의 의존성이 좌표다)
  //    그 뒤 사용자가 직접 확대·축소한 것은 그대로 남는다 — 원래 의도도 지킨다.
  useEffect(() => {
    if (focusLat != null && focusLng != null) {
      const at = new kakao.maps.LatLng(focusLat, focusLng);
      // 순서: 배율 먼저, 이동 나중. 반대로 하면 넓은 배율에서 이동한 뒤 확대돼 두 번 움직인다.
      map.setLevel(FOCUS_LEVEL);
      map.panTo(at);
    }
  }, [map, focusLat, focusLng]);

  return null;
}

/**
 * 화면 밖 표지 — 지금 화면 밖 상권을 방향마다 「↙ 이름 등 3곳」 단추로 가장자리에 단다(결정 0039 W1).
 * 누르면 그 묶음의 가운데로 옮긴다(`panTo` — 배율은 그대로).
 *
 * ⓘ `<Map>` 안에 둬야 `useMap()` 이 지도를 준다. 그려지는 DOM 은 지도 칸 바로 옆(`.dmap__canvas` 안)이라
 *   `.dmap__canvas` 를 기준으로 가장자리에 띄운다(styles.css).
 * ⓘ 휴대폰(720px 이하)에서는 이름을 숨기고 「↙ 3곳」만 — styles.css 의 `@media screen and (max-width: 720px)` 묶음.
 * ⛔ 종이에는 안 나온다(누르는 장치다 — styles.css 인쇄 감춤 목록).
 */
function OffscreenBadges({ groups }: { groups: OffscreenGroup[] }) {
  const map = useMap();
  return (
    <>
      {groups.map((g) => (
        <button
          key={g.dir}
          type="button"
          className={`dmap__off dmap__off--${g.dir}`}
          aria-label={`${g.word} 화면 밖 상권 ${g.count}곳(${g.nm}${g.count > 1 ? ' 등' : ''}) — 그쪽으로 옮기기`}
          onClick={() => map.panTo(new kakao.maps.LatLng(g.center.lat, g.center.lng))}
        >
          <span aria-hidden="true">{g.arrow}</span>
          <span className="dmap__off-nm">{g.nm}</span>
          {g.count > 1 && <span className="dmap__off-etc">등</span>}
          <span>{g.count}곳</span>
        </button>
      ))}
    </>
  );
}

/**
 * 누른 자리에 걸친 상권 목록.
 *
 * 말해야 하는 상태가 셋이고 뭉뚱그리지 않는다(#51 "속한 상권"과 같은 규칙):
 *  ① 아직 안 눌렀다 → 눌러 보라고 안내
 *  ② 눌렀는데 어느 상권에도 안 든다 → "없음"이 정상이다
 *  ③ 여럿에 걸친다 → **전부** 나열
 */
function PickedList({
  picked,
  openId,
  onPick,
}: {
  picked: DistrictFeature[] | null;
  /** 지금 건물 목록을 펼쳐 둔 상권. 없으면 null. */
  openId: string | null;
  onPick: (f: DistrictFeature) => void;
}) {
  if (picked === null) {
    return (
      <p className="dmap__picked dmap__picked--idle">
        지도를 누르면 그 자리의 상권을 알려드립니다. 상권 이름을 다시 누르면 그 안의 건물이
        나옵니다.
      </p>
    );
  }

  if (picked.length === 0) {
    return (
      <p className="dmap__picked">
        <span className="dmap__picked-key">누른 자리:</span>
        어느 상권 경계에도 들지 않는 위치입니다.
      </p>
    );
  }

  return (
    <div className="dmap__picked">
      <span className="dmap__picked-key">누른 자리 ({picked.length}곳):</span>
      <ul className="dmap__picked-list">
        {picked.map((f) => (
          <li key={f.properties.district_id}>
            {/* 이름을 **버튼**으로 만든 것이 이 조각의 전부다 — 여태 이 목록은 이름만
                알려주고 끝나는 막다른 길이었다(창업자는 건물 이름을 모른다). */}
            <button
              type="button"
              className={`dmap__picked-btn${
                openId === f.properties.district_id ? ' dmap__picked-btn--on' : ''
              }`}
              aria-expanded={openId === f.properties.district_id}
              onClick={() => onPick(f)}
            >
              <span
                className="dmap__swatch"
                style={{ background: colorOf(f.properties.district_type) }}
              />
              <span className="dmap__picked-nm">{f.properties.district_nm || '(이름 없음)'}</span>
              <span className="dmap__picked-ty">{f.properties.district_type ?? '유형 미상'}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
