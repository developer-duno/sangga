import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { PRICE_GATE_FN } from '../lib/appConstants';
import { ENTRY_SECTION_PLAN } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import {
  coverageNote,
  formatPercent,
  gateLine,
  isPriceGateList,
  loadScorecard,
  pickGate,
  stageDistribution,
  stampDate,
} from '../lib/scorecard';
import type { PriceGateRow, Scorecard } from '../types';

/**
 * "참고 시세는 얼마나 맞나" 카드 — **입구**(구는 골랐고 건물은 아직 안 고른 자리)에 선다.
 *
 * 왜 이 카드가 있나 (로드맵 Wave 4 『성적표 공개 + 방법 공개』)
 * -----------------------------------------------------------
 * 층별 화면의 『참고 매매 시세』는 **어떤 구에서는 아예 안 나온다**(결정 0013 §2 — 사다리가
 * 이미 화면에 있는 구 평균보다 못한 구에서는 켜지 않는다). 그런데 그 사실을 화면 어디서도
 * 말하지 않으면, 사람은 "자료가 없나 보다"로 읽는다 — 실제로는 **자료가 있는데도 못 믿을
 * 값이라 안 내는 것**이고, 그 구별을 밝히는 것이 이 카드의 일이다.
 *
 * ⛔ 숫자를 옮겨 적지 않는다
 * --------------------------
 * 판정은 서버(`list_price_gate()`)가, 방법·단계 분포는 구워 둔 파일(`/scorecard-v1.json`)이
 * 준다. 이 파일에 통계 수치 리터럴은 **한 개도 없다** — 한 번 옮겨 적으면 성적표를 다시
 * 뽑는 날 화면만 옛 성적을 말하고, 그것은 에러가 아니라 조용한 거짓말이다.
 * (`src/lib/scorecard.test.ts` 가 이 두 파일을 정규식으로 훑어 지킨다.)
 *
 * ⛔ 못 읽었으면 아무 말도 안 한다
 * --------------------------------
 * 게이트를 못 읽으면 카드를 통째로 생략한다(LH 공고 카드와 같은 규칙). "성적 없음"이라
 * 적으면 모르는 것을 없는 것이라 말하게 된다.
 */
type Props = {
  /**
   * 고른 구 코드 5자리. 이 구의 판정이 접힌 요약 한 줄에 나온다.
   *
   * ⓘ 서버에는 **구를 안 넘긴다** — 함수가 인자 없이 열린 구를 전부 주고, 화면은 그중
   *   한 줄을 골라 쓴다. 전체 표(③)도 같은 답에서 나오므로 왕복이 한 번이면 된다.
   */
  sigungu: string;
};

/** 게이트와 성적표를 함께 담는다 — 둘이 따로 도착해 카드가 두 번 튀지 않게. */
type Loaded = {
  gate: PriceGateRow[];
  /** 못 읽었으면 null — 그때는 판정만 보여주고 방법·분포는 없다고 밝힌다. */
  card: Scorecard | null;
};

export function ScorecardSection({ sigungu }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;

    /*
      ⓘ 둘을 **같이 기다린다.** 따로 담으면 게이트가 먼저 와서 카드가 섰다가 성적표가
        도착하며 내용이 늘어난다 — 그 깜빡임을 사람은 고장으로 읽는다.
      ⓘ 구가 바뀌어도 답은 같다(함수가 열린 구 전부를 준다). 그래도 다시 묻는 것은
        supabase 쪽에 캐시가 없어서고, 성적표 파일 쪽은 `loadScorecard` 가 한 번만 받는다.
    */
    const gatePromise = supabase.rpc(PRICE_GATE_FN).then(({ data, error }) => {
      // ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 카드는
      //    **입구**에 있어 터지면 검색창·지역 고르개까지 함께 사라진다.
      if (error || !isPriceGateList(data)) {
        // 마이그레이션 적용 전 라이브가 바로 이 상태다(PGRST202).
        console.warn('참고 시세 성적 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return null;
      }
      return data;
    });

    // 성적표 파일은 **없어도 카드는 선다** — 판정만으로도 할 말이 있다.
    const cardPromise = loadScorecard().catch((err) => {
      console.warn('성적표 파일을 못 읽었습니다 — 판정만 표시합니다', err);
      return null;
    });

    Promise.all([gatePromise, cardPromise]).then(([gate, card]) => {
      if (cancelled) return;
      // ⛔ 판정이 없으면 카드를 안 만든다 — 요약 한 줄이 거기서 나오기 때문이다.
      //    빈 배열도 같다(게이트 표가 아직 안 채워진 상태라 할 말이 없다).
      if (gate === null || gate.length === 0) return;
      setLoaded({ gate, card });
    });

    return () => {
      cancelled = true;
    };
  }, []);

  /*
    ⓘ 기다리는 동안 **아무것도 그리지 않는다**(LH 공고 카드와 같은 판단). 못 읽는 것이
      흔한 정상 결과라, 로딩 카드를 먼저 띄우면 나타났다 사라지는 깜빡임이 된다.
  */
  if (loaded === null) return null;

  const { gate, card } = loaded;
  const mine = pickGate(gate, sigungu);
  const stamp = card === null ? null : stampDate(card.generated_at);

  // 접혀 있어도 보이는 한 줄 — "우리 구는 받나 못 받나" + 언제 잰 성적인가.
  const summary = [
    gateLine(mine),
    card === null ? null : `성적표 ${card.version}`,
    stamp === null ? null : `${stamp} 생성`,
  ]
    .filter((s) => s !== null)
    .join(' · ');

  const stages = card === null ? [] : stageDistribution(card);
  const note = card === null ? null : coverageNote(card);

  return (
    <SectionCard plan={ENTRY_SECTION_PLAN.scorecard} className="score" summary={summary}>
      <p className="score__lead">
        참고 매매 시세는 <strong>곁에서 실제로 팔린 값</strong>으로 어림합니다. 그 어림이 얼마나
        맞는지 실제 계약가로 채점해 봤고, <strong>잘 맞는 구에서만</strong> 값을 냅니다.
      </p>

      {/* ① 이 구 */}
      <div className="score__mine">
        <h4 className="score__h">이 구의 성적</h4>
        {mine === null ? (
          <p className="score__none">
            고른 구의 성적을 찾지 못했습니다. 아직 채점하지 않은 지역일 수 있습니다.
          </p>
        ) : (
          <ul className="score__facts">
            <li>
              <span className="score__k">검증 거래</span>
              <span className="score__v">
                {mine.n_paired === null ? '모름' : `${mine.n_paired.toLocaleString('ko-KR')}건`}
              </span>
            </li>
            <li>
              <span className="score__k">곁의 거래로 어림했을 때 오차 중앙값</span>
              <span className="score__v">{formatPercent(mine.ladder_mdape) ?? '모름'}</span>
            </li>
            <li>
              <span className="score__k">구 평균만 썼을 때 오차 중앙값</span>
              <span className="score__v">{formatPercent(mine.base_mdape) ?? '모름'}</span>
            </li>
            <li>
              <span className="score__k">참고 시세 제공</span>
              <span className={`score__v score__v--${mine.gate_pass ? 'pass' : 'fail'}`}>
                {mine.gate_pass ? '제공' : '제공 안 함'}
              </span>
            </li>
          </ul>
        )}
        {mine !== null && !mine.gate_pass && (
          // ⛔ 탈락 사유를 적는다 — "자료가 없어서"와 "믿을 만하지 않아서"는 다른 말이다.
          //    특히 오차가 기준선 안인데도 떨어진 구가 있다(구 평균이 더 정확한 경우).
          <p className="score__why">{gateLine(mine)}</p>
        )}
      </div>

      {/* ② 화면에서 체감하는 단계 분포 */}
      {stages.length > 0 && (
        <div className="score__stages">
          <h4 className="score__h">화면에서 체감하는 단계 분포</h4>
          <p className="score__sub">
            곁의 거래를 위에서부터 찾다가 <strong>처음 걸린 자리</strong>의 값을 씁니다. 아래는
            채점한 거래들이 실제로 어느 자리에서 멈췄는지입니다 — <strong>많이 걸린 순서</strong>
            라, 맨 위가 사람들이 화면에서 가장 자주 만나는 자리입니다.
          </p>
          <ul className="score__rows">
            {stages.map((s) => (
              <li key={s.code}>
                <span className="score__stage">{s.code}</span>
                {s.note !== '' && <span className="score__note">{s.note}</span>}
                <span className="score__share">
                  {formatPercent(s.share) ?? '—'} ({s.n.toLocaleString('ko-KR')}건)
                </span>
                {/* ⛔ 값을 못 낸 자리에는 '0%'를 적지 않는다 — 모르는 것을 없는 것이라
                    말하게 된다(오차가 0이라는 정반대의 뜻이 된다). */}
                {formatPercent(s.mdape) !== null && (
                  <span className="score__err">오차 중앙값 {formatPercent(s.mdape)}</span>
                )}
              </li>
            ))}
          </ul>
          {note !== null && <p className="score__honest">{note}</p>}
        </div>
      )}

      {/* ③ 전체 구 */}
      <div className="score__all">
        <h4 className="score__h">채점한 구 전체</h4>
        <ul className="score__rows">
          {gate.map((g) => (
            <li key={g.sigungu_code} className={g.gate_pass ? 'is-pass' : 'is-fail'}>
              {/* 구 이름만으로는 갈리지 않는다 — '중구'·'동구'·'서구'가 서울과 대전에 함께
                  있다. 코드를 함께 적어 두면 같은 이름 두 줄이 서로 다른 곳임이 보인다. */}
              <span className="score__gu">{g.sigungu_nm ?? g.sigungu_code}</span>
              <span className="score__code">{g.sigungu_code}</span>
              <span className={`score__v score__v--${g.gate_pass ? 'pass' : 'fail'}`}>
                {g.gate_pass ? '제공' : '제공 안 함'}
              </span>
              <span className="score__err">
                {formatPercent(g.ladder_mdape) ?? '—'} / 구평균 {formatPercent(g.base_mdape) ?? '—'}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* ④ 방법 + 도장 */}
      <div className="score__how">
        <h4 className="score__h">어떻게 채점했나</h4>
        {card === null ? (
          // 파일만 못 읽은 경우. 판정은 위에 그대로 있으므로 이 칸만 비운다.
          <p className="score__none">방법·단계 분포는 지금 읽을 수 없습니다.</p>
        ) : (
          <ul className="score__how-list">
            <li>
              <strong>지난 자료로 그 뒤를 맞혀 봤습니다.</strong> 어느 시점까지의 거래만
              보여주고 그 뒤에 실제로 팔린 값을 맞히게 한 뒤 계약가와 견줬습니다 — 답을 미리
              안 보여주는 시험입니다(무작위로 섞어 나누면 성적이 부풀려집니다).
            </li>
            <li>
              <strong>구마다 따로 채점했습니다.</strong> 상가는 지역별 표본이 적어 전체 평균
              하나로는 아무 말도 못 합니다.
            </li>
            <li>
              <strong>이미 화면에 있는 값과 견줬습니다.</strong> 견줄 상대는 그 구의 비슷한 층
              평균값입니다. 그것보다 낫지 않으면 새 어림을 얹을 이유가 없습니다.
            </li>
            <li>
              <strong>두 조건을 다 넘긴 구에서만 켭니다</strong> — 오차 중앙값이 기준선 안이고,
              구 평균보다 정확할 것(결정 0013).
            </li>
          </ul>
        )}
        <p className="grade">
          <span className="grade__badge">
            검증 성적 · 원본 성적표{card === null ? '' : ` ${card.version}`}
          </span>
          {stamp === null
            ? '성적표를 뽑은 날짜를 읽지 못했습니다.'
            : `${stamp}에 뽑은 성적입니다.`}{' '}
          새 거래가 쌓여 성적표를 다시 뽑으면 켜지고 꺼지는 구가 바뀔 수 있습니다.
        </p>
      </div>
    </SectionCard>
  );
}
