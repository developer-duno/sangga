import { useRef, useState } from 'react';
import type { SubmitEvent } from 'react';
import { supabase, FLOOR_STACK_VIEW } from '../lib/supabase';
import { formatFloor } from '../lib/format';
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
  /** 1차 표본이 상한에 잘렸거나 건물이 MAX_BUILDINGS보다 많아 일부만 보여주는 중인가. */
  const [truncated, setTruncated] = useState(false);
  /** 늦게 도착한 옛 검색 응답이 최신 결과를 덮는 것을 막는다. */
  const latestRun = useRef(0);

  async function runSearch(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    const runId = ++latestRun.current;
    setLoading(true);
    setError(null);
    try {
      const pattern = likePattern(q);

      // 1차 — 어떤 건물이 걸리는지 찾는다. 뷰는 "건물 × 층"이라 한 건물이 여러 줄로 온다.
      //
      // order가 없으면 안 된다: PostgreSQL은 ORDER BY 없는 LIMIT의 행 순서를 보장하지
      // 않아서, 같은 검색어를 다시 눌러도 다른 건물 묶음이 온다(2026-08-08 실측 —
      // '래미안' 20회 반복에 93개/48개 두 상태가 번갈아 나왔고 겹치는 건물은 1개뿐이었다).
      const { data, error: err } = await supabase
        .from(FLOOR_STACK_VIEW)
        .select('bld_id,pnu,bld_nm,road_addr,bld_cnt_in_pnu')
        .or(`bld_nm.ilike.${pattern},road_addr.ilike.${pattern}`)
        .order('bld_id')
        .limit(FETCH_LIMIT);

      if (runId !== latestRun.current) return; // 그새 새 검색이 시작됐다
      if (err) throw new Error(err.message);

      const rows = data ?? [];
      const found = dedupeBuildings(rows);
      // 1차가 상한까지 꽉 찼다면 그 뒤에 건물이 더 있어도 우리는 못 봤다.
      // 이때 "건물 N개"를 확정적으로 말하면 거짓이 된다.
      setTruncated(rows.length >= FETCH_LIMIT || found.length > MAX_BUILDINGS);
      const shown = found.slice(0, MAX_BUILDINGS);

      // 2차 — 보여줄 건물들의 "진짜" 층 목록을 다시 받는다.
      //
      // 1차 결과로 층 수를 세면 안 된다. 그건 줄 수 상한(FETCH_LIMIT)에 잘린 표본이라
      // 층이 많은 건물일수록 심하게 모자라게 나온다 — KB손해보험빌딩(실제 27개 층)이
      // "5개 층"으로 찍혔다(2026-08-08 실측). 층 수는 반드시 건물을 특정해 다시 센다.
      const withFloors = await attachFloorRange(shown);
      if (runId !== latestRun.current) return;
      setHits(withFloors);
      setSearched(true);
    } catch (ex) {
      if (runId !== latestRun.current) return;
      setError(ex instanceof Error ? ex.message : String(ex));
      setHits([]);
    } finally {
      if (runId === latestRun.current) setLoading(false);
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
            건물 {hits.length.toLocaleString('ko-KR')}개{truncated && ' 이상'}
            {truncated && (
              <span className="search__hint">
                {' '}
                · 전부는 아닙니다. 검색어를 좁혀 주세요
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

/**
 * 검색어를 PostgREST `ilike` 값으로 안전하게 감싼다.
 *
 * 큰따옴표로 감싸지 않으면 검색어 안의 `(` `)` `,` 가 `or=(...)` 문법으로 해석돼
 * 조건이 통째로 잘려 나간다 — 실재하는 "역삼동 609-26 제1종근린생활시설 (안제호)"를
 * 화면에 뜬 이름 그대로 "(안제호)"로 검색하면 **에러 없이** "결과 없음"이 떴다
 * (2026-08-08 실측. 이름에 괄호가 든 건물이 전체 5,903개 중 276개 = 4.7%).
 * 괄호를 지워버리는 대신 감싸는 이유는 검색어를 훼손하지 않기 위해서다.
 *
 * 큰따옴표 안에서는 `"` 와 `\` 만 이스케이프하면 된다.
 */
function likePattern(q: string): string {
  const escaped = q.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  return `"*${escaped}*"`;
}

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
      // 옥탑(99)은 범위 계산에서 뺀다. 섞으면 최고층이 항상 99가 되어 지상 최고층이
      // 사라진다 — KB손해보험빌딩(지상 19층 + 옥탑)이 "지하 7층 ~ 옥탑"으로만 보였다.
      const ground = list.filter((f) => f !== 99);
      return {
        ...r,
        floor_cnt: list.length,
        min_floor: ground.length ? Math.min(...ground) : null,
        max_floor: ground.length ? Math.max(...ground) : null,
        has_roof: list.includes(99),
      };
    })
    .sort((a, b) => b.floor_cnt - a.floor_cnt);
}

/**
 * "지하 2층 ~ 15층 + 옥탑"처럼 층 범위를 한 줄로.
 *
 * 부호 처리를 직접 하지 않고 `formatFloor`를 재사용한다 — 예전엔 아래쪽만 음수를
 * 처리하고 위쪽은 그대로 찍어서, 지하만 있는 건물이 "지하 5층 ~ -1층"으로 보였다
 * (2026-08-08 실측: 강남에 지하층만 있는 건물 213개).
 */
function describeRange(h: BuildingHit): string {
  if (h.min_floor === null || h.max_floor === null) {
    return h.has_roof ? '옥탑만' : '층 정보 없음';
  }
  const bottom = formatFloor(h.min_floor, null);
  const top = formatFloor(h.max_floor, null);
  const range = bottom === top ? bottom : `${bottom} ~ ${top}`;
  return h.has_roof ? `${range} + 옥탑` : range;
}
