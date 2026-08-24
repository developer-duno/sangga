import { useCallback, useEffect, useState } from 'react';
import { AppFooter } from './components/AppFooter';
import { BuildingSearch } from './components/BuildingSearch';
import { DistrictMap } from './components/DistrictMap';
import { ErrorBoundary } from './components/ErrorBoundary';
import { FloorStack } from './components/FloorStack';
import { RegionPicker } from './components/RegionPicker';
import { ShareButton } from './components/ShareButton';
import { FLOOR_STACK_VIEW } from './lib/appConstants';
import { buildingFromFloorRows } from './lib/restoreBuilding';
import { supabase } from './lib/supabase';
import { buildAppSearch, buildShareUrl, isSameSearch, parseAppUrl } from './lib/urlState';
import type { BuildingHit, FloorRow } from './types';

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

  // 구가 바뀌면 이전 구의 선택 건물은 더는 맞지 않는다(스택이 다른 구 건물을 계속
  // 그리면 안 된다). 검색어·검색 결과는 BuildingSearch 쪽 key로 함께 비운다(아래).
  function handleSelectSigungu(code: string | null, name?: string | null) {
    setRestoreFailed(false);
    setSigungu(code);
    setSigunguName(code ? (name ?? null) : null);
    setSelected(null);
  }

  // 검색으로 건물을 고르면 "링크로 들어왔다가 실패한 상태"는 끝난 것이다.
  const handleSelectBuilding = useCallback((hit: BuildingHit) => {
    setRestoreFailed(false);
    setSelected(hit);
  }, []);

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
    window.history.replaceState(null, '', `${window.location.pathname}${buildAppSearch(next)}`);
  }, [sigungu, selected, restoring, restoreFailed]);

  return (
    <div className="app">
      <header className="app__head">
        <h1 className="app__title">상가 층별 스택뷰</h1>
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

      <RegionPicker
        selectedSigungu={sigungu}
        onSelectSigungu={handleSelectSigungu}
        onSigunguNameResolved={handleSigunguNameResolved}
      />

      {/*
        구가 바뀔 때마다 BuildingSearch를 key로 통째로 새로 그린다. 검색어·검색 결과·
        안내창은 전부 그 컴포넌트 내부 상태라 밖에서 하나씩 비울 수 없고, 다른 구에서
        찾은 결과가 화면에 남아 있으면 안 되기 때문이다(2026-08-13 사장님 결정).

        onSearchStart 로는 (구를 바꾸지 않고) 같은 구 안에서 새로 검색했을 때 이전
        선택을 비운다 — 안 그러면 새 검색을 해도 아래 스택이 **이전에 고른 건물**
        그대로 남는다. "결과가 없습니다"가 뜬 상태에서도 옛 건물 스택이 그대로
        보였다(2026-08-08 적대검증 라이브 재현).
      */}
      <BuildingSearch
        key={sigungu ?? '__no_region__'}
        onSelect={handleSelectBuilding}
        onSearchStart={() => setSelected(null)}
        selectedBldId={selected?.bld_id ?? null}
        sigungu={sigungu}
        sigunguName={sigunguName}
      />

      {/*
        상권 지도(결정 0010). 구를 고르면 **건물을 안 골랐어도** 보인다 — 지도는 이 서비스의
        첫인상이라 탭이나 건물 선택 뒤에 숨기면 있는 줄도 모른다. 구를 안 골랐을 때는
        컴포넌트가 스스로 아무것도 그리지 않는다(그릴 범위가 정해지지 않았으므로).
      */}
      {/*
        ⚠️ key 를 구 코드로 주는 이유 — 그물(ErrorBoundary)은 한 번 오류를 받으면 스스로
           풀리지 않는다. key 가 없으면 A구 지도에서 한 번 터진 뒤 B구로 옮겨도 **계속**
           오류 안내만 보인다. 구가 바뀌면 그물을 새로 쳐서 다시 그려 보게 한다.
        지도는 바깥 지도 SDK 를 태우는 자리라 우리 코드만으로는 터질 자리를 다 못 셈한다.
      */}
      <ErrorBoundary
        key={`map:${sigungu ?? '__none__'}`}
        area="상권 지도"
        context={{ sigungu, sigungu_nm: sigunguName }}
      >
        <DistrictMap sigungu={sigungu} sigunguName={sigunguName} selected={selected} />
      </ErrorBoundary>

      {selected ? (
        <>
          {/*
            보고 있는 화면을 가지고 나가는 자리. 건물을 고른 뒤에만 보인다 — 고르기
            전에는 담아 갈 것이 없다.
          */}
          <ShareButton
            url={buildShareUrl(window.location.origin, window.location.pathname, {
              sigungu,
              bldId: selected.bld_id,
            })}
            label={selected.bld_nm}
          />

          {/*
            층별 화면은 이 앱에서 가장 크고(카드 다섯 장) 바깥 자료를 가장 많이 다루는
            자리다. 여기가 죽어도 위쪽 검색은 살아 있어야 다른 건물로 옮겨 갈 수 있다.
          */}
          <ErrorBoundary
            key={`stack:${selected.bld_id}`}
            area="층별 화면"
            context={{ bld_id: selected.bld_id, sigungu }}
          >
            <FloorStack building={selected} />
          </ErrorBoundary>
        </>
      ) : restoring ? (
        <p className="msg msg--idle">링크에 담긴 건물을 불러오는 중입니다…</p>
      ) : restoreFailed ? (
        // 층 자료가 없는 건물(239동)이거나 서버가 잠깐 흔들린 경우다. 어느 쪽이든
        // 빈 화면을 그리지 않고 다음에 할 일을 알려 준다.
        <p className="msg msg--idle">
          링크에 담긴 건물을 찾지 못했습니다. 위에서 건물을 검색해 선택해 주세요.
        </p>
      ) : (
        <p className="msg msg--idle">위에서 건물을 검색해 선택해 주세요.</p>
      )}

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
      />
    </div>
  );
}
