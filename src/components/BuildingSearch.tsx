import { useEffect, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';
import { supabase } from '../lib/supabase';
import { SEARCH_BUILDINGS_FN, SEARCH_SCOPE_FN } from '../lib/appConstants';
import { describeError, describeRange } from '../lib/format';
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

/**
 * 이 글자 수보다 짧으면 서버에 묻지 않는다.
 *
 * 한 글자는 **어떤 글자든** 수만 곳과 맞는다(라이브 실측 2026-08-13: '동'은 전체 필지
 * 197,076곳 중 193,090곳 = 98%와 매칭). 물어봐야 답이 안 나오는 질문이므로 왕복을
 * 아끼고 바로 안내한다. 두 글자부터는 서버가 실제로 몇 곳인지 세어 판정한다
 * — '명동'(1,420곳)은 되고 '강남'(13,529곳)은 안 되는데, 이건 글자 수로는 못 가른다.
 */
const MIN_QUERY_CHARS = 2;

/** 서버 `search_key()`와 **같은 방식**으로 정규화한다(공백 제거 + 소문자). 기준이 갈리면 안 된다. */
function normalizeQuery(q: string): string {
  return q.replace(/\s+/g, '').toLowerCase();
}

/**
 * "이 검색어로는 분석할 곳이 안 정해진다"는 안내.
 *
 * `short`는 화면이 바로 판단하고, `broad`는 서버가 실제 매칭 수를 세어 알려준다.
 * `no-region`은 구를 아직 안 고른 채 검색을 눌렀을 때다(2026-08-13 사장님 결정 —
 * 검색은 이제 고른 구 안에서만 한다).
 */
type ScopeNotice =
  | { kind: 'short' }
  | { kind: 'broad'; word: string; count: number }
  | { kind: 'no-region' };

type Props = {
  onSelect: (hit: BuildingHit) => void;
  /** 새 검색이 시작될 때. 아래 스택뷰가 옛 건물을 계속 그리지 않도록 선택을 비운다. */
  onSearchStart: () => void;
  selectedBldId: string | null;
  /** 지금 고른 시군구 코드. 없으면 검색을 막고 먼저 고르라고 안내한다. */
  sigungu: string | null;
  /** 고른 시군구 이름(화면 표시용). RPC에는 넘기지 않는다. */
  sigunguName: string | null;
};

export function BuildingSearch({ onSelect, onSearchStart, selectedBldId, sigungu, sigunguName }: Props) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<BuildingHit[]>([]);
  /** 검색어에 걸린 전체 건물 수(보여주는 수가 아니다). */
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  /** "이 검색어로는 어디를 볼지 안 정해진다"는 안내창. null이면 안 띄운다. */
  const [notice, setNotice] = useState<ScopeNotice | null>(null);
  /** 늦게 도착한 옛 검색 응답이 최신 결과를 덮는 것을 막는다. */
  const latestRun = useRef(0);
  const noticeCloseRef = useRef<HTMLButtonElement>(null);

  // Esc로 닫기 — 안내창을 띄워 놓고 빠져나갈 길이 없으면 안 된다(RegionPicker와 같은 방식).
  useEffect(() => {
    if (!notice) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNotice(null);
    };
    window.addEventListener('keydown', onKey);
    noticeCloseRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [notice]);

  async function runSearch(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    // 한 글자는 물어볼 필요가 없다 — 어떤 글자든 수만 곳과 맞는다. 왕복을 아끼고 바로 안내.
    if (normalizeQuery(q).length < MIN_QUERY_CHARS) {
      setNotice({ kind: 'short' });
      return;
    }

    // 구를 안 골랐으면 서버를 부르지 않는다 — 같은 건물 이름이 여러 구에 겹치므로
    // 어느 구인지 정해지지 않은 채로는 정확한 결과를 낼 수 없다(2026-08-13 사장님 결정).
    if (!sigungu) {
      setNotice({ kind: 'no-region' });
      return;
    }

    const runId = ++latestRun.current;
    setLoading(true);
    setError(null);
    setNotice(null);
    onSearchStart(); // 새 검색 = 이전 선택 해제(아래 스택뷰가 옛 건물을 계속 그리지 않게)
    try {
      // 검색어는 파라미터로 넘어간다 — % _ \ 를 서버가 리터럴로 이스케이프하므로
      // 여기서 따로 손대지 않는다(직접 문자열을 이어 붙이면 필터가 깨진다).
      const { data, error: err } = await supabase.rpc(SEARCH_BUILDINGS_FN, {
        q,
        lim: MAX_BUILDINGS,
        sigungu,
      });

      if (runId !== latestRun.current) return; // 그새 새 검색이 시작됐다
      if (err) throw err;

      const rows = (data ?? []) as BuildingHit[];

      // 0건은 두 가지 뜻이다 — ① 정말 그런 곳이 없다 ② 검색어가 너무 넓어 서버가 끊었다.
      // 서버는 ②일 때 무거운 일을 하기 전에 0건으로 돌려주므로, 여기서 한 번 더 물어
      // 어느 쪽인지 가린다(0건일 때만 물으므로 평소 검색은 느려지지 않는다).
      if (rows.length === 0) {
        const scope = await supabase.rpc(SEARCH_SCOPE_FN, { q, sigungu });
        if (runId !== latestRun.current) return;
        const row = (scope.data ?? [])[0] as { too_broad?: boolean; match_cnt?: number } | undefined;
        if (row?.too_broad) {
          setNotice({ kind: 'broad', word: q, count: Number(row.match_cnt ?? 0) });
          setHits([]);
          setTotal(0);
          setSearched(false); // "결과가 없습니다"와 안내창이 겹쳐 보이지 않게
          return;
        }
      }

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
          {/* ⚠️ 구 단위 검색으로 바뀐 뒤에도 "전체 열린 지역"을 안내하면 엉뚱하다 —
              사용자는 이미 한 구를 골랐고, 없는 것은 **그 구 안에서** 없는 것이다. */}
          <strong>{sigunguName ?? '고른 지역'}</strong>에서 찾지 못했습니다. 건물 이름이나
          지번을 다시 확인해 주시거나, 위에서 다른 구를 골라 보세요.
        </p>
      )}

      {hits.length > 0 && (
        <>
          <p className="search__count">
            {sigunguName && `${sigunguName}에서 `}건물 {total.toLocaleString('ko-KR')}개
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

      {notice && (
        <div className="modal__back" onClick={() => setNotice(null)} role="presentation">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="scope-modal-title"
            onClick={(ev) => ev.stopPropagation()}
          >
            <h2 className="modal__title" id="scope-modal-title">
              {notice.kind === 'short' && '한 글자로는 찾을 수 없어요'}
              {notice.kind === 'no-region' && '먼저 지역을 골라 주세요'}
              {notice.kind === 'broad' && `‘${notice.word}’ — 너무 넓은 검색이에요`}
            </h2>
            <p className="modal__body">
              {notice.kind === 'broad' && (
                <>
                  이 검색어에는 <strong>{notice.count.toLocaleString('ko-KR')}곳</strong>이 걸립니다.{' '}
                </>
              )}
              {notice.kind === 'short' && (
                <>한 글자는 거의 모든 주소에 들어 있어서 어디를 볼지 정해지지 않습니다. </>
              )}
              {notice.kind === 'no-region' ? (
                <>
                  위에서 <strong>시·도와 구</strong>를 먼저 골라 주세요. 같은 건물 이름이 여러
                  구에 있을 수 있어서, 지역을 정해야 그 안에서만 정확하게 찾을 수 있습니다.
                </>
              ) : (
                <>
                  이 서비스는 <strong>건물 한 채·필지 한 곳</strong>을 놓고 상권을 분석합니다. 어느
                  곳인지 정해지지 않으면 옆 동네와 비교할 수도, 층별로 볼 수도 없어요.
                </>
              )}
            </p>
            {notice.kind !== 'no-region' && (
              <p className="modal__body">
                아래 셋 중 하나를 넣어 주세요.
                <br />· 동 이름 — <strong>역삼동</strong>, <strong>둔산동</strong>, <strong>명동</strong>
                <br />· 건물 이름 — <strong>그랑프리빌딩</strong>
                <br />· 지번·도로명 — <strong>역삼동 823-4</strong>, <strong>테헤란로 117</strong>
              </p>
            )}
            <button
              type="button"
              className="modal__close"
              ref={noticeCloseRef}
              onClick={() => setNotice(null)}
            >
              닫기
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
