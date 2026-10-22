import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { AppFooter } from './components/AppFooter';
import { BrokerOfficeForm } from './components/BrokerOfficeForm';
import { BuildingSearch } from './components/BuildingSearch';
import { DistrictMap } from './components/DistrictMap';
import { ErrorBoundary } from './components/ErrorBoundary';
import { FloorStack } from './components/FloorStack';
import { FounderChips } from './components/FounderChips';
import { LeftRail } from './components/LeftRail';
import { LhNoticeSection } from './components/LhNoticeSection';
import { PrintButton } from './components/PrintButton';
import { PrintHeader } from './components/PrintHeader';
import { RecentPrinted } from './components/RecentPrinted';
import { RegionPicker } from './components/RegionPicker';
import { RegionStrip } from './components/RegionStrip';
import { RoleCards } from './components/RoleCards';
import { RolePicker } from './components/RolePicker';
import { ShareButton } from './components/ShareButton';
import { TabBar } from './components/TabBar';
import { TxFlowSection } from './components/TxFlowSection';
import { UnitPrintPicker } from './components/UnitPrintPicker';
import { FLOOR_STACK_VIEW, PARCEL_BUILDINGS_FN } from './lib/appConstants';
import { dongSuffix } from './lib/buildingHead';
import { isParcelBuildingList } from './lib/districtBuildings';
import {
  EMPTY_BUILDING_BODY,
  EMPTY_BUILDING_GO,
  EMPTY_BUILDING_TITLE,
  HISTORY_KEY,
  firstTab,
  historyMarkOf,
  tabAfterRoleChange,
  tabsFor,
  type AppTab,
} from './lib/appTabs';
import { EMPTY_MAP_PICK, type DistrictMapPick } from './lib/districtMapPick';
import { buildingFromFloorRows } from './lib/restoreBuilding';
import { FOUNDER_CHIP_ALL, type FounderChip } from './lib/founderChips';
import { entryBlockOrder, type EntryBlockKey, type ViewerRole } from './lib/sectionCards';
import { supabase } from './lib/supabase';
import { buildAppSearch, buildShareUrl, isSameSearch, parseAppUrl } from './lib/urlState';
import { pageTitle } from './lib/seo';
import { hubPlace, hubTitle } from './lib/hubHead';
import { SIDOS } from './lib/regions';
import type { AddrArea } from './lib/shortAddr';
import { useIsPhone } from './lib/useIsPhone';
import { useIsWide } from './lib/useIsWide';
import {
  BROWSE_ROLE,
  loadStoredRole,
  saveStoredRole,
  viewerRoleOf,
  type StoredRole,
} from './lib/viewerRoleStore';
import {
  clearRecentPrinted,
  loadRecentPrinted,
  recordPrinted,
  type RecentPrinted as RecentPrintedEntry,
} from './lib/recentPrintedStore';
import {
  clearBrokerOffice,
  loadBrokerOffice,
  saveBrokerOffice,
  type BrokerOffice,
} from './lib/brokerOfficeStore';
import { UNIT_PRINT_DEFAULT, type UnitPrintMode } from './lib/unitPrint';
import type { BuildingHit, FloorRow, ParcelBuilding } from './types';

export default function App() {
  /*
    주소에 담겨 온 것(구·건물)을 **첫 그림 한 번만** 읽는다. 그 뒤로는 화면 상태가
    주인이고 주소는 따라 적히기만 한다 — 양쪽이 서로를 고치려 들면 무한히 돌게 된다.
  */
  const [openedWith] = useState(() => parseAppUrl(window.location.search));

  const [selected, setSelected] = useState<BuildingHit | null>(null);
  const [sigungu, setSigungu] = useState<string | null>(openedWith.sigungu);
  const [sigunguName, setSigunguName] = useState<string | null>(null);

  /* 링크로 들어온 경우에만 참으로 시작한다(그냥 들어온 사람은 기다릴 것이 없다). */
  const [restoring, setRestoring] = useState(openedWith.bldId !== null);
  const [restoreFailed, setRestoreFailed] = useState(false);

  /*
    첫 화면에서 고른 역할(결정 0036 결정 18). **이 기기에만** 적어 두고 첫 그림에 한 번 읽는다.
    ⛔ 주소·의견함에는 싣지 않는다(위 주소 쓰기·아래 `feedbackContext` 에 넣지 말 것).
    저장값은 세 역할 또는 `둘러보기`(결정 0039 §7-4) — 화면이 쓰는 `viewerRole` 은 셋 또는 null(둘러보기 = 역할 없음).
    `storedRole === null` = 아직 안 물어봤다 → 입구 맨 위 큰 카드(결정 0039 Q3 · W3). 단 **건물 직행 링크(`bld`)로
    연 방문에는 그 방문 내내 안 띄운다**(첫 주소 한 번만 본다 · 저장도 안 해서 다음에 `/` 로 오면 뜬다).
  */
  const [storedRole, setStoredRole] = useState<StoredRole | null>(() => loadStoredRole());
  const viewerRole: ViewerRole | null = viewerRoleOf(storedRole);
  const showRoleCards = storedRole === null && openedWith.bldId === null;
  /*
    창업자 업종 칩(결정 0036 결정 18 ④⑤⑨). ⛔ **화면만** — 이 기기 저장·주소·의견함 어디에도 싣지
    않는다(새로고침 = 전체). 창업자에서 벗어나면 전체로 돌린다 — 다른 역할에 칩 효과가 남지 않게.
  */
  const [founderChip, setFounderChip] = useState<FounderChip>(FOUNDER_CHIP_ALL);
  const activeChip = viewerRole === '창업자' ? founderChip : FOUNDER_CHIP_ALL;
  /*
    지도에서 누른 상권·펼친 상권 목록(👤 2026-10-15 G1). 입구가 접히면(S1) 지도는 안 그려지는데, 다시 펼쳐 새로 그릴 때
    아까 누른 상권과 건물 목록이 그대로 서게 여기서 쥔다(다음 건물로 바로 넘어가게).
    ⛔ **화면만** — 이 기기 저장·주소·의견함에 싣지 않는다 · 구가 바뀌면 비운다(`handleSelectSigungu`·`handlePickRecent`).
  */
  const [mapPick, setMapPick] = useState<DistrictMapPick>(EMPTY_MAP_PICK);

  /*
    휴대폰 아래 탭(결정 0039 Q1 · W4a). `isPhone` = CSS 의 `@media screen and (max-width: 720px)` 와 같은 질의(인쇄 중엔 얼림 —
    `useIsPhone`). 넓은 화면은 탭이 없고 아래 S1 입구 접기가 지금 그대로 돈다 — `tab` 은 휴대폰에서만 뜻이 있다.
    ⛔ 탭은 주소·이 기기 저장·의견함에 안 싣는다(§4-1). 첫 탭 = `firstTab`(첫 그림 한 번만 · 건물 직행 = 건물 · 창업자 = 지도).
    `curTab` = 그 역할에게 없는 탭이면 찾기(중개사의 지도 · 중개사 아닌 사람의 뽑은 건물).
    `phoneRef`·`tabRef` = 첫 그림의 것을 쥐는 콜백(`handleSelectBuilding`)이 지금 값을 읽게 — 그리기와 상관없어 ref 다.
  */
  const isPhone = useIsPhone();
  /*
    PC 두 칸(결정 0039 Q5 · W5 · §4-13) — 1024px 이상에서 왼쪽 찾기(역할·지역·검색·지도) / 오른쪽 건물. `isWide` = CSS 의
    `@media screen and (min-width: 1024px)` 와 같은 질의(인쇄 중 얼림 — `useIsWide`). 721~1023 은 지금 한 열(S1 접기) 그대로.
    ⛔ 두 칸에서는 건물을 열어도 왼쪽(지도 포함)을 자동으로 접지 않는다(Q5 「건물을 바꿔도 지도가 사라지지 않음」) — 대신 손님이
       「왼쪽 칸 접기」로 56px 띠로 접는다(`leftCollapsed` · 👤 2026-10-21 「가」). 접어도 왼쪽은 CSS 로 숨기기만 한다(언마운트 0).
    `printMap` = 인쇄 단추 옆 「상권 지도 넣기」(§7-2 · 기본 끔). 둘 다 ⛔ 화면만 — 이 기기 저장·주소·의견함에 안 싣는다.
  */
  const isWide = useIsWide();
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [printMap, setPrintMap] = useState(false);
  /*
    한 열(1023 이하)에서 두 칸(1024+)으로 돌아오면 왼쪽 칸은 펼친 채 시작한다(W5 보완 F6 · 메인 판단) — 띠로 접은 채 줄었다 돌아오면
    지도가 숨은(`visible=false`) 칸에서 새로 태어나 `<Map>` 이 없고, 그 채로 「상권 지도 넣기」 종이를 뽑으면 지도 칸이 빈다.
    그리는 도중에 바로잡는다(React 공식 꼴 — effect 로 하면 접힌 채 한 번 그려진 뒤 다시 그린다).
  */
  const [prevWide, setPrevWide] = useState(isWide);
  if (prevWide !== isWide) {
    setPrevWide(isWide);
    if (isWide) setLeftCollapsed(false);
  }
  /*
    PC 두 칸 지역 줄 접기(W5 보완 D2 · 👤 2026-10-21 「가」) — 구를 고르면 칩 상자는 접고 「서울 강남구 · 바꾸기」 한 줄만.
    `regionFoldOpen` = 「바꾸기」로 칩 상자를 펼쳤나(구를 고르면 다시 접힌다). 칩 상자는 같은 하나 — CSS 로 숨기기만 한다.
    `regionFoldFocusRef` = 구를 고른 뒤 커서를 「바꾸기」로(누른 칩이 숨어 커서가 문서 맨 앞으로 날아가지 않게) — 그리기와 상관없어 ref.
  */
  const [regionFoldOpen, setRegionFoldOpen] = useState(false);
  const regionFoldFocusRef = useRef(false);
  const [tab, setTab] = useState<AppTab>(() => firstTab(viewerRole, openedWith.bldId !== null));
  const curTab = tabAfterRoleChange(tab, viewerRole);
  const phoneRef = useRef(isPhone);
  const tabRef = useRef<AppTab>(curTab);
  phoneRef.current = isPhone;
  tabRef.current = curTab;
  /* 탭마다 굴린 자리(탭을 옮겼다 돌아오면 그 자리로) · 뒤로가기로 돌아갈 탭(건물을 열기 직전 탭). */
  const tabScrollRef = useRef<Partial<Record<AppTab, number>>>({});
  const returnTabRef = useRef<AppTab>('find');
  const [tabSignal, setTabSignal] = useState(0);
  function pickTab(next: AppTab) {
    tabScrollRef.current[tabRef.current] = window.scrollY;
    setTab(next);
    setTabSignal((n) => n + 1);
    setRegionOpen(false); // 지도 탭 띠로 펼친 지역 고르개는 탭을 옮기면 닫는다(W4b)
  }
  useEffect(() => {
    if (tabSignal === 0) return;
    window.scrollTo(0, tabScrollRef.current[tabRef.current] ?? 0);
  }, [tabSignal]);
  /*
    휴대폰에서 사람이 건물을 열었다 → 건물 탭 + 뒤로가기 한 칸(👤 2026-10-17 「건물에서만 한 칸」). 지금 칸이 이미 건물 칸이면
    더 쌓지 않는다(여럿 열어도 늘 한 칸). 주소는 아래 주소 쓰기 effect 가 그 칸에 적는다(지금 규칙 그대로).
    ⛔ 넓은 화면은 쌓지 않는다 — 탭이 없어 뒤로가기가 화면 변화 없이 헛눌린다.
  */
  function openBuildingTab() {
    if (!phoneRef.current) return;
    if (tabRef.current !== 'building') returnTabRef.current = tabRef.current;
    tabScrollRef.current.building = 0;
    setTab('building');
    if (historyMarkOf(window.history.state) !== 'bld') {
      window.history.replaceState({ ...(window.history.state ?? {}), [HISTORY_KEY]: 'base' }, '');
      window.history.pushState({ [HISTORY_KEY]: 'bld' }, '', window.location.href);
    }
  }
  /* 뒤로·앞으로 — 건물 칸이면 건물 탭, 그 앞 칸이면 열기 직전 탭. 그 칸의 주소는 옛것이라 다시 적는다(`popSeq`). */
  const [popSeq, setPopSeq] = useState(0);
  useEffect(() => {
    function onPop(e: PopStateEvent) {
      // 넓은 화면은 탭이 없다 — 휴대폰에서 쌓인 칸이 남아 있어도 탭·주소 다시 쓰기는 안 한다(W4a 전과 같게 · 검사 🟡 F9).
      if (!phoneRef.current) return;
      const mark = historyMarkOf(e.state);
      if (mark === null) return;
      setTab(mark === 'bld' ? 'building' : returnTabRef.current);
      setPopSeq((n) => n + 1);
    }
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  /** 역할 고르기(큰 카드·작은 단추 줄 공용). null = 둘러보기·해제 — 지우지 않고 `둘러보기` 로 적는다(다시 안 묻는다). */
  function handlePickRole(role: ViewerRole | null) {
    const v: StoredRole = role ?? BROWSE_ROLE;
    setStoredRole(v);
    saveStoredRole(v);
    if (role !== '창업자') setFounderChip(FOUNDER_CHIP_ALL);
    setTab((t) => tabAfterRoleChange(t, role));
  }
  /*
    큰 카드에서 골랐다 — 카드가 사라지며 커서가 문서 맨 앞(body)으로 떨어지지 않게, 다음 그림에서 그 자리에 서는 작은
    단추 줄로 옮긴다(아래 effect · 검사 🟡 W3). `useRef` 인 이유 = 그리기와 상관없는 '다음 그림에서 할 일' 표시다.
  */
  const roleCardsFocusRef = useRef(false);
  function handlePickFromCards(role: ViewerRole | null) {
    roleCardsFocusRef.current = true;
    handlePickRole(role);
    // 휴대폰에서 큰 카드로 창업자를 고르면 지도 탭으로 — 카드 문구 「상권 지도·업종 분포를 먼저 보여 드립니다」와 0036 ④
    // (`firstTab` 과 같은 규칙 · 검사 🟠 F3). 건물이 열려 있거나 되살리는 중이면 탭을 안 옮긴다 · 다른 역할은 찾기 그대로.
    if (isPhone && role === '창업자' && selected === null && !restoring) setTab('map');
  }

  /*
    링크 복원(아래)이 끝나기 전에 사용자가 직접 무언가를 골랐는지 표시하는 깃발.
    ⚠️ `useState` 가 아니라 `useRef` 인 이유 — 이 값이 바뀐다고 화면을 다시 그릴 필요는
       없고, 복원 `.then` 콜백이 (리렌더 사이에도) **가장 최신 값**을 즉시 읽어야 한다.

    ⛔ **이 깃발을 세우는 곳은 아래 세 곳뿐이다** — "사용자가 실제로 고른 행동"만 해당한다.
       `handleSigunguNameResolved`(RegionPicker 가 서버 목록에서 구 이름을 알려주는 자동
       흐름)에는 절대 세우지 않는다 — 거긴 사용자 행동이 아니라 링크를 열자마자 저절로
       일어나는 일이라, 거기서 세우면 복원 자체가 "사용자가 이미 뭔가 했다"고 오판해
       통째로 죽는다.
  */
  const userActedRef = useRef(false);

  /*
    입구 접기(S1 · 👤 2026-10-14 승인 · 10-15 결정 둘). 건물을 연 동안에는 위 덩어리(소개 한 줄·역할 줄·지역 고르개·
    검색·지도)를 한 줄 바로 접어 건물이 첫 화면에 오게 한다. 건물이 없으면 지금 화면 그대로다.
    `entryOpen` = 건물을 연 채 손님이 바에서 위 칸을 펼쳤나 — **새 건물을 고르면 다시 접는다**
    (`handleSelectBuilding`·`handlePickRecent` → `foldAfterPick`).
    링크로 들어온 건물은 **되살리는 동안에도** 접힌 모양으로 선다 — 입구 전체·지도가 그려졌다 접히며 화면이 뛰고
    지도 스크립트까지 받기 시작하던 것을 막는다(검사 🟡 10-15). 되살리기에 실패하면 펼친 화면 그대로다.
    ⛔ 접어도 검색창·지역 고르개는 숨기기만 한다(다시 태어나면 검색어·결과가 날아가고, 링크로 연 건물의
       구 이름 되살리기도 끊긴다). 지도만 접힌 동안 그리지 않는다 — 그래서 종이에도 안 나온다(👤 10-15).
    `entryFocusRef` = 펼친 뒤 옮겨 갈 자리(바의 어느 단추로 펼쳤나) — 그리기와 상관없어 ref 다.
  */
  const [entryOpen, setEntryOpen] = useState(false);
  const entryRef = useRef<HTMLDivElement>(null);
  const barFirstRef = useRef<HTMLButtonElement>(null);
  const entryFocusRef = useRef<'search' | 'map' | 'role' | null>(null);
  // ⛔ PC 두 칸(1024+)에서는 S1 자동 접기를 끈다(W5 · Q5) — 왼쪽 칸은 손님이 띠로 접을 때만 숨는다(`leftCollapsed`).
  const folded = !isWide && (selected !== null || restoring) && !entryOpen;
  /*
    휴대폰 탭 꼴에서 입구가 숨는 때 = 찾기·지도 탭이 아닐 때(건물 유무와 상관없이 — S1 의 바·접기는 휴대폰에선 탭이 대신한다).
    지도는 **보이는 탭에서만** 그린다(접힌 동안 안 그리는 S1 규칙과 같은 결 · 보이는 칸에서 태어나 relayout 이 필요 없다):
    중개사 = 찾기 탭(지도 탭 자리가 「뽑은 건물」) · 나머지 = 지도 탭. 지역 고르개는 찾기·지도 두 탭에 같은 하나로 보인다(CSS).
  */
  const entryHidden = isPhone ? curTab !== 'find' && curTab !== 'map' : folded;
  // PC 두 칸은 왼쪽 칸이 펼쳐 있으면 늘 보인다 · 띠로 접으면 숨기만 한다(아래 `mapMounted` 가 그려 둔 지도를 남긴다 · W5).
  const showMap = isPhone ? curTab === (viewerRole === '중개사' ? 'find' : 'map') : isWide ? !leftCollapsed : !folded;
  // 머리(사이트 제목 줄)는 두 칸에서도 건물을 연 동안 작게 — 1280 화면 지금 모양 그대로(제목 작게 · 소개 한 줄 없음).
  const headFolded = isPhone || isWide ? selected !== null || restoring : folded;
  /*
    휴대폰 지도 가득(👤 2026-10-19 W4b 1번 「안 A」) — 중개사가 아닌 사람이 구를 고른 채 「지도」 탭에 있을 때.
    `mapLayout` = 지도 꼴(휴대폰 비중개사는 **탭과 상관없이** full — 탭을 옮겨도 같은 노드가 숨기만 하게 · 중개사·넓은 화면은 카드).
    `regionOpen` = 띠 「서울 강남구 ▾」로 지역 고르개를 펼쳤나(구를 고르거나 탭을 옮기면 닫힌다).
  */
  const mapLayout: 'card' | 'full' = isPhone && viewerRole !== '중개사' ? 'full' : 'card';
  const mapFull = mapLayout === 'full' && sigungu !== null && curTab === 'map';
  const [regionOpen, setRegionOpen] = useState(false);
  /*
    띠로 펼친 지역 고르개에서 구를 고르면 고르개가 닫혀(숨어) 커서가 갈 곳을 잃는다 → 띠 단추로 돌려 둔다(W4b 보완 C2).
    ⓘ 화면은 굴리지 않는다(`preventScroll`) · 띠가 없어진 경우(구 해제)는 아무것도 안 한다.
  */
  const stripFocusRef = useRef(false);
  useEffect(() => {
    if (regionOpen || !stripFocusRef.current) return;
    stripFocusRef.current = false;
    document.querySelector<HTMLButtonElement>('.rstrip__btn')?.focus({ preventScroll: true });
  }, [regionOpen]);
  // PC 두 칸에서 구를 고른 뒤 — 칩 상자가 접혀 숨으니 커서를 지역 한 줄의 「바꾸기」로(D2 · 위 C2 와 같은 꼴).
  useEffect(() => {
    if (!regionFoldFocusRef.current) return;
    regionFoldFocusRef.current = false;
    document.querySelector<HTMLButtonElement>('.regionfold__btn')?.focus({ preventScroll: true });
  }, [sigungu, regionFoldOpen]);
  /*
    지도 그려 두기(W4b · 결정 0039 §4-11) — 휴대폰에서 한 번 보인 지도는 탭을 옮겨도 언마운트하지 않고 `hidden` 으로 숨긴다
    (돌아오면 `relayout` 한 번 → 확대·이동·누른 상권 그대로). 첫 방문(그 지도 탭에 아직 안 간 사람)은 지금처럼 안 그린다
    (카카오·상권 파일을 안 받는다). ⛔ 구·꼴이 바뀌면 다시 보일 때 새로 그린다 — 숨은(크기 0) 칸에서 태어나면 첫 범위가 틀린다.
    넓은 화면(721~1023)은 지금 그대로(접히면 안 그림 — S1). PC 두 칸(1024+)은 휴대폰과 같은 길 — 왼쪽 칸을 띠로 접어도 그려 둔
    지도는 남기고 숨기기만 한다 → 펼치면 relayout 한 번(👤 2026-10-21 W5 「가」 · W4b 배선 재사용).
    ⓘ 꼴 칸에 `cols`(두 칸)를 따로 둔다 — 1023↔1024 를 넘나들면 지도 칸 폭이 크게 바뀌므로 새 칸 크기에서 다시 태어나게.
  */
  const mapKey = `map:${sigungu ?? '__none__'}:${isPhone ? 'phone' : isWide ? 'cols' : 'wide'}:${mapLayout}`;
  const [mapSeenKey, setMapSeenKey] = useState<string | null>(null);
  if ((isPhone || isWide) && showMap && sigungu !== null && mapSeenKey !== mapKey) setMapSeenKey(mapKey);
  const mapMounted = showMap || ((isPhone || isWide) && mapSeenKey === mapKey);
  /*
    입구 카드 둘(LH·단가 흐름)을 세울 때 — 구를 골랐고 되살리는 중이 아니고, 넓은 화면은 건물을 안 열었을 때만(지금 그대로).
    휴대폰은 건물을 열어 둔 채여도 찾기 탭에 선다(보던 건물이 남는 탭 꼴이라 · 검사 🟠 F2) — 다른 탭에선 CSS 가 숨기고,
    종이(건물 있음)에서는 인쇄 감춤 `.app--tabs.app--bld .app__main > .card` 가 빼서 종이는 건물 한 장 그대로다.
  */
  const showEntryCards = sigungu !== null && !restoring && (selected === null || isPhone);
  /*
    PC 두 칸에서 첫 방문 큰 카드를 오른쪽 빈 칸에 세우나(👤 2026-10-22 L6) — 건물이 없을 때(되살리는 중 아님)만.
    ⓘ 건물 직행 링크로 온 방문은 `showRoleCards` 가 이미 거짓이라 여기도 거짓(W3 ① 그대로).
  */
  const roleCardsRight = isWide && showRoleCards && selected === null && !restoring;
  /*
    큰 카드에서 고른 뒤(위 `handlePickFromCards`) — 역할을 골랐으면 눌린 단추, 「그냥 둘러보기」면 첫 단추에 커서.
    ⓘ 화면은 굴리지 않는다(`preventScroll`) — 작은 줄은 카드가 있던 바로 그 자리라 이미 화면 안이다.
  */
  useEffect(() => {
    if (!roleCardsFocusRef.current) return;
    roleCardsFocusRef.current = false;
    // 휴대폰은 작은 줄이 「더보기」 탭(숨음)에 있다 — 지금 고른 탭 단추에 커서(body 로 떨어지지 않게 · 검사 🟡 F4).
    if (phoneRef.current) {
      document.querySelector<HTMLButtonElement>('.tabbar__btn[aria-current="page"]')?.focus({ preventScroll: true });
      return;
    }
    const row = entryRef.current?.querySelector('.role');
    (
      row?.querySelector<HTMLButtonElement>('.role__chip[aria-pressed="true"]') ??
      row?.querySelector<HTMLButtonElement>('.role__chip')
    )?.focus({ preventScroll: true });
  }, [storedRole]);
  function openEntry(target: 'search' | 'map' | 'role') {
    entryFocusRef.current = target;
    setEntryOpen(true);
  }
  /*
    층별 머리의 「○○구 다른 건물 찾기」 링크(결정 0042 H5)의 보통 누름 — 바의 「다른 건물 찾기」와 같은 일(보던 건물은 그대로):
    넓은 화면 = 위 칸을 펼치고 입력칸에 커서(이미 펼쳐 있으면 커서만) · 휴대폰 = 찾기 탭.
  */
  function handleFindInSigungu() {
    if (isPhone) {
      pickTab('find');
      return;
    }
    // PC 두 칸 — 왼쪽 칸이 늘 서 있다(접혀 있으면 펼친 뒤) · 입력칸에 커서.
    if (isWide) {
      if (leftCollapsed) expandLeft('search');
      else entryRef.current?.querySelector<HTMLInputElement>('.search__input')?.focus();
      return;
    }
    if (entryOpen) entryRef.current?.querySelector<HTMLInputElement>('.search__input')?.focus();
    else openEntry('search');
  }
  /*
    PC 두 칸 왼쪽 칸 접기·펼치기(W5 · 👤 2026-10-21 「가 · 세로 띠 56px」). 커서가 숨는 칸에 남아 문서 맨 앞으로 날아가지 않게
    접으면 띠의 펼치기 단추로, 펼치면 누른 단추가 가리킨 자리(접기 단추 · 지도 · 입력칸)로 옮긴다 — 그리기와 상관없어 ref 다.
  */
  const railExpandRef = useRef<HTMLButtonElement>(null);
  const leftFocusRef = useRef<'rail' | 'fold' | 'map' | 'search' | null>(null);
  function collapseLeft() {
    leftFocusRef.current = 'rail';
    setLeftCollapsed(true);
  }
  function expandLeft(target: 'fold' | 'map' | 'search') {
    leftFocusRef.current = target;
    setLeftCollapsed(false);
  }
  useEffect(() => {
    const target = leftFocusRef.current;
    if (target === null) return;
    leftFocusRef.current = null;
    if (target === 'rail') {
      railExpandRef.current?.focus({ preventScroll: true });
      return;
    }
    const root = entryRef.current;
    if (target === 'search') {
      root?.querySelector<HTMLInputElement>('.search__input')?.focus();
      return;
    }
    if (target === 'map') {
      const map = root?.querySelector('.dmap');
      map?.querySelector<HTMLButtonElement>('.dmap__toggle')?.focus({ preventScroll: true });
      // 왼쪽 칸 안에서만 굴린다(칸이 화면에 붙어 있다) · jsdom 에는 scrollIntoView 가 없다.
      map?.scrollIntoView?.({ block: 'nearest' });
      return;
    }
    root?.querySelector<HTMLButtonElement>('.entry__fold')?.focus({ preventScroll: true });
  }, [leftCollapsed]);
  useEffect(() => {
    const target = entryFocusRef.current;
    const root = entryRef.current;
    if (!entryOpen || target === null || root === null) return;
    entryFocusRef.current = null;
    if (target === 'search') {
      // 입력칸에 커서 — focus 가 그 자리로 화면도 옮긴다.
      root.querySelector<HTMLInputElement>('.search__input')?.focus();
      return;
    }
    // 키보드·낭독기 손님도 그 자리에 서게 — 지도는 머리의 접기 단추, 역할은 첫 역할 단추에 커서(검사 🟡 10-15).
    // 아직 안 물어봐 큰 카드가 서 있으면(작은 단추 줄은 숨음) 첫 카드 단추에(결정 0039 W3).
    // ⓘ 화면은 덩어리 맨 위로 옮긴다(커서 자리로 옮기면 지도 제목이 위로 잘린다). jsdom 에는 scrollIntoView 가 없다.
    const block = root.querySelector(target === 'map' ? '.dmap' : '.rolecards, .role');
    block
      ?.querySelector<HTMLButtonElement>(target === 'map' ? '.dmap__toggle' : '.rolecards__card, .role__chip')
      ?.focus({ preventScroll: true });
    block?.scrollIntoView?.({ block: 'start' });
  }, [entryOpen]);

  /*
    접힌 뒤 — 커서를 바의 첫 단추로(고른 결과 줄·'위 칸 접기' 단추가 숨거나 사라져 커서가 문서 맨 앞으로 날아가지
    않게). 건물을 **고른** 뒤에는 화면도 맨 위로 — 검색 결과를 내려 고르면 위 칸이 접히며 건물 이름이 화면 위로
    지나가 버린다(검사 🟠 10-15). 링크 되살리기는 여기를 거치지 않는다(처음부터 맨 위다).
  */
  const [foldSignal, setFoldSignal] = useState<{ seq: number; toTop: boolean }>({ seq: 0, toTop: false });
  function foldEntry(toTop: boolean) {
    setEntryOpen(false);
    setFoldSignal((p) => ({ seq: p.seq + 1, toTop }));
  }
  useEffect(() => {
    if (foldSignal.seq === 0) return;
    if (foldSignal.toTop) {
      const root = document.scrollingElement;
      if (root) root.scrollTop = 0;
    }
    // 휴대폰은 바 대신 탭 막대 — 고른 탭(건물)에 커서(고른 결과 줄이 숨어 커서가 문서 맨 앞으로 날아가지 않게).
    (barFirstRef.current ?? document.querySelector<HTMLButtonElement>('.tabbar__btn[aria-current="page"]'))?.focus({
      preventScroll: true,
    });
  }, [foldSignal]);

  // 구가 바뀌면 이전 구의 선택 건물은 더는 맞지 않는다(스택이 다른 구 건물을 계속
  // 그리면 안 된다). 검색어·검색 결과는 BuildingSearch 쪽 key로 함께 비운다(아래).
  function handleSelectSigungu(code: string | null, name?: string | null) {
    userActedRef.current = true;
    setRestoreFailed(false);
    setSigungu(code);
    setSigunguName(code ? (name ?? null) : null);
    setMapPick(EMPTY_MAP_PICK);
    setSelected(null);
    if (regionOpen) stripFocusRef.current = true; // 닫은 뒤 커서를 띠 단추로(위 effect · C2)
    setRegionOpen(false); // 띠로 펼쳤으면 구를 고른 뒤 닫는다(다른 구를 골라도 · W4b)
    // PC 두 칸 — 구를 고르면 칩 상자를 다시 접고 커서는 「바꾸기」로(D2). 구를 풀면 한 줄이 없어져 칩 상자 그대로다.
    if (isWide && code !== null) regionFoldFocusRef.current = true;
    setRegionFoldOpen(false);
  }

  // 검색으로 건물을 고르면 "링크로 들어왔다가 실패한 상태"는 끝난 것이다.
  const handleSelectBuilding = useCallback((hit: BuildingHit) => {
    userActedRef.current = true;
    setRestoreFailed(false);
    setSelected(hit);
    openBuildingTab(); // 휴대폰만 — 지금 폭·탭은 ref 로 읽는다
    foldEntry(true); // 첫 그림의 것을 쥐어도 된다 — setState·ref 만 쓴다
  }, []);

  /*
    중개사 「최근 뽑은 건물」(결정 0036 결정 18 ⑥⑩). 목록의 주인은 **이 기기 저장소**이고 이 상태는
    그것을 비춘다 — 적거나 지운 뒤 저장소를 다시 읽은 값을 받는다(막힌 창이면 빈 목록).
    ⛔ 적는 곳은 인쇄 단추 하나(`handleBeforePrint`) · 역할 = 중개사일 때만 적고 보인다(다른 역할
       손님의 기기에 기록을 남기지 않는다) · ⛔ 주소·의견함(`feedbackContext`)에 싣지 않는다.
  */
  const [recentPrinted, setRecentPrinted] = useState<RecentPrintedEntry[]>(() => loadRecentPrinted());
  function handleBeforePrint() {
    if (viewerRole === '중개사' && selected) setRecentPrinted(recordPrinted(selected));
  }
  /*
    중개사 「종이에 찍을 내 사무소 정보」(결정 0036 결정 3 · 물결 1-C2). 주인은 이 상태이고 **이 기기 저장소에는
    덤으로** 적는다 — 저장이 막힌 창에서도 입력·인쇄는 그대로 된다(기억만 못 한다).
    ⛔ 종이 머리에 찍는 것은 역할 = 중개사일 때만(다른 역할로 바꾸면 저장은 그대로 두고 종이에만 안 찍힌다) ·
       ⛔ 주소·의견함(`feedbackContext`)에 싣지 않는다.
  */
  const [office, setOffice] = useState<BrokerOffice>(() => loadBrokerOffice());
  function handleOfficeChange(next: BrokerOffice) {
    setOffice(next);
    saveBrokerOffice(next);
  }

  /*
    호실 구성표 고르기(결정 0036 결정 8 · 물결 1-C2) — 누구에게나. ⛔ 저장하지 않는다 · 기본값 = 「지하~3층」
    (👤 2026-10-11 · 결정 8 원문) · **건물이 바뀔 때마다 기본값으로**(다른 건물에 갔다 돌아와도 옛 고르기가 살아나지
    않는다). 고른 값을 그 건물 번호에 묶어 두고, 건물이 바뀌면 그리는 도중에 기본값으로 다시 세운다(React 공식
    꼴 — effect 로 지우면 새 건물에서 옛 고르기로 한 번 그려져 요청이 샌다).
    `opened` = 손님이 직접 고른 횟수 — 그때만 층 목록 카드를 펼친다(기본값은 카드를 강제로 펼치지 않는다).
  */
  const [unitPick, setUnitPick] = useState<{ bldId: string | null; mode: UnitPrintMode; opened: number }>({
    bldId: null,
    mode: UNIT_PRINT_DEFAULT,
    opened: 0,
  });
  if (selected !== null && unitPick.bldId !== selected.bld_id) {
    setUnitPick({ bldId: selected.bld_id, mode: UNIT_PRINT_DEFAULT, opened: 0 });
  }
  const unitPrintMode: UnitPrintMode =
    selected !== null && unitPick.bldId === selected.bld_id ? unitPick.mode : UNIT_PRINT_DEFAULT;
  /* 이 건물에서 호 목록이 있는 층 수(층별 화면이 요약을 받은 뒤 알려 준다) — 0개거나 아직 모르면 고르기 줄을 숨긴다. */
  const [unitListed, setUnitListed] = useState<{ bldId: string; count: number } | null>(null);
  const handleUnitListedCount = useCallback((bldId: string, count: number) => {
    setUnitListed({ bldId, count });
  }, []);
  const showUnitPicker =
    selected !== null && unitListed !== null && unitListed.bldId === selected.bld_id && unitListed.count > 0;

  /*
    목록에서 고르기 — 그 건물 층별 화면으로 간다. 다른 구 건물이면 구도 그 구로(구 코드 = 저장해 둔
    건물의 **pnu 앞 5자리** · 이름은 지역 고르개가 서버 목록에서 채운다 — `handleSigunguNameResolved`).
    ⓘ 구를 바꾸면 검색창은 key 로 새로 선다(다른 구의 검색 결과를 남기지 않는 기존 규칙 그대로).
  */
  function handlePickRecent(item: RecentPrintedEntry) {
    userActedRef.current = true;
    setRestoreFailed(false);
    const code = item.pnu.slice(0, 5);
    if (code !== sigungu) {
      setSigungu(code);
      setSigunguName(null);
      setMapPick(EMPTY_MAP_PICK);
    }
    setSelected({ ...item });
    openBuildingTab();
    foldEntry(true);
  }

  /*
    링크로 들어온 사람은 구 코드만 갖고 있어 **구 이름을 모른다.** 이름이 없어도
    화면은 안 깨지지만("고른 지역 상권 지도"로 적힌다) 링크를 받은 사람이 보는 첫
    화면이라 아쉽다. 지역 고르개는 서버 목록을 이미 갖고 있어 이름을 알므로 그것만
    받아 온다. 이미 아는 경우(직접 눌러서 고른 경우)에는 아무 일도 하지 않는다.
  */
  const handleSigunguNameResolved = useCallback((name: string) => {
    setSigunguName((prev) => (prev === null ? name : prev));
  }, []);

  /*
    ── 링크로 들어온 건물 되살리기 ──────────────────────────────────────────
    검색을 거치지 않았으므로 건물 정보(이름·주소·좌표·층 범위)가 없다. 층 목록
    (v_floor_stack)이 그 값을 이미 갖고 있어 새 서버 함수 없이 접어서 만든다
    (src/lib/restoreBuilding.ts — 층수 세는 규칙은 검색 서버와 같다).

    ⚠️ 층이 한 줄도 없는 건물이 239동 실재한다. 그런 건물은 되살릴 수 없으므로
       없는 것을 지어내지 않고 정직하게 안내한다.
  */
  useEffect(() => {
    const bldId = openedWith.bldId;
    if (!bldId) return;

    let cancelled = false;
    supabase
      .from(FLOOR_STACK_VIEW)
      .select('*')
      .eq('bld_id', bldId)
      .then(({ data, error }) => {
        if (cancelled) return;
        // ⛔ 이 사이 사용자가 검색으로 다른 건물을 고르거나 구를 바꿨으면, 뒤늦게 도착한
        //    복원 결과로 그 선택을 덮어쓰면 안 된다(`cancelled` 로는 못 막는다 — `openedWith`
        //    가 첫 그림 뒤 절대 안 바뀌어 이 useEffect 의 cleanup 은 언마운트에만 돈다).
        //    받아 온 것은 통째로 버린다 — 되살리기가 성공했든 실패했든 사용자가 지금 보고
        //    있는 화면과는 아무 상관이 없다(실패 안내를 띄우면 오히려 남의 화면을 덮는다).
        //    다만 `setRestoring(false)` 만은 꼭 해 준다 — 빠뜨리면 "불러오는 중" 안내가
        //    남거나(사용자는 이미 다른 걸 보고 있는데) 주소 쓰기 useEffect 가 계속 막힌다.
        if (userActedRef.current) {
          setRestoring(false);
          return;
        }
        if (error) {
          console.error('링크의 건물 조회 실패', error);
        }
        const hit = error ? null : buildingFromFloorRows((data ?? []) as FloorRow[]);
        if (hit) setSelected(hit);
        else setRestoreFailed(true);
        setRestoring(false);
      });

    return () => {
      cancelled = true;
    };
  }, [openedWith.bldId]);

  /*
    ── 지금 보고 있는 것을 주소에 적기 ──────────────────────────────────────
    ⛔ 되살리는 **중에는 절대 적지 않는다.** 그때 selected 는 아직 null 이라, 적으면
       주소에서 건물이 지워진다 — 링크를 열자마자 그 링크가 스스로 사라지는 셈이다.
       이 한 줄이 이 기능 전체에서 가장 조용히 깨지는 자리다.
    ⛔ 되살리기에 **실패했을 때도 지우지 않는다.** 서버가 잠깐 흔들린 것일 수 있는데,
       주소를 지워 버리면 새로고침으로 다시 시도할 길까지 없어진다.

    pushState 가 아니라 replaceState 를 쓴다 — 검색할 때마다 뒤로가기 단계가 쌓이면
    앱을 빠져나가려고 뒤로가기를 여러 번 눌러야 한다. 여기서 필요한 것은 뒤로가기가
    아니라 **새로고침 복원·즐겨찾기·보내기**다.
  */
  useEffect(() => {
    if (restoring) return;
    if (restoreFailed && selected === null) return;

    const next = { sigungu, bldId: selected?.bld_id ?? null };
    if (isSameSearch(window.location.search, next)) return;
    // 칸의 표식(휴대폰 뒤로가기 한 칸 · `openBuildingTab`)은 그대로 둔다 — 넓은 화면은 표식이 없어 지금처럼 null 이다.
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${buildAppSearch(next)}`);
  }, [sigungu, selected, restoring, restoreFailed, popSeq]);

  /*
    탭 제목 — 건물을 고르면 그 이름, 풀면 첫 화면 제목으로 돌아온다(정본 = `src/lib/seo.ts`).
    즐겨찾기·탭 여러 개·방문 기록에서 어느 건물인지 보이게 한다.
    ⛔ 되살리는 **중에는 건드리지 않는다** — 그때 selected 는 아직 null 이라, 적으면 서버 조각(결정 0037)이
       첫 HTML 에 넣어 둔 건물 제목을 첫 화면 제목으로 잠깐 덮는다. 꼴은 서버와 같다(`pageTitle`).
  */
  /*
    같은 땅의 동 목록(결정 0042 H2·H5) — 고른 건물의 땅에 동이 여럿일 때만 한 번 받는다(같은 땅 동끼리 옮겨 다녀도 다시 안 묻는다).
    쓰는 곳 둘: 탭 제목의 동 구분(첫 HTML 제목과 같은 `dongSuffix` — 구글은 화면이 그린 제목을 보니 갈리면 안 된다)과
    층별 머리의 「같은 땅 다른 동」 링크 줄. 실패·모양 틀림이면 없음(구분·줄 없이 지금 화면 그대로).
  */
  const [parcelDongs, setParcelDongs] = useState<{ pnu: string; list: ParcelBuilding[] } | null>(null);
  const dongPnu = selected !== null && (selected.bld_cnt_in_pnu ?? 1) > 1 ? selected.pnu : null;
  useEffect(() => {
    if (dongPnu === null) return;
    let cancelled = false;
    supabase.rpc(PARCEL_BUILDINGS_FN, { p_pnu: dongPnu }).then(({ data, error }) => {
      if (cancelled) return;
      if (error || !isParcelBuildingList(data)) {
        if (error) console.error('같은 땅 동 목록 조회 실패', error);
        return;
      }
      setParcelDongs({ pnu: dongPnu, list: data });
    });
    return () => {
      cancelled = true;
    };
  }, [dongPnu]);
  const dongs = dongPnu !== null && parcelDongs?.pnu === dongPnu ? parcelDongs.list : null;
  // N = 고른 건물의 `bld_cnt_in_pnu`(뷰와 같은 수 — 첫 HTML 은 뷰 행의 값 · 결정 0042 보완 F1).
  const dong = selected && dongs ? dongSuffix(selected.bld_id, dongs, selected.bld_cnt_in_pnu) : null;

  /*
    구만 고른 동안(건물 없음)은 구 입구 허브 첫 HTML(결정 0043)과 같은 제목 — 같은 함수(`hubHead.ts` 의 `hubPlace`·`hubTitle`).
    구 이름을 아직 모르면(링크로 들어와 지역 고르개가 이름을 채우기 전) 건드리지 않는다 — 서버가 넣은 허브 제목을 덮지 않게.
  */
  const hubPlaceName = selected === null && sigungu !== null && sigunguName
    ? hubPlace({ sido_code: sigungu.slice(0, 2), sigungu_nm: sigunguName })
    : null;
  useEffect(() => {
    if (restoring) return;
    if (selected === null && sigungu !== null) {
      if (hubPlaceName) document.title = hubTitle(hubPlaceName);
      return;
    }
    document.title = pageTitle(selected?.bld_nm, selected?.road_addr, dong);
  }, [selected, sigungu, hubPlaceName, dong, restoring]);

  /*
    지금 화면의 온전한 주소. **링크 복사 버튼과 종이 머리글이 같은 값을 쓴다** — 두 곳에서
    따로 만들면 언젠가 한쪽만 고쳐져 "복사한 주소"와 "종이에 적힌 주소"가 갈린다.
    건물을 안 골랐으면 첫 화면 주소가 되는데, 쓰는 자리가 둘 다 `selected` 안이라 무해하다.
  */
  const shareUrl = buildShareUrl(window.location.origin, window.location.pathname, {
    sigungu,
    bldId: selected?.bld_id ?? null,
  });

  /*
    PC 두 칸 왼쪽 칸의 고른 시·구(👤 2026-10-22 왼쪽 칸 다듬기 「가」 L2·L5) — 목록 주소를 길 이름부터 적고 검색칸 안내 글을 짧게.
    두 칸이 아니면 null(휴대폰·한 열 변화 0) · 두 칸이면 구를 아직 몰라도 빈 이름으로 준다(주소는 그대로 · 안내 글만 짧게).
  */
  const paneArea: AddrArea | null = isWide
    ? { sido: SIDOS.find((s) => s.code === sigungu?.slice(0, 2))?.fullName ?? '', sigungu: sigunguName ?? '' }
    : null;

  /*
    입구 두 덩어리 — 그리는 차례는 아래 `entryBlockOrder` 가 정한다(층별 카드의 `sectionOrder` 와 같은 꼴).
  */
  const entryBlocks: Record<EntryBlockKey, ReactNode> = {
    search: (
      /*
        구가 바뀔 때마다 BuildingSearch를 key로 통째로 새로 그린다. 검색어·검색 결과·
        안내창은 전부 그 컴포넌트 내부 상태라 밖에서 하나씩 비울 수 없고, 다른 구에서
        찾은 결과가 화면에 남아 있으면 안 되기 때문이다(2026-08-13 사장님 결정).

        onSearchStart 로는 (구를 바꾸지 않고) 같은 구 안에서 새로 검색했을 때 이전
        선택을 비운다 — 안 그러면 새 검색을 해도 아래 스택이 **이전에 고른 건물**
        그대로 남는다. "결과가 없습니다"가 뜬 상태에서도 옛 건물 스택이 그대로
        보였다(2026-08-08 적대검증 라이브 재현).
      */
      <BuildingSearch
        key={sigungu ?? '__no_region__'}
        onSelect={handleSelectBuilding}
        onSearchStart={() => {
          userActedRef.current = true;
          // 휴대폰 탭 꼴은 보던 건물을 남긴다 — 「건물」 탭으로 돌아가면 그대로(👤 확정 결정 0039 §7-1).
          // PC 두 칸도 같은 규칙(👤 2026-10-21 W5 보완 D1 「가 · 건물은 그대로 남김」) — 오른쪽 건물은 결과를 눌러 고를 때 바뀐다.
          // ⓘ 한 열(721~1023)은 지금 그대로 비운다(2026-08-08 「새 검색에도 옛 건물」 회귀 막이 — 위 주석).
          if (!isPhone && !isWide) setSelected(null);
        }}
        selectedBldId={selected?.bld_id ?? null}
        sigungu={sigungu}
        sigunguName={sigunguName}
        showOwnership={viewerRole === '중개사'}
        paneArea={paneArea}
        /*
          중개사만 — 검색 입력칸 바로 아래·결과 목록 위(👤 결정 0036 결정 18 ⑩ "검색창 바로 아래").
          ⓘ 목록·지우기 상태는 App 이 쥔다 — 구가 바뀌어 검색창이 key 로 다시 태어나도 목록은 그대로다.
        */
        belowInput={
          // 휴대폰은 검색 아래가 아니라 「뽑은 건물」 탭에(👤 2026-10-17 W4a 2번 「가」).
          viewerRole === '중개사' && !isPhone ? (
            <RecentPrinted
              items={recentPrinted}
              onPick={handlePickRecent}
              onClear={() => setRecentPrinted(clearRecentPrinted())}
            />
          ) : null
        }
      />
    ),
    map: (
      /*
        상권 지도(결정 0010). 구를 고르면 **건물을 안 골랐어도** 보인다 — 지도는 이 서비스의
        첫인상이라 탭이나 건물 선택 뒤에 숨기면 있는 줄도 모른다. 구를 안 골랐을 때는
        컴포넌트가 스스로 아무것도 그리지 않는다(그릴 범위가 정해지지 않았으므로).
      */
      /*
        ⚠️ key 를 구 코드로 주는 이유 — 그물(ErrorBoundary)은 한 번 오류를 받으면 스스로
           풀리지 않는다. key 가 없으면 A구 지도에서 한 번 터진 뒤 B구로 옮겨도 **계속**
           오류 안내만 보인다. 구가 바뀌면 그물을 새로 쳐서 다시 그려 보게 한다.
        지도는 바깥 지도 SDK 를 태우는 자리라 우리 코드만으로는 터질 자리를 다 못 셈한다.
        ⛔ 입구가 접힌 동안(건물을 연 채)에는 그리지 않는다 — 종이에도 안 나온다(👤 2026-10-15). 펼치면 새로 그린다.
      */
      !mapMounted ? null : (
        <ErrorBoundary
          // 휴대폰 ↔ 넓은 화면이 바뀌면(돌리기) 새 칸 크기에서 다시 태어나게 꼴도 넣는다(W4a) · 지도 꼴(card·full)도(W4b).
          key={mapKey}
          area="상권 지도"
          context={{ sigungu, sigungu_nm: sigunguName }}
        >
          <DistrictMap
            sigungu={sigungu}
            sigunguName={sigunguName}
            selected={selected}
            onSelectBuilding={handleSelectBuilding}
            chip={activeChip}
            pick={mapPick}
            onPickChange={setMapPick}
            layout={mapLayout}
            visible={showMap}
            paneArea={paneArea}
            headExtra={
              viewerRole === '창업자' ? (
                <FounderChips chip={founderChip} onChange={setFounderChip} />
              ) : null
            }
          />
        </ErrorBoundary>
      )
    ),
  };

  /* 바에 적는 지금 구 — 시도 짧은 이름표 + 서버가 준 구 이름. 구 이름을 아직 모르면(되살리는 중 등) 비워 둔다. */
  const placeLabel = sigunguName
    ? [SIDOS.find((s) => s.code === sigungu?.slice(0, 2))?.name, sigunguName].filter(Boolean).join(' ')
    : '';
  /* PC 두 칸 지역 한 줄(D2) — 구를 골랐고 그 이름을 알 때만(되살리는 중 이름을 모르면 칩 상자 그대로) · 「바꾸기」로 펼친 동안은 칩 상자도 보인다. */
  const showRegionFold = isWide && sigungu !== null && placeLabel !== '';
  const regionFolded = showRegionFold && !regionFoldOpen;

  return (
    <div
      className={`app${headFolded ? ' app--folded' : ''}${isPhone ? ' app--tabs' : ''}${
        isPhone && selected !== null ? ' app--bld' : ''
      }${mapFull ? ' app--mapfull' : ''}${mapFull && regionOpen ? ' app--regionopen' : ''}${
        // PC 두 칸(W5) — 꼴 · 왼쪽 띠로 접힘 · 건물을 연 채(종이 = 오른쪽만) · 「상권 지도 넣기」 켬(종이에 지도). 종이는 이 이름표로 가른다.
        isWide ? ' app--wide' : ''
      }${isWide && leftCollapsed ? ' app--lcollapsed' : ''}${isWide && (selected !== null || restoring) ? ' app--wbld' : ''}${
        isWide && selected !== null && sigungu !== null && printMap ? ' app--printmap' : ''
      }${regionFolded ? ' app--rfold' : ''}`}
      data-tab={isPhone ? curTab : undefined}
    >
      {/*
        종이에만 나오는 머리글(결정 0020). 화면에서는 보이지 않는다 — 맨 위에 두는 이유는
        인쇄물의 첫 줄이 "무슨 서류인가"여야 하기 때문이다. 지도가 그 아래에 오므로, 여기에
        이름이 없으면 종이를 받은 사람이 지도부터 보게 된다.
      */}
      {selected && (
        <PrintHeader
          name={selected.bld_nm}
          address={selected.road_addr}
          url={shareUrl}
          office={viewerRole === '중개사' ? office : null}
        />
      )}

      <header className="app__head">
        {/*
          h1 은 화면에 정확히 1개(결정 0042 H1) — 건물을 연 동안은 층별 머리의 건물 이름이 h1 이고 사이트 이름은 p 로 내려간다
          (모양은 같다 — `.app__title` 이 굵기까지 적는다). 첫 화면·입구에서는 지금처럼 사이트 이름이 h1.
        */}
        {selected ? (
          <p className="app__title">상가 층별 스택뷰</p>
        ) : (
          <h1 className="app__title">상가 층별 스택뷰</h1>
        )}
        {/*
          ⛔ 담긴 지역을 여기에 글자로 박지 말 것. 자료가 늘면 문구가 곧바로 거짓말이
             된다(2026-08-11 실제로 그랬다 — 헤더는 '강남구'인데 각주는 서울·대전
             전체 63만 곳을 말했다). 지역 안내는 RegionPicker 가 **서버 목록**
             (`list_open_sigungu()`)에서 만든다 — 자료가 늘면 문구가 저절로 따라온다.
        */}
        <p className="app__sub">
          건물을 찾으면 층마다 무슨 용도인지·얼마나 넓은지·어떤 점포가 있는지 쌓아서 보여줍니다.
        </p>
      </header>

      {/*
        본문 자리(`<main>` — 검색 봇·화면 읽기 프로그램이 "여기가 본론"을 알게). 머리글·종이 머리글·
        바닥글은 밖에 둔다. ⓘ CSS 는 안 붙였다 — `.app` 에 자식 선택자가 없어 감싸도 배치가 그대로다.
      */}
      <main className="app__main">
        {/*
          접힌 입구의 한 줄 바(S1 · 시안 Qjdr1GXX). 건물을 연 동안에만 선다 — 누르면 위 칸을 펼치고 그 자리로
          옮긴다. ⓘ 종이에서는 빠진다(`@media print` · 누르는 장치).
        */}
        {/*
          접힌 입구의 한 줄 바(S1 · 시안 Qjdr1GXX). 건물을 연 동안(되살리는 동안 포함)에만 선다 — 누르면 위 칸을 펼치고
          그 자리로 옮긴다. 펼친 동안은 같은 자리(펼친 덩어리 맨 위)에 '위 칸 접기' 하나 — 위를 보는 사람이 찾게.
          ⓘ 기호(←·▾·▲)는 낭독기가 기호 이름으로 읽지 않게 따로 감춘다(`aria-hidden`) · 종이에서는 빠진다.
        */}
        {/* PC 두 칸(1024+)은 바 대신 왼쪽 칸 머리의 「왼쪽 칸 접기」·접힌 띠(W5 · 결정 0039 §4-13) — 바 DOM 0. */}
        {isPhone || isWide ? null : folded ? (
          <div className="entrybar">
            {placeLabel && <span className="entrybar__place">{placeLabel}</span>}
            {/* 창업자가 고른 업종(👤 2026-10-15 G2) — 카드의 굵은 줄이 왜 굵은지 접힌 채로도 보이게. '전체'면 안 적는다. */}
            {activeChip !== FOUNDER_CHIP_ALL && (
              <span className="entrybar__chip">업종: {activeChip}</span>
            )}
            <button
              type="button"
              className="entrybar__btn"
              ref={barFirstRef}
              aria-expanded={false}
              aria-controls="entry-panel"
              onClick={() => openEntry('search')}
            >
              <span aria-hidden="true">← </span>다른 건물 찾기
            </button>
            {sigungu !== null && (
              <button
                type="button"
                className="entrybar__btn"
                aria-expanded={false}
                aria-controls="entry-panel"
                onClick={() => openEntry('map')}
              >
                상권 지도 보기
              </button>
            )}
            <button
              type="button"
              className="entrybar__btn entrybar__role"
              aria-expanded={false}
              aria-controls="entry-panel"
              onClick={() => openEntry('role')}
            >
              나는 {viewerRole ?? '역할 고르기'}
              <span aria-hidden="true"> ▾</span>
            </button>
          </div>
        ) : (
          (selected !== null || restoring) && (
            <div className="entrybar entrybar--open">
              <button
                type="button"
                className="entrybar__btn"
                aria-expanded={true}
                aria-controls="entry-panel"
                onClick={() => foldEntry(false)}
              >
                <span aria-hidden="true">▲ </span>위 칸 접기
              </button>
            </div>
          )
        )}

        {/*
          휴대폰 지도 탭 위 한 줄 띠(👤 W4b 1번 「안 A」) — 누르면 아래 지역 고르개(같은 하나)가 띠 아래로 펼쳐진다.
          ⓘ 휴대폰 지도 가득일 때만 그린다(넓은 화면·중개사·구 고르기 전 DOM 0) · 종이에서 빠진다(`.rstrip`).
        */}
        {mapFull && (
          <RegionStrip
            place={placeLabel}
            open={regionOpen}
            controls="region-panel"
            onToggle={() => setRegionOpen((v) => !v)}
          />
        )}

        {/*
          PC 두 칸에서 왼쪽 칸을 접은 띠(W5 · 56px · 👤 2026-10-21 「가」) — 왼쪽 열에 `.entry` 대신 선다(`.entry` 는 CSS 로 숨김).
        */}
        {isWide && leftCollapsed && (
          <LeftRail place={placeLabel} hasMap={sigungu !== null} onExpand={expandLeft} expandRef={railExpandRef} />
        )}

        {/*
          ⓘ 접힌 동안 `hidden` 으로 숨기기만 한다 — 안의 검색창·지역 고르개가 다시 태어나지 않게(위 `entryOpen`).
          PC 두 칸에서 띠로 접은 동안은 `hidden` 이 아니라 CSS(`.app--lcollapsed .entry`)로 숨기고 `inert`(키보드·낭독기 0 · W5).
        */}
        <div className="entry" id="entry-panel" ref={entryRef} hidden={entryHidden} inert={isWide && leftCollapsed}>
          {/* PC 두 칸 왼쪽 칸 머리(지역 줄 위) — S1 바 대신 「왼쪽 칸 접기」(W5 · §4-13). 종이에서 빠진다(`.entry__fold`). */}
          {isWide && (
            <button
              type="button"
              className="entry__fold"
              aria-expanded={!leftCollapsed}
              aria-controls="entry-panel"
              onClick={collapseLeft}
            >
              왼쪽 칸 접기<span aria-hidden="true"> ‹</span>
            </button>
          )}
          {/*
            역할 단추 줄 — 지역 고르기 바로 위(👤 결정 0036 결정 18 ⑧). 아직 안 물어봤으면 그 자리에 큰 카드
            (결정 0039 Q3 · W3) — 카드가 서 있는 동안 작은 줄은 숨긴다(같은 질문이 두 번 안 보이게).
          */}
          {showRoleCards && !isWide ? (
            <RoleCards onPick={handlePickFromCards} />
          ) : isPhone || roleCardsRight ? null : (
            // PC 두 칸은 큰 카드가 오른쪽 빈 칸에 선다(아래 `roleCardsRight` · 👤 2026-10-22 L6) — 그동안 작은 줄은 안 그린다(질문 한 번).
            // 아직 안 물어본 채 건물을 열면 오른쪽은 건물 차지라 큰 카드는 숨고 여기 작은 줄이 선다(건물을 닫으면 다시 오른쪽 큰 카드).
            // 휴대폰은 「더보기」 탭 맨 위(아래 꼬리말 `lead` · 0036 ⑧ → 결정 0039 §5 W4a) — 큰 카드는 이 자리 그대로.
            <RolePicker role={viewerRole} onChange={handlePickRole} />
          )}

          {/*
            PC 두 칸 지역 한 줄(W5 보완 D2 · 👤 2026-10-21 「가」) — 구를 고르면 칩 상자(아래 `RegionPicker` · 같은 하나)는 CSS 로 접고
            「서울 강남구 · 바꾸기」만. 「바꾸기」를 누르면 칩 상자가 펼쳐지고 구를 고르면 다시 접힌다. 종이에서 빠진다(`.regionfold`).
          */}
          {showRegionFold && (
            <div className="regionfold">
              <span className="regionfold__place">{placeLabel}</span>
              <button
                type="button"
                className="regionfold__btn"
                aria-expanded={regionFoldOpen}
                aria-controls="region-panel"
                onClick={() => setRegionFoldOpen((v) => !v)}
              >
                바꾸기
              </button>
            </div>
          )}

          <RegionPicker
            selectedSigungu={sigungu}
            onSelectSigungu={handleSelectSigungu}
            onSigunguNameResolved={handleSigunguNameResolved}
            id={mapFull || isWide ? 'region-panel' : undefined}
          />

          {/*
            입구 두 덩어리(검색창·상권 지도). 차례는 역할이 정한다 — 창업자만 지도가 위(👤 결정 0036
            결정 18 ④ · `entryBlockOrder`). ⛔ 조건부 JSX 로 두 자리에 나눠 그리지 않는다 — 이름 key 를
            단 배열이라 차례가 바뀌어도 **같은 조각이 자리만 옮긴다**(검색어·검색 결과·지도가 다시
            태어나지 않는다 · `App.test` 가 DOM 조각이 같은 물건인지 본다).
          */}
          {entryBlockOrder(viewerRole).map((k) => (
            <Fragment key={k}>{entryBlocks[k]}</Fragment>
          ))}
        </div>


        {/*
          입구에서만 서는 카드 — LH 상가 분양·입점 공고.

          ⛔ 조건 셋을 모두 만족할 때만 그린다: **구를 골랐고**(물을 곳이 정해졌다),
             **건물을 아직 안 골랐고**(고르면 화면의 주제가 그 건물이라 분석을 어지럽히지
             않는다), **링크로 되살리는 중도 아니다**(곧 건물이 서는데 카드를 먼저 그리면
             나타났다 사라진다). 건물 선택을 풀면 다시 보인다.
          ⓘ `key` 를 일부러 안 준다 — 같은 시도 안에서 구만 바꾸면(강남구 → 서초구) 답이
            같으므로 다시 묻지 않는 것이 맞다. 카드가 시도 코드에만 매여 있다.
        */}
        {/*
          PC 두 칸에서 건물이 없을 때 오른쪽 맨 위 한 줄(👤 2026-10-21 W5 「가」 — 글자 그대로) · 그 아래 입구 카드 둘이 오른쪽 열에 선다.
          ⓘ 두 칸에서는 아래 「위에서 건물을 검색해…」 줄 대신 이 줄이다(왼쪽이 찾기 칸) · 종이에서 빠진다(화면 안내).
        */}
        {/*
          PC 두 칸 첫 방문 큰 카드(결정 0039 W3 → 👤 2026-10-22 왼쪽 칸 다듬기 「가」 L6) — 오른쪽 빈 칸 맨 위(덮개 아님 · 제자리 카드).
          왼쪽은 지역·검색·지도가 바로 보이게. 언제·저장·건물 직행 링크 예외는 W3 규칙 그대로(`showRoleCards`) · 종이에서 빠진다(`.rolecards`).
        */}
        {roleCardsRight && <RoleCards onPick={handlePickFromCards} />}

        {isWide && selected === null && !restoring && !restoreFailed && (
          <p className="rpane-empty">왼쪽에서 건물을 고르면 여기에 층별 화면이 섭니다</p>
        )}

        {showEntryCards && <LhNoticeSection sigungu={sigungu} />}

        {/*
          입구의 두 번째 카드 — 동네 매매 단가 흐름(결정 0027).

          ⛔ **LH 공고 뒤에 둔다.** 앞의 것은 "지금 무엇이 열려 있나"(할 일)이고 이쪽은
             "그동안 흐름은 어땠나"(읽을거리)다. (그 사이에 서던 참고 시세 성적표 카드는 결정 0041 로 내렸다.)
          ⓘ 조건은 LH 카드와 **똑같다** — 구를 골랐고, 건물은 아직 안 골랐고, 되살리는
            중도 아니다. 건물을 고르면 화면의 주제가 그 건물이므로 함께 물러난다.
          ⓘ `key` 를 일부러 안 준다 — 구가 바뀌면 `sigungu` prop 이 바뀌고 카드가 스스로
            다시 묻는다(카드 안의 `useEffect` 가 그 값에 매여 있다).
        */}
        {showEntryCards && <TxFlowSection sigungu={sigungu} />}

        {selected ? (
          <>
            {/*
              보고 있는 화면을 가지고 나가는 자리. 건물을 고른 뒤에만 보인다 — 고르기
              전에는 담아 갈 것이 없다.

              링크와 종이를 **한 줄에 둔다.** 둘 다 "다 보고 나서 남기는 방법"이라, 떨어뜨려
              놓으면 하나만 있는 줄 안다(결정 0020).
            */}
            <div className="takeout">
              <ShareButton url={shareUrl} label={selected.bld_nm} />
              <PrintButton onBeforePrint={handleBeforePrint} />
              {/*
                「상권 지도 넣기」(결정 0039 §7-2 · W5) — PC 두 칸에서만(721~1023 은 10-15 「지도는 펼쳤을 때만 종이에」 그대로).
                기본 끔 = 종이는 오른쪽(건물)만 · 켜면 왼쪽 칸의 지도 덩어리가 종이에(`.app--printmap` · Ctrl+P 도 같은 종이).
                ⛔ 저장하지 않는다 · 이 고르기 자체는 종이에서 빠진다(`.mapprint` · `.takeout`).
              */}
              {isWide && sigungu !== null && (
                <label className="mapprint">
                  <input type="checkbox" checked={printMap} onChange={(e) => setPrintMap(e.target.checked)} />
                  상권 지도 넣기
                </label>
              )}
              {showUnitPicker && (
                <UnitPrintPicker
                  mode={unitPrintMode}
                  onChange={(mode) =>
                    setUnitPick((p) => ({
                      bldId: selected.bld_id,
                      mode,
                      opened: mode === 'none' ? p.opened : p.opened + 1,
                    }))
                  }
                />
              )}
              {viewerRole === '중개사' && (
                <BrokerOfficeForm
                  value={office}
                  onChange={handleOfficeChange}
                  onClear={() => setOffice(clearBrokerOffice())}
                />
              )}
            </div>

            {/*
              층별 화면은 이 앱에서 가장 크고(카드 다섯 장) 바깥 자료를 가장 많이 다루는
              자리다. 여기가 죽어도 위쪽 검색은 살아 있어야 다른 건물로 옮겨 갈 수 있다.
            */}
            <ErrorBoundary
              key={`stack:${selected.bld_id}`}
              area="층별 화면"
              context={{ bld_id: selected.bld_id, sigungu }}
              // 그물이 뜨면 층별 화면의 h1 이 사라진다 — 안내 위에 건물 이름 h1 을 세운다(h1 정확히 1개 · 결정 0042 보완 F4).
              heading={
                <h1 className="stack__title">
                  {[selected.bld_nm?.trim() || null, dong].filter(Boolean).join(' ') || '(이름 없는 건물)'}
                </h1>
              }
            >
              <FloorStack
                building={selected}
                viewerRole={viewerRole}
                founderChip={activeChip}
                unitPrintMode={unitPrintMode}
                unitPrintOpenSignal={unitPick.bldId === selected.bld_id ? unitPick.opened : 0}
                onUnitListedCount={handleUnitListedCount}
                onBeforePrint={handleBeforePrint}
                dongs={dongs}
                // 구 이름은 지금 고른 구가 이 건물의 구일 때만(다른 구 이름으로 「○○구 다른 건물 찾기」를 적지 않게).
                sigunguName={sigungu === selected.pnu.slice(0, 5) ? sigunguName : null}
                onSelectBuilding={handleSelectBuilding}
                onFindInSigungu={handleFindInSigungu}
              />
            </ErrorBoundary>
          </>
        ) : restoring ? (
          <p className="msg msg--idle">링크에 담긴 건물을 불러오는 중입니다…</p>
        ) : restoreFailed ? (
          // 층 자료가 없는 건물(239동)이거나 서버가 잠깐 흔들린 경우다. 어느 쪽이든
          // 빈 화면을 그리지 않고 다음에 할 일을 알려 준다.
          // 휴대폰 건물 탭엔 위에 검색창이 없다 — 「위에서…」 대신 빈 건물 탭의 「건물 찾으러 가기」 단추(검사 🟡 F5).
          isPhone ? (
            curTab === 'building' && (
              <section className="tabempty" aria-label="링크의 건물을 찾지 못함">
                <p className="tabempty__title">링크에 담긴 건물을 찾지 못했습니다.</p>
                <button type="button" className="tabempty__go" onClick={() => pickTab('find')}>
                  {EMPTY_BUILDING_GO}
                </button>
              </section>
            )
          ) : (
            <p className="msg msg--idle">
              링크에 담긴 건물을 찾지 못했습니다. 위에서 건물을 검색해 선택해 주세요.
            </p>
          )
        ) : isPhone ? (
          /*
            휴대폰 빈 「건물」 탭(👤 2026-10-17 W4a 1번 「가」 — 시안 글자 그대로). 「위에서 건물을…」 줄은 휴대폰에선 안 그린다
            (메인 판단 ⑩ — 찾기 탭엔 검색이 바로 있고, 건물 탭엔 이 안내가 대신한다).
          */
          curTab === 'building' && (
            <section className="tabempty" aria-label="고른 건물 없음">
              <p className="tabempty__title">{EMPTY_BUILDING_TITLE}</p>
              <p className="tabempty__body">{EMPTY_BUILDING_BODY}</p>
              <button type="button" className="tabempty__go" onClick={() => pickTab('find')}>
                {EMPTY_BUILDING_GO}
              </button>
            </section>
          )
        ) : isWide ? null : (
          // PC 두 칸은 위 `.rpane-empty` 한 줄이 대신한다(W5 — 찾기는 위가 아니라 왼쪽).
          <p className="msg msg--idle">위에서 건물을 검색해 선택해 주세요.</p>
        )}

        {/* 중개사 휴대폰 「뽑은 건물」 탭 — 지금의 「최근 뽑은 건물」 목록을 펼친 채(👤 W4a 2번 「가」 · 결정 0036 ⑩). */}
        {isPhone && curTab === 'printed' && (
          <RecentPrinted
            inTab
            items={recentPrinted}
            onPick={handlePickRecent}
            onClear={() => setRecentPrinted(clearRecentPrinted())}
          />
        )}
      </main>

      {/*
        무엇을 보던 중이었는지를 의견함이 함께 실어 보낸다 — 사람이 손으로 적지 않아도
        "어디를 보다 무엇이 아쉬웠나"가 남는다. 개인을 가리키는 값은 담지 않는다.
      */}
      <AppFooter
        feedbackContext={{
          bld_id: selected?.bld_id ?? null,
          sigungu,
          sigungu_nm: sigunguName,
        }}
        lead={isPhone && !showRoleCards ? <RolePicker role={viewerRole} onChange={handlePickRole} /> : null}
        phoneOrder={isPhone}
      />

      {/* 휴대폰 아래 탭(결정 0039 W4a) — 넓은 화면엔 없다 · 종이에서 빠진다. */}
      {isPhone && (
        <TabBar tabs={tabsFor(viewerRole)} current={curTab} buildingDim={selected === null} onPick={pickTab} />
      )}
    </div>
  );
}
