import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { RENT_STATS_FN } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import {
  defaultBldType,
  isRentStatList,
  RENT_NO_COORD_TEXT,
  rentSummary,
  toRentRows,
  typeOptions,
} from '../lib/rentStats';
import type { RentStat } from '../types';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';

/**
 * "상권 임대 동향 (부동산원 조사)" 카드 — 층별 화면의 여섯 번째 카드(결정 0024).
 *
 * ⛔ **추정이 아니다.** 한국부동산원이 분기마다 표본을 조사해 공표한 값을 **그대로** 옮겨
 *    적는다. 층별 표도 부동산원이 층 구간마다 공표한 임대료 그대로다(결정 0031). 건물·층별
 *    임대료를 우리가 계산해 추정하는 일은 검증 수단이 생기기 전까지 하지 않는다(절대 규칙 5)
 *    — 이 카드에는 곱하기가 하나도 없다. 공표 단위(천원/㎡)를 원으로 바꾸는 것뿐이고 그
 *    사실도 화면이 밝힌다.
 * ⛔ **층별 표를 층 목록의 층 줄에 붙이지 않는다**(결정 0031 결정 2) — 붙이면 "이 건물 이
 *    층의 임대료"로 읽힌다. 실제로는 조사 상권의 평균이라 이 카드 안에서만 보여준다.
 * ⛔ **이 건물의 임대료가 아니다.** 이 건물이 **속한 상권**의 조사값이다. 그래서 제목부터
 *    "상권"이라 적고, 첫 줄과 등급 문단이 같은 말을 한 번 더 한다.
 * ⛔ **종류(집합상가·중대형·소규모·오피스)를 섞지 않는다.** 모집단이 다른 네 조사라 더하거나
 *    평균 내면 아무것도 아닌 숫자가 된다 — 한 번에 하나만 보여주고, 무엇을 보는 중인지
 *    늘 글자로 적는다(고르개는 종이에서 사라지지만 그 글자는 남는다).
 * ⛔ **없는 값을 이웃 값으로 메우지 않는다.** 조사 대상이 아닌 자리에는 시·도 평균을 적지
 *    않고 그렇다고 말한다 — 조사하지 않은 곳을 조사한 것처럼 말하지 않기 위해서다.
 */
type Props = {
  /** 이 필지. 바뀌면 처음부터 다시 묻는다. */
  pnu: string;
  /**
   * 부모(층별 화면)가 건물을 고른 순간 먼저 보내 둔 요청. 이 pnu 것이 있으면 그 결과를 쓰고,
   * 없으면(다른 필지 것·안 줌) 지금처럼 스스로 묻는다 — `lib/sidePrefetch.ts`.
   */
  prefetch?: SidePrefetch | null;
  /**
   * 이 건물의 좌표가 없다(`lacksCoord` — lat/lng 가 명시적 null). 그때 빈 답은 "조사 대상
   * 아님"이 아니라 "상권을 못 찾음"이다(서버가 좌표 없는 필지에도 빈 배열을 준다 · 2026-10-06).
   * 안 주면(옛 부모) 지금 글 그대로.
   */
  noCoord?: boolean;
  /**
   * 이 카드의 배치(제목·역할·기본 펼침). 층별 화면이 고른 역할의 표를 준다(결정 0036 결정 18).
   * 안 주면 `SECTION_PLAN.rent` — 역할을 고르기 전 화면 그대로.
   */
  plan?: SectionPlan;
};

export function RentStatSection({
  pnu,
  prefetch,
  noCoord = false,
  plan = SECTION_PLAN.rent,
}: Props) {
  /**
   * 받아 온 조사값. **아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다.**
   *
   * ⓘ LH 공고 카드와 같은 판단이다 — 기다리는 동안에도 아무것도 안 그리므로 두 상태의
   *   결과가 같다. 결과가 같은 상태를 둘로 나눠 두면 읽는 사람이 "어딘가 다르게 쓰이겠지"
   *   하고 찾아 헤맨다. (업종 분포는 "불러오는 중…"을 그려서 갈라 둘 이유가 있었다.)
   * ⛔ 빈 배열(`[]`)은 null 과 **다르다** — "물어봤더니 조사 대상이 아니었다"는 답이라
   *   카드를 세우고 그렇게 적는다.
   */
  const [rows, setRows] = useState<RentStat[] | null>(null);
  /** 고른 건물 종류. null = 아직 안 골랐다(그때는 있는 것 중 첫째를 본다). */
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다 — 안 지우면 새 건물 밑에 앞 건물의 상권 조사값이 잠깐
    // 붙어 보이고, 그 짧은 순간이 그대로 틀린 정보다(다른 카드들과 같은 원칙).
    setRows(null);
    setPicked(null);

    // 부모가 먼저 보내 둔 이 필지의 답이 있으면 그것을 받는다(`lib/sidePrefetch.ts`).
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, RENT_STATS_FN, pnu) ??
      supabase.rpc(RENT_STATS_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      if (cancelled) return;
      // ⚠️ 모양까지 본다(칸 하나하나). 뜻밖의 답이 렌더로 흘러들면 그 자리에서 터지고,
      //    그러면 곁다리 카드 하나 때문에 층별 화면이 통째로 오류 안내가 된다.
      if (error || !isRentStatList(data)) {
        // 마이그레이션 적용 전 라이브가 바로 이 상태다(PGRST202). "조사값 없음"이라
        // 적지 않는다 — 없는 것과 모르는 것은 다르다(업종 분포·LH 카드와 같은 규칙).
        console.warn('상권 임대 조사값 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
    });

    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  // 아직 안 왔거나 못 읽었다 = 카드 없음(위 주석 참조).
  if (rows === null) return null;

  const summary = rentSummary(rows, noCoord);

  /*
    ⛔ 조사 대상이 아닌 자리에서도 **카드는 선다.** 그냥 사라지면 사람은 "이 서비스는 임대
       이야기를 안 하는구나"로 읽고 다른 데를 찾아간다. "조사가 닿지 않은 자리"라는 사실
       자체가 정보이고, 그것이 곧 **왜 여기 숫자가 없는지**에 대한 답이다(건물 스펙 4칸을
       "미상"으로 남겨 두는 것과 같은 판단).
  */
  if (rows.length === 0 && noCoord) {
    // 좌표가 없어 상권을 못 찾은 것이다 — 개업·폐업 카드의 같은 사정과 같은 글(`rentStats.ts`).
    return (
      <SectionCard plan={plan} className="rent rent--none" summary={summary}>
        <p className="rent__lead">{RENT_NO_COORD_TEXT}</p>
        <p className="rent__src">출처: 한국부동산원 상업용부동산 임대동향조사.</p>
      </SectionCard>
    );
  }

  if (rows.length === 0) {
    return (
      <SectionCard plan={plan} className="rent rent--none" summary={summary}>
        <p className="rent__lead">
          부동산원 임대동향조사는 전국 모든 상권이 아니라 <strong>정해진 표본 상권</strong>만
          조사합니다. 이 자리가 그 표본에 들지 않았다는 뜻이지, 장사가 안 되는 자리라는 뜻이
          아닙니다.
        </p>
        <p className="rent__note">
          가까운 다른 상권이나 시·도 평균을 대신 적지 않습니다 —{' '}
          <strong>조사하지 않은 곳을 조사한 것처럼</strong> 말하게 되기 때문입니다.
        </p>
        <p className="rent__src">출처: 한국부동산원 상업용부동산 임대동향조사.</p>
      </SectionCard>
    );
  }

  const options = typeOptions(rows);
  // 고른 것이 지금 목록에 없으면(건물이 바뀌던 찰나) 있는 것 중 첫째로 되돌린다 —
  // 없는 종류를 고른 채로 두면 값이 하나도 없는 카드가 된다.
  // ⓘ 되돌릴 기본값은 `defaultBldType` **한 곳**에서 정한다. 여기 `options[0]` 이라고 손으로
  //   다시 적어 두면(2026-09-05 이전이 그랬다) 그 함수의 규칙이 바뀌는 날 이 화면만 옛
  //   규칙을 쓰게 된다 — 값은 글자 그대로 같다(`typeOptions(rows)[0]`).
  const bldType = picked !== null && options.includes(picked) ? picked : defaultBldType(rows);
  // ⓘ `bldType` 이 null 이 되는 경우는 하나다 — 온 줄이 전부 종류 칸이 빈 글자일 때.
  //   예전에는 `options[0]`(런타임 undefined)이라 결과가 마찬가지로 빈 목록이었다 —
  //   그 때도 카드는 서고 "이번 조사에서 값이 나오지 않았습니다"라고 적는다(동작 그대로).
  const shown = bldType === null ? [] : toRentRows(rows, bldType);
  // 층별 표가 하나라도 그려질 때만 표에 딸린 문장(표 아래 · 1층 값과의 관계)을 적는다 —
  // 표가 없는데 "층별 표의 1층 값"을 말하면 찾을 수 없는 것을 가리키게 된다.
  const hasFloorTable = shown.some((r) => r.floorRents.length > 0);
  // 소득수익률 값이 보이는 줄이 하나라도 있을 때만 그 정의를 적는다 — 값이 없는데 정의만
  // 남으면 찾을 수 없는 것을 설명하게 된다(층별 표 문장과 같은 이치).
  const hasIncome = shown.some((r) => r.metrics.some((m) => m.key === 'income'));
  // 상가 3종과 오피스는 ㎡당 임대료의 기준층이 다르다(부동산원 정의) — 문장도 갈라 적는다.
  // 그 밖의 종류(부동산원이 늘리는 날)는 기준을 모르므로 아무 말도 붙이지 않는다.
  const isShop = bldType === '집합상가' || bldType === '중대형상가' || bldType === '소규모상가';
  const isOffice = bldType === '오피스';

  return (
    <SectionCard plan={plan} className="rent" summary={summary}>
      <p className="rent__lead">
        <strong>이 건물의 임대료가 아니라 이 건물이 속한 상권의 조사값입니다.</strong> 한국부동산원이
        분기마다 표본을 조사해 공표한 값을 그대로 옮겨 적었습니다.
      </p>

      {/* 종이에서는 고르개가 빠지므로(인쇄 규칙) **무엇을 보는 중인지는 이 줄이 지킨다.** */}
      <p className="rent__now">
        지금 보는 종류: <strong className="rent__now-type">{bldType}</strong>
      </p>

      {options.length > 1 && (
        <div className="rent__pick">
          <label className="rent__pick-label" htmlFor="rent-type">
            건물 종류 골라보기
          </label>
          <select
            id="rent-type"
            className="rent__select"
            value={bldType ?? ''}
            onChange={(e) => setPicked(e.target.value)}
          >
            {options.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      )}

      {shown.length === 0 ? (
        // 종류는 있는데 이번 조사에 값이 안 온 경우(부동산원은 지표별로 따로 공표한다).
        // "0%"라고 적지 않는다 — 모르는 것을 없는 것이라 말하게 된다.
        <p className="rent__none">이 종류는 이번 조사에서 값이 나오지 않았습니다.</p>
      ) : (
        <ul className="rent__rows">
          {shown.map((r) => (
            <li key={r.key}>
              <span className="rent__where">{r.districtNm}</span>
              {/*
                우리 상권 이름과 부동산원 조사구역 이름은 **다른 이름**이라 함께 적는다.
                한 상권이 조사구역 둘에 이어져 있으면 같은 상권 아래 줄이 둘 서는데, 이
                이름이 없으면 사람은 같은 것을 두 번 보는 줄 안다.
              */}
              <span className="rent__scope">부동산원 조사구역 {r.regionNm}</span>
              <span className="rent__vals">
                {r.metrics.map((m) => (
                  <span className="rent__val" key={m.key}>
                    {/* 한 덩어리 글자로 낸다 — 조각으로 쪼개면 화면에는 같아 보여도
                        "공실률 3.5%"를 한 낱말로 찾는 시험이 못 찾는다. */}
                    <strong className={`rent__num rent__num--${m.key}`}>{`${m.label} ${m.value}`}</strong>
                  </span>
                ))}
              </span>
              {/*
                층별 표 — **이 줄(조사구역 × 보는 중인 종류) 바로 아래**에 선다. 줄이 여럿이면
                표도 여럿이라 어느 조사구역의 표인지 섞이지 않는다(결정 0031).
                ⛔ 머리글에 "이 건물 값이 아님"을 박는다 — 표 모양이 층 목록과 닮아 이 건물의
                   층 임대료로 읽히기 쉽다. 없거나 모양이 이상하면 이 표만 빠진다.
              */}
              {r.floorRents.length > 0 && (
                <table className="rent__floors">
                  <caption className="rent__floors-cap">
                    층별 ㎡당 월 임대료 — 조사 상권 평균, 이 건물 값이 아님
                  </caption>
                  <tbody>
                    {r.floorRents.map((f) => (
                      <tr key={f.key} data-floor={f.key}>
                        <th scope="row">{f.label}</th>
                        <td>{f.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {/* ⛔ 분기 도장을 지우지 말 것 — 줄마다 최신 분기가 다를 수 있고, 임대 자료는
                  "언제 것인가"가 값만큼 중요하다. 못 읽었으면 지어내지 않고 뺀다. */}
              {r.quarter && <span className="rent__quarter">{r.quarter} 조사</span>}
            </li>
          ))}
        </ul>
      )}

      {hasFloorTable && (
        <p className="rent__floor-note">
          이 건물의 임대료가 아니라 이 건물이 속한 조사 상권의 평균입니다. 조사값이 없는 층 구간은
          적지 않습니다 — 지하 2층 이하와 옥탑은 부동산원이 층 구간을 발표하지 않습니다.
        </p>
      )}
      {/* 소규모상가는 조사 대상이 2층 이하 건물이라 3층 이상 줄이 **원래 없다** — 빠진 줄을
          "조사가 안 됐다"나 "값이 없다"로 읽지 않게 그 사실을 적는다(결정 0031). */}
      {bldType === '소규모상가' && (
        <p className="rent__floor-note">
          소규모상가 조사는 2층 이하 건물이 대상이라 3층 이상 값이 없습니다.
        </p>
      )}

      <p className="grade">
        <span className="grade__badge">B등급 · 공식 표본조사</span>
        우리가 어림한 값이 아니라 <strong>한국부동산원이 표본을 조사해 공표한 값</strong>입니다.
        다만 조사 단위가 건물이 아니라 상권이라, 같은 상권 안에서도 건물·층·자리에 따라 실제
        임대료는 크게 다릅니다.
      </p>
      <ul className="rent__why">
        <li>
          <strong>관리비는 포함되지 않습니다.</strong> 실제로 내는 돈은 이 값보다 큽니다. 부가가치세도
          뺀 금액입니다.
        </li>
        <li>
          임대료는 <strong>㎡당 한 달 값</strong>입니다 — 보증금을 월세로 바꿔 더한 값이고(부동산원
          환산임대료), 나누는 면적은 <strong>공용 부분까지 넣은 임대면적</strong>(전용면적+공용면적)입니다.
          ㎡당 천원 단위로 공표된 것을 원으로 바꿔 적었습니다.
        </li>
        <li>
          <strong>㎡당 임대료</strong>는 상가는 <strong>1층 기준</strong>(1층이 없으면 2층), 오피스는{' '}
          <strong>3층부터 최고층까지의 평균</strong>입니다(부동산원 정의).
          {hasFloorTable && (
            <>
              {' '}
              층별 표는 부동산원이 층 구간마다 공표한 값이며, 우리가 곱하거나 나눠 만든 값이 아닙니다.
            </>
          )}
        </li>
        {hasIncome ? (
          <li>
            투자수익률과 소득수익률은 <strong>분기 값</strong>입니다. 소득수익률은 순영업소득(임대 수입과
            그 밖의 수입에서 운영 경비를 뺀 것)을 분기 초 자산가치로 나눈 값이고, 투자수익률은 거기에
            건물값이 오르내린 몫(자본수익률)을 더한 값입니다. 4를 곱해 한 해 수익률로 바꾸지 않습니다.
          </li>
        ) : (
          <li>
            투자수익률은 <strong>분기 값</strong>입니다. 4를 곱해 한 해 수익률로 바꾸지 않습니다.
          </li>
        )}
        {/* 카드 위쪽 ㎡당 임대료와 층별 표의 1층 값이 어긋나 보일 때의 답 — 종류마다 사실만. */}
        {hasFloorTable && isShop && (
          <li>
            ㎡당 임대료는 층별 표의 1층 값과 같은 기준이라 거의 같습니다(집합상가 일부 상권은 조금
            다릅니다 — 원인은 확인되지 않았습니다).
          </li>
        )}
        {hasFloorTable && isOffice && (
          <li>㎡당 임대료는 3층 이상 평균이라 층별 표의 1층 값과 다릅니다.</li>
        )}
        <li>
          <strong>건물 종류끼리 더하거나 견주지 않습니다.</strong> 넷은 조사 대상이 서로 다른 별개의
          조사입니다.
        </li>
      </ul>
      <p className="rent__src">출처: 한국부동산원 상업용부동산 임대동향조사.</p>
    </SectionCard>
  );
}
