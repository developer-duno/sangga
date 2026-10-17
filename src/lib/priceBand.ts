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
import {
  formatArea,
  formatEokBand,
  formatFloor,
  formatManWon,
  formatManWonBand,
} from './format';
import { niceCeil, pctOf, rangePct } from './viz';

/**
 * 서버가 주는 status 여덟. 모르는 값이 오면 화면은 **그 층을 조용히 안 그린다**
 * — 뜻을 지어내는 것보다 침묵이 낫다. 대신 콘솔에 남겨 다음 사람이 알아채게 한다.
 * 결정 0040(2026-10-18a): `floor_resid`(주거 층) · `floor_officetel`(오피스텔 층) · `no_use`(대장에 그 층 용도 없음).
 */
export const KNOWN_BAND_STATUS: ReadonlySet<string> = new Set([
  'ok',
  'gate_fail',
  'floor_1f',
  'no_evidence',
  'no_estimate',
  'floor_resid',
  'floor_officetel',
  'no_use',
]);

/**
 * 서버 응답(`list_price_bands`) → 화면이 믿고 쓸 줄들(결정 0040 · 맹점 🟠6).
 *
 * · 모르는 status 줄은 **뺀다**(콘솔 경고 한 줄 — 예전 `FloorStack` 의 동작 그대로).
 * · `use_group` 이 글자가 아니면(숫자·객체 등) **그 칸만 null** — 줄은 살린다(값·근거는 멀쩡하다).
 *   옛 서버는 칸 자체를 안 주므로 그대로 둔다(undefined).
 * ⛔ 숫자를 새로 계산하지 않는다(나누기·비율 0) — 모양만 거른다.
 */
export function normalizePriceBands(rows: unknown): PriceBand[] {
  if (!Array.isArray(rows)) return [];
  const out: PriceBand[] = [];
  const unknown = new Set<string>();
  for (const raw of rows as PriceBand[]) {
    if (raw === null || typeof raw !== 'object') continue;
    if (!KNOWN_BAND_STATUS.has(raw.status)) {
      unknown.add(String(raw.status));
      continue;
    }
    if ('use_group' in raw && raw.use_group !== null && typeof raw.use_group !== 'string') {
      out.push({ ...raw, use_group: null });
    } else {
      out.push(raw);
    }
  }
  // 서버가 status 를 늘리면 화면은 그 층을 조용히 안 그린다(뜻을 지어내지 않는다). 눈에 안 띄므로
  // 콘솔에는 반드시 남긴다 — status 를 늘리는 날 화면도 같은 커밋에서 고쳐야 한다는 신호다(문구는 예전 그대로).
  if (unknown.size > 0) console.warn('모르는 status 라 그 층은 그리지 않습니다', [...unknown]);
  return out;
}

/** 서버가 묶음 칸을 한 줄이라도 줬나(결정 0040 이후 서버) — 카드의 「같은 종류끼리」 글을 낼지 정한다. 옛 서버면 false. */
export function hasUseGroup(bands: readonly PriceBand[]): boolean {
  return bands.some((b) => typeof b.use_group === 'string' && b.use_group !== '');
}

/**
 * 값을 못 낸 이 층을 『층대별 거래 단가』(상가 거래 기준)로 안내해도 되나(결정 0040 ㉨ · 맹점 🟠7).
 * 그 층의 묶음이 **상가**이거나 **묶음을 모를 때만** 참이다 — 업무·숙박·기타 층이나 주거·오피스텔 층을 상가 표로 보내지 않는다.
 * · 값을 낸 줄(ok) → false(안내할 까닭이 없다)
 * · floor_resid·floor_officetel → false(상가가 아닌 층이라고 서버가 말했다)
 * · 그 밖(floor_1f·no_evidence·no_use·no_estimate) → 묶음이 shop 이거나 없거나 모르는 글자면 true
 * ⓘ 옛 서버(묶음 칸 없음)에서는 예전처럼 값 못 낸 층마다 참이다.
 */
export function bandPointsToSigunguTable(b: PriceBand): boolean {
  if (b.status === 'ok' || b.status === 'floor_resid' || b.status === 'floor_officetel') return false;
  const g = b.use_group;
  return g === undefined || g === null || g === 'shop' || bandGroupLabel(g) === null;
}

/**
 * 용도 묶음 이름표(결정 0040 D7) — 근거 줄 「업무 거래 5건」의 앞말. 모르는 값·없음 → null(그때는 「거래 5건」).
 * ⛔ 지어내지 않는다 — 넷 밖의 글자가 오면 묶음 이름을 안 붙인다.
 */
export function bandGroupLabel(group: string | null | undefined): string | null {
  switch (group) {
    case 'shop':
      return '상가';
    case 'office':
      return '업무';
    case 'lodging':
      return '숙박';
    case 'other':
      return '기타';
    default:
      return null;
  }
}

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

/**
 * 값이 같아 한 줄로 묶어도 되는가를 정하는 열쇠. 하나라도 다르면 새 줄이 된다.
 * `use_group` 도 넣는다(결정 0040 🟡19) — 값이 우연히 같은 상가 층·업무 층이 한 줄로 묶이면 종류 이름표가 하나만 남는다.
 */
function valueKey(b: PriceBand): string {
  return [b.status, b.stage, b.n, b.p25, b.median, b.p75, b.median_area_m2, b.use_group ?? ''].join('|');
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

// ── 그림: 층마다 가로 띠 (결정 0038 A · 화면만) ────────────────────────────────────

/**
 * 이 줄이 값을 내는가 — `PriceBandSection` 의 `BandBody` 가 값 글을 쓰는 조건과 **같다**
 * (status ok · 근거 글이 있음 · n·가운데값·p25·p75 가 다 있음). 값 글이 없는 줄에 띠가 서지 않게 한다.
 * ⛔ BandBody 의 조건을 바꾸면 여기도 함께 바꾼다(컴포넌트 시험 「근거를 표시할 수 없어」 줄이 "–" 인지 본다).
 */
export function bandShowsValue(g: BandGroup): boolean {
  const b = g.band;
  return (
    b.status === 'ok' &&
    describeStage(b.stage, g.floors[0].floor_no) !== null &&
    b.n !== null &&
    b.median !== null &&
    b.p25 !== null &&
    b.p75 !== null
  );
}

/**
 * 카드 축 상한(㎡당 원) — 값을 내는 줄의 p75·가운데값 가운데 가장 큰 값을 **만원 단위로** `niceCeil`(1·2·2.5·5 × 10ⁿ) 올린 값.
 * 예: p75 최대 1,904.6만 → 2,000만. 값을 내는 줄이 하나도 없으면 null(축·띠를 그리지 않는다).
 * 못 보는 것: 한 줄의 p75 가 다른 줄보다 열 배쯤 크면 나머지 띠가 얇아진다(축은 카드에 하나 — §2-7 한 눈금에 자료 하나).
 */
export function bandAxisMaxWon(groups: BandGroup[]): number | null {
  let top = 0;
  for (const g of groups) {
    if (!bandShowsValue(g)) continue;
    top = Math.max(top, g.band.p75 as number, g.band.median as number);
  }
  const man = niceCeil(top / 10_000);
  return man === null ? null : man * 10_000;
}

/** 한 줄의 그림 — 띠(p25~p75) + 가운데값 눈금 · 눈금만(폭 0) · 없음("–"). 자리·폭은 축 0~상한 위 %. */
export type BandMark =
  | { kind: 'none' }
  | { kind: 'tick'; x: number; far: boolean }
  | { kind: 'band'; left: number; width: number; x: number; far: boolean };

/**
 * 줄 하나 → 그림. 값을 안 내는 줄은 `none`(띠 없이 "–" — 까닭 글은 옆에 그대로).
 * 거래 1건뿐·모두 같은 값(`isSinglePoint`)이거나 p25 > p75 처럼 범위를 못 세우면 띠 없이 눈금만.
 * `far` = 먼 근거(L5·L6) — 연한 띠로 그린다.
 */
export function bandMark(g: BandGroup, maxWon: number | null): BandMark {
  if (!bandShowsValue(g)) return { kind: 'none' };
  const b = g.band;
  const x = pctOf(b.median, maxWon);
  if (x === null) return { kind: 'none' };
  const far = isFarStage(b.stage);
  if (isSinglePoint(b)) return { kind: 'tick', x, far };
  const r = rangePct(b.p25, b.p75, maxWon);
  if (r === null || r.width <= 0) return { kind: 'tick', x, far };
  return { kind: 'band', left: r.left, width: r.width, x, far };
}

/** '2층' 또는 '3층~17층'. `floors` 는 고층 → 저층 순서로 들어온다. */
function rangeLabel(floors: FloorRow[]): string {
  const top = floors[0];
  const bottom = floors[floors.length - 1];
  const topText = formatFloor(top.floor_no, top.floor_label);
  if (floors.length === 1) return topText;
  return `${formatFloor(bottom.floor_no, bottom.floor_label)}~${topText}`;
}

/**
 * 이보다 적은 곁 거래로 낸 폭에는 '표본 적음' 표식을 붙인다.
 *
 * ⚠️ 카드 각주의 한글 문구("곁 거래가 **다섯 건**이 안 된다는 뜻입니다" — `PriceBandSection`)와 짝이다 —
 *    바꿀 땐 두 곳을 함께 고친다(숫자만 고치면 표식과 설명이 어긋난다).
 * ⛔ 이름이 비슷한 이웃 둘과 **뜻이 다르다. 합치지 말 것**:
 *    · `FloorStack` 의 `MIN_SAMPLE` — 구 층대별 단가에서 수치를 아예 안 적는 임계
 *    · 서버 L5 의 `min_n`(`supabase/schema.sql`) — 그 근거 단계를 채택할지 정하는 임계
 *    여기 것은 "값은 내되 못 미덥다고 표시할" 임계다.
 * ⓘ 2026-10-17(결정 0039 W2) `PriceBandSection` 에서 옮김 — 값 글(`bandText`)이 여기로 와서.
 */
export const THIN_SAMPLE = 5;

/**
 * 카드 접힌 요약 줄의 빈 글 둘 — 카드(`PriceBandSection`)와 역할 요약 판의 시세 타일이 **같은 상수**를 쓴다(결정 0039 W2 · 글자 그대로).
 * `BAND_GATE_TEXT` = 이 구가 아직 참고 시세를 안 낸다(gate_fail) · `BAND_NO_VALUE_TEXT` = 값을 낸 층이 하나도 없다.
 */
export const BAND_GATE_TEXT = '아직 참고 시세를 내지 않는 구입니다';
export const BAND_NO_VALUE_TEXT = '이 건물에서는 값을 낸 층이 없습니다';

/**
 * 줄 하나의 값 글 — 카드 `BandBody` 와 역할 요약 판(결정 0039 W2)이 **같이 쓴다**(2026-10-17 카드에서 옮김 · 글자 그대로).
 * `none` = 값을 안 내는 줄의 사유 글 · `value` = 값 줄(`val`) + 근거 줄(`sub` — 근거 단계·표본 수 · 절대 규칙 3).
 * ⛔ 값을 낼지의 조건은 `bandShowsValue` 와 같다 — 한쪽을 바꾸면 다른 쪽도.
 */
export type BandText = { kind: 'none'; text: string } | { kind: 'value'; val: string; sub: string };

export function bandText(group: BandGroup): BandText {
  const band = group.band;
  if (band.status !== 'ok') return { kind: 'none', text: missingLabel(band.status) };

  // 근거를 말할 수 없으면 값도 내지 않는다 — 절대 규칙 3은 "값과 근거는 한 몸"이라는 뜻이다.
  const label = describeStage(band.stage, group.floors[0].floor_no);
  if (
    label === null ||
    band.n === null ||
    band.median === null ||
    band.p25 === null ||
    band.p75 === null
  ) {
    return { kind: 'none', text: '근거를 표시할 수 없어 값을 내지 않습니다' };
  }

  const area = band.median_area_m2;
  // 줄마다 종류(결정 0040 D7) — 「업무 거래 5건」. 묶음을 모르면(옛 서버·모르는 값) 지금처럼 「거래 5건」.
  const groupLabel = bandGroupLabel(band.use_group);
  const count = `${groupLabel !== null ? `${groupLabel} ` : ''}거래 ${band.n.toLocaleString('ko-KR')}건`;
  // 층대 평균은 층별로 따로 잰 값이 아니다. 라벨만으로도 알 수 있게 했지만, 한 줄로 묶여
  // 여러 층을 덮을 때가 많아 한 번 더 못 박는다.
  const note = band.stage === 'L6' ? '층별로 따로 잰 값이 아닙니다' : null;

  // 폭이 0인 밴드는 '2.4억~2.4억'으로 적지 않는다 — 사람은 그걸 "아주 정확하다"로 읽는데
  // 사실은 정반대다. 밴드가 아니라 사실로 적는다(채택의 절반이 최소 표본 1건짜리 단계라
  // 드문 예외가 아니다).
  //
  // ⚠️ 다만 폭이 0인 **까닭이 둘**이라 문장을 갈라야 한다: ① 곁 거래가 한 건뿐이라 폭이
  //    없는 것 ② 여러 건인데 **전부 같은 단가**로 신고돼 사분위 셋이 같아진 것(`unit_price`
  //    가 생성 컬럼이라 같은 층 동일 단가 신고가 겹치면 그렇게 된다 — 라이브에 실제로 있다).
  //    하나로 뭉뚱그리면 "1건뿐"이라 적어 놓고 바로 밑 근거 줄에서 "거래 10건"이라 말하는
  //    자기모순이 난다. 판정(`isSinglePoint`)은 폭을 묻는 것이므로 그대로 두고, **문구만** 가른다.
  if (isSinglePoint(band)) {
    const one = toTotalWon(band.median, area);
    const pointMarks = [
      isFarStage(band.stage) ? '먼 근거' : null,
      // n=1 은 헤드라인이 이미 "1건뿐"이라 말한다 — 표식을 겹쳐 붙이지 않는다.
      band.n > 1 && band.n < THIN_SAMPLE ? '표본 적음' : null,
    ].filter((m): m is string => m !== null);
    const val =
      band.n === 1
        ? `곁의 거래 1건뿐 — 그 거래는 ㎡당 ${formatManWon(band.median)}`
        : `곁 거래 ${band.n.toLocaleString('ko-KR')}건이 모두 같은 값 — ㎡당 ${formatManWon(band.median)}`;
    const sub =
      (one !== null ? `비슷한 호실 한 칸 ${formatArea(area)} 기준 ${formatEokBand(one, one)} · ` : '') +
      `근거: ${label} · ${count}` +
      (note !== null ? ` · ${note}` : '') +
      (pointMarks.length > 0 ? ` · ${pointMarks.join(' · ')}` : '');
    return { kind: 'value', val, sub };
  }

  const lo = toTotalWon(band.p25, area);
  const hi = toTotalWon(band.p75, area);
  const perBand = formatManWonBand(band.p25, band.p75);
  const marks = [
    isFarStage(band.stage) ? '먼 근거' : null,
    band.n < THIN_SAMPLE ? '표본 적음' : null,
  ].filter((m): m is string => m !== null);

  const val =
    lo !== null && hi !== null
      ? `비슷한 호실 한 칸 ${formatArea(area)} 기준 ${formatEokBand(lo, hi)}`
      : `㎡당 ${perBand}`;
  const sub =
    (lo !== null && hi !== null ? `㎡당 ${perBand} · ` : '') +
    `가운데값 ㎡당 ${formatManWon(band.median)} · 근거: ${label} · ${count}` +
    (note !== null ? ` · ${note}` : '') +
    (marks.length > 0 ? ` · ${marks.join(' · ')}` : '');
  return { kind: 'value', val, sub };
}

/**
 * 값을 못 내는 층의 사유.
 *
 * ⛔ `no_evidence` 에 "표본 부족"을 쓰지 않는다 — "조금만 더 모으면 나오나?"라는 오해를
 *    만든다(결정 0001). 그 층은 아예 줄로 그리지 않고 각주에서 한 번만 말한다.
 */
function missingLabel(status: string): string {
  if (status === 'floor_1f') {
    // ⛔ "그 자리를 알려 주는 자료가 공공데이터에 없다"고 쓰지 않는다 — 틀린 말로 드러났다
    //    (도로접면·상권 안팎은 자료에 있고, 그것까지 맞춰 다시 채점해도 기준선을 못 넘었다 —
    //    docs/backtest/1층-유형축-검증.md). 숫자는 여기 적지 않고 첫 화면 성적표 카드로 보낸다.
    return '1층은 내지 않습니다 — 같은 1층이라도 큰길 코너인지 골목 안쪽인지에 따라 값이 크게 갈립니다. 길의 넓이와 상권 안팎까지 맞춰 다시 채점해 봤지만 오차가 기준선을 넘어, 믿고 쓸 값이 못 됩니다. 층마다 얼마나 맞는지는 건물을 고르기 전 첫 화면의 「참고 시세는 얼마나 맞나」 카드에서 볼 수 있습니다.';
  }
  // 결정 0040 — 세 문구는 👤 결정 원문(D2·D9) · 메인 판단 ㉡ 그대로.
  if (status === 'floor_resid') return '주거 층이라 상가 시세를 내지 않습니다.';
  if (status === 'floor_officetel') return '오피스텔 층이라 상가 시세를 내지 않습니다.';
  if (status === 'no_use') return '대장에 이 층의 용도가 없어 값을 내지 않습니다.';
  return '표본 부족 — 곁에서 참고할 만한 거래를 아직 찾지 못했습니다. 거래가 쌓이면 나올 수 있습니다.';
}
