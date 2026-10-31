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
  moreText,
  rowText,
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
 * ⓘ 모든 지역(서울·대전)에 같은 카드다(전국 점포 자료).
 */
type Props = {
  /** 이 필지. 바뀌면 처음부터 다시 묻는다. */
  pnu: string;
  /** 부모가 건물을 고른 순간 먼저 보내 둔 요청(첫 쪽). 이 pnu 것이면 쓴다. */
  prefetch?: SidePrefetch | null;
  /** 이 카드의 배치. 안 주면 `SECTION_PLAN.history`. */
  plan?: SectionPlan;
};

export function HistorySection({ pnu, prefetch, plan = SECTION_PLAN.history }: Props) {
  /** 받아 온 줄들(쪽을 이어 붙인 것). 아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다. */
  const [rows, setRows] = useState<StoreHistoryRow[] | null>(null);
  /** 신선도 표 — 어긋남 줄에만 쓴다(못 받으면 null · 그 줄만 없음). */
  const [freshness, setFreshness] = useState<DataFreshnessRow[] | null>(null);
  /** 「더 보기」를 묻는 중 · 실패해 단추를 거뒀는가. */
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreDead, setMoreDead] = useState(false);
  /** 지금 필지 — 늦게 온 「더 보기」 답이 다른 필지에 붙지 않게. */
  const pnuRef = useRef(pnu);

  useEffect(() => {
    let cancelled = false;
    pnuRef.current = pnu;
    // 필지가 바뀌면 옛 답·쪽 상태를 지운다 — 안 지우면 새 건물 밑에 앞 땅의 가게가 잠깐 붙는다.
    setRows(null);
    setLoadingMore(false);
    setMoreDead(false);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, STORE_HISTORY_FN, pnu) ?? supabase.rpc(STORE_HISTORY_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      // ⛔ 늦은 답은 버린다.
      if (cancelled) return;
      if (error || !isStoreHistoryList(data)) {
        console.warn('가게 이력 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
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

  if (rows === null) return null;

  const summary = historySummary(rows);
  if (rows[0].status === 'no_data') {
    return <SectionCard plan={plan} className="card--history hist hist--none" summary={summary} />;
  }

  const head = rows[0];
  const counts = groupCounts(rows);
  const lag = lagText(rows, freshness);
  const notes = historyNotes(rows);
  // 줄 key = 받은 차례 번호(서버 차례 고정 · 「더 보기」는 뒤에 붙기만 한다 — 보완 1 F-2). 보이는 칸이 전부 같은 줄 둘
  // (같은 가게가 번호 둘로 올라 있던 꼴)도 둘 다 그린다.
  const numbered = rows.map((r, i) => ({ r, i }));
  const current = numbered.filter((x) => x.r.is_current);
  const gone = numbered.filter((x) => !x.r.is_current);
  const canMore = rows.length < head.total_cnt && !moreDead;

  const loadMore = () => {
    const askedPnu = pnu;
    const offset = rows.length;
    setLoadingMore(true);
    Promise.resolve(
      supabase.rpc(STORE_HISTORY_FN, { p_pnu: askedPnu, p_limit: STORE_HISTORY_PAGE, p_offset: offset }),
    ).then(
      ({ data, error }) => {
        if (pnuRef.current !== askedPnu) return;
        setLoadingMore(false);
        if (error || !isStoreHistoryList(data) || data[0].status !== 'ok') {
          console.warn('가게 이력 더 보기 실패 — 단추를 거둡니다', error ?? data);
          setMoreDead(true);
          return;
        }
        if (data[0].total_cnt !== head.total_cnt) {
          // 사이에 적재가 바뀌었다 — 이어 붙이면 줄이 겹치거나 빠진다.
          console.warn('가게 이력 더 보기 — 그 사이 자료가 바뀌어 답을 버립니다', data[0].total_cnt, head.total_cnt);
          setMoreDead(true);
          return;
        }
        setRows((prev) => (prev && prev.length === offset ? [...prev, ...data] : prev));
      },
      (err: unknown) => {
        if (pnuRef.current !== askedPnu) return;
        setLoadingMore(false);
        console.warn('가게 이력 더 보기 실패 — 단추를 거둡니다', err);
        setMoreDead(true);
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

      {current.length > 0 && (
        <div className="hist__grp">
          <p className="hist__grp-h">
            <b>{HISTORY_CURRENT_HEAD}</b> {countText(counts.current)}곳
          </p>
          <ul className="hist__rows">
            {current.map((x) => (
              <HistoryRow key={x.i} row={x.r} />
            ))}
          </ul>
        </div>
      )}
      {gone.length > 0 && (
        <div className="hist__grp">
          <p className="hist__grp-h">
            <b>{HISTORY_GONE_HEAD}</b> {countText(counts.gone)}곳 <span className="hist__q">{HISTORY_GONE_HEAD_NOTE}</span>
          </p>
          <ul className="hist__rows">
            {gone.map((x) => (
              <HistoryRow key={x.i} row={x.r} />
            ))}
          </ul>
        </div>
      )}
      {canMore && (
        <button type="button" className="hist__more" disabled={loadingMore} onClick={loadMore}>
          {moreText(rows.length, head.total_cnt)}
        </button>
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
