import { useEffect, useState, type CSSProperties } from 'react';
import { supabase } from '../lib/supabase';
import { DAEJEON_CLOSURE_FN, OPEN_CLOSE_ALL_FN, OPEN_CLOSE_FN } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import {
  OPEN_CLOSE_MIN_SAMPLE,
  allQuartersCount,
  countRateText,
  districtName,
  formatStoreCount,
  franchiseText,
  industryRateShown,
  industryRows,
  isOpenCloseAllList,
  isOpenCloseList,
  latestOf,
  openCloseQuarterLabel,
  openCloseSummary,
  otherIndustries,
  scaleText,
  sidoNameOfPnu,
  storeTotalText,
  tableCellText,
  trendCells,
  trendScaleMax,
  windowText,
  type TrendCell,
} from '../lib/openClose';
import { formatRate } from '../lib/rentStats';
import type { DaejeonDongClosure, DistrictOpenClose, DistrictOpenCloseAll } from '../types';
import {
  DAEJEON_CLOSURE_NOTES,
  DAEJEON_CLOSURE_TITLE,
  DAEJEON_NO_DONG_TEXT,
  closureBigText,
  closureCount,
  daejeonBars,
  daejeonSummary,
  dongLine,
  industryTable,
  isDaejeonPnu,
  parseDaejeonClosure,
  quarterRangeText,
  restText,
} from '../lib/daejeonClosure';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';
import { FOUNDER_CHIP_ALL, chipMatch, type FounderChip } from '../lib/founderChips';

/**
 * "상권 개업·폐업 (서울시 공표)" 카드 — 결정 0033 R2.
 *
 * ⛔ **공표값 그대로다.** 서울시 상권분석서비스(점포-상권)가 분기마다 공표한 점포 수·개업·
 *    폐업을 서버가 상권마다 더해 준다. 상권 전체 비율도 서버가 서울시 산식으로 낸다 —
 *    이 화면의 나누기는 추이 막대의 높이 비례와 **프랜차이즈 비중 하나뿐**이다(둘 다 `lib/openClose.ts` ·
 *    비중은 서울시가 공표하지 않아 공표 개수 둘을 나눈 예외 — 👤 결정 · 물결 1-B).
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 **서울시 상권 전체**의 값이다 — 첫 줄과 발
 *    문구가 같은 말을 한다. 상권이 여럿이면 **합치지 않고** 상권마다 한 덩어리다(겹치는 자리의
 *    가게가 양쪽에 세어진다).
 * ⛔ **분기·연도 글자를 박지 않는다.** 어느 분기를 그릴지는 서버의 창이 정한다.
 * ⓘ **「전부 보기 (N분기)」**(결정 0038 H · V6) — 기본은 서버의 최근 8분기 창 그대로. 8분기 답에 상권 줄이 있으면
 *   `OPEN_CLOSE_ALL_FN`(표 전체 분기 전부 · 같은 모양)을 한 번 더 묻고, 그 답의 `total_quarters` 를 N 으로 단추에 적는다.
 *   누르면 서버를 다시 부르지 않고 그 답으로 바꿔 그린다(모든 상권이 같은 창 · 눈금도 그 창 기준). 그 답이 없거나
 *   이상하면 단추만 없다(카드는 선다).
 * ⛔ **지역·상권 이름을 박지 않는다.** 서울 밖 지역 이름은 `regions.ts` 의 표에서 고른다.
 * ⓘ **대전 건물**(결정 0044) — 8분기 답이 `not_seoul` 이고 대전 필지면 `DAEJEON_CLOSURE_FN`(대전시 공표 행정동 폐업)을
 *   받아 같은 자리에 제목 「동네 폐업 (대전시 공표)」 카드를 세운다(`DaejeonCard` · 글·검사는 `lib/daejeonClosure.ts`).
 *   그 답이 실패·0줄·모양 이상이면 **지금 대전 화면 그대로**(옛 제목·「그 자료가 없습니다」). 묻는 동안은 카드를 안 그린다
 *   (옛 제목이 먼저 섰다가 바뀌지 않게 — 미리 부르기가 대전 필지에 이 함수를 함께 보내 둔다).
 */
type Props = {
  /** 이 필지. 바뀌면 처음부터 다시 묻는다. */
  pnu: string;
  /** 부모가 건물을 고른 순간 먼저 보내 둔 요청(`lib/sidePrefetch.ts`). 이 pnu 것이면 쓴다. */
  prefetch?: SidePrefetch | null;
  /**
   * 이 카드의 배치(제목·역할·기본 펼침). 층별 화면이 고른 역할의 표를 준다(결정 0036 결정 18).
   * 안 주면 `SECTION_PLAN.openclose` — 역할을 고르기 전 화면 그대로.
   */
  plan?: SectionPlan;
  /**
   * 창업자가 고른 업종 칩(결정 0036 결정 18 ⑨). 업종 표에서 짝 업종 줄을 굵게 하고 표를 펼친 채로
   * 둔다(짝은 `lib/founderChips.ts` 표 한 곳). 안 줌·'전체' = 지금 화면 그대로.
   */
  chip?: FounderChip;
};

export function OpenCloseSection({
  pnu,
  prefetch,
  plan = SECTION_PLAN.openclose,
  chip = FOUNDER_CHIP_ALL,
}: Props) {
  /**
   * 받아 온 줄들. **아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다**(임대 카드와 같은
   * 판단 — 둘 다 아무것도 안 그린다). 함수가 아직 없으면(PGRST202) 이 상태로 남는다 —
   * "자료 없음"이라 적지 않는다(없는 것과 모르는 것은 다르다).
   */
  const [rows, setRows] = useState<DistrictOpenClose[] | null>(null);
  /** 위 rows 가 어느 필지의 답인가(전부 보기 묻기를 그 필지 것일 때만 하려고 · 아래 wantAll). */
  const [rowsPnu, setRowsPnu] = useState<string | null>(null);
  /** 「전부 보기」 답(표 전체 분기 전부). 못 받았거나 못 읽었으면 null — 그때는 단추가 없다. */
  const [allRows, setAllRows] = useState<DistrictOpenCloseAll[] | null>(null);
  /** 「전부 보기」 답이 실패(오류·모양 이상·함수 없음)했나 — 묻는 중(빈 상자를 둔다)과 실패(빈 상자를 거둔다)를 가른다. */
  const [allFailed, setAllFailed] = useState(false);
  /** 전부 보기로 그리는 중인가. 필지가 바뀌면 기본(8분기)으로 돌아간다. */
  const [showAll, setShowAll] = useState(false);
  /**
   * 대전시 동네 폐업 답(결정 0044) — 어느 필지 것인가와 함께. row null = 실패·0줄·모양 이상(옛 대전 화면).
   * 아직 못 받았으면 상태 자체가 null.
   */
  const [dj, setDj] = useState<{ pnu: string; row: DaejeonDongClosure | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다 — 안 지우면 새 건물 밑에 앞 건물 상권의 숫자가 잠깐 붙는다.
    // 전부 보기 답·상태도 함께 지운다(앞 건물의 22분기 그림이 새 건물 밑에 남지 않게).
    setRows(null);
    setAllRows(null);
    setAllFailed(false);
    setShowAll(false);
    setDj(null);

    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, OPEN_CLOSE_FN, pnu) ?? supabase.rpc(OPEN_CLOSE_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      if (cancelled) return;
      // ⚠️ 모양까지 본다 — 뜻밖의 답이 렌더로 흘러들면 곁다리 카드 하나 때문에 층별 화면이
      //    통째로 오류 안내가 된다.
      if (error || !isOpenCloseList(data)) {
        console.warn('상권 개업·폐업 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
      setRowsPnu(pnu);
    });

    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  // 상권 줄(ok·no_data)이 있을 때만 전부 보기 답을 묻는다 — 대전·상권 밖·좌표 없음에는 단추가 없다.
  // ⓘ 필지가 바뀐 바로 그 그리기에서는 rows 가 아직 앞 건물 것이라(위 효과가 비우기 전) 묻지 않는다 — 같은 필지를
  //   두 번 묻지 않게 8분기 답이 이 필지 것일 때만 참이 되도록 rowsPnu 로 가른다.
  const wantAll =
    rows !== null && rowsPnu === pnu && rows.some((r) => r.status === 'ok' || r.status === 'no_data');

  useEffect(() => {
    if (!wantAll) return;
    let cancelled = false;
    supabase.rpc(OPEN_CLOSE_ALL_FN, { p_pnu: pnu }).then(({ data, error }) => {
      // ⛔ 늦은 답은 버린다 — 그 사이 필지가 바뀌었으면 앞 건물 상권의 전부 그림이 새 건물 밑에 붙는다.
      if (cancelled) return;
      // 함수 없음(PGRST202)·오류·모양 이상이면 단추만 빠진다 — 8분기 카드는 그대로 선다.
      if (error || !isOpenCloseAllList(data)) {
        console.warn('상권 개업·폐업 전부 보기 조회 실패 — 최근 분기만 표시합니다', error ?? data);
        setAllFailed(true);
        return;
      }
      setAllRows(data);
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, wantAll]);

  // 대전 필지의 not_seoul 답일 때만 대전시 답을 쓴다(결정 0044) — 서울 건물·상권 밖·좌표 없음은 지금 그대로.
  const wantDj =
    rows !== null && rowsPnu === pnu && isDaejeonPnu(pnu) && rows.some((r) => r.status === 'not_seoul');

  useEffect(() => {
    if (!wantDj) return;
    let cancelled = false;
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, DAEJEON_CLOSURE_FN, pnu) ?? supabase.rpc(DAEJEON_CLOSURE_FN, { p_pnu: pnu });
    req.then(
      ({ data, error }) => {
        // ⛔ 늦은 답은 버린다 — 그 사이 필지가 바뀌었으면 앞 건물 동의 숫자가 새 건물 밑에 붙는다.
        if (cancelled) return;
        const row = error ? null : parseDaejeonClosure(data);
        if (row === null) console.warn('대전 동네 폐업 조회 실패 — 지금 대전 카드로 표시합니다', error ?? data);
        setDj({ pnu, row });
      },
      (e: unknown) => {
        if (cancelled) return;
        console.warn('대전 동네 폐업 조회 실패 — 지금 대전 카드로 표시합니다', e);
        setDj({ pnu, row: null });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch, wantDj]);

  if (rows === null) return null;

  const summary = openCloseSummary(rows, pnu);
  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');

  if (wantDj) {
    const djRow = dj !== null && dj.pnu === pnu ? dj.row : undefined;
    if (djRow === undefined) return null; // 묻는 중
    if (djRow !== null) return <DaejeonCard row={djRow} plan={plan} />;
    // 실패·0줄·모양 이상 → 아래 지금 대전 화면 그대로.
  }

  /*
    ⛔ 서울 밖·상권 밖·좌표 없음에서도 **카드는 선다.** 그냥 사라지면 "이 서비스는 개업·폐업
       이야기를 안 하는구나"로 읽힌다. 왜 숫자가 없는지가 곧 이 자리의 답이다.
  */
  if (head) {
    let text: string;
    if (head.status === 'not_seoul') {
      const sido = sidoNameOfPnu(pnu);
      text =
        sido === null
          ? '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물에는 그 자료가 없습니다.'
          : `서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(${sido})에는 그 자료가 없습니다.`;
    } else if (head.status === 'outside_seoul_district') {
      text = '이 건물이 속한 서울시 상권이 없어 자료가 없습니다.';
    } else {
      text = '이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.';
    }
    return (
      <SectionCard plan={plan} className="oc oc--none" summary={summary}>
        <p className="oc__lead">{text}</p>
        <p className="oc__src">{SOURCE_TEXT}</p>
      </SectionCard>
    );
  }

  // 단추 「전부 보기 (N분기)」의 N — 전부 답의 total_quarters 칸 값 그대로. 없으면 단추도 없다.
  const allN = allQuartersCount(rows, allRows);
  // 지금 그리는 창 — 전부 보기면 전부 답, 아니면 8분기 답(모든 상권이 같은 창).
  const view: DistrictOpenClose[] = showAll && allN !== null && allRows !== null ? allRows : rows;
  const wide = view !== rows;
  // 카드 하나에 눈금 하나 — 상권끼리 같은 높이가 같은 비율이 되게 한다(`trendScaleMax`). 눈금은 **보는 창** 기준이다.
  const scaleMax = trendScaleMax(view);

  return (
    <SectionCard plan={plan} className="oc" summary={summary}>
      <p className="oc__lead">
        <strong>이 건물이 속한 상권의 개업·폐업입니다</strong> — 서울시가 공표한 점포 수 그대로입니다.
      </p>
      {/*
        전부 보기 단추(결정 0038 H · V6) — 카드 하나에 하나(모든 상권이 같은 창). 누르는 장치라 종이에는 안 나온다.
        N 은 서버 칸 값이고, 되돌리는 글의 기간도 8분기 답의 창에서 읽는다(분기 수를 박지 않는다).
      */}
      {allN !== null ? (
        <button type="button" className="oc__all" aria-expanded={wide} onClick={() => setShowAll(!wide)}>
          {wide ? `${windowText(rows[0].window_quarters)}만 보기` : `전부 보기 (${allN}분기)`}
        </button>
      ) : (
        /*
          전부 답을 묻는 동안은 단추와 같은 크기의 보이지 않는 빈 상자로 자리를 미리 비운다(👤 「빈 자리 미리」) —
          답이 와서 단추가 끼어들 때 아래 눈금 줄·상권 그림이 밀리지 않게. 실패하면 거둔다(그때 한 번 접힌다).
          같은 이름표라 높이·여백이 단추와 같고, 종이에서는 단추와 함께 빠진다.
        */
        wantAll &&
        allRows === null &&
        !allFailed && <span className="oc__all oc__all--slot" aria-hidden="true" />
      )}
      {/* 막대 눈금 — 눈에 보이는 글로 둔다(인쇄에도 나온다). 그릴 막대가 없으면 줄도 없다. */}
      {scaleMax > 0 && <p className="oc__scale">{scaleText(scaleMax, view[0].window_quarters)}</p>}

      {view.map((r) => (
        <DistrictBlock key={r.district_id ?? r.status} row={r} scaleMax={scaleMax} chip={chip} wide={wide} />
      ))}

      <ul className="oc__why">
        <li className="oc__src">{SOURCE_TEXT}</li>
        <li>
          <strong>상권 전체 값이며 이 건물의 값이 아닙니다.</strong>
        </li>
        <li>
          점포 수는 서울시 100업종 기준이라 &lsquo;{SECTION_PLAN.industry.title}&rsquo; 카드(소상공인시장진흥공단
          전 업종)와 다릅니다.
        </li>
        <li>
          상권 전체 비율은 서울시가 업종별로 공표한 점포 수를 더해 서울시 계산식(개업·폐업 점포 ÷
          점포(프랜차이즈 포함) × 100)으로 낸 값입니다 — 서울시 자료는 이 점포 수를 &lsquo;유사 업종 점포
          수&rsquo;라고 부릅니다.
        </li>
      </ul>
    </SectionCard>
  );
}

/**
 * 대전 건물의 카드(결정 0044) — 제목 「동네 폐업 (대전시 공표)」 · 날짜 줄은 대전시 받은 날(`daejeon_closure`).
 * 역할·펼침은 받은 배치 그대로(제목·자료 갈래만 바꿔 끼운다).
 * ⛔ 폐업률(%)·개업·점포 수 없음 — 건수만(대전시가 개업 수를 내지 않는다 · 👤 결정 0044 ⑤).
 */
function DaejeonCard({ row, plan }: { row: DaejeonDongClosure; plan: SectionPlan }) {
  const djPlan: SectionPlan = { ...plan, title: DAEJEON_CLOSURE_TITLE, sources: ['daejeon_closure'] };
  const summary = daejeonSummary(row);
  if (row.status !== 'ok' || row.dong_nm === null || row.quarters === null || row.clsbiz_sum === null) {
    return (
      <SectionCard plan={djPlan} className="oc oc--none oc--dj" summary={summary}>
        <p className="oc__lead">{DAEJEON_NO_DONG_TEXT}</p>
        <p className="oc__src">{DAEJEON_CLOSURE_NOTES[0]}</p>
      </SectionCard>
    );
  }
  const range = quarterRangeText(row.sum_quarters ?? []);
  const bars = daejeonBars(row.quarters);
  const windowLabel = quarterRangeText(row.quarters.map((q) => q.quarter)) ?? '';
  const { top, rest } = industryTable(row.industries ?? []);
  const sumN = (row.sum_quarters ?? []).length;
  return (
    <SectionCard plan={djPlan} className="oc oc--dj" summary={summary}>
      <div className="oc__district">
        <p className="oc__name">{dongLine(row.dong_nm)}</p>
        <p className="oc__latest">
          <strong className="oc__num oc__num--close">{closureBigText(row.clsbiz_sum)}</strong>
          {range && <span className="oc__quarter">{range}</span>}
        </p>
        {/* 분기 막대 — 서울 카드의 추이 막대 모양 그대로(옛 분기 왼쪽 → 최근 오른쪽 · 막대 위 건수 · 0 건도 「0」). */}
        <figure className="oc__trend">
          <figcaption className="oc__trend-cap">
            {`분기별 폐업 건수 — ${windowLabel}`}
            <span className="oc__dir">왼쪽이 옛 분기, 오른쪽이 최근</span>
          </figcaption>
          <div className="oc__cols" style={{ gridTemplateColumns: `repeat(${bars.length}, minmax(0, 1fr))` }}>
            {bars.map((b, i) => (
              <div key={b.quarter} className="oc__col oc__col--ok" data-quarter={b.quarter}>
                <div className="oc__bars">
                  <span className="oc__djcol">
                    <span className="oc__val" aria-hidden="true">
                      {b.count.toLocaleString('ko-KR')}
                    </span>
                    <span
                      className="oc__bar oc__bar--close"
                      role="img"
                      aria-label={`${b.label} 폐업 ${closureCount(b.count)}`}
                      title={`${b.label} 폐업 ${closureCount(b.count)}`}
                      style={{ height: `calc((100% - 16px) * ${(b.h / 100).toFixed(4)})` }}
                    />
                  </span>
                </div>
                <span className="oc__tick">
                  <span className="oc__tick-q">{`${b.q}분기`}</span>
                  {i === 0 || b.q === '1' ? <span className="oc__tick-year">{`${b.year}년`}</span> : null}
                </span>
              </div>
            ))}
          </div>
        </figure>
        {top.length > 0 && (
          <table className="oc__table oc__table--dj">
            <thead>
              <tr>
                <th scope="col">업종</th>
                <th scope="col">{`폐업 ${sumN}분기`}</th>
              </tr>
            </thead>
            <tbody>
              {top.map((x) => (
                <tr key={x.induty_nm}>
                  <th scope="row">{x.induty_nm}</th>
                  <td>{closureCount(x.clsbiz_co)}</td>
                </tr>
              ))}
              {rest && (
                <tr className="oc__other">
                  <th scope="row" colSpan={2}>
                    {restText(rest)}
                  </th>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      <ul className="oc__why">
        {DAEJEON_CLOSURE_NOTES.map((t, i) =>
          i === 0 ? (
            <li key={t} className="oc__src">
              {t}
            </li>
          ) : (
            <li key={t}>{i === 1 ? <strong>{t}</strong> : t}</li>
          ),
        )}
      </ul>
    </SectionCard>
  );
}

/** 발 문구 ① — 자료 이름·이용허락은 포털 원문 그대로다. */
const SOURCE_TEXT =
  '출처: 서울시 상권분석서비스(점포-상권) · 서울 열린데이터광장 · 공공누리 1유형(출처표시)';

/** 상권 하나의 덩어리. 상권끼리 더하지 않는다. */
function DistrictBlock({
  row,
  scaleMax,
  chip,
  wide,
}: {
  row: DistrictOpenClose;
  scaleMax: number;
  chip: FounderChip;
  /** 전부 보기 창(넓은 그림 — 화면에서 옆으로 민다). */
  wide: boolean;
}) {
  const name = districtName(row);
  const title = row.district_type ? `${name} · ${row.district_type}` : name;

  if (row.status === 'no_data') {
    return (
      <div className="oc__district oc__district--nodata">
        <p className="oc__name">{title}</p>
        <p className="oc__none">
          {windowText(row.window_quarters)} 동안 서울시가 이 상권의 개업·폐업 자료를 내지 않았습니다.
        </p>
      </div>
    );
  }

  const latest = latestOf(row);
  const label = openCloseQuarterLabel(row.latest_quarter);
  // 모양 검사가 ok 줄에는 최신 분기 합이 있음을 보장한다 — 그래도 없으면 덩어리째 뺀다.
  if (!latest || !label) return null;

  const noRate = latest.opbiz_rt === null || latest.clsbiz_rt === null;
  // ⛔ 표본 문장은 **점포 수 합이 정말 30 곳 미만일 때만**(비율 null 만으로 띄우지 않는다 — F5).
  const smallSample = latest.similr_induty_stor_co < OPEN_CLOSE_MIN_SAMPLE;
  const windowLatest = row.window_quarters[0];
  const behind = windowLatest !== undefined && windowLatest !== row.latest_quarter;
  const cells = trendCells(row.window_quarters, row.quarters ?? [], scaleMax);
  const inds = industryRows(row.industries);
  const other = otherIndustries(row.other_industries);
  // 창업자 칩의 짝 업종(결정 0036 결정 18 ⑨). 짝 줄이 상위 표에 하나도 없으면 그렇다고 한 줄 적는다.
  const match = chipMatch(chip);
  const isHit = (cd: string) => match !== null && match.seoul.includes(cd);
  const hitMissing = match !== null && inds !== null && !inds.some((i) => isHit(i.svc_induty_cd));
  // 일부만 있으면 빠진 것만 이름으로 적는다(👤 F5 · 이름은 짝짓기 표에서 — 표 차례 그대로).
  const missingNames =
    match !== null && inds !== null && !hitMissing
      ? match.seoul
          .filter((cd) => !inds.some((i) => i.svc_induty_cd === cd))
          .map((cd) => match.seoulNm[cd] ?? cd)
      : [];

  return (
    <div className="oc__district">
      <p className="oc__name">{title}</p>
      <p className="oc__latest">
        <strong className="oc__num">{storeTotalText(latest.similr_induty_stor_co)}</strong>
        {/* 프랜차이즈 비중 — 이 카드에서 화면이 나누는 유일한 값(👤 결정 · `franchiseText`). */}
        <strong className="oc__num oc__num--frc">
          {franchiseText(latest.frc_stor_co, latest.similr_induty_stor_co)}
        </strong>
        <strong className="oc__num oc__num--open">
          {countRateText('개업', latest.opbiz_stor_co, noRate ? null : latest.opbiz_rt)}
        </strong>
        <strong className="oc__num oc__num--close">
          {countRateText('폐업', latest.clsbiz_stor_co, noRate ? null : latest.clsbiz_rt)}
        </strong>
        <span className="oc__quarter">{label}</span>
      </p>
      {smallSample && (
        <p className="oc__note">
          {`표본 ${formatStoreCount(latest.similr_induty_stor_co)}(점포 · 프랜차이즈 포함) — ${OPEN_CLOSE_MIN_SAMPLE}곳이 안 돼 비율은 적지 않습니다.`}
        </p>
      )}
      {/* ⛔ 전부 보기에서 8분기 창의 no_data 가 ok 로 바뀐 상권도 이 줄을 지난다 — 옛 분기 숫자를 최근처럼 보이지 않게(결정 0033). */}
      {behind && <p className="oc__note">{`이 상권 자료는 ${label}까지입니다.`}</p>}

      {cells.length > 0 && <Trend cells={cells} windowLabel={windowText(row.window_quarters)} wide={wide} />}

      {hitMissing && (
        <p className="oc__note oc__chip-none">{`고른 업종(${chip})은 이 상권 점포 수 상위 업종에 없습니다`}</p>
      )}
      {missingNames.length > 0 && (
        <p className="oc__note oc__chip-part">{`고른 업종 가운데 ${missingNames.join('·')}은 상위 업종에 없습니다`}</p>
      )}
      {/*
        칩을 골랐으면 표를 펼친 채로 둔다 — 굵은 줄이 접힌 표 안에 있으면 안 보인다. 손님이 접고 펴는
        것은 그대로 되고(같은 값으로 다시 그려도 React 가 건드리지 않는다), 칩이 바뀔 때만 따라간다.
        ⓘ key 가 칩이라 칩을 바꿀 때마다 표가 새로 선다 — 손님이 접어 둔 뒤 다른 칩을 골라도 다시
          펼친 채다(같은 값 true → true 는 React 가 안 건드려 접힌 채 남는다 · 검사 뒤 보완 F2).
      */}
      {inds && (
        <details key={chip} className="oc__ind" open={match !== null}>
          <summary className="oc__ind-sum">업종별 표 — {label} · 점포가 많은 순</summary>
          <table className="oc__table">
            <thead>
              <tr>
                <th scope="col">업종</th>
                <th scope="col">점포(프랜차이즈 포함)</th>
                <th scope="col">개업 (개업률·분기)</th>
                <th scope="col">폐업 (폐업률·분기)</th>
              </tr>
            </thead>
            <tbody>
              {inds.map((i) => {
                // 점포(프랜차이즈 포함)가 30곳이 안 되는 업종은 비율만 '–'(개수는 그대로) — 서울시는
                // 점포 1~5곳 업종에도 '200%' 같은 비율을 공표한다(카드 위 큰 숫자와 같은 규칙).
                const shown = industryRateShown(i.similr_induty_stor_co);
                return (
                  <tr key={i.svc_induty_cd} className={isHit(i.svc_induty_cd) ? 'oc__hit' : undefined}>
                    <th scope="row">
                      {isHit(i.svc_induty_cd) ? (
                        <strong>{i.svc_induty_cd_nm || i.svc_induty_cd}</strong>
                      ) : (
                        i.svc_induty_cd_nm || i.svc_induty_cd
                      )}
                    </th>
                    <td>{formatStoreCount(i.similr_induty_stor_co)}</td>
                    <td>{tableCellText(i.opbiz_stor_co, shown ? i.opbiz_rt : null)}</td>
                    <td>{tableCellText(i.clsbiz_stor_co, shown ? i.clsbiz_rt : null)}</td>
                  </tr>
                );
              })}
              {/* 그 밖 줄의 비율은 공표값이 아니라 서버가 업종 합을 나눈 값이다 — 머리에 그렇게 적는다
                  (서버가 이미 합 30 미만이면 null 로 보낸다). */}
              {other && (
                <tr className="oc__other">
                  <th scope="row">{`그 밖 ${other.industry_count}업종 (더해서 계산)`}</th>
                  <td>{formatStoreCount(other.similr_induty_stor_co)}</td>
                  <td>{tableCellText(other.opbiz_stor_co, other.opbiz_rt)}</td>
                  <td>{tableCellText(other.clsbiz_stor_co, other.clsbiz_rt)}</td>
                </tr>
              )}
            </tbody>
          </table>
          {/* 표 안 '–' 는 두 뜻이다 — 표본이 작아 우리가 비율을 안 적은 칸 · 서울시가 비율을 안 낸 칸. */}
          <p className="oc__note">{`'–' = 점포(프랜차이즈 포함)가 ${OPEN_CLOSE_MIN_SAMPLE}곳이 안 되거나 서울시가 비율을 내지 않은 칸입니다.`}</p>
        </details>
      )}
    </div>
  );
}

/**
 * 추이 막대 — 창 안의 분기마다 개업률·폐업률 막대 둘(옛 분기 왼쪽 → 최신 오른쪽).
 *
 * ⛔ 자료가 없는 분기는 **빈 칸('–')** 이다(0 막대가 아니다). 표본이 모자란 분기도 막대 없이
 *    '표본' 이라 적는다.
 * ⓘ 막대마다 값은 `aria-label`(읽어 주기)과 `title`(마우스) 로 단다 — 열여섯 개 숫자를 좁은
 *   화면에 늘어놓으면 서로 겹친다. 최신 분기 숫자는 바로 위 큰 숫자 줄에 글자로 있다.
 */
function Trend({ cells, windowLabel, wide }: { cells: TrendCell[]; windowLabel: string; wide: boolean }) {
  const cols = (
    <div
      className={wide ? 'oc__cols oc__cols--wide' : 'oc__cols'}
      style={
        {
          gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))`,
          // 넓은 그림의 최소 폭은 칸 수로만 정한다(styles.css 의 calc — DOM 을 재지 않는다 · 결정 0038 §2-3).
          ...(wide ? { '--oc-n': cells.length } : {}),
        } as CSSProperties
      }
    >
      {cells.map((c, i) => {
        const showYear = i === 0 || c.q === '1';
        return (
          <div key={c.quarter} className={`oc__col oc__col--${c.kind}`} data-quarter={c.quarter}>
            <div className="oc__bars">
              {c.kind === 'ok' && (
                <>
                  <span
                    className="oc__bar oc__bar--open"
                    role="img"
                    aria-label={`${c.label} 개업률 ${formatRate(c.openRt)}`}
                    title={`${c.label} 개업률 ${formatRate(c.openRt)}`}
                    style={{ height: `${c.openH}%` }}
                  />
                  <span
                    className="oc__bar oc__bar--close"
                    role="img"
                    aria-label={`${c.label} 폐업률 ${formatRate(c.closeRt)}`}
                    title={`${c.label} 폐업률 ${formatRate(c.closeRt)}`}
                    style={{ height: `${c.closeH}%` }}
                  />
                </>
              )}
              {c.kind === 'missing' && (
                <span className="oc__gap" role="img" aria-label={`${c.label} 자료 없음`} title={`${c.label} 자료 없음`}>
                  –
                </span>
              )}
              {c.kind === 'nosample' && (
                <span
                  className="oc__gap"
                  role="img"
                  aria-label={`${c.label} 표본 ${formatStoreCount(c.similr)} — 비율 없음`}
                  title={`${c.label} 표본 ${formatStoreCount(c.similr)} — 비율 없음`}
                >
                  표본
                </span>
              )}
            </div>
            <span className="oc__tick">
              <span className="oc__tick-q">{c.q ? `${c.q}분기` : ''}</span>
              {showYear && c.year ? (
                // 끝에서 셋째 칸 안쪽의 해 글은 종이에서 오른쪽에 붙인다(styles.css · 그림 밖으로 안 나가게 — 칸 차례로만 정한다).
                <span className={wide && cells.length - i <= 3 ? 'oc__tick-year oc__tick-year--end' : 'oc__tick-year'}>
                  {`${c.year}년`}
                </span>
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
  return (
    <figure className="oc__trend">
      <figcaption className="oc__trend-cap">
        {`분기별 개업률·폐업률 — ${windowLabel}`}
        <span className="oc__dir">왼쪽이 옛 분기, 오른쪽이 최근</span>
        <span className="oc__legend">
          <span className="oc__key oc__key--open" aria-hidden="true" />
          개업률
          <span className="oc__key oc__key--close" aria-hidden="true" />
          폐업률
        </span>
      </figcaption>
      {wide ? (
        // 넓은 그림만 화면에서 옆으로 민다 — 종이에서는 styles.css 가 밀기를 풀고 폭에 맞춘다(오른쪽 잘림 0).
        <div className="oc__scroll" role="region" aria-label={`분기별 막대 — ${windowLabel} · 왼쪽이 옛 분기, 오른쪽이 최근 · 옆으로 밀어 봅니다`} tabIndex={0}>
          {cols}
        </div>
      ) : (
        cols
      )}
      {cells.some((c) => c.kind !== 'ok') && (
        <p className="oc__note">
          &lsquo;–&rsquo; 칸은 그 분기에 서울시가 이 상권 자료를 내지 않은 것이고, &lsquo;표본&rsquo; 칸은 점포(프랜차이즈
          포함)가 {OPEN_CLOSE_MIN_SAMPLE}곳이 안 돼 비율을 적지 않은 분기입니다.
        </p>
      )}
    </figure>
  );
}
