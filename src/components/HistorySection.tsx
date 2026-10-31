import { useEffect, useRef, useState } from 'react';
import { supabase } from '../lib/supabase';
import { STORE_HISTORY_FN, STORE_HISTORY_PAGE } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import {
  HISTORY_BADGE,
  HISTORY_BADGE_NOTE,
  HISTORY_CHIP,
  HISTORY_CURRENT_HEAD,
  HISTORY_GONE_HEAD,
  HISTORY_GONE_HEAD_NOTE,
  HISTORY_LEAD_BOLD,
  HISTORY_LEAD_MID,
  HISTORY_LEAD_STRONG,
  countText,
  floorText,
  groupCounts,
  historyNotes,
  historySummary,
  isStoreHistoryList,
  lagText,
  moreCurrentText,
  moreText,
  rowText,
  skipToGoneText,
  type BoldText,
} from '../lib/storeHistory';
import { loadDataFreshness } from '../lib/loadDataFreshness';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';
import type { DataFreshnessRow, StoreHistoryRow } from '../types';

/**
 * 「이 자리 가게 이력 (점포 자료 누적)」 카드 — 결정 0045 PR④(본보기 = `SalesSection`·`OpenCloseSection`).
 *
 * ⛔ **그 땅(필지)의 점포 줄**이지 건물 값이 아니다 · D등급 · 보인 분기 수는 영업 기간이 아니다(글은 `lib/storeHistory.ts`).
 * ⛔ **함수 없음(PGRST202)·오류·모양 이상·0줄(적재 전)이면 카드째 숨긴다** — 「자료 없음」이라 적지 않는다.
 *    그 땅에 줄이 없으면(no_data 한 줄) 카드는 서되 요약 글만.
 * ⛔ 줄은 서버 차례 그대로 · 묶음은 `is_current` 로만 가른다(재정렬 0) · 「더 보기」는 서버 넘기기(p_offset).
 * ⛔ 묶음마다 제 커서(👤 11-01 · 보완 3 H-2) — 서버 차례는 지금 보임 전부 → 전에 보임 전부라, 전에 보임 묶음의 k번째 줄은
 *    p_offset = current_cnt + k 다. 지금 묶음이 덜 온 큰 땅도 「전에 보였던 가게 보기」로 그 묶음 첫 쪽을 받을 수 있다.
 * ⓘ 모든 지역(서울·대전)에 같은 카드다(전국 점포 자료).
 */

type GroupKey = 'cur' | 'past';
/** 지금 보임 묶음에 받은 줄 · 전에 보임 묶음에 받은 줄(각각 그 묶음 앞에서부터 빈틈 없이). */
type Groups = { cur: StoreHistoryRow[]; past: StoreHistoryRow[] };
const NO_DEAD: Record<GroupKey, boolean> = { cur: false, past: false };

/**
 * 첫 쪽(offset 0)을 두 묶음에 나눈다 — `placePage` 와 같은 자리 규칙. no_data 한 줄은 cur 에 둔다(그 줄만 그린다).
 * 서버 차례(지금 보임 전부 → 전에 보임)와 어긋나면 null(모양 이상과 같은 길 — 카드째 숨김).
 */
function firstPage(data: StoreHistoryRow[]): Groups | null {
  if (data[0].status === 'no_data') return { cur: data, past: [] };
  return placePage({ cur: [], past: [] }, data, 0, data[0].current_cnt);
}

/**
 * 서버 차례 `offset` 부터 온 쪽을 두 묶음에 놓는다 — 차례 a < current_cnt 면 지금 묶음 a번째, 아니면 전에 묶음 (a − current_cnt)번째.
 * 줄의 `is_current` 가 그 자리의 묶음과 다르면 null(버림). 이미 받은 자리는 건너뛰고(겹침 0), 빈틈 뒤 줄은 놓지 않는다.
 */
function placePage(groups: Groups, data: StoreHistoryRow[], offset: number, currentCnt: number): Groups | null {
  const cur = [...groups.cur];
  const past = [...groups.past];
  for (let j = 0; j < data.length; j++) {
    const a = offset + j;
    const inCur = a < currentCnt;
    if (data[j].is_current !== inCur) return null;
    const list = inCur ? cur : past;
    const at = inCur ? a : a - currentCnt;
    if (at === list.length) list.push(data[j]);
  }
  return { cur, past };
}
type Props = {
  /** 이 필지. 바뀌면 처음부터 다시 묻는다. */
  pnu: string;
  /** 부모가 건물을 고른 순간 먼저 보내 둔 요청(첫 쪽). 이 pnu 것이면 쓴다. */
  prefetch?: SidePrefetch | null;
  /** 이 카드의 배치. 안 주면 `SECTION_PLAN.history`. */
  plan?: SectionPlan;
};

export function HistorySection({ pnu, prefetch, plan = SECTION_PLAN.history }: Props) {
  /** 받아 온 줄 — 두 묶음 따로(보완 3 H-2 「묶음마다 제 커서」). 아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다. */
  const [groups, setGroups] = useState<Groups | null>(null);
  /** 신선도 표 — 어긋남 줄에만 쓴다(못 받으면 null · 그 줄만 없음). */
  const [freshness, setFreshness] = useState<DataFreshnessRow[] | null>(null);
  /** 단추를 묻는 중인 묶음(묻는 동안 단추 전부 비활성) · 실패해 그 묶음 단추를 거뒀는가. */
  const [loadingMore, setLoadingMore] = useState<GroupKey | null>(null);
  const [dead, setDead] = useState<Record<GroupKey, boolean>>(NO_DEAD);
  /** 지금 필지 — 늦게 온 「더 보기」 답이 다른 필지에 붙지 않게. */
  const pnuRef = useRef(pnu);

  useEffect(() => {
    let cancelled = false;
    pnuRef.current = pnu;
    // 필지가 바뀌면 옛 답·쪽 상태를 지운다 — 안 지우면 새 건물 밑에 앞 땅의 가게가 잠깐 붙는다.
    setGroups(null);
    setLoadingMore(null);
    setDead(NO_DEAD);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, STORE_HISTORY_FN, pnu) ?? supabase.rpc(STORE_HISTORY_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      // ⛔ 늦은 답은 버린다.
      if (cancelled) return;
      if (error || !isStoreHistoryList(data)) {
        console.warn('가게 이력 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      const first = firstPage(data);
      if (first === null) {
        console.warn('가게 이력 — 묶음 차례가 맞지 않아 그 카드 없이 표시합니다', data);
        return;
      }
      setGroups(first);
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  useEffect(() => {
    let cancelled = false;
    void loadDataFreshness().then((data) => {
      if (!cancelled) setFreshness(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (groups === null) return null;

  const { cur, past } = groups;
  const all = [...cur, ...past];
  const summary = historySummary(all);
  if (all[0].status === 'no_data') {
    return <SectionCard plan={plan} className="card--history hist hist--none" summary={summary} />;
  }

  const head = all[0];
  const counts = groupCounts(all);
  const lag = lagText(all, freshness);
  const notes = historyNotes(all);
  // 단추 셋(👤 11-01 · 보완 3 H-2) — 지금 묶음 아래 ⓐ · 전에 묶음이 비었고 지금 묶음이 덜 왔으면 그 자리에 건너뛰기 ⓑ ·
  // 전에 묶음 아래 ⓒ(지금 묶음이 다 왔거나 전에 묶음을 받기 시작했을 때 — 작은 땅은 ⓒ 하나라 예전 화면과 같다).
  const curLeft = cur.length < head.current_cnt;
  const showCurMore = curLeft && !dead.cur;
  const showSkip = curLeft && past.length === 0 && counts.gone > 0 && !dead.past;
  const showPastMore = past.length < counts.gone && (past.length > 0 || !curLeft) && !dead.past;

  /** 그 묶음의 다음 쪽 — 지금 묶음은 받은 지금 줄 뒤부터, 전에 묶음은 current_cnt + 받은 전에 줄 뒤부터. */
  const loadMore = (group: GroupKey) => {
    const askedPnu = pnu;
    const offset = group === 'cur' ? cur.length : head.current_cnt + past.length;
    setLoadingMore(group);
    const fail = (why: unknown, msg = '가게 이력 더 보기 실패 — 단추를 거둡니다') => {
      console.warn(msg, why);
      setDead((d) => ({ ...d, [group]: true }));
    };
    Promise.resolve(
      supabase.rpc(STORE_HISTORY_FN, { p_pnu: askedPnu, p_limit: STORE_HISTORY_PAGE, p_offset: offset }),
    ).then(
      ({ data, error }) => {
        if (pnuRef.current !== askedPnu) return;
        setLoadingMore(null);
        if (error || !isStoreHistoryList(data) || data[0].status !== 'ok') {
          fail(error ?? data);
          return;
        }
        if (data[0].total_cnt !== head.total_cnt || data[0].current_cnt !== head.current_cnt) {
          // 사이에 적재가 바뀌었다 — 이어 붙이면 줄이 겹치거나 빠진다.
          fail([data[0].total_cnt, data[0].current_cnt], '가게 이력 더 보기 — 그 사이 자료가 바뀌어 답을 버립니다');
          return;
        }
        const next = placePage(groups, data, offset, head.current_cnt);
        if (next === null) {
          // 이 자리에 와야 할 묶음과 줄의 is_current 가 다르다 — 사이에 적재가 바뀐 것과 같은 길.
          fail(data, '가게 이력 더 보기 — 묶음이 맞지 않아 답을 버립니다');
          return;
        }
        setGroups((prev) => (prev === groups ? next : prev));
      },
      (err: unknown) => {
        if (pnuRef.current !== askedPnu) return;
        setLoadingMore(null);
        fail(err);
      },
    );
  };

  return (
    <SectionCard plan={plan} className="card--history hist" summary={summary}>
      <p className="hist__lead">
        <strong>{HISTORY_LEAD_STRONG}</strong>
        {HISTORY_LEAD_MID}
        <b>{HISTORY_LEAD_BOLD}</b>
      </p>
      <p className="hist__badge-line">
        <span className="grade__badge grade__badge--est">{HISTORY_BADGE}</span>
        <span className="hist__q">{HISTORY_BADGE_NOTE}</span>
      </p>
      {lag && (
        <p className="hist__lag">
          <Bold text={lag} />
        </p>
      )}

      {cur.length > 0 && (
        <div className="hist__grp">
          <p className="hist__grp-h">
            <b>{HISTORY_CURRENT_HEAD}</b> {countText(counts.current)}곳
          </p>
          <ul className="hist__rows">
            {/* 줄 key = 묶음 안 차례 번호(서버 차례 고정 · 쪽은 그 묶음 뒤에 붙기만 한다 — 보완 1 F-2). */}
            {cur.map((r, i) => (
              <HistoryRow key={i} row={r} />
            ))}
          </ul>
        </div>
      )}
      {(showCurMore || showSkip) && (
        <div className="hist__mores">
          {showCurMore && (
            <button type="button" className="hist__more" disabled={loadingMore !== null} onClick={() => loadMore('cur')}>
              {moreCurrentText(cur.length, head.current_cnt)}
            </button>
          )}
          {showSkip && (
            <button
              type="button"
              className="hist__more hist__more--skip"
              disabled={loadingMore !== null}
              onClick={() => loadMore('past')}
            >
              {skipToGoneText(counts.gone)}
            </button>
          )}
        </div>
      )}
      {past.length > 0 && (
        <div className="hist__grp">
          <p className="hist__grp-h">
            <b>{HISTORY_GONE_HEAD}</b> {countText(counts.gone)}곳 <span className="hist__q">{HISTORY_GONE_HEAD_NOTE}</span>
          </p>
          <ul className="hist__rows">
            {past.map((r, i) => (
              <HistoryRow key={i} row={r} />
            ))}
          </ul>
        </div>
      )}
      {showPastMore && (
        <div className="hist__mores">
          <button type="button" className="hist__more" disabled={loadingMore !== null} onClick={() => loadMore('past')}>
            {moreText(past.length, counts.gone)}
          </button>
        </div>
      )}

      <ul className="card__note hist__notes">
        <li>{notes.source}</li>
        <li>
          <strong>{notes.gone[0]}</strong>
          {notes.gone[1]}
        </li>
        <li>{notes.name}</li>
      </ul>
    </SectionCard>
  );
}

function Bold({ text }: { text: BoldText }) {
  return (
    <>
      {text.pre}
      {text.bold && <b>{text.bold}</b>}
      {text.post}
    </>
  );
}

/** 가게 한 줄 — 층 칸 + 상호(+ 안 보임 칩) + 설명. */
function HistoryRow({ row }: { row: StoreHistoryRow }) {
  return (
    <li className={row.is_current ? 'hist__row' : 'hist__row hist__row--gone'}>
      <span className="hist__fl">{floorText(row.floor_no)}</span>
      <span className="hist__body">
        <span className="hist__nm">{row.biz_name}</span>
        {!row.is_current && <span className="hist__chip">{HISTORY_CHIP}</span>}
        <br />
        <span className="hist__sp">
          <Bold text={rowText(row)} />
        </span>
      </span>
    </li>
  );
}
