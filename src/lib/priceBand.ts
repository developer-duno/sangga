/**
 * 참고 매매 시세 밴드(Stage B · 결정 0013)의 순수 계산·어휘.
 *
 * ⚠️ 왜 `format.ts` 가 아니라 여기인가 — 그 파일의 첫 줄이 "계산은 하지 않고 보기 좋게만
 *    바꾼다"고 약속했다. 단가 × 면적 같은 **곱셈**을 그리로 옮기면 그 약속이 깨지고,
 *    다음 사람이 "여기 계산이 있으니 나도" 하며 늘리게 된다.
 *
 * ⚠️ `median_area_m2` 는 **이 층의 면적이 아니다.** 근거로 쓴 곁 거래들의 전용면적
 *    중앙값이다 — 총액을 환산하는 자일 뿐이라, 화면에서 "이 층 32.8㎡"라고 말하면 거짓말이다
 *    (층 목록의 300㎡ 는 층 전체 연면적이라 아예 다른 단위다).
 */

import type { FloorRow, PriceBand } from '../types';
import { formatFloor } from './format';

/**
 * 서버가 주는 status 다섯. 모르는 값이 오면 화면은 **그 층을 조용히 안 그린다**
 * — 뜻을 지어내는 것보다 침묵이 낫다. 대신 콘솔에 남겨 다음 사람이 알아채게 한다.
 */
export const KNOWN_BAND_STATUS: ReadonlySet<string> = new Set([
  'ok',
  'gate_fail',
  'floor_1f',
  'no_evidence',
  'no_estimate',
]);

/**
 * ㎡당 단가 × 면적 = 총액(원). 둘 중 하나라도 없으면 null.
 *
 * ⚠️ 면적 0 도 null 로 준다. 0 을 곱해 '0원'을 만들면 없는 사실을 지어내는 것이다.
 */
export function toTotalWon(unit: number | null, areaM2: number | null): number | null {
  if (unit === null || areaM2 === null) return null;
  if (!Number.isFinite(unit) || !Number.isFinite(areaM2) || areaM2 <= 0) return null;
  return unit * areaM2;
}

/**
 * 층대 이름. 서버 함수 `price_floor_band()`(= 백테스트 `floor_band()`)와 **같은 정의**다.
 *
 * ⚠️ Stage A 의 층대(옥탑을 '3층이상'에 흡수)와 일부러 다르다 — 두 블록은 각자의 근거와
 *    같은 자를 쓴다. 화면 문구는 읽기 쉽게 '3층 이상'으로 띄어 쓰지만 뜻은 서버의 '3층+' 다.
 */
export function floorBandName(floorNo: number | null): string {
  if (floorNo === null) return '비슷한 층대';
  if (floorNo < 0) return '지하';
  if (floorNo === 99) return '옥탑';
  if (floorNo === 1) return '1층';
  if (floorNo === 2) return '2층';
  return '3층 이상';
}

/**
 * 근거 단계를 사람 말로. 모르는 코드면 null 이고, 그때 화면은 값을 내지 않는다
 * (절대 규칙 3 — 근거를 못 적으면 값도 못 낸다).
 *
 * ⛔ 'L2'·'L5' 같은 **코드 자체를 화면에 내지 않는다**(내부 번호다). ⛔ 'L1'·'L3' 은
 *    사다리에 없으므로 "4단계 중 2번째" 같은 서수도 쓰지 않는다.
 *
 * ⚠️ L2 는 "이 **건물**"이 아니라 "이 **땅**"이다 — 서버 조건이 `t.pnu = v_pnu` 라
 *    한 땅에 여러 동이 있으면 옆 동 거래가 함께 들어온다.
 * ⚠️ L6 은 같은 층이 아니라 같은 **층대**의 평균이다. 그래서 라벨에 층대 이름을 박아,
 *    사용자가 라벨만 읽고도 "이 층 값이 아니라 동네 값"임을 알게 한다.
 */
export function describeStage(
  stage: string | null | undefined,
  floorNo: number | null = null,
): string | null {
  switch (stage) {
    case 'L2':
      return '이 땅 같은 층 실거래';
    case 'L4':
      return '걸어서 1~2분 거리(100m 안) 같은 층';
    case 'L5':
      return '500m 안 같은 층';
    case 'L6':
      return `이 동네(법정동) ${floorBandName(floorNo)} 평균`;
    default:
      return null;
  }
}

/**
 * 이 땅에서 멀리 떨어진 근거인가(L5·L6).
 *
 * 백테스트에서 이 둘은 1층과 비슷한 오차대였다 — 결정 0013 이 1층을 그 오차 때문에
 * 잘라냈으므로, 같은 오차대의 근거로 낸 값에는 그렇다고 표시해 준다.
 */
export function isFarStage(stage: string | null | undefined): boolean {
  return stage === 'L5' || stage === 'L6';
}

/**
 * **폭이 0인 밴드인가** — 위아래가 붙어 밴드로 적을 수 없는 상태를 묻는다.
 *
 * ⛔ **건수 판정이 아니다.** 참이 되는 길이 둘이다: ① 표본이 1건 ② 표본이 여러 건인데
 *    사분위 셋이 같은 값(`unit_price` 가 생성 컬럼이라 같은 층 동일 단가 신고가 겹치면
 *    그렇게 된다 — 라이브에 n=10·n=6·n=5 사례가 있다). 그래서 이 술어가 참이라고 해서
 *    "거래 1건뿐"이라고 적으면 바로 밑의 표본 수와 어긋난다(건수는 `n` 으로만 판단할 것).
 *
 * L2·L6 의 최소 표본이 1건이라 폭 0 이 오는 일이 흔하다. 이걸 '2.4억~2.4억'으로 적으면
 * 사람은 "아주 정확하다"로 읽는데 사실은 정반대다.
 */
export function isSinglePoint(b: PriceBand): boolean {
  if (b.n === 1) return true;
  return b.p25 !== null && b.p75 !== null && b.p25 === b.p75;
}

/** 층을 묶은 한 줄. 층이 하나뿐이면 `floors` 길이가 1이다. */
export type BandGroup = {
  /** 화면 키 + 테스트용 식별자. */
  key: string;
  /** 이 줄이 덮는 층들. **표시 순서(고층 → 저층) 그대로**다. */
  floors: FloorRow[];
  /** 대표 밴드. 묶인 층들의 값이 전부 같으므로 아무 층 것이나 같다. */
  band: PriceBand;
  /** '2층' 또는 '3층~17층'. */
  label: string;
};

/** 값이 같아 한 줄로 묶어도 되는가를 정하는 열쇠. 하나라도 다르면 새 줄이 된다. */
function valueKey(b: PriceBand): string {
  return [b.status, b.stage, b.n, b.p25, b.median, b.p75, b.median_area_m2].join('|');
}

/**
 * 서버가 준 층별 밴드를 **화면에 그릴 줄**로 바꾼다.
 *
 * ## 왜 묶나 (2026-08-16 라이브 실측)
 *
 * 강남 필지를 재 보니 층 17개에 서로 다른 값이 **3개뿐**이었다. 15층·14층·11층 건물도
 * 마찬가지다 — 사다리의 마지막 칸(L6)은 **층대별로 한 번** 계산되므로 3층 이상 전체가
 * 같은 값이기 때문이다. 그걸 층마다 한 줄씩 뿌리면 "층마다 따로 계산했다"는 착시를 준다.
 *
 * ⚠️ 묶는 것은 **표시할 때뿐**이다. 서버·타입은 층별로 그대로 받는다 — 거래가 쌓여 층마다
 *    값이 갈라지는 날 줄이 저절로 나뉘어야 하기 때문이다(그게 이 구조의 핵심 이유다).
 *
 * ## 어떻게 묶나
 *
 * **연속한 층**(층 번호가 정확히 1씩 이어질 때) + **값이 전부 같을 때**만 묶는다. 층이
 * 중간에 비면 억지로 묶지 않고 줄을 나눈다 — 없는 층까지 덮는 범위를 적지 않기 위해서다.
 *
 * ## 짝짓기 함정
 *
 * 서버는 **필지**의 모든 층을 오름차순으로 주고, 화면은 **이 건물**의 층을 내림차순으로
 * 그린다. 인덱스로 맞추면 층이 통째로 뒤집히고 복수동 필지에서는 옆 동 층까지 섞인다 —
 * 그래서 `floors` 를 돌며 `floor_no` 로만 짝짓는다(둘 다 이 한 줄로 막힌다).
 */
export function groupBands(
  bands: PriceBand[],
  floors: FloorRow[],
): { listed: BandGroup[]; silent: FloorRow[] } {
  const byFloor = new Map<number, PriceBand>();
  for (const b of bands) {
    if (b.floor_no === null) continue;
    if (!KNOWN_BAND_STATUS.has(b.status)) continue;
    byFloor.set(b.floor_no, b);
  }

  const listed: BandGroup[] = [];
  const silent: FloorRow[] = [];

  for (const f of floors) {
    const band = byFloor.get(f.floor_no);
    if (band === undefined) continue;

    // 지하·옥탑은 같은 문장이 서너 번 반복되므로 줄에서 침묵하고, 각주에서 층 이름만
    // 모아 한 번 말한다.
    if (band.status === 'no_evidence') {
      silent.push(f);
      continue;
    }

    const prev = listed[listed.length - 1];
    const prevFloor = prev?.floors[prev.floors.length - 1];
    const canJoin =
      prev !== undefined &&
      prevFloor !== undefined &&
      valueKey(prev.band) === valueKey(band) &&
      prevFloor.floor_no - f.floor_no === 1;

    if (canJoin) prev.floors.push(f);
    else listed.push({ key: `band-${f.floor_no}`, floors: [f], band, label: '' });
  }

  for (const g of listed) g.label = rangeLabel(g.floors);
  return { listed, silent };
}

/** '2층' 또는 '3층~17층'. `floors` 는 고층 → 저층 순서로 들어온다. */
function rangeLabel(floors: FloorRow[]): string {
  const top = floors[0];
  const bottom = floors[floors.length - 1];
  const topText = formatFloor(top.floor_no, top.floor_label);
  if (floors.length === 1) return topText;
  return `${formatFloor(bottom.floor_no, bottom.floor_label)}~${topText}`;
}
