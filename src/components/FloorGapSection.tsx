import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { RENT_STATS_FN } from '../lib/appConstants';
import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { isRentStatList } from '../lib/rentStats';
import { takePrefetched, type RpcResult, type SidePrefetch } from '../lib/sidePrefetch';
import {
  FLOOR_GAP_BASE_NOTE,
  FLOOR_GAP_FOOT,
  FLOOR_GAP_SUMMARY,
  floorGapHeads,
  floorGapRows,
  floorGapShowable,
  txTotal,
  type GapCell,
} from '../lib/floorGap';
import type { BasePrice, FloorRow, RentStat, SigunguTxStat } from '../types';
import { SectionCard } from './SectionCard';

/**
 * 「층별 공표값 나란히」 카드(결정 0036 결정 15 · 물결 1-C2 · 👤 2026-10-11 → 결정 0041 E2 · 👤 2026-10-18).
 *
 * 이 건물의 층마다 국세청 기준시가 · 구 상가 단가 · 부동산원 층별 임대료를 **각자 원래 단위로**
 * 한 줄에 둔다. 짝짓기는 `lib/floorGap.ts` 한 곳이다. 결정 0041 로 내린 참고 매매 시세 카드의 자리를
 * 이어받았고, 그 카드 안에 있던 국세청 기준시가의 「호 N개 가운데값 · 고시일」은 이 카드의 기준시가 칸으로 옮겼다.
 *
 * ⛔ **비율·나누기 0** — 층끼리도 자료끼리도 견주는 산수를 넣지 않는다(결정 15 · 0031). 발 문구가
 *    그 사실을 적는다. 접힌 요약에도 값을 적지 않는다.
 * ⛔ 재료 셋은 층별 화면이 이미 받는 것을 그대로 쓴다 — 기준시가·구 단가는 부모가 받은 것,
 *    부동산원은 임대 카드와 **같은 미리 보낸 답**(`takePrefetched` 는 같은 Promise 를 몇 번이든
 *    내준다 — 꺼내 가도 비지 않는다). 새 서버 함수 0.
 * ⛔ 재료 하나가 실패하면 그 칸만 '–' · 값 든 칸이 **하나라도** 있으면 선다 — 셋 다 비면(실패·null·빈 배열·
 *    모든 층 '–') 카드째 숨긴다(결정 0041 E2 · `floorGapShowable`) · 층 0줄도 숨긴다.
 * ⓘ 부동산원은 미리 보낸 답이 없을 때만 한 번 직접 묻는다(아래 폴백 — 지금 층별 화면은 늘 미리 보낸다).
 */
type Props = {
  floors: FloorRow[];
  /** 부모가 받은 기준시가. null = 아직 안 왔거나 못 읽음. */
  basePrices: BasePrice[] | null;
  /** 부모가 받은 구 층대 단가. null = 아직 안 왔거나 못 읽음. */
  txStats: SigunguTxStat[] | null;
  pnu: string;
  prefetch?: SidePrefetch | null;
  /** 건물 좌표가 없다(`lacksCoord`) — 부동산원 빈 답의 뜻이 '조사 대상 아님'이 아니다. */
  noCoord?: boolean;
  plan?: SectionPlan;
};

export function FloorGapSection({
  floors,
  basePrices,
  txStats,
  pnu,
  prefetch,
  noCoord = false,
  plan = SECTION_PLAN.floorgap,
}: Props) {
  /** 부동산원 조사값. null = 아직 안 왔거나 못 읽음(그때 그 칸만 '–'). */
  const [rentRows, setRentRows] = useState<RentStat[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRentRows(null);
    const req: PromiseLike<RpcResult> =
      takePrefetched(prefetch, RENT_STATS_FN, pnu) ?? supabase.rpc(RENT_STATS_FN, { p_pnu: pnu });
    req.then(({ data, error }) => {
      if (cancelled) return;
      if (error || !isRentStatList(data)) {
        console.warn('세 잣대 — 부동산원 조사값을 못 받아 그 칸 없이 표시합니다', error ?? data);
        return;
      }
      setRentRows(data);
    });
    return () => {
      cancelled = true;
    };
  }, [pnu, prefetch]);

  if (floors.length === 0) return null;

  const rows = floorGapRows(floors, basePrices, txStats, rentRows);
  if (!floorGapShowable(rows)) return null;
  const heads = floorGapHeads(txStats, rentRows, noCoord);
  const total = txTotal(txStats);

  return (
    <SectionCard plan={plan} className="gap card--floorgap" summary={FLOOR_GAP_SUMMARY}>
      <ol className="gap__heads">
        <li className="gap__head gap__head--base">
          <span className="grade__badge">A등급 · 공식 고시</span> {heads.base}
        </li>
        <li className="gap__head gap__head--tx">
          <span className="grade__badge">A등급 · 실거래</span> {heads.tx}
          {total !== null && <span className="gap__n"> · 구 합계 표본 {total.toLocaleString('ko-KR')}건</span>}
        </li>
        <li className="gap__head gap__head--rent">
          <span className="grade__badge">B등급 · 공식 표본조사</span> {heads.rent}
        </li>
      </ol>
      <ol className="gap__rows">
        {rows.map((r) => (
          <li className="gap__row" key={r.floorNo} data-floor={r.floorNo}>
            <span className="gap__floor">{r.label}</span>
            <GapValue k="base" label="국세청" cell={r.base} />
            <GapValue k="tx" label="구 실거래" cell={r.tx} />
            <GapValue k="rent" label="부동산원" cell={r.rent} />
          </li>
        ))}
      </ol>
      <p className="gap__foot">{FLOOR_GAP_FOOT}</p>
      <p className="gap__foot">{FLOOR_GAP_BASE_NOTE}</p>
    </SectionCard>
  );
}

/** 칸 하나. `gap__k` 는 좁은 화면(칸 머리가 위에 따로 서는 곳)에서만 보이는 짧은 이름표. */
function GapValue({ k, label, cell }: { k: string; label: string; cell: GapCell }) {
  return (
    <span className={`gap__cell gap__cell--${k}`}>
      <span className="gap__k">{label}</span>
      <span className="gap__val">{cell.value}</span>
      {cell.sub && <span className="gap__sub"> ({cell.sub})</span>}
    </span>
  );
}
