import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { DISTRICT_CENSUS_POP_FN } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import { districtTitle } from '../lib/districtSales';
import {
  CENSUS_BADGE,
  CENSUS_CHUNK_TITLES,
  CENSUS_LEAD_REST,
  CENSUS_LEAD_STRONG,
  CENSUS_NOTES,
  CENSUS_NO_DATA_TEXT,
  CENSUS_POP_TITLE,
  censusBadgeNote,
  censusHeadBody,
  censusHeadRow,
  censusNote,
  censusSourceText,
  censusSummary,
  empBig,
  isDistrictCensusPopList,
  residentBig,
  type CensusBig,
} from '../lib/districtCensusPop';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';
import type { DistrictCensusPop } from '../types';

/**
 * 대전 건물의 「상권 인구 (통계청 집계구)」 카드 — 결정 0045 PR⑤(본보기 = 서울 카드 `PopSection` · 제목·자료 갈래만
 * 바꿔 끼우는 꼴은 결정 0044 의 `DaejeonCard`).
 *
 * ⛔ **서버 값 그대로다.** 값·하한·상한을 쉼표만 찍어 적는다 · 「범위가 값의 2배 넘으면 범위만」은 `lib/districtCensusPop.ts` 의 비교 하나.
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 대전 상권 안의 합계(어림)다. 상권이 여럿이면 상권마다 한 덩어리(서버 차례 그대로).
 * ⛔ **연도 글자를 박지 않는다**(시험이 이 파일 원문을 훑는다) — 연도는 서버 표지 칸에서. 계산은 전부 lib 에.
 * ⓘ 대전 필지에만 그린다(FloorStack 이 고른다). 함수가 없거나·오류·모양 이상·0줄(표지 없음)이면 카드째 숨긴다.
 */
type Props = {
  pnu: string;
  prefetch?: SidePrefetch | null;
  /** 이 카드의 배치(역할별 자리·펼침). 안 주면 `SECTION_PLAN.pop` · 제목·자료 갈래는 이 카드 것으로 바꿔 끼운다. */
  plan?: SectionPlan;
};

export function CensusPopSection({ pnu, prefetch, plan = SECTION_PLAN.pop }: Props) {
  const [rows, setRows] = useState<DistrictCensusPop[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다.
    setRows(null);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, DISTRICT_CENSUS_POP_FN, pnu) ??
      supabase.rpc(DISTRICT_CENSUS_POP_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      // ⛔ 늦은 답은 버린다.
      if (cancelled) return;
      if (error || !isDistrictCensusPopList(data)) {
        // 0줄(표지 없음)도 여기로 온다 — 「자료 없음」이라 적지 않고 카드째 숨긴다.
        console.warn('통계청 집계구 상권 인구 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  if (rows === null) return null;

  const cardPlan: SectionPlan = { ...plan, title: CENSUS_POP_TITLE, sources: ['census_pop'] };
  const summary = censusSummary(rows, pnu);
  const head = censusHeadRow(rows);
  const source = censusSourceText(rows[0]);

  if (head) {
    return (
      <SectionCard plan={cardPlan} className="pop pop--census pop--none" summary={summary}>
        <p className="pop__lead">{censusHeadBody(head.status, pnu)}</p>
        <p className="pop__src">{source}</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard plan={cardPlan} className="pop pop--census" summary={summary}>
      <p className="pop__lead">
        <strong>{CENSUS_LEAD_STRONG}</strong>
        {CENSUS_LEAD_REST[0]}
        <b>{CENSUS_LEAD_REST[1]}</b>
        {CENSUS_LEAD_REST[2]}
      </p>
      <p className="pop__badge-line">
        <span className="grade__badge grade__badge--est">{CENSUS_BADGE}</span>
        <span className="pop__badge-note">{censusBadgeNote(rows[0])}</span>
      </p>

      {rows.map((r) => (
        <CensusBlock key={r.district_id ?? r.status} row={r} />
      ))}

      <ul className="pop__why">
        <li className="pop__src">{source}</li>
        <li>
          <strong>{CENSUS_NOTES.notBuilding}</strong>
        </li>
        <li>{CENSUS_NOTES.method}</li>
        <li>{CENSUS_NOTES.empNotWorker}</li>
        <li>{CENSUS_NOTES.next}</li>
      </ul>
    </SectionCard>
  );
}

/** 상권 하나의 덩어리 — 사는 사람(가구 포함) · 사업체 종사자 · 발 한 줄. 상권끼리 더하지 않는다. */
function CensusBlock({ row }: { row: DistrictCensusPop }) {
  const title = districtTitle(row);
  const resident = residentBig(row);
  const emp = empBig(row);
  if (row.status === 'no_data' || (!resident && !emp)) {
    return (
      <div className="pop__district pop__district--nodata">
        <p className="pop__name">{title}</p>
        <p className="pop__none">{CENSUS_NO_DATA_TEXT}</p>
      </div>
    );
  }
  const note = censusNote(row);
  return (
    <div className="pop__district">
      <p className="pop__name">{title}</p>
      {resident && (
        <div className="pop__chunk pop__chunk--resident">
          <p className="pop__chunk-h">{CENSUS_CHUNK_TITLES.resident}</p>
          <Big big={resident} />
        </div>
      )}
      {emp && (
        <div className="pop__chunk pop__chunk--emp">
          <p className="pop__chunk-h">{CENSUS_CHUNK_TITLES.emp}</p>
          <Big big={emp} />
        </div>
      )}
      {note && <p className="pop__note">{note}</p>}
    </div>
  );
}

function Big({ big }: { big: CensusBig }) {
  return (
    <p className="pop__big">
      <strong className="pop__num">{big.num}</strong>
      {big.range && <span className="pop__q">{big.range}</span>}
      {big.detail && <span>{big.detail}</span>}
    </p>
  );
}
