import { useEffect, useState } from 'react';
import {
  INDUSTRY_MEDIAN_FN,
  INDUSTRY_MIX_FN,
  OPEN_CLOSE_FN,
  RENT_STATS_FN,
} from '../lib/appConstants';
import { takePrefetched, type SidePrefetch } from '../lib/sidePrefetch';
import { isIndustryMedian, isIndustryMix } from '../lib/industryMix';
import { isOpenCloseList } from '../lib/openClose';
import { isRentStatList } from '../lib/rentStats';
import { roleSummaryView, type RoleSummaryInput } from '../lib/roleSummary';
import type { DistrictOpenClose, IndustryMedian, IndustryMix, RentStat } from '../types';

/**
 * 역할 요약 판(결정 0039 W2) — 건물 머리(`.stack__head`) **위**. 고르기는 `lib/roleSummary.ts`, 여기는 그리기만.
 *
 * ⛔ **서버에 스스로 묻지 않는다**(결정 0039 §4-9 「추가 서버 호출 0」). 곁 카드 값은 층별 화면이 건물을 고른 순간 미리 보낸
 *    **같은 Promise** 를 `takePrefetched` 로 받기만 한다 — 없으면(다른 필지 것·안 줌) 그 타일은 없다(카드처럼 스스로 묻지 않는다).
 *    그래서 `supabase` 를 import 하지 않는다(시험이 FloorStack 전체의 rpc 호출 수가 판 유무와 같은지 본다).
 * ⛔ 받은 답은 물어본 pnu 와 함께 둔다 — 건물이 바뀐 첫 그림에 앞 건물 값이 한 순간도 붙지 않게(`sidePrefetch.ts` 머리말).
 * ⛔ 종이에서는 빠진다(§4-2) — `styles.css` 인쇄 감춤 목록의 `.rsum` 한 줄. 넣기로 하면 그 한 줄만 뺀다.
 */
type SideGot = {
  pnu: string;
  rent: RentStat[] | null;
  openClose: DistrictOpenClose[] | null;
  mix: IndustryMix | null;
  median: IndustryMedian | null;
};

const emptyGot = (pnu: string): SideGot => ({ pnu, rent: null, openClose: null, mix: null, median: null });

type Props = Omit<RoleSummaryInput, 'rent' | 'openClose' | 'mix' | 'median'> & {
  /** 층별 화면이 미리 보낸 곁 카드 요청(이 건물 pnu 것만 쓴다). */
  prefetch: SidePrefetch | null;
  /** 「한 장으로 뽑기」 — 인쇄 창 **전에** 부른다(App 의 `handleBeforePrint` · 중개사 최근 뽑은 건물 기록). */
  onBeforePrint?: () => void;
};

export function RoleSummary({ prefetch, onBeforePrint, ...input }: Props) {
  const pnu = input.building.pnu;
  const active = input.role !== null;
  const [got, setGot] = useState<SideGot>(() => emptyGot(pnu));

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setGot(emptyGot(pnu));
    function take<K extends Exclude<keyof SideGot, 'pnu'>>(
      fn: string,
      key: K,
      ok: (x: unknown) => x is NonNullable<SideGot[K]>,
    ) {
      const p = takePrefetched(prefetch, fn, pnu);
      if (p === null) return;
      p.then(
        ({ data, error }) => {
          if (cancelled || error || !ok(data)) return;
          setGot((g) => (g.pnu === pnu ? { ...g, [key]: data } : g));
        },
        () => {},
      );
    }
    take(RENT_STATS_FN, 'rent', isRentStatList);
    take(OPEN_CLOSE_FN, 'openClose', isOpenCloseList);
    take(INDUSTRY_MIX_FN, 'mix', isIndustryMix);
    take(INDUSTRY_MEDIAN_FN, 'median', isIndustryMedian);
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch, active]);

  const mine = got.pnu === pnu ? got : emptyGot(pnu);
  const view = roleSummaryView({ ...input, ...mine });
  if (view === null) return null;

  return (
    <section className="rsum" aria-label={`${view.role} 요약`}>
      <p className="rsum__q">
        <span className="rsum__role">{view.role}</span>
        <span className="rsum__question">{view.question}</span>
      </p>
      {view.answer !== null && <p className="rsum__answer">{view.answer}</p>}
      <ul className="rsum__tiles">
        {view.tiles.map((t) => (
          <li key={t.key} className={`rsum__tile rsum__tile--${t.key}${t.grade?.est ? ' rsum__tile--est' : ''}`}>
            <span className="rsum__label">{t.label}</span>
            {t.lines.map((line, i) => (
              <span key={i} className={i === 0 ? 'rsum__val' : 'rsum__val rsum__val--more'}>
                {line}
              </span>
            ))}
            {t.grade !== null && (
              <span className={`grade__badge rsum__grade${t.grade.est ? ' grade__badge--est' : ''}`}>
                {t.grade.text}
              </span>
            )}
            {t.basis.map((b, i) => (
              <span key={i} className="rsum__basis">
                {b}
              </span>
            ))}
          </li>
        ))}
      </ul>
      {view.role === '중개사' && (
        <button
          type="button"
          className="rsum__print"
          onClick={() => {
            // 인쇄 단추(`PrintButton`)와 같은 길 — 적기가 던져도 인쇄 창은 뜬다.
            try {
              onBeforePrint?.();
            } finally {
              window.print();
            }
          }}
        >
          한 장으로 뽑기
        </button>
      )}
    </section>
  );
}
