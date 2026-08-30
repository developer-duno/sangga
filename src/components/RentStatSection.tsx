import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { RENT_STATS_FN } from '../lib/appConstants';
import { SECTION_PLAN } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import { isRentStatList, rentSummary, toRentRows, typeOptions } from '../lib/rentStats';
import type { RentStat } from '../types';

/**
 * "상권 임대 동향 (부동산원 조사)" 카드 — 층별 화면의 여섯 번째 카드(결정 0024).
 *
 * ⛔ **추정이 아니다.** 한국부동산원이 분기마다 표본을 조사해 공표한 값을 **그대로** 옮겨
 *    적는다. 절대 규칙 5 가 말하는 "수익률·층별효용비율 역산"은 백테스트와 재결재를 거친
 *    뒤의 일이라(매매가 결정 0013 으로 그렇게 했다), 이 카드에는 곱하기가 하나도 없다 —
 *    공표 단위(천원/㎡)를 원으로 바꾸는 것뿐이고 그 사실도 화면이 밝힌다.
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
};

export function RentStatSection({ pnu }: Props) {
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

    supabase.rpc(RENT_STATS_FN, { p_pnu: pnu }).then(({ data, error }) => {
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
  }, [pnu]);

  // 아직 안 왔거나 못 읽었다 = 카드 없음(위 주석 참조).
  if (rows === null) return null;

  const summary = rentSummary(rows);

  /*
    ⛔ 조사 대상이 아닌 자리에서도 **카드는 선다.** 그냥 사라지면 사람은 "이 서비스는 임대
       이야기를 안 하는구나"로 읽고 다른 데를 찾아간다. "조사가 닿지 않은 자리"라는 사실
       자체가 정보이고, 그것이 곧 **왜 여기 숫자가 없는지**에 대한 답이다(건물 스펙 4칸을
       "미상"으로 남겨 두는 것과 같은 판단).
  */
  if (rows.length === 0) {
    return (
      <SectionCard plan={SECTION_PLAN.rent} className="rent rent--none" summary={summary}>
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
  const bldType = picked !== null && options.includes(picked) ? picked : options[0];
  const shown = toRentRows(rows, bldType);

  return (
    <SectionCard plan={SECTION_PLAN.rent} className="rent" summary={summary}>
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
            value={bldType}
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
              {/* ⛔ 분기 도장을 지우지 말 것 — 줄마다 최신 분기가 다를 수 있고, 임대 자료는
                  "언제 것인가"가 값만큼 중요하다. 못 읽었으면 지어내지 않고 뺀다. */}
              {r.quarter && <span className="rent__quarter">{r.quarter} 조사</span>}
            </li>
          ))}
        </ul>
      )}

      <p className="grade">
        <span className="grade__badge">B등급 · 공식 표본조사</span>
        우리가 어림한 값이 아니라 <strong>한국부동산원이 표본을 조사해 공표한 값</strong>입니다.
        다만 조사 단위가 건물이 아니라 상권이라, 같은 상권 안에서도 건물·층·자리에 따라 실제
        임대료는 크게 다릅니다.
      </p>
      <ul className="rent__why">
        <li>
          <strong>관리비는 포함되지 않습니다.</strong> 실제로 내는 돈은 이 값보다 큽니다.
        </li>
        <li>
          <strong>임대료는 ㎡당 값</strong>입니다 — 부동산원이 ㎡당 천원 단위로 공표한 값을 원으로
          바꿔 적었습니다.
        </li>
        <li>
          <strong>투자수익률은 분기 값</strong>입니다. 4를 곱해 한 해 수익률로 바꾸지 않습니다 —
          공표되지 않은 값을 지어내는 일입니다.
        </li>
        <li>
          <strong>건물 종류끼리 더하거나 견주지 않습니다.</strong> 넷은 조사 대상이 서로 다른 별개의
          조사입니다.
        </li>
      </ul>
      <p className="rent__src">출처: 한국부동산원 상업용부동산 임대동향조사.</p>
    </SectionCard>
  );
}
