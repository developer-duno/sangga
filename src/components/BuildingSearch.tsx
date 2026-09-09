import { useEffect, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';
import { supabase } from '../lib/supabase';
import {
  SEARCH_BUILDINGS_FN,
  SEARCH_SCOPE_FN,
  SEARCH_STORES_FN,
  SEARCH_STORES_PAGE,
} from '../lib/appConstants';
import { describeError, describeRange, formatMonthKo } from '../lib/format';
import {
  hasMoreStores,
  isStoreHitList,
  matchedLabel,
  readStoreAnswer,
  storeToHit,
  type RpcAnswer,
  type StoreState,
} from '../lib/storeSearch';
import type { BuildingHit, StoreHit } from '../types';

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
 *
 * 2026-09-09부터 **가게 이름으로도 찾는다**(결정 0028)
 * -----------------------------------------------------
 * 창업자는 건물 이름을 모른다 — "스타벅스 있는 건물"로 찾는다. 그래서 검색 한 번에 서버를
 * **둘** 부르고(건물 · 가게 이름) 결과를 두 구역으로 나란히 그린다. 사용자가 고를 것은 없다.
 *
 * ⛔ 두 질의를 **한 함수로 합치지 않는다** — `search_buildings` 에 상호 가지를 더하면 가지
 *    2→3 에 763→1,550ms 다(알려진한계 §4).
 * ⛔ 가게 구역의 한 줄은 **건물이 아니라 땅(필지)** 이다(점포는 필지 단위로만 셀 수 있다).
 *    그래서 문구는 "이 **땅에** 가게 N곳"이지 "이 건물의 가게"가 아니다(결정 0025 의 함정).
 * ⛔ 실패는 **구역별로 따로** 다룬다 — 한쪽이 죽어도 다른 쪽 결과는 산다.
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
  /** 가게 이름 구역(결정 0028). 건물 구역과 **상태를 따로** 든다 — 한쪽이 죽어도 다른 쪽은 산다. */
  const [store, setStore] = useState<StoreState>({ at: 'hidden' });
  /** '더 보기'로 다음 쪽을 받는 중인가. 검색 자체의 `loading` 과 다른 일이다. */
  const [moreLoading, setMoreLoading] = useState(false);
  /** 더 받다가 실패했다 — 이미 받은 목록은 그대로 두고 그 사실만 알린다(0025 규칙). */
  const [moreFailed, setMoreFailed] = useState(false);
  /**
   * 늦게 도착한 옛 검색 응답이 최신 결과를 덮는 것을 막는다.
   *
   * ⛔ **건물 질의와 가게 질의가 이 번호 하나를 함께 본다**(결정 0028 결정 4). 구역마다
   *    번호를 따로 두면 새 검색이 한쪽만 무효로 만들 수 있어, 화면 위쪽은 새 검색어의
   *    건물을 말하는데 아래쪽은 옛 검색어의 가게를 말하는 상태가 생긴다.
   */
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
    // 가게 구역도 **먼저 비운다** — 안 비우면 새 답이 올 때까지 옛 검색어의 가게가 서 있다.
    setStore({ at: 'hidden' });
    setMoreFailed(false);
    onSearchStart(); // 새 검색 = 이전 선택 해제(아래 스택뷰가 옛 건물을 계속 그리지 않게)
    try {
      /*
        검색어는 파라미터로 넘어간다 — % _ \ 를 서버가 리터럴로 이스케이프하므로
        여기서 따로 손대지 않는다(직접 문자열을 이어 붙이면 필터가 깨진다).

        ⛔ 둘을 **나란히** 보내고 `allSettled` 로 받는다(결정 0028 결정 4). `all` 이면 가게
           질의가 던지는 순간 건물 결과까지 통째로 버려진다 — 부분 실패는 부분으로 다뤄야 한다.
        ⓘ 건물 질의를 **먼저** 적는다. 두 요청은 어차피 겹쳐 나가지만, 이 순서가 곧 화면의
          순서이고 시험이 "첫 호출이 무엇을 어떻게 넘겼는가"를 보는 자리이기도 하다.
      */
      const [bldRes, storeRes] = (await Promise.allSettled([
        supabase.rpc(SEARCH_BUILDINGS_FN, { q, lim: MAX_BUILDINGS, sigungu }),
        supabase.rpc(SEARCH_STORES_FN, {
          q,
          lim: SEARCH_STORES_PAGE,
          sigungu,
          p_offset: 0,
        }),
      ])) as [PromiseSettledResult<RpcAnswer>, PromiseSettledResult<RpcAnswer>];

      if (runId !== latestRun.current) return; // 그새 새 검색이 시작됐다

      setStore(readStoreAnswer(storeRes, q));

      if (bldRes.status === 'rejected') throw bldRes.reason;
      const { data, error: err } = bldRes.value;
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

  /**
   * 가게 이름 결과의 다음 쪽(50곳)을 받아 뒤에 잇는다.
   *
   * ⛔ 여기서는 `latestRun` 을 **올리지 않고 지금 값을 적어 둔다**. 올리면 그 순간 날아가 있는
   *    다른 요청(0건일 때 뒤따라 묻는 `search_scope`)까지 함께 무효가 돼, 눌러도 안 뜨는
   *    "너무 넓은 검색" 안내가 된다. 새 검색이 시작되면 그쪽이 번호를 올리므로 이 쪽은
   *    그때 저절로 버려진다 — 막으려던 것은 정확히 그 경우다.
   */
  function loadMoreStores(rows: StoreHit[]) {
    const runId = latestRun.current;
    setMoreLoading(true);
    setMoreFailed(false);
    supabase
      .rpc(SEARCH_STORES_FN, {
        q: query.trim(),
        lim: SEARCH_STORES_PAGE,
        sigungu,
        p_offset: rows.length,
      })
      .then(({ data, error: err }) => {
        if (runId !== latestRun.current) return; // 그새 새 검색이 시작됐다
        setMoreLoading(false);
        if (err || !isStoreHitList(data)) {
          console.warn('가게 이름 결과 더 보기 실패', err ?? data);
          setMoreFailed(true);
          return;
        }
        setStore((prev) =>
          // 받아 온 사이에 구역이 통째로 바뀌었으면(실패·새 검색) 이어 붙이지 않는다.
          prev.at === 'done' ? { at: 'done', rows: [...prev.rows, ...data] } : prev,
        );
      });
  }

  const shownAll = total > 0 && total <= hits.length;

  return (
    <section className="search">
      {/* ⛔ `aria-label` 은 **바꾸지 않는다** — 이 이름을 부르는 시험이 vitest 9곳·E2E 2곳이고,
          바꾸면 그 전부가 한꺼번에 깨진다. 무엇을 더 찾을 수 있는지는 placeholder 가 말한다
          (결정 0028 결정 4). */}
      <form onSubmit={runSearch} className="search__form">
        <input
          className="search__input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="건물명 · 도로명주소 · 지번 · 가게 이름 (예: 미도맨션, 테헤란로 117, 역삼동 823-4, 스타벅스)"
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

      {/*
        ── 가게 이름으로 찾은 땅 (결정 0028) ────────────────────────────────
        ⛔ 반드시 `<section className="search">` 의 **자손**이어야 한다 — `.search` 가
           `@media print` 에서 통째로 빠지므로, 형제로 빼면 이 구역만 종이에 남는다.
        ⛔ `hidden` 상태에서는 아무것도 그리지 않는다(0건 · 서버에 함수가 아직 없음).
      */}
      {store.at === 'failed' && (
        <section className="search__stores" aria-label="가게 이름으로 찾은 땅">
          {/* ⛔ 조용히 생략하지 않는다 — 사람이 누른 결과다(0025 규칙). */}
          <p className="msg msg--error" role="alert">
            가게 이름 결과를 불러오지 못했습니다.
          </p>
        </section>
      )}

      {store.at === 'broad' && (
        <section className="search__stores" aria-label="가게 이름으로 찾은 땅">
          {/*
            ⓘ 건물 쪽처럼 **안내창(모달)을 띄우지 않는다.** 건물 결과는 멀쩡히 서 있을 수
              있는데 그 위를 덮으면 사람이 이미 얻은 답을 가린다. 문구는 건물 안내창의 뜻을
              그대로 빌리되("더 좁혀 주세요") 숫자는 가게 수다.
          */}
          <p className="msg">
            ‘{store.word}’ 이름의 가게가{' '}
            <strong>{store.count.toLocaleString('ko-KR')}곳</strong>입니다 — 더 좁혀 주세요.
          </p>
        </section>
      )}

      {store.at === 'done' && (
        <section className="search__stores" aria-label="가게 이름으로 찾은 땅">
          <p className="search__count">
            이 이름의 가게가 있는 땅 {store.rows[0].total_parcel_cnt.toLocaleString('ko-KR')}곳 ·
            가게 {store.rows[0].total_store_cnt.toLocaleString('ko-KR')}곳
            {/* ⛔ 분기를 화면에 글자로 박지 않는다 — 서버가 준 값을 옮길 뿐이다. */}
            {formatMonthKo(store.rows[0].store_snapshot_ym) && (
              <span className="stores__stamp">
                {' '}
                · {formatMonthKo(store.rows[0].store_snapshot_ym)} 기준 점포 자료
              </span>
            )}
          </p>
          <ul className="stores">
            {store.rows.map((s) => {
              const names = matchedLabel(s);
              const many = (s.bld_cnt_in_pnu ?? 1) > 1;
              const body = (
                <>
                  <span className="stores__name">{s.bld_nm || '(이름 없는 건물)'}</span>
                  <span className="stores__addr">{s.road_addr || '주소 없음'}</span>
                  {s.jibun_addr && <span className="stores__jibun">지번 {s.jibun_addr}</span>}
                  {names && <span className="stores__names">{names}</span>}
                  <span className="stores__meta">
                    {/* ⛔ "이 건물의 가게"가 아니라 **이 땅에** 다 — 층별 화면의 점포 칸과
                        세는 대상이 다르다(결정 0025 의 함정). */}
                    이 땅에 가게 {(s.match_store_cnt ?? 0).toLocaleString('ko-KR')}곳 일치
                    {many && (
                      <span className="stores__warn"> · 같은 땅에 {s.bld_cnt_in_pnu}동</span>
                    )}
                  </span>
                </>
              );
              /*
                ⚠️ 대표 동이 없을 수 있다(그 땅에 건물 기록이 없는 경우). 그때는 누를 곳이
                   없으므로 **버튼이 아니라 그냥 줄**로 그리고 왜 못 가는지 적는다 —
                   목록에서 빼 버리면 "그 이름의 가게가 여기 없다"는 거짓말이 된다.
              */
              const bldId = s.bld_id;
              return (
                <li key={s.pnu}>
                  {bldId === null || bldId === undefined ? (
                    <div className="stores__row stores__row--flat">
                      {body}
                      <span className="stores__note">
                        건물 자료가 없어 층별 화면으로 갈 수 없습니다
                      </span>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className={`stores__row${bldId === selectedBldId ? ' stores__row--on' : ''}`}
                      onClick={() => onSelect(storeToHit({ ...s, bld_id: bldId }))}
                    >
                      {body}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>

          {hasMoreStores(store.rows) && (
            <button
              type="button"
              className="stores__more"
              disabled={moreLoading}
              onClick={() => loadMoreStores(store.rows)}
            >
              {moreLoading ? '불러오는 중…' : '더 보기'}
            </button>
          )}
          {moreFailed && (
            <p className="msg msg--error" role="alert">
              더 불러오지 못했습니다.
            </p>
          )}

          {/* ⛔ 무엇을 센 숫자인지 밝힌다(상권 건물 목록과 같은 규칙). */}
          <p className="stores__src">
            가게 수는 <strong>그 땅 전체</strong>를 센 것이라, 한 땅에 여러 동이 서 있으면 그
            동들이 같은 수를 함께 씁니다. 몇 층인지는 건물을 고른 뒤 층별 화면에서 봅니다.
          </p>
        </section>
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
