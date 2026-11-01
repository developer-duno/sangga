import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { DISTRICT_POP_FN, NEARBY_SUBWAY_FN } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import { districtTitle, formatCount, headBody } from '../lib/districtSales';
import {
  POP_BADGE,
  POP_BADGE_NOTE,
  POP_BAR_GROUPS,
  POP_CHUNK_TITLES,
  POP_LEAD_REST,
  POP_LEAD_STRONG,
  POP_NOTES,
  POP_NO_DATA_TEXT,
  flowBars,
  flowBigText,
  flowLagText,
  isDistrictPopList,
  normalizePopRows,
  popSummary,
  residentLagText,
  residentText,
  workerLagText,
  workerText,
  type FlowBars,
  type PopBig,
} from '../lib/districtPop';
import {
  SUBWAY_BADGE,
  SUBWAY_CHUNK_TITLE,
  SUBWAY_NOTES,
  isNearbySubwayList,
  subwayBars,
  subwayNoStationText,
  subwayNumbers,
  subwayShows,
  subwayStationLine,
  subwaySummaryTail,
} from '../lib/subwayNearby';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';
import type { DistrictPop, NearbySubway } from '../types';

/**
 * 「상권 인구 (서울시 공표)」 카드 — 결정 0045 PR③(본보기 = 개업·폐업 카드 `OpenCloseSection`).
 *
 * ⛔ **공표값 그대로다.** 길단위인구는 3개월간 인구수 그대로(👤 결정 ②) — 하루 평균·면적당으로 바꾸지 않는다.
 *    사는 사람·일하는 사람은 「YYYY년 기준」 = 값이 마지막으로 바뀐 해(서버 `*_value_quarter`).
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 서울시 상권 전체의 값이다. 상권이 여럿이면 상권마다 한 덩어리다.
 * ⛔ **분기·연도 글자를 박지 않는다**(시험이 이 파일 원문을 훑는다). 계산은 전부 `lib/districtPop.ts`.
 * ⓘ 서울 필지에만 그린다(FloorStack 이 고른다). 함수가 없거나 모양이 이상하면 카드째 숨긴다.
 * ⓘ 넷째 덩이 = 가까운 지하철역 승하차(결정 0045 PR⑥ · 카드 수 안 늘림) — 상권 덩어리들 뒤 · 발 문구 앞. 따로 묻고,
 *   못 읽었거나(PGRST202·오류·모양 이상) no_data·no_coord·not_seoul 이면 **덩이만** 없다(카드는 그대로 · 「자료 없음」 안 적음).
 *   빈 상태 셋 가운데 상권 밖(outside_seoul_district)에도 덩이는 선다(역은 상권과 무관). 접힌 요약 꼬리는 역 수만.
 */
type Props = {
  pnu: string;
  prefetch?: SidePrefetch | null;
  /** 이 카드의 배치. 안 주면 `SECTION_PLAN.pop`. */
  plan?: SectionPlan;
};

export function PopSection({ pnu, prefetch, plan = SECTION_PLAN.pop }: Props) {
  const [rows, setRows] = useState<DistrictPop[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다.
    setRows(null);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, DISTRICT_POP_FN, pnu) ?? supabase.rpc(DISTRICT_POP_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      // ⛔ 늦은 답은 버린다.
      if (cancelled) return;
      if (error || !isDistrictPopList(data)) {
        console.warn('상권 인구 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      // ok 인데 셋 다 없는 줄은 no_data 로(검사 뒤 보완 F12 — 빈 덩어리를 그리지 않는다).
      setRows(normalizePopRows(data));
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  // 넷째 덩이 — 가까운 지하철역 승하차(결정 0045 PR⑥). 카드와 따로 묻고, 못 읽으면 **덩이만** 없다(카드는 그대로).
  // ⓘ 이 effect 는 위 상권 인구 effect 뒤에 둔다(같은 그림 안 effect 는 적은 차례로 돈다).
  const [subway, setSubway] = useState<NearbySubway[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    setSubway(null);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, NEARBY_SUBWAY_FN, pnu) ?? supabase.rpc(NEARBY_SUBWAY_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      if (cancelled) return;
      if (error || !isNearbySubwayList(data)) {
        console.warn('지하철 승하차 조회 실패 — 그 덩이 없이 표시합니다', error ?? data);
        return;
      }
      setSubway(data);
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  if (rows === null) return null;

  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');
  // 상권 밖 건물에도 역은 있다(역은 상권과 무관) — 빈 상태 셋 가운데 상권 밖만 덩이를 그린다.
  const withSubway = subwayShows(subway) && (!head || head.status === 'outside_seoul_district');
  const tail = withSubway ? subwaySummaryTail(subway) : null;
  const base = popSummary(rows, pnu);
  const summary = tail ? `${base} · ${tail}` : base;

  if (head) {
    return (
      <SectionCard plan={plan} className="pop pop--none" summary={summary}>
        <p className="pop__lead">{headBody(head.status, pnu)}</p>
        {withSubway && <SubwayChunk rows={subway!} />}
        <p className="pop__src">{POP_NOTES.source}</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard plan={plan} className="pop" summary={summary}>
      <p className="pop__lead">
        <strong>{POP_LEAD_STRONG}</strong>
        {POP_LEAD_REST[0]}
        <b>{POP_LEAD_REST[1]}</b>
        {POP_LEAD_REST[2]}
      </p>
      <p className="pop__badge-line">
        <span className="grade__badge grade__badge--est">{POP_BADGE}</span>
        <span className="pop__badge-note">{POP_BADGE_NOTE}</span>
      </p>

      {rows.map((r) => (
        <PopBlock key={r.district_id ?? r.status} row={r} />
      ))}

      {withSubway && <SubwayChunk rows={subway!} />}

      <ul className="pop__why">
        <li className="pop__src">{POP_NOTES.source}</li>
        <li>
          <strong>{POP_NOTES.notBuilding}</strong>
        </li>
        <li>{POP_NOTES.method}</li>
        <li>{POP_NOTES.yearly}</li>
      </ul>
    </SectionCard>
  );
}

/** 상권 하나의 덩어리 — 길단위인구 · 사는 사람 · 일하는 사람. 상권끼리 더하지 않는다. */
function PopBlock({ row }: { row: DistrictPop }) {
  const title = districtTitle(row);
  if (row.status === 'no_data') {
    return (
      <div className="pop__district pop__district--nodata">
        <p className="pop__name">{title}</p>
        <p className="pop__none">{POP_NO_DATA_TEXT}</p>
      </div>
    );
  }
  const flow = flowBigText(row);
  const bars = flowBars(row);
  const flowLag = flowLagText(row);
  const resident = residentText(row);
  const residentLag = residentLagText(row);
  const worker = workerText(row);
  const workerLag = workerLagText(row);

  return (
    <div className="pop__district">
      <p className="pop__name">{title}</p>
      {flow && (
        <div className="pop__chunk pop__chunk--flow">
          <p className="pop__chunk-h">{POP_CHUNK_TITLES.flow}</p>
          <Big big={flow} />
          {flowLag && <p className="pop__note">{flowLag}</p>}
          {bars && (
            <div className="pop__mini">
              <MiniBars name={POP_BAR_GROUPS.time} bars={bars.time} />
              <MiniBars name={POP_BAR_GROUPS.day} bars={bars.day} />
            </div>
          )}
        </div>
      )}
      {!flow && flowLag && <p className="pop__note">{flowLag}</p>}
      {(resident || residentLag) && (
        <div className="pop__chunk pop__chunk--resident">
          <p className="pop__chunk-h">{POP_CHUNK_TITLES.resident}</p>
          {resident ? <Big big={resident} /> : <p className="pop__note">{residentLag}</p>}
        </div>
      )}
      {(worker || workerLag) && (
        <div className="pop__chunk pop__chunk--worker">
          <p className="pop__chunk-h">{POP_CHUNK_TITLES.worker}</p>
          {worker ? <Big big={worker} /> : <p className="pop__note">{workerLag}</p>}
        </div>
      )}
    </div>
  );
}

/**
 * 넷째 덩이 — 가까운 지하철역 승하차(결정 0045 PR⑥ · 👤 Q1 가 · Q2 가 · Q3 가 · Q4 나). 역은 서버 차례 그대로(가까운 순).
 * ⛔ 숫자는 서버 값 그대로 · 막대는 높이만 · 글은 전부 `lib/subwayNearby.ts` 에서(이 파일에 글자를 박지 않는다).
 */
function SubwayChunk({ rows }: { rows: readonly NearbySubway[] }) {
  const noStation = rows.length === 1 && rows[0].status === 'no_station' ? subwayNoStationText(rows[0]) : null;
  return (
    <div className="pop__chunk pop__chunk--subway">
      <p className="pop__chunk-h">
        {SUBWAY_CHUNK_TITLE} <span className="grade__badge">{SUBWAY_BADGE}</span>
      </p>
      {noStation ? (
        <div className="subway__none">
          <p>{noStation.main}</p>
          {noStation.nearest && <p>{noStation.nearest}</p>}
        </div>
      ) : (
        rows.map((r) => <SubwayStation key={r.group_id ?? r.station_nm} row={r} />)
      )}
      <ul className="pop__why subway__why">
        <li className="pop__src">{SUBWAY_NOTES.source}</li>
        <li>
          {SUBWAY_NOTES.count[0]}
          <strong>{SUBWAY_NOTES.count[1]}</strong>
          {SUBWAY_NOTES.count[2]}
        </li>
        <li>{SUBWAY_NOTES.transfer}</li>
        <li>
          <strong>{SUBWAY_NOTES.notBuilding}</strong>
        </li>
      </ul>
    </div>
  );
}

function SubwayStation({ row }: { row: NearbySubway }) {
  const st = subwayStationLine(row);
  const num = subwayNumbers(row);
  const bars = subwayBars(row);
  return (
    <div className={'none' in num ? 'subway__st subway__st--none' : 'subway__st'}>
      <p className="subway__nm">
        {st.name} <small>{st.sub}</small>
      </p>
      {'none' in num ? (
        <p className="subway__num">{num.none}</p>
      ) : (
        <>
          <p className="subway__num">
            <b>{num.on}</b> · <b>{num.off}</b> <span className="subway__unit">{num.tail}</span>
          </p>
          <p className="subway__sub">{num.period}</p>
        </>
      )}
      {bars && <MiniBars name={POP_BAR_GROUPS.time} bars={bars} />}
    </div>
  );
}

function Big({ big }: { big: PopBig }) {
  return (
    <p className="pop__big">
      <strong className="pop__num">{big.num}</strong>
      {big.when && <span className="pop__q">{big.when}</span>}
      <span>{big.detail}</span>
    </p>
  );
}

/** 미니 막대 한 묶음(시간대 · 요일) — 값 그대로 · 높이 = 값 ÷ 그 묶음 최댓값. 값은 읽어 주기·마우스 글에. */
function MiniBars({ name, bars }: { name: string; bars: FlowBars }) {
  return (
    <figure className="pop__bars-fig">
      <figcaption className="pop__scale">{bars.scale ? `${name} · ${bars.scale}` : name}</figcaption>
      <div className="pop__cols" style={{ gridTemplateColumns: `repeat(${bars.bars.length}, minmax(0, 1fr))` }}>
        {bars.bars.map((b) => {
          const said = `${name} ${b.label ?? `${b.tick} ${formatCount(b.value, '명')}`}`;
          return (
            <div key={b.key} className="pop__col">
              <div className="pop__bars">
                <span className="pop__bar" role="img" aria-label={said} title={said} style={{ height: `${b.h}%` }} />
              </div>
              <span className="pop__tick">{b.tick}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
