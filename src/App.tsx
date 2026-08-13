import { useState } from 'react';
import { BuildingSearch } from './components/BuildingSearch';
import { FloorStack } from './components/FloorStack';
import { RegionPicker } from './components/RegionPicker';
import type { BuildingHit } from './types';

export default function App() {
  const [selected, setSelected] = useState<BuildingHit | null>(null);
  const [sigungu, setSigungu] = useState<string | null>(null);
  const [sigunguName, setSigunguName] = useState<string | null>(null);

  // 구가 바뀌면 이전 구의 선택 건물은 더는 맞지 않는다(스택이 다른 구 건물을 계속
  // 그리면 안 된다). 검색어·검색 결과는 BuildingSearch 쪽 key로 함께 비운다(아래).
  function handleSelectSigungu(code: string | null, name?: string | null) {
    setSigungu(code);
    setSigunguName(code ? (name ?? null) : null);
    setSelected(null);
  }

  return (
    <div className="app">
      <header className="app__head">
        <h1 className="app__title">상가 층별 스택뷰</h1>
        {/*
          ⛔ 담긴 지역을 여기에 글자로 박지 말 것. 자료가 늘면 문구가 곧바로 거짓말이
             된다(2026-08-11 실제로 그랬다 — 헤더는 '강남구'인데 각주는 서울·대전
             전체 63만 곳을 말했다). 지역 안내는 RegionPicker 가 regions.ts 에서 만든다.
        */}
        <p className="app__sub">
          건물을 찾으면 층마다 무슨 용도인지·얼마나 넓은지·어떤 점포가 있는지 쌓아서 보여줍니다.
        </p>
      </header>

      <RegionPicker selectedSigungu={sigungu} onSelectSigungu={handleSelectSigungu} />

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
        onSelect={setSelected}
        onSearchStart={() => setSelected(null)}
        selectedBldId={selected?.bld_id ?? null}
        sigungu={sigungu}
        sigunguName={sigunguName}
      />

      {selected ? (
        <FloorStack building={selected} />
      ) : (
        <p className="msg msg--idle">위에서 건물을 검색해 선택해 주세요.</p>
      )}
    </div>
  );
}
