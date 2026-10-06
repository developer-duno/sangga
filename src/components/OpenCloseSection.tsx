import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { OPEN_CLOSE_FN } from '../lib/appConstants';
import { SECTION_PLAN } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import {
  OPEN_CLOSE_MIN_SAMPLE,
  countRateText,
  districtName,
  formatStoreCount,
  industryRateShown,
  industryRows,
  isOpenCloseList,
  latestOf,
  openCloseQuarterLabel,
  openCloseSummary,
  otherIndustries,
  sidoNameOfPnu,
  storeTotalText,
  tableCellText,
  trendCells,
  trendScaleMax,
  windowText,
  type TrendCell,
} from '../lib/openClose';
import { formatRate } from '../lib/rentStats';
import type { DistrictOpenClose } from '../types';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';

/**
 * "상권 개업·폐업 (서울시 공표)" 카드 — 결정 0033 R2.
 *
 * ⛔ **공표값 그대로다.** 서울시 상권분석서비스(점포-상권)가 분기마다 공표한 점포 수·개업·
 *    폐업을 서버가 상권마다 더해 준다. 상권 전체 비율도 서버가 서울시 산식으로 낸다 —
 *    이 화면에는 나누기가 하나도 없다(추이 막대의 높이 비례만 `lib/openClose.ts` 에서 한다).
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 **서울시 상권 전체**의 값이다 — 첫 줄과 발
 *    문구가 같은 말을 한다. 상권이 여럿이면 **합치지 않고** 상권마다 한 덩어리다(겹치는 자리의
 *    가게가 양쪽에 세어진다).
 * ⛔ **분기·연도 글자를 박지 않는다.** 어느 분기를 그릴지는 서버의 창이 정한다.
 * ⛔ **지역·상권 이름을 박지 않는다.** 서울 밖 지역 이름은 `regions.ts` 의 표에서 고른다.
 */
type Props = {
  /** 이 필지. 바뀌면 처음부터 다시 묻는다. */
  pnu: string;
  /** 부모가 건물을 고른 순간 먼저 보내 둔 요청(`lib/sidePrefetch.ts`). 이 pnu 것이면 쓴다. */
  prefetch?: SidePrefetch | null;
};

export function OpenCloseSection({ pnu, prefetch }: Props) {
  /**
   * 받아 온 줄들. **아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다**(임대 카드와 같은
   * 판단 — 둘 다 아무것도 안 그린다). 함수가 아직 없으면(PGRST202) 이 상태로 남는다 —
   * "자료 없음"이라 적지 않는다(없는 것과 모르는 것은 다르다).
   */
  const [rows, setRows] = useState<DistrictOpenClose[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다 — 안 지우면 새 건물 밑에 앞 건물 상권의 숫자가 잠깐 붙는다.
    setRows(null);

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
    });

    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  if (rows === null) return null;

  const summary = openCloseSummary(rows, pnu);
  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');

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
      <SectionCard plan={SECTION_PLAN.openclose} className="oc oc--none" summary={summary}>
        <p className="oc__lead">{text}</p>
        <p className="oc__src">{SOURCE_TEXT}</p>
      </SectionCard>
    );
  }

  // 카드 하나에 눈금 하나 — 상권끼리 같은 높이가 같은 비율이 되게 한다(`trendScaleMax`).
  const scaleMax = trendScaleMax(rows);

  return (
    <SectionCard plan={SECTION_PLAN.openclose} className="oc" summary={summary}>
      <p className="oc__lead">
        <strong>이 건물이 속한 상권의 개업·폐업입니다</strong> — 서울시가 공표한 점포 수 그대로입니다.
      </p>
      {/* 막대 눈금 — 눈에 보이는 글로 둔다(인쇄에도 나온다). 그릴 막대가 없으면 줄도 없다. */}
      {scaleMax > 0 && <p className="oc__scale">{`막대가 꽉 차면 ${formatRate(scaleMax)}(분기)`}</p>}

      {rows.map((r) => (
        <DistrictBlock key={r.district_id ?? r.status} row={r} scaleMax={scaleMax} />
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

/** 발 문구 ① — 자료 이름·이용허락은 포털 원문 그대로다. */
const SOURCE_TEXT =
  '출처: 서울시 상권분석서비스(점포-상권) · 서울 열린데이터광장 · 공공누리 1유형(출처표시)';

/** 상권 하나의 덩어리. 상권끼리 더하지 않는다. */
function DistrictBlock({ row, scaleMax }: { row: DistrictOpenClose; scaleMax: number }) {
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

  return (
    <div className="oc__district">
      <p className="oc__name">{title}</p>
      <p className="oc__latest">
        <strong className="oc__num">{storeTotalText(latest.similr_induty_stor_co)}</strong>
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
      {behind && <p className="oc__note">{`이 상권 자료는 ${label}까지입니다.`}</p>}

      {cells.length > 0 && <Trend cells={cells} windowLabel={windowText(row.window_quarters)} />}

      {inds && (
        <details className="oc__ind">
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
                  <tr key={i.svc_induty_cd}>
                    <th scope="row">{i.svc_induty_cd_nm || i.svc_induty_cd}</th>
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
function Trend({ cells, windowLabel }: { cells: TrendCell[]; windowLabel: string }) {
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
      <div className="oc__cols" style={{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }}>
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
                {c.q ? `${c.q}분기` : ''}
                {showYear && c.year ? <span className="oc__tick-year">{`${c.year}년`}</span> : null}
              </span>
            </div>
          );
        })}
      </div>
      {cells.some((c) => c.kind !== 'ok') && (
        <p className="oc__note">
          &lsquo;–&rsquo; 칸은 그 분기에 서울시가 이 상권 자료를 내지 않은 것이고, &lsquo;표본&rsquo; 칸은 점포(프랜차이즈
          포함)가 {OPEN_CLOSE_MIN_SAMPLE}곳이 안 돼 비율을 적지 않은 분기입니다.
        </p>
      )}
    </figure>
  );
}
