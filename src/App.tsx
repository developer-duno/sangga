import { useState } from 'react';
import { BuildingSearch } from './components/BuildingSearch';
import { FloorStack } from './components/FloorStack';
import type { BuildingHit } from './types';

export default function App() {
  const [selected, setSelected] = useState<BuildingHit | null>(null);

  return (
    <div className="app">
      <header className="app__head">
        <h1 className="app__title">상가 층별 스택뷰</h1>
        <p className="app__sub">
          건물을 찾으면 층마다 무슨 용도인지·얼마나 넓은지·어떤 점포가 있는지 쌓아서 보여줍니다.
          지금 담긴 자료는 <strong>서울 강남구</strong>입니다.
        </p>
      </header>

      <BuildingSearch onSelect={setSelected} selectedBldId={selected?.bld_id ?? null} />

      {selected ? (
        <FloorStack building={selected} />
      ) : (
        <p className="msg msg--idle">위에서 건물을 검색해 선택해 주세요.</p>
      )}
    </div>
  );
}
