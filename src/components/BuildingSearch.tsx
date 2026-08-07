import { useState } from 'react';
import type { SubmitEvent } from 'react';
import { supabase, FLOOR_STACK_VIEW } from '../lib/supabase';
import type { BuildingHit } from '../types';

/**
 * 건물명·도로명주소로 건물을 찾는다.
 *
 * 뷰는 "건물 × 층"이라 한 건물이 여러 줄로 온다. 그래서 받아온 뒤 건물 단위로 접어서
 * 층 수·최고/최저 층을 같이 보여준다 — 검색 결과에서 이미 "몇 층짜리인지"가 보이면
 * 원하는 건물을 고르기 쉽다.
 */

/** 1차 검색에서 훑을 "건물 × 층" 줄 수. */
const FETCH_LIMIT = 600;
/** 목록에 보여줄 건물 수. 이 만큼만 2차로 진짜 층 목록을 받아온다. */
const MAX_BUILDINGS = 25;
/** 2차 조회 상한. 25개 건물 × 최대 층수를 넉넉히 덮는 값. */
const FLOOR_FETCH_LIMIT = 3000;

type Props = {
  onSelect: (hit: BuildingHit) => void;
  selectedBldId: string | null;
};

export function BuildingSearch({ onSelect, selectedBldId }: Props) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<BuildingHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  /** 걸린 건물이 MAX_BUILDINGS보다 많아 잘라서 보여주는 중인가. */
  const [truncated, setTruncated] = useState(false);

  async function runSearch(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    try {
      const escaped = q.replace(/[%,]/g, ' ');

      // 1차 — 어떤 건물이 걸리는지 찾는다. 뷰는 "건물 × 층"이라 한 건물이 여러 줄로 온다.
      const { data, error: err } = await supabase
        .from(FLOOR_STACK_VIEW)
        .select('bld_id,pnu,bld_nm,road_addr,bld_cnt_in_pnu')
        .or(`bld_nm.ilike.%${escaped}%,road_addr.ilike.%${escaped}%`)
        .limit(FETCH_LIMIT);

      if (err) throw new Error(err.message);

      const found = dedupeBuildings(data ?? []);
      setTruncated(found.length > MAX_BUILDINGS);
      const shown = found.slice(0, MAX_BUILDINGS);

      // 2차 — 보여줄 건물들의 "진짜" 층 목록을 다시 받는다.
      //
      // 1차 결과로 층 수를 세면 안 된다. 그건 줄 수 상한(FETCH_LIMIT)에 잘린 표본이라
      // 층이 많은 건물일수록 심하게 모자라게 나온다 — KB손해보험빌딩(실제 27개 층)이
      // "5개 층"으로 찍혔다(2026-08-08 실측). 층 수는 반드시 건물을 특정해 다시 센다.
      setHits(await attachFloorRange(shown));
      setSearched(true);
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : String(ex));
      setHits([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="search">
      <form onSubmit={runSearch} className="search__form">
        <input
          className="search__input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="건물명 또는 도로명주소 (예: 테헤란로, 미도맨션)"
          aria-label="건물명 또는 도로명주소"
        />
        <button className="search__btn" type="submit" disabled={loading || !query.trim()}>
          {loading ? '찾는 중…' : '검색'}
        </button>
      </form>

      {error && <p className="msg msg--error">검색 실패: {error}</p>}

      {searched && !loading && hits.length === 0 && !error && (
        <p className="msg">결과가 없습니다. 지금 담긴 자료는 <strong>서울 강남구</strong>뿐입니다.</p>
      )}

      {hits.length > 0 && (
        <>
          <p className="search__count">
            건물 {hits.length.toLocaleString('ko-KR')}개
            {truncated && (
              <span className="search__hint">
                {' '}
                · 더 있습니다. 검색어를 좁혀 주세요
              </span>
            )}
          </p>
          <ul className="hits">
            {hits.map((h) => (
              <li key={h.bld_id}>
                <button
                  className={`hit${h.bld_id === selectedBldId ? ' hit--on' : ''}`}
                  onClick={() => onSelect(h)}
                >
                  <span className="hit__name">{h.bld_nm || '(이름 없는 건물)'}</span>
                  <span className="hit__addr">{h.road_addr || '주소 없음'}</span>
                  <span className="hit__meta">
                    {describeRange(h)} · {h.floor_cnt}개 층
                    {h.bld_cnt_in_pnu > 1 && (
                      <span className="hit__warn"> · 같은 땅에 {h.bld_cnt_in_pnu}동</span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

type RawHit = Pick<BuildingHit, 'bld_id' | 'pnu' | 'bld_nm' | 'road_addr' | 'bld_cnt_in_pnu'>;

/** "건물 × 층" 줄들에서 건물만 골라낸다(층 수는 여기서 세지 않는다 — 표본이라 틀린다). */
function dedupeBuildings(rows: RawHit[]): RawHit[] {
  const byId = new Map<string, RawHit>();
  for (const r of rows) {
    if (!byId.has(r.bld_id)) byId.set(r.bld_id, r);
  }
  return [...byId.values()];
}

/** 건물별 진짜 층 목록을 받아 층 수·최저·최고 층을 채운다. */
async function attachFloorRange(rows: RawHit[]): Promise<BuildingHit[]> {
  if (rows.length === 0) return [];

  const ids = rows.map((r) => r.bld_id);
  const { data, error } = await supabase
    .from(FLOOR_STACK_VIEW)
    .select('bld_id,floor_no')
    .in('bld_id', ids)
    .limit(FLOOR_FETCH_LIMIT);

  if (error) throw new Error(error.message);

  const floors = new Map<string, number[]>();
  for (const f of (data ?? []) as { bld_id: string; floor_no: number }[]) {
    const list = floors.get(f.bld_id);
    if (list) list.push(f.floor_no);
    else floors.set(f.bld_id, [f.floor_no]);
  }

  return rows
    .map((r) => {
      const list = floors.get(r.bld_id) ?? [];
      return {
        ...r,
        floor_cnt: list.length,
        min_floor: list.length ? Math.min(...list) : 0,
        max_floor: list.length ? Math.max(...list) : 0,
      };
    })
    .sort((a, b) => b.floor_cnt - a.floor_cnt);
}

/** "지하 2층 ~ 15층"처럼 층 범위를 한 줄로. 옥탑(99)은 층수로 세지 않고 따로 적는다. */
function describeRange(h: BuildingHit): string {
  const hasRoof = h.max_floor === 99;
  const top = hasRoof ? '옥탑' : `${h.max_floor}층`;
  const bottom = h.min_floor < 0 ? `지하 ${Math.abs(h.min_floor)}층` : `${h.min_floor}층`;
  return `${bottom} ~ ${top}`;
}
