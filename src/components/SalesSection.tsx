import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { DISTRICT_SALES_FN } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import {
  SALES_BADGE,
  SALES_BADGE_NOTE,
  SALES_GAP_NOTE,
  SALES_LEAD_REST,
  SALES_LEAD_STRONG,
  SALES_NOTES,
  districtTitle,
  formatAmount,
  formatCount,
  headBody,
  isDistrictSalesList,
  salesBigText,
  salesLagText,
  salesNoDataText,
  salesScaleMax,
  salesScaleText,
  salesSummary,
  salesTableRows,
  salesTrendCells,
} from '../lib/districtSales';
import { openCloseQuarterLabel } from '../lib/openClose';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';
import { FOUNDER_CHIP_ALL, type FounderChip } from '../lib/founderChips';
import type { DistrictSales } from '../types';

/**
 * 「업종별 추정매출 (서울시 추정)」 카드 — 결정 0045 PR③(본보기 = 개업·폐업 카드 `OpenCloseSection`).
 *
 * ⛔ **공표값 그대로다.** 금액·건수는 서울시가 공표한 분기(3개월) 합계 — 화면이 나누지 않는다(👤 결정 ①).
 *    이 화면의 산수는 막대의 높이·길이뿐이다(계산은 전부 `lib/districtSales.ts`).
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 서울시 상권 전체의 값이다 — 첫 줄과 발 문구가 같은 말을 한다.
 *    상권이 여럿이면 합치지 않고 상권마다 한 덩어리다.
 * ⛔ **분기·연도 글자를 박지 않는다**(서버 창이 정한다 · 시험이 이 파일 원문을 훑는다).
 * ⓘ 서울 필지에만 그린다(FloorStack 이 고른다 — 서울 밖은 빈 카드). 함수가 없거나 모양이 이상하면 카드째 숨긴다.
 */
type Props = {
  /** 이 필지. 바뀌면 처음부터 다시 묻는다. */
  pnu: string;
  /** 부모가 건물을 고른 순간 먼저 보내 둔 요청. 이 pnu 것이면 쓴다. */
  prefetch?: SidePrefetch | null;
  /** 이 카드의 배치. 안 주면 `SECTION_PLAN.sales`. */
  plan?: SectionPlan;
  /** 창업자가 고른 업종 칩 — 짝 업종 줄을 굵게 하고, 상위 5 밖이면 따로 한 줄, 없으면 없다고 적는다. */
  chip?: FounderChip;
};

export function SalesSection({ pnu, prefetch, plan = SECTION_PLAN.sales, chip = FOUNDER_CHIP_ALL }: Props) {
  /** 받아 온 줄들. 아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다(둘 다 아무것도 안 그린다). */
  const [rows, setRows] = useState<DistrictSales[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다 — 안 지우면 새 건물 밑에 앞 건물 상권의 숫자가 잠깐 붙는다.
    setRows(null);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, DISTRICT_SALES_FN, pnu) ?? supabase.rpc(DISTRICT_SALES_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      // ⛔ 늦은 답은 버린다 — 그 사이 필지가 바뀌었으면 앞 건물 상권의 숫자가 새 건물 밑에 붙는다.
      if (cancelled) return;
      if (error || !isDistrictSalesList(data)) {
        console.warn('상권 추정매출 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  if (rows === null) return null;

  const summary = salesSummary(rows, pnu);
  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');

  // ⛔ 서울 밖·상권 밖·좌표 없음에서도 카드는 선다 — 왜 숫자가 없는지가 곧 이 자리의 답이다.
  if (head) {
    return (
      <SectionCard plan={plan} className="sales sales--none" summary={summary}>
        <p className="sales__lead">{headBody(head.status, pnu)}</p>
        <p className="sales__src">{SALES_NOTES.source}</p>
      </SectionCard>
    );
  }

  // 카드 하나에 눈금 하나 — 상권끼리 같은 높이가 같은 금액이 되게 한다.
  const scaleMax = salesScaleMax(rows);

  return (
    <SectionCard plan={plan} className="sales" summary={summary}>
      <p className="sales__lead">
        <strong>{SALES_LEAD_STRONG}</strong>
        {SALES_LEAD_REST[0]}
        <b>{SALES_LEAD_REST[1]}</b>
        {SALES_LEAD_REST[2]}
      </p>
      <p className="sales__badge-line">
        <span className="grade__badge grade__badge--est">{SALES_BADGE}</span>
        <span className="sales__q">{SALES_BADGE_NOTE}</span>
      </p>
      {scaleMax > 0 && <p className="sales__scale">{salesScaleText(scaleMax)}</p>}

      {rows.map((r) => (
        <SalesBlock key={r.district_id ?? r.status} row={r} scaleMax={scaleMax} chip={chip} />
      ))}

      <ul className="sales__why">
        <li className="sales__src">{SALES_NOTES.source}</li>
        <li>
          <strong>{SALES_NOTES.notBuilding[0]}</strong>
          {SALES_NOTES.notBuilding[1]}
        </li>
        <li>{SALES_NOTES.unit}</li>
        <li>{SALES_NOTES.method}</li>
        <li>{SALES_NOTES.industry}</li>
      </ul>
    </SectionCard>
  );
}

/** 상권 하나의 덩어리. 상권끼리 더하지 않는다. */
function SalesBlock({ row, scaleMax, chip }: { row: DistrictSales; scaleMax: number; chip: FounderChip }) {
  const title = districtTitle(row);
  if (row.status === 'no_data') {
    return (
      <div className="sales__district sales__district--nodata">
        <p className="sales__name">{title}</p>
        <p className="sales__none">{salesNoDataText(row)}</p>
      </div>
    );
  }
  const big = salesBigText(row);
  const label = openCloseQuarterLabel(row.latest_quarter);
  // 모양 검사가 ok 줄에는 최신 분기가 있음을 보장한다 — 그래도 없으면 덩어리째 뺀다.
  if (!big || !label) return null;
  const lag = salesLagText(row);
  const cells = salesTrendCells(row, scaleMax);
  const table = salesTableRows(row, chip);

  return (
    <div className="sales__district">
      <p className="sales__name">{title}</p>
      <p className="sales__big">
        <strong className="sales__num">{big.amount}</strong>
        <span>{big.count}</span>
        <span className="sales__q">{big.industries}</span>
      </p>
      {lag && <p className="sales__note">{lag}</p>}

      {cells.length > 0 && (
        <figure className="sales__trend">
          <figcaption className="sales__trend-cap">
            <b>분기별 매출 흐름</b>
            <span className="sales__dir">왼쪽이 옛 분기, 오른쪽이 최근 · 3개월 합</span>
          </figcaption>
          <div className="sales__cols" style={{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }}>
            {cells.map((c, i) => (
              <div key={c.quarter} className={`sales__col sales__col--${c.kind}`} data-quarter={c.quarter}>
                <div className="sales__bars">
                  {c.kind === 'ok' ? (
                    <span
                      className={c.last ? 'sales__bar sales__bar--last' : 'sales__bar'}
                      role="img"
                      aria-label={`${c.label} 매출 ${formatAmount(c.amt)} · 결제 ${formatCount(c.co, '건')} (3개월 합)`}
                      title={`${c.label} 매출 ${formatAmount(c.amt)} · 결제 ${formatCount(c.co, '건')} (3개월 합)`}
                      style={{ height: `${c.h}%` }}
                    />
                  ) : (
                    <span className="sales__gap" role="img" aria-label={`${c.label} 자료 없음`} title={`${c.label} 자료 없음`}>
                      –
                    </span>
                  )}
                </div>
                <span className="sales__tick">
                  <span className="sales__tick-q">{c.q ? `${c.q}분기` : ''}</span>
                  {(i === 0 || c.q === '1') && c.year ? <span className="sales__tick-year">{`${c.year}년`}</span> : null}
                </span>
              </div>
            ))}
          </div>
          {cells.some((c) => c.kind === 'missing') && <p className="sales__note">{SALES_GAP_NOTE}</p>}
        </figure>
      )}

      {table.rows.length > 0 && (
        <table className="sales__table" aria-label="업종별 추정매출 상위 5">
          <thead>
            <tr>
              <th scope="col">{`업종 (${label})`}</th>
              <th scope="col">3개월 매출</th>
              <th scope="col">결제</th>
              <th scope="col" aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {table.rows.map((t) => (
              <tr key={t.cd} className={t.hit ? 'sales__hit' : undefined}>
                <th scope="row">
                  {t.hit ? <strong>{t.name}</strong> : t.name}
                  {t.hit && table.hitTail && <span className="sales__hit-tail">{table.hitTail}</span>}
                </th>
                <td>{t.amount}</td>
                <td>{t.count}</td>
                <td className="sales__w" aria-hidden="true">
                  <i style={{ width: `${t.w}%` }} />
                </td>
              </tr>
            ))}
            {table.rest && (
              <tr className="sales__rest">
                <th scope="row">{table.rest.label}</th>
                <td>{table.rest.amount}</td>
                <td>{table.rest.count}</td>
                <td className="sales__w" aria-hidden="true" />
              </tr>
            )}
          </tbody>
        </table>
      )}
      {table.chipOutside.map((t) => (
        <p key={t} className="sales__note sales__chip-out">
          {t}
        </p>
      ))}
      {table.chipNone && <p className="sales__note sales__chip-none">{table.chipNone}</p>}
      {table.chipPartial && <p className="sales__note sales__chip-part">{table.chipPartial}</p>}
    </div>
  );
}
