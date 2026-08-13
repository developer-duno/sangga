import { useState } from 'react';
import { BuildingSearch } from './components/BuildingSearch';
import { FloorStack } from './components/FloorStack';
import { RegionPicker } from './components/RegionPicker';
import type { BuildingHit } from './types';

export default function App() {
  const [selected, setSelected] = useState<BuildingHit | null>(null);

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

      <RegionPicker />

      {/*
        onSearchStart 로 선택을 비운다. 안 그러면 새 검색을 해도 아래 스택이 **이전에 고른
        건물** 그대로 남는다 — 목록엔 없는 건물이라 하이라이트도 사라져서, 아래 화면이
        무엇을 가리키는지 알 수 없게 된다. 심지어 "결과가 없습니다"가 뜬 상태에서도
        옛 건물 스택이 그대로 보였다(2026-08-08 적대검증 라이브 재현).
      */}
      <BuildingSearch
        onSelect={setSelected}
        onSearchStart={() => setSelected(null)}
        selectedBldId={selected?.bld_id ?? null}
      />

      {selected ? (
        <FloorStack building={selected} />
      ) : (
        <p className="msg msg--idle">위에서 건물을 검색해 선택해 주세요.</p>
      )}
    </div>
  );
}
