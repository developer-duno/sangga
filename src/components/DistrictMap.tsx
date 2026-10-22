import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
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
import type { AddrArea } from '../lib/shortAddr';
import type { BuildingHit, DistrictFeature } from '../types';
import { DistrictBuildings } from './DistrictBuildings';
import { DistrictSheet, type SheetStage } from './DistrictSheet';

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
  /**
   * 꼴 — `card`(기본 · 넓은 화면·중개사: 제목·접기 단추 → 지도 칸 → 범례·누른 자리·건물 목록·출처) ·
   * `full`(휴대폰 지도 탭 · 👤 2026-10-19 W4b: 칩 줄만 → 지도 칸(남은 높이 전부) → 끌어올리는 판 안에 범례·누른 자리·건물 목록·출처).
   * ⓘ 화면 배치(지도 칸이 화면을 채우는 것)는 App 의 `.app--mapfull` + styles.css 720 화면 묶음이 맡는다.
   */
  layout?: 'card' | 'full';
  /**
   * 보이나(휴대폰 탭 · W4b) — false 면 `hidden` 으로 숨기기만 한다(언마운트 0 · 확대·이동·누른 상권이 그대로).
   * 다시 보이면 카카오 `relayout()` 을 한 번 부른다. 넓은 화면은 늘 true(속성 없음 — DOM 그대로).
   */
  visible?: boolean;
  /** PC 두 칸 왼쪽 칸이면 고른 시·구 — 상권 건물 목록 주소를 길 이름부터(👤 2026-10-22 L2 · `DistrictBuildings` 로 넘기기만). */
  paneArea?: AddrArea | null;
  /** PC 두 칸 오른쪽 목록 자리 · 목록 이름 알리기(👤 2026-10-22 방법 나 R1 · `DistrictBuildings` 로 넘기기만). */
  listHost?: HTMLElement | null;
  onListChange?: (label: string | null) => void;
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

/** 지도 칸 크기 변화 → relayout 디바운스(ms) — 창을 끌어 늘리는 동안 매 프레임 부르지 않고 멈춘 뒤 한 번(보완 3). */
const RELAYOUT_DEBOUNCE_MS = 150;

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
  pick: pickProp,
  onPickChange,
  layout = 'card',
  visible = true,
  paneArea = null,
  listHost = null,
  onListChange,
}: Props) {
  const [open, setOpen] = useState(true);
  const full = layout === 'full';
  /*
    끌어올리는 판의 단계(휴대폰 지도 탭 · W4b). ⛔ 구가 바뀌면 엿보기로 — 그리는 도중에 맞춘다(React 공식 꼴 ·
    effect 로 돌리면 새 구가 옛 단계로 한 번 그려진다).
  */
  const [stage, setStage] = useState<SheetStage>('peek');
  const [stageFor, setStageFor] = useState(sigungu);
  if (stageFor !== sigungu) {
    setStageFor(sigungu);
    setStage('peek');
  }

  // ⚠️ 키를 모듈 바깥이 아니라 여기서 읽는다 — 없는 상태를 테스트로 재현할 수 있어야 한다.
  const appkey = import.meta.env.VITE_KAKAO_JS_KEY;
  /*
    경계 파일을 받을 때 — 카드 꼴은 지금처럼 **키가 있고 펼쳐 있을 때만**(키가 없으면 1.13MB 를 받아 봐야 그릴 데가 없다).
    휴대폰 지도 가득(full)은 키가 없어도 받는다 — 판(상권 수·범례·출처)은 지도 없이도 선다(E2E·CI 에는 키가 없다).
  */
  const needData = sigungu !== null && (full || (open && Boolean(appkey)));

  const [features, setFeatures] = useState<DistrictFeature[] | null>(null);
  const [fileError, setFileError] = useState(false);
  useEffect(() => {
    if (!needData) return;
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
  }, [needData]);

  /*
    누른 자리·펼친 상권(`DistrictMapPick`). 위(App)가 주면 그것을, 안 주면 스스로 쥔다.
    ⛔ 다른 구에서 누른 기억은 없는 것으로 본다 — 안 그러면 다른 구의 상권이 그대로 남는다.
  */
  const [ownPick, setOwnPick] = useState<DistrictMapPick>(EMPTY_MAP_PICK);
  const pickNow = pickProp ?? ownPick;
  const setPick = onPickChange ?? setOwnPick;
  const mine = pickNow.sigungu === sigungu ? pickNow : EMPTY_MAP_PICK;

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

  if (!sigungu) return null;

  /** 지도를 눌렀다 — 그 자리에 걸친 상권(전부). 휴대폰 지도 가득에서는 판이 엿보기면 반으로 올라온다(👤 W4b 2번). */
  function handleMapPick(lng: number, lat: number) {
    setPick({
      sigungu,
      pickedIds: shown.filter((f) => pointInGeometry(lng, lat, f.geometry)).map((f) => f.properties.district_id),
      openId: null,
    });
    if (full && stage === 'peek') setStage('half');
  }

  /* 지도 아래 것 — 범례 → 누른 자리 상권 → 건물 목록 → 출처(카드 꼴은 지도 칸 아래, 휴대폰 지도 가득은 판 안). */
  const below = (
    <>
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
        inSheet={full}
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
          paneArea={paneArea}
          listHost={listHost}
          onListChange={onListChange}
        />
      )}

      {/* 공공누리 1유형(출처표시) 의무. 문구가 아니라 자료(source_nm)에서 온다. */}
      {sources.length > 0 && <p className="dmap__src">출처: {sources.join(' · ')}</p>}
    </>
  );

  const noKey = (
    <p className="msg">
      지도 키가 설정되지 않았습니다. <code>python scripts/make_env_local.py</code>를 실행하면{' '}
      <code>.env</code>에서 만들어집니다.
    </p>
  );

  const body = (
    <DistrictMapBody
      appkey={appkey ?? ''}
      sigungu={sigungu}
      full={full}
      visible={visible}
      stage={stage}
      ready={features !== null}
      fileError={fileError}
      bounds={bounds}
      shown={shown}
      selected={selected}
      onMapPick={handleMapPick}
      below={below}
    />
  );

  if (full) {
    /*
      휴대폰 지도 가득(👤 2026-10-19 W4b 1번 「안 A」) — 제목·접기 단추 없이 칩 줄만(창업자) → 지도 칸(남은 높이 전부) → 판.
      ⓘ 판은 카카오 키가 없어도 선다(지도 칸에는 키 안내 글만) — 상권이 있는 구에서만(자료를 받기 전·없는 구·실패면 판 없음).
    */
    const sheetHead =
      picked === null ? (
        <>
          <span className="dsheet__title">
            {sigunguName ?? '고른 지역'} 상권 {shown.length}곳
          </span>
          <span className="dsheet__hint">지도를 누르면 그 자리 상권</span>
        </>
      ) : picked.length === 0 ? (
        <span className="dsheet__title">어느 상권 경계에도 들지 않는 위치입니다.</span>
      ) : (
        <span className="dsheet__title">누른 자리 ({picked.length}곳):</span>
      );
    /*
      판이 가득이면 덮인 칩 줄·지도 칸은 `inert`(W4b 보완 C2) — 눈에 안 보이는 단추(칩·화면 밖 표지)에 키보드·낭독기가 가지 않게.
    */
    const covered = stage === 'full';
    return (
      <section className="dmap dmap--full" hidden={!visible}>
        {headExtra && (
          <header className="dmap__head" inert={covered}>
            {headExtra}
          </header>
        )}
        {appkey ? body : <div className="dmap__canvas" inert={covered}>{noKey}</div>}
        {features !== null && !fileError && bounds !== null && (
          <DistrictSheet stage={stage} onStage={setStage} head={sheetHead}>
            {below}
          </DistrictSheet>
        )}
      </section>
    );
  }

  return (
    <section className="dmap" hidden={!visible}>
      <header className="dmap__head">
        <h2 className="dmap__title">{sigunguName ?? '고른 지역'} 상권 지도</h2>
        <button type="button" className="dmap__toggle" onClick={() => setOpen(!open)}>
          {open ? '지도 접기' : '지도 펴기'}
        </button>
        {headExtra}
      </header>

      {!open ? <p className="dmap__folded">지도를 접어 두었습니다.</p> : !appkey ? noKey : body}
    </section>
  );
}

/**
 * 키가 있을 때만 그려지는 알맹이 — 카카오 지도 그리기만 맡는다(자료·누른 자리는 바깥 `DistrictMap` 이 쥔다 · W4b).
 *
 * ⚠️ 컴포넌트를 굳이 나눈 이유: `useKakaoLoader`는 부르는 순간 카카오 스크립트를 내려받는다.
 *    키가 없을 때 그 훅을 부르면(훅은 조건부로 못 부른다) 빈 키로 요청이 나간다. 컴포넌트
 *    자체를 안 그리면 훅도 안 불린다 — CI·E2E 처럼 키가 없는 환경에서 바깥 요청이 0이다.
 * ⓘ 카드 꼴은 지도 칸 아래에 `below`(범례·누른 자리·건물 목록·출처)를 함께 그린다 — 지도가 서기 전(불러오는 중·실패)에는
 *   지금처럼 안내 한 줄뿐. 휴대폰 지도 가득은 지도 칸 하나만(안내도 그 칸 안) — `below` 는 판이 든다.
 * ⓘ `relayout`(카카오 공식: 지도 칸 크기를 바꾼 뒤엔 반드시 부른다 · 창 크기 변화는 스스로) — 숨겼다가 다시 보일 때
 *   (`visible` false→true) 한 번, 판 단계가 바뀌어 지도 칸 높이가 바뀐 뒤 한 번. 지도 객체는 `onCreate` 로 받는다(SDK 권장 꼴).
 */
function DistrictMapBody({
  appkey,
  sigungu,
  full,
  visible,
  stage,
  ready,
  fileError,
  bounds,
  shown,
  selected,
  onMapPick,
  below,
}: {
  appkey: string;
  sigungu: string;
  full: boolean;
  visible: boolean;
  stage: SheetStage;
  ready: boolean;
  fileError: boolean;
  bounds: Bounds | null;
  shown: DistrictFeature[];
  selected: BuildingHit | null;
  onMapPick: (lng: number, lat: number) => void;
  below: ReactNode;
}) {
  const [kakaoLoading, kakaoError] = useKakaoLoader({ appkey });
  /**
   * 지금 확대 수준. 이름표를 켤지 말지에만 쓴다.
   *
   * ⚠️ 이 값을 `<Map level>`로 되먹이지 **않는다.** 지도가 실제로 몇 배율인지는 카카오가
   *    쥐고 있고(사용자 휠·`setBounds`·`setLevel`이 다 바꾼다), 우리는 그 결과를
   *    `onZoomChanged`로 **받아 적기만** 한다. 되먹이면 우리가 적은 값이 다시 지도를
   *    밀어 사용자가 맞춘 배율과 다투게 된다.
   */
  const [level, setLevel] = useState(INITIAL_LEVEL);
  /** 카카오 지도 객체(`onCreate`) — `relayout` 을 부르려고만 쥔다. */
  const [map, setMap] = useState<kakao.maps.Map | null>(null);
  /*
    한 번이라도 보였나(W4b 보완 B1) — `<Map>` 은 보이는 칸에서만 태어나게 한다. 숨은(크기 0) 칸에서 태어나면 첫 범위(`setBounds`)를
    0×0 에 맞춰 엉뚱한 배율이 된다. 경계 파일·카카오 SDK 는 숨은 동안 받아도 된다(위 `useKakaoLoader` 는 그대로 부른다).
    ⛔ 한 번 참이 되면 다시 거짓으로 돌리지 않는다 — 숨길 때마다 지도를 치우면 확대·이동·누른 상권이 날아간다(§4-11).
  */
  const [everVisible, setEverVisible] = useState(visible);
  if (visible && !everVisible) setEverVisible(true);
  /*
    마지막으로 **제대로 잰**(칸 크기가 0 이 아닌) 중심·배율(W4b 보완 B2 · `onIdle` 이 적는다). 숨었다 다시 보일 때 `relayout` 만으로는
    중심이 어긋난다(카카오 데브톡 97194 꼴 — 크기 0 동안 중심 기준이 흐트러진다) → `relayout` 뒤 배율 → 중심 차례로 되돌린다.
    ⛔ 다른 구에서 잰 값은 쓰지 않는다.
  */
  const lastView = useRef<{ sigungu: string; center: kakao.maps.LatLng; level: number } | null>(null);
  /** 마지막으로 누른 자리(W4b 보완 B3) — 판이 올라와 지도 칸이 줄어든 뒤 그 자리가 화면 밖이면 그쪽으로 옮긴다. 구가 다르면 없는 것. */
  const lastClick = useRef<{ sigungu: string; at: kakao.maps.LatLng } | null>(null);
  const wasVisible = useRef(visible);
  useEffect(() => {
    const was = wasVisible.current;
    wasVisible.current = visible;
    if (!map || !visible || was) return;
    // 숨김(display: none · 크기 0)에서 다시 보였다 — 카카오는 칸 크기 변화를 스스로 모른다(공식 설명).
    map.relayout();
    const v = lastView.current;
    if (v && v.sigungu === sigungu) {
      map.setLevel(v.level);
      map.setCenter(v.center);
    }
  }, [map, visible, sigungu]);
  const lastStage = useRef(stage);
  useEffect(() => {
    if (lastStage.current === stage) return;
    lastStage.current = stage;
    // 판 단계가 바뀌어 지도 칸 높이가 바뀌었다(손을 뗀 단계에서 한 번 — 끄는 도중에는 칸 높이를 안 바꾼다).
    if (!map || !visible) return;
    map.relayout();
    /*
      누른 자리가 줄어든 칸 밖으로 밀려났으면 그쪽으로 옮긴다(B3 — 지도를 눌러 판이 반으로 올라오면 아래쪽을 누른 자리가 판 밑에 깔린다).
      ⛔ 안이면 아무것도 안 한다 — 단계가 바뀔 때마다 가운데로 끌고 가면 사용자가 옮긴 화면을 빼앗는다.
    */
    const c = lastClick.current;
    // 한 번 쓰고 비운다(재검사 🟠) — 안 비우면 사용자가 지도를 옮긴 뒤 판을 접었다 펼 때마다 옛 누른 자리로 끌려간다.
    lastClick.current = null;
    if (c && c.sigungu === sigungu && !map.getBounds().contain(c.at)) map.panTo(c.at);
  }, [map, stage, visible, sigungu]);
  /*
    지도 칸 크기가 바뀌면 relayout(👤 2026-10-23 D3 — PC 두 칸 지도 칸은 왼쪽 칸의 남은 높이를 채워 **창 높이를 따라** 크기가 바뀐다 ·
    창 크기가 그대로여도 왼쪽 칸 안(지역 칩 상자를 「바꾸기」로 펼침 · 역할·칩 줄)이 바뀌면 칸 크기가 바뀐다).
    ⓘ 공식 문서(https://apis.map.kakao.com/web/documentation/#Map_relayout — 2026-10-22 원문 확인): 「지도를 표시하는 HTML elemente의 크기를
      변경한 후에는 반드시 이 함수를 호출해야 한다. 단, window의 resize 이벤트에 대해서는 자동으로 호출한다.」 — 그래도 창 크기 변화에도 **직접**
      부른다(보완 3 · 화면 적대검증 🟡 — 자동 호출은 칸 크기를 CSS 가 다시 정한 **뒤**라는 보장이 문서에 없다 · 두 번 불러도 해가 없다).
    → 두 신호(칸 크기 감시 · 창 크기)를 **디바운스 하나**(150ms)로 묶어 마지막에 한 번만 부른다. 숨은(크기 0) 칸에서는 안 부른다 —
      0 ↔ 크기(숨김·다시 보임)는 위 `visible` effect 몫이다(그쪽이 relayout 뒤 배율·중심을 되돌린다 — 겹쳐 부르면 순서가 엇갈린다).
    ⓘ jsdom 에는 ResizeObserver 가 없다 — 그때는 창 크기 신호만 쓴다.
  */
  const canvasRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = canvasRef.current;
    if (!map || !el) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const soon = () => {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        if (el.clientWidth > 0 && el.clientHeight > 0) map.relayout();
      }, RELAYOUT_DEBOUNCE_MS);
    };
    let last = { w: el.clientWidth, h: el.clientHeight };
    const ro =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            const now = { w: el.clientWidth, h: el.clientHeight };
            const was = last;
            last = now;
            if (now.w === 0 || now.h === 0 || was.w === 0 || was.h === 0) return;
            if (now.w === was.w && now.h === was.h) return;
            soon();
          });
    ro?.observe(el);
    window.addEventListener('resize', soon);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', soon);
      if (timer !== null) clearTimeout(timer);
    };
  }, [map]);

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

  const note = kakaoError ? (
    <p className="msg msg--error">지도를 불러오지 못했습니다.</p>
  ) : fileError ? (
    <p className="msg msg--error">상권 경계 자료를 불러오지 못했습니다.</p>
  ) : !ready || kakaoLoading ? (
    <p className="msg">지도를 불러오는 중…</p>
  ) : bounds === null ? (
    // 상권이 0개인 구는 실제로 있다(대전은 5개 구에 37개가 흩어져 있다). 빈 지도를 띄우고
    // "왜 아무것도 없지?" 하게 두는 대신, 자료가 없다고 말한다.
    <p className="msg">이 구에는 아직 상권 경계 자료가 없습니다.</p>
  ) : null;
  /** 휴대폰 판이 가득이라 지도 칸이 덮였다 — `inert`(W4b 보완 C2 · 바깥 `DistrictMap` 의 칩 줄과 같이). */
  const covered = full && stage === 'full';
  if (note !== null || bounds === null)
    return full ? (
      <div className="dmap__canvas" inert={covered}>
        {note}
      </div>
    ) : (
      note
    );
  // 아직 한 번도 안 보였다 — 지도를 만들지 않는다(B1 · 위 `everVisible`). 숨은 칸이라 빈 자리여도 눈에 안 띈다.
  if (!everVisible) return full ? <div className="dmap__canvas" inert={covered} /> : null;

  /*
    화면에서 그린 지도 칸 폭(`onIdle` 이 잰 값)을 칸의 style 변수 `--dmap-w` 로 남긴다(결정 0039 W5 보완 F3) — PC 두 칸에서
    「상권 지도 넣기」를 켠 종이는 이 폭 그대로 가운데 놓는다(인쇄 묶음 `.app--printmap .dmap__canvas`). 종이 폭으로 늘리면 카카오가
    화면 폭만큼만 타일을 그려 둬 오른쪽이 빈 회색이 된다 — 인쇄 직전 relayout 뒤 비동기 타일은 믿지 않는다.
    ⓘ 카드 꼴만(휴대폰 지도 가득은 DOM 그대로) · 아직 못 쟀거나 다른 구에서 잰 값이면 안 적는다(0 은 `onIdle` 이 이미 버린다).
    높이도 같은 까닭으로 `--dmap-h` 에 남긴다(👤 2026-10-22 방법 나 R5 — 두 칸 지도 칸 높이가 창 높이를 따라 300px 보다 커졌다 ·
    종이는 그린 높이 그대로 · 인쇄 묶음 `.app--wide .entry .dmap__canvas`).
  */
  const canvasStyle =
    !full && view !== null && view.widthPx > 0
      ? ({ '--dmap-w': `${view.widthPx}px`, '--dmap-h': `${view.heightPx}px` } as CSSProperties)
      : undefined;
  const canvas = (
    <div className="dmap__canvas" inert={covered} style={canvasStyle} ref={canvasRef}>
      <Map
        center={{ lat: (bounds.swLat + bounds.neLat) / 2, lng: (bounds.swLng + bounds.neLng) / 2 }}
        style={{ width: '100%', height: '100%' }}
        level={INITIAL_LEVEL}
        onCreate={setMap}
        onClick={(_map, mouseEvent) => {
          lastClick.current = { sigungu, at: mouseEvent.latLng };
          onMapPick(mouseEvent.latLng.getLng(), mouseEvent.latLng.getLat());
        }}
        onZoomChanged={(m) => setLevel(m.getLevel())}
        onIdle={(m) => {
          // 지도가 멈출 때마다 지금 범위와 지도 칸 크기를 잰다(배율별 표를 박지 않는다).
          const node = m.getNode();
          // ⛔ 숨은(크기 0) 칸에서 잰 값은 버린다(B2) — 그 범위로 세면 상권이 전부 '화면 밖'이 되고, 되돌릴 중심도 틀린다.
          if (node.clientWidth === 0 || node.clientHeight === 0) return;
          lastView.current = { sigungu, center: m.getCenter(), level: m.getLevel() };
          const b = m.getBounds();
          const sw = b.getSouthWest();
          const ne = b.getNorthEast();
          setMeasured({
            sigungu,
            bounds: { swLat: sw.getLat(), swLng: sw.getLng(), neLat: ne.getLat(), neLng: ne.getLng() },
            widthPx: node.clientWidth,
            heightPx: node.clientHeight,
            level: m.getLevel(),
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
  );

  if (full) return canvas;
  return (
    <>
      {canvas}
      {below}
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
  inSheet = false,
  openId,
  onPick,
}: {
  picked: DistrictFeature[] | null;
  /**
   * 휴대폰 판 안이다(W4b 보완 A2) — 판 머리 줄(`.dsheet__title`)이 이미 「누른 자리 (N곳):」·「어느 상권 경계에도…」를 말하므로
   * 여기서는 그 머리를 다시 쓰지 않는다(같은 글 두 번 · 낭독기도 두 번 읽는다). 카드 꼴(넓은 화면·중개사)은 그대로.
   */
  inSheet?: boolean;
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
    // 판 안이면 머리 줄이 이 글 전부를 이미 말한다(A2).
    if (inSheet) return null;
    return (
      <p className="dmap__picked">
        <span className="dmap__picked-key">누른 자리:</span>
        어느 상권 경계에도 들지 않는 위치입니다.
      </p>
    );
  }

  return (
    <div className="dmap__picked">
      {!inSheet && <span className="dmap__picked-key">누른 자리 ({picked.length}곳):</span>}
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
