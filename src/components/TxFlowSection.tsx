import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import {
  SIGUNGU_TX_YEARLY_FN,
  TX_BASEMENT_MISSING_SINCE,
  TX_MIN_SAMPLE,
  TX_OPEN_SINCE_LABEL,
} from '../lib/appConstants';
import { ENTRY_SECTION_PLAN } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import { formatManWon, formatManWonBand } from '../lib/format';
import {
  barWidthPct,
  flowSummary,
  hasEnoughSample,
  isSigunguTxYearlyList,
  maxMedian,
  medianAreaText,
  missingRatePct,
  partialYearLabel,
} from '../lib/txFlow';
import type { SigunguTxYearly } from '../types';

/**
 * 『동네 매매 단가 흐름』 카드 — **입구**(구는 골랐고 건물은 아직 안 고른 자리)에 선다.
 *
 * 왜 이 카드가 있나 (결정 0027 · 로드맵 Wave 5)
 * --------------------------------------------
 * 층별 화면은 **한 건물**의 이야기를 하고, 그 건물에 거래가 없으면 할 말이 없다. 그런데
 * 사람이 먼저 궁금한 것은 "이 동네 단가가 그동안 어떻게 움직였나"이고, 그건 건물이 아니라
 * **구 단위**로만 답할 수 있다 — 지번이 열린 시점(`TX_OPEN_SINCE_LABEL`) 이전 거래는
 * 주소가 가려져 있어 건물에 붙일 수 없기 때문이다.
 *
 * ⛔ 숫자를 옮겨 적지 않는다
 * --------------------------
 * 자료 범위(첫 달·끝 달)·건수는 전부 서버가 준다. 이 파일과 `txFlow.ts` 에는 연도 리터럴이
 * **한 개도 없다** — 주석에도 없다(주석에 박힌 연도는 다음 사람이 그대로 화면으로 옮긴다).
 * 그 사실을 `src/lib/txFlow.test.ts` 가 두 파일의 원문을 훑어 지킨다.
 *
 * ⛔ 층별 화면의 구 단가 줄과 **다른 표**다
 * ----------------------------------------
 * 그쪽(`get_sigungu_tx_stats`)은 최근 24개월 창을 층대로 갈라 본다. 이쪽은 연도 축이고 층을
 * 가르지 않는다. 두 숫자를 한 자리에서 견주면 같은 구의 값이 서로 안 맞아 보인다.
 *
 * ⛔ 못 읽었으면 아무 말도 안 한다
 * --------------------------------
 * 마이그레이션 적용 전 라이브가 그 상태다(PGRST202). "자료 없음"이라 적으면 모르는 것을
 * 없는 것이라 말하게 된다 — LH 공고·성적표 카드와 같은 규칙이다.
 */
type Props = {
  /** 고른 구 코드 5자리. 이 구의 연도별 흐름을 서버에 묻는다. */
  sigungu: string;
};

export function TxFlowSection({ sigungu }: Props) {
  const [rows, setRows] = useState<SigunguTxYearly[] | null>(null);

  useEffect(() => {
    /*
      ⛔ 구가 바뀌면 **먼저 비운다**(LH 공고 카드와 같은 규칙). 안 비우면 새 답이 올 때까지
         앞 구의 줄이 그대로 서 있고, 새 요청이 실패하거나 빈손이면 그 줄이 **영영** 남는다 —
         강남구를 보다 서초구를 골랐는데 화면은 강남구 이름과 강남구 숫자를 계속 말한다.
         그건 에러가 아니라서 아무도 모른다.
    */
    setRows(null);

    let cancelled = false;

    supabase.rpc(SIGUNGU_TX_YEARLY_FN, { sigungu }).then(({ data, error }) => {
      if (cancelled) return;
      /*
        ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 카드는
           **입구**에 있어 터지면 검색창·지역 고르개까지 함께 사라진다.
        ⓘ 빈 배열도 여기서 함께 걷는다 — "그 구 자료가 아직 없다"는 뜻이라 할 말이 없다.
      */
      if (error || !isSigunguTxYearlyList(data) || data.length === 0) {
        console.warn('연도별 매매 단가 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
    });

    return () => {
      cancelled = true;
    };
  }, [sigungu]);

  /*
    ⓘ 기다리는 동안 **아무것도 그리지 않는다**(LH·성적표 카드와 같은 판단). 못 읽는 것이
      흔한 정상 결과라, 로딩 카드를 먼저 띄우면 나타났다 사라지는 깜빡임이 된다.
  */
  if (rows === null) return null;

  // 지역 이름도 서버가 준다 — 화면에 지역명을 글자로 박지 않는다.
  const guName = rows.find((r) => r.sigungu_nm)?.sigungu_nm ?? null;
  const max = maxMedian(rows);

  return (
    <SectionCard plan={ENTRY_SECTION_PLAN.txFlow} className="flow" summary={flowSummary(rows)}>
      <p className="flow__lead">
        {guName === null ? '' : `${guName}에서 `}신고된{' '}
        <strong>집합상가(구분소유) 매매</strong>를 해마다 모아 ㎡당 가운데값을 잰 것입니다.
        어림한 값이 아니라 <strong>신고된 거래를 그대로 센 값</strong>입니다.
      </p>

      <ul className="flow__rows">
        {rows.map((r) => {
          const enough = hasEnoughSample(r);
          const part = partialYearLabel(r);
          const miss = missingRatePct(r);
          const area = medianAreaText(r);
          return (
            <li key={r.yr}>
              <span className="flow__yr">
                {r.yr}
                {/* 해의 일부만 있는 해는 그렇다고 적는다 — 안 적으면 다른 해와 나란히
                    서면서 "그 해에는 이만큼 팔렸다"로 읽힌다. */}
                {part === null ? null : <span className="flow__part"> ({part})</span>}
              </span>
              {/* 막대는 눈으로 보는 보조선일 뿐이고, 같은 사실이 오른쪽에 글자로 있다. */}
              <span className="flow__bar" aria-hidden="true">
                <span className="flow__fill" style={{ width: `${barWidthPct(r, max)}%` }} />
              </span>
              <span className={`flow__val${enough ? '' : ' flow__val--none'}`}>
                {enough ? (
                  <>
                    ㎡당 {formatManWon(r.median_unit_price)}
                    <span className="flow__spread">
                      {' '}
                      (가운데 절반 {formatManWonBand(r.p25_unit_price, r.p75_unit_price)})
                    </span>
                  </>
                ) : (
                  /*
                    ⛔ 무엇이 모자란지 밝힌다. 오른쪽 건수 칸은 **그 해 거래 전부**(`n_all`)인데
                       모자란지 아닌지는 **단가가 있는 거래**(`n`)로 가른다. 둘이 갈리는 날
                       ("표본 부족 · 100건") 사람은 우리가 100건을 놓고 숨긴다고 읽는다.
                  */
                  `표본 부족 (단가 있는 거래 ${r.n.toLocaleString('ko-KR')}건)`
                )}
              </span>
              {/*
                꼬리는 조각마다 통째로 유지한다(`.flow__n > span` 이 nowrap). 좁은 폭에서는
                조각 **사이**에서만 접힌다 — 조각 안에서 끊기면 '한 건 면적 / 중앙값 40㎡'
                처럼 한 사실이 두 줄에 갈려 읽힌다.
              */}
              <span className="flow__n">
                <span>
                  {r.n_all.toLocaleString('ko-KR')}건
                  {miss === null ? '' : ` · 층 미상 ${miss}%`}
                </span>
                {/*
                  ⛔ 표본이 모자란 해는 이 칸도 감춘다 — 단가와 **같은 거래들**을 잰 값이라,
                     값을 감추면서 이것만 남기면 감춘 근거를 곁눈으로 말해 주는 셈이 된다.
                  ⛔ 서버가 이 칸을 안 주면(마이그레이션 전) 이 조각만 조용히 빠진다.
                */}
                {enough && area !== null ? <span> · 한 건 면적 중앙값 {area}</span> : null}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="grade">
        <span className="grade__badge">A등급 · 실거래</span>
        어림한 값이 아니라 <strong>신고된 거래를 그대로 센 값</strong>입니다. 표본이{' '}
        {TX_MIN_SAMPLE}건 미만인 해는 수치를 적지 않습니다 — 몇 건으로 낸 가운데값은 숫자
        모양만 통계이기 때문입니다.
      </p>

      <p className="flow__src">
        출처: 국토교통부 상업업무용 부동산 매매 실거래가 · 집합(구분소유) 거래만 · 해제된
        거래 제외. “층 미상”은 신고 자료에 층이 빠진 거래의 비율입니다 —{' '}
        {TX_BASEMENT_MISSING_SINCE}년부터는 지하층이 자료에 아예 없어 이 칸에 섞여 있습니다.{' '}
        “한 건 면적”은 그 해 단가 근거가 된 거래 한 건의 건물면적 중앙값입니다 — 다른 해보다
        유난히 작으면 초소형 구획이 무더기로 거래된 해입니다. {TX_OPEN_SINCE_LABEL} 이전
        거래는 지번이 가려져 건물과 잇지 못하므로, 이 카드는 구 단위로만 셉니다.
      </p>
    </SectionCard>
  );
}
