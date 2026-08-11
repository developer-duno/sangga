import { useRef, useState } from 'react';
import type { SubmitEvent } from 'react';
import { supabase } from '../lib/supabase';
import { describeError, describeRange } from '../lib/format';
import { openRegionLabel } from '../lib/regions';
import type { BuildingHit } from '../types';

/**
 * 건물명·도로명주소로 건물을 찾는다.
 *
 * 서버 함수 `search_buildings`가 **건물 1개 = 1행**으로 돌려주고, 검색어에 걸린 전체
 * 건수(`total_cnt`)도 함께 준다.
 *
 * ⛔ 예전처럼 뷰에서 "건물 × 층" 줄을 표본으로 받아 건물로 접으면 안 된다. 층이 27개인
 *    건물 하나가 27줄을 먹으므로 표본이 건물을 대표하지 못하고, 정렬을 `bld_id`로 주면
 *    앞자리가 법정동 코드라 **검색 결과가 한 동네에 갇힌다.**
 *    2026-08-08 실측: '빌딩' 검색 → 매칭 15,068행인데 화면엔 역삼동 69개 건물뿐,
 *    '테헤란로' → 10,517행인데 역삼동 95개뿐. 다른 동네는 재검색해도 안 나왔다.
 */

/** 목록에 보여줄 건물 수. 서버가 관련도 높은 순으로 이 수만큼만 돌려준다. */
const MAX_BUILDINGS = 25;

type Props = {
  onSelect: (hit: BuildingHit) => void;
  /** 새 검색이 시작될 때. 아래 스택뷰가 옛 건물을 계속 그리지 않도록 선택을 비운다. */
  onSearchStart: () => void;
  selectedBldId: string | null;
};

export function BuildingSearch({ onSelect, onSearchStart, selectedBldId }: Props) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<BuildingHit[]>([]);
  /** 검색어에 걸린 전체 건물 수(보여주는 수가 아니다). */
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  /** 늦게 도착한 옛 검색 응답이 최신 결과를 덮는 것을 막는다. */
  const latestRun = useRef(0);

  async function runSearch(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    const runId = ++latestRun.current;
    setLoading(true);
    setError(null);
    onSearchStart(); // 새 검색 = 이전 선택 해제(아래 스택뷰가 옛 건물을 계속 그리지 않게)
    try {
      // 검색어는 파라미터로 넘어간다 — % _ \ 를 서버가 리터럴로 이스케이프하므로
      // 여기서 따로 손대지 않는다(직접 문자열을 이어 붙이면 필터가 깨진다).
      const { data, error: err } = await supabase.rpc('search_buildings', {
        q,
        lim: MAX_BUILDINGS,
      });

      if (runId !== latestRun.current) return; // 그새 새 검색이 시작됐다
      if (err) throw err;

      const rows = (data ?? []) as BuildingHit[];
      setHits(rows);
      setTotal(rows.length ? Number(rows[0].total_cnt ?? rows.length) : 0);
      setSearched(true);
    } catch (ex) {
      if (runId !== latestRun.current) return;
      // 원문에는 내부 표 이름이 섞여 있다 — 콘솔에만 남기고 화면엔 사람 말로.
      console.error('건물 검색 실패', ex);
      setError(describeError(ex));
      setHits([]);
      setTotal(0);
    } finally {
      if (runId === latestRun.current) setLoading(false);
    }
  }

  const shownAll = total > 0 && total <= hits.length;

  return (
    <section className="search">
      <form onSubmit={runSearch} className="search__form">
        <input
          className="search__input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="건물명 · 도로명주소 · 지번 (예: 미도맨션, 테헤란로 117, 역삼동 823-4)"
          aria-label="건물명 또는 주소"
        />
        <button className="search__btn" type="submit" disabled={loading || !query.trim()}>
          {loading ? '찾는 중…' : '검색'}
        </button>
      </form>

      {error && <p className="msg msg--error">{error}</p>}

      {searched && !loading && hits.length === 0 && !error && (
        <p className="msg">
          결과가 없습니다. 지금 보실 수 있는 지역은 <strong>{openRegionLabel()}</strong>입니다.
        </p>
      )}

      {hits.length > 0 && (
        <>
          <p className="search__count">
            건물 {total.toLocaleString('ko-KR')}개
            {!shownAll && (
              <span className="search__hint">
                {' '}
                · 이 중 {hits.length}개만 보여드립니다. 검색어를 좁혀 주세요
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
                  {/* 지번으로 찾은 사람이 "왜 이게 나왔나"를 알 수 있게 함께 보여준다. */}
                  {h.jibun_addr && <span className="hit__jibun">지번 {h.jibun_addr}</span>}
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
