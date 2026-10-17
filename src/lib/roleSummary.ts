import type {
  BuildingHit,
  CoverageStats,
  DistrictOpenClose,
  FloorRow,
  IndustryMedian,
  IndustryMix,
  ParcelLandPrice,
  ParcelTransaction,
  PriceBand,
  RentStat,
} from '../types';
import type { ViewerRole } from './sectionCards';
import { chipMatch, type FounderChip } from './founderChips';
import { BAND_GATE_TEXT, BAND_NO_VALUE_TEXT, bandText, groupBands, type BandGroup } from './priceBand';
import { TX_LIST_CAP, TX_OPEN_SINCE_LABEL } from './appConstants';
import { LAND_PRICE_BADGE, LAND_PRICE_NOTE, formatLandPriceAmount } from './landPrice';
import { defaultBldType, rentSummary, toRentRows } from './rentStats';
import {
  OPEN_CLOSE_MIN_SAMPLE,
  countRateText,
  districtName,
  formatStoreCount,
  latestOf,
  openCloseQuarterLabel,
  openCloseSummary,
  storeTotalText,
} from './openClose';
import { MEDIAN_BADGE, districtLabel, medianViewOf, toBars, type MixBar } from './industryMix';
import {
  UNKNOWN_SPEC,
  describeHoCnt,
  describeOwnership,
  floorMissingPhrase,
  formatArea,
  formatFloor,
  formatJiphap,
  formatManWon,
  formatWon,
  formatYearMonth,
} from './format';
import { buildingFromFloorRows } from './restoreBuilding';

/**
 * 역할 요약 판(결정 0039 Q2 · §4-2 · §4-9 · W2) — 건물 화면 맨 위, 고른 역할의 첫 질문에 답하는 숫자 타일 3~4개 + 한 줄 답.
 *
 * 이 파일은 **고르기만** 한다(입력 = 층별 화면의 카드 상태 + 미리 보낸 곁 카드 답 · 출력 = 타일 목록 + 한 줄 답). 그리기는 `RoleSummary`.
 * ⛔ **숫자는 전부 카드 값의 복사** — 새 계산·추정 0. 글은 카드와 **같은 함수**(bandText·toRentRows·countRateText·toBars·
 *    medianViewOf·describeOwnership·describeHoCnt·landPrice…)에서 온다. 여기서 숫자를 더하거나 나누지 않는다.
 * ⛔ 카드가 따로 부르는 값(중분류 비중·중분류 가운데값 등)은 쓰지 않는다 — 입력에 그 자리가 없다(추가 서버 호출 0).
 * ⛔ **한 줄 답은 사실 문장만** — 많다·적다·되겠다·좋다 같은 판단 낱말 0(결정 0036 ㉕ · 시험이 낱말 목록으로 훑는다).
 * ⛔ **시세와 임대를 한 줄에 잇지 않는다** — 임대 타일에는 시세 숫자, 시세 타일에는 임대 숫자가 없고, 한 줄 답에는 임대가 없다
 *    (나누기·비율·수익률 0 — 결정 0031). 임대 타일은 ㎡당 임대료만(부동산원 수익률은 싣지 않는다 · 메인 ㉦).
 * ⛔ 빈 값은 뭉치지 않는다 — 실패·아직 = 타일 없음 · 0건 = 「이 땅 거래 0건」 · 대상 아님 = 카드 글 그대로.
 * ⛔ 금지어(적정가격·적정가·평가액·감정가·가치평가) 0 · 추정값은 카드처럼 근거 레벨 + 표본 수.
 */

/** 역할마다 첫 질문(결정 0039 Q2 원문). */
export const ROLE_QUESTIONS: Readonly<Record<ViewerRole, string>> = {
  투자자: '얼마고 얼마 벌리나',
  창업자: '여기서 장사가 되나',
  중개사: '손님에게 뭘 보여 주나',
};

export type TileKey =
  | 'band'
  | 'tx'
  | 'rent'
  | 'land'
  | 'industry'
  | 'openclose'
  | 'floor1'
  | 'owner'
  | 'ho'
  | 'tx3';

/** 등급 배지 — 카드와 같은 글·같은 시각 구분(`est` = 카드가 `grade__badge--est` 를 쓰는 C등급 추정·비교값). */
export type TileGrade = { text: string; est: boolean };

export type SummaryTile = {
  key: TileKey;
  /** 타일 이름표. */
  label: string;
  /** 값 글(첫 줄이 큰 글). 카드 글 그대로. */
  lines: string[];
  /** 근거·표본 줄(절대 규칙 3). */
  basis: string[];
  grade: TileGrade | null;
};

export type RoleSummaryView = {
  role: ViewerRole;
  question: string;
  tiles: SummaryTile[];
  /** 한 줄 답(사실 문장만). 말할 사실이 없으면 null. */
  answer: string | null;
};

/**
 * 입력 — 층별 화면의 카드 상태 그대로(null = 실패·아직 · 카드와 같은 뜻).
 * ⛔ 곁 카드 넷(rent·openClose·mix·median)은 **이 건물 pnu 로 미리 보낸 답**이어야 한다(부르는 쪽이 pnu 를 대조한다).
 */
export type RoleSummaryInput = {
  role: ViewerRole | null;
  chip: FounderChip;
  building: BuildingHit;
  /** 이 건물의 층(층별 화면 정렬 그대로 — 위층 먼저). 비면 판 없음. */
  floors: FloorRow[];
  stats: CoverageStats | null;
  txs: ParcelTransaction[] | null;
  bands: PriceBand[] | null;
  bandsFailed: boolean;
  landPrice: ParcelLandPrice | null;
  /** 좌표 없는 건물(`lacksCoord`) — 임대 카드의 빈 답 글이 갈린다. */
  noCoord: boolean;
  rent: RentStat[] | null;
  openClose: DistrictOpenClose[] | null;
  mix: IndustryMix | null;
  median: IndustryMedian | null;
};

/**
 * 1층 칸의 '층 미상' 근거 글 — **이 함수 하나에서만** 나온다.
 * ⓘ 👤 확정(결정 0039 §7-6 · 2026-10-17): 이 건물의 층 미상 점포 수는 자료에 없어 **서비스 지역 전체 비율**(카드 각주와 같은
 *    `floorMissingPhrase`)을 「서비스 지역 전체」 글자와 함께 싣는다. 이 글을 바꿀 일이 생기면 이 함수만 고친다.
 */
export function floorUnknownNote(stats: CoverageStats | null): string {
  const phrase = floorMissingPhrase(stats?.floor_missing_pct);
  return phrase === null
    ? '층이 적히지 않은 점포는 이 수에 들지 않습니다'
    : `층이 적히지 않은 점포(서비스 지역 전체 ${phrase})는 이 수에 들지 않습니다`;
}

const TX_SINCE_NOTE = `${TX_OPEN_SINCE_LABEL} 이후 계약분만 보입니다`;

/** 거래 한 줄 — 카드 거래 목록의 칸(층·계약 연월·면적·금액·㎡당·유형·지분)을 같은 서식 함수로 이은 것. */
export function txLineText(t: ParcelTransaction): string {
  return [
    t.floor_no === null ? '층 미상' : formatFloor(t.floor_no, null),
    formatYearMonth(t.contract_ym),
    formatArea(t.bld_area_m2),
    formatWon(t.price_won),
    t.unit_price === null ? '㎡당 —' : `㎡당 ${formatManWon(t.unit_price)}`,
    t.tx_type || '거래유형 미상',
    ...(t.is_share === true ? ['지분'] : []),
  ].join(' · ');
}

/**
 * 거래 건수 뒤 꼬리 — 목록이 서버 상한(`TX_LIST_CAP`)에 닿았으면 카드 제목과 같은 「 (최근 100건까지)」, 아니면 빈 글.
 * ⓘ 타일 첫 줄·중개사 근거 줄·한 줄 답이 **이 함수 하나**로 같은 꼴을 붙인다(셋이 서로 다른 건수를 말하지 않게).
 */
function txCapTail(n: number): string {
  return n >= TX_LIST_CAP ? ` (최근 ${TX_LIST_CAP}건까지)` : '';
}

/** 카드의 「이 땅 거래 N건」(목록이 서버 상한에 닿았으면 그렇다고). */
function txCountText(n: number): string {
  return `이 땅 거래 ${n.toLocaleString('ko-KR')}건${txCapTail(n)}`;
}

// ── 참고 시세 ──────────────────────────────────────────────────────────────

type BandPick =
  | { kind: 'gate' }
  | { kind: 'noValue' }
  | { kind: 'group'; group: BandGroup };

/**
 * 시세 띠에서 보일 줄 — 값을 낸 줄 가운데 **땅에 가장 가까운 지상층 묶음 하나**(메인 ㉠ · 대개 2층 — 1층은 원래 안 낸다).
 * 지상 묶음이 없으면 값을 낸 줄 가운데 땅에 가장 가까운 것. null = 카드도 안 서는 상태(실패·아직·빈 답).
 */
function pickBand(input: RoleSummaryInput): BandPick | null {
  const { bands, bandsFailed, floors } = input;
  if (bandsFailed || bands === null || bands.length === 0) return null;
  if (bands.some((b) => b.status === 'gate_fail')) return { kind: 'gate' };
  const { listed, silent } = groupBands(bands, floors);
  if (listed.length === 0 && silent.length === 0) return null;
  const ok = listed.filter((g) => g.band.status === 'ok');
  if (ok.length === 0) return { kind: 'noValue' };
  const dist = (no: number) => (no >= 1 && no !== 99 ? no : 1000 + Math.abs(no));
  const near = (g: BandGroup) => Math.min(...g.floors.map((f) => dist(f.floor_no)));
  const best = ok.reduce((a, b) => (near(b) < near(a) ? b : a));
  return { kind: 'group', group: best };
}

function bandTile(input: RoleSummaryInput): SummaryTile | null {
  const pick = pickBand(input);
  if (pick === null) return null;
  if (pick.kind === 'gate') {
    return { key: 'band', label: '참고 시세', lines: [BAND_GATE_TEXT], basis: [], grade: null };
  }
  if (pick.kind === 'noValue') {
    return { key: 'band', label: '참고 시세', lines: [BAND_NO_VALUE_TEXT], basis: [], grade: null };
  }
  const t = bandText(pick.group);
  const label = `참고 시세 (${pick.group.label})`;
  if (t.kind === 'none') return { key: 'band', label, lines: [t.text], basis: [], grade: null };
  return {
    key: 'band',
    label,
    lines: [t.val],
    basis: [t.sub],
    grade: { text: 'C등급 · 파생 추정', est: true },
  };
}

// ── 실거래 ─────────────────────────────────────────────────────────────────

function txTile(input: RoleSummaryInput): SummaryTile | null {
  const { txs } = input;
  if (txs === null) return null;
  if (txs.length === 0) {
    return { key: 'tx', label: '이 땅 최근 거래', lines: ['이 땅 거래 0건'], basis: [TX_SINCE_NOTE], grade: null };
  }
  return {
    key: 'tx',
    label: '이 땅 최근 거래',
    lines: [txCountText(txs.length)],
    basis: [`가장 최근: ${txLineText(txs[0])}`, TX_SINCE_NOTE],
    grade: null,
  };
}

function tx3Tile(input: RoleSummaryInput): SummaryTile | null {
  const { txs } = input;
  if (txs === null) return null;
  if (txs.length === 0) {
    return { key: 'tx3', label: '실거래 최근 3건', lines: ['이 땅 거래 0건'], basis: [TX_SINCE_NOTE], grade: null };
  }
  const shown = txs.slice(0, 3);
  return {
    key: 'tx3',
    label: '실거래 최근 3건',
    lines: shown.map(txLineText),
    basis: [
      `이 땅에서 신고된 거래 ${txs.length.toLocaleString('ko-KR')}건${txCapTail(txs.length)} 중 최근 ${shown.length}건`,
      TX_SINCE_NOTE,
    ],
    grade: null,
  };
}

// ── 상권 임대료(부동산원 조사 · 상권 평균) ───────────────────────────────────

function rentTile(input: RoleSummaryInput): SummaryTile | null {
  const { rent, noCoord } = input;
  if (rent === null) return null;
  const label = '상권 임대료 (상권 평균)';
  if (rent.length === 0) {
    return {
      key: 'rent',
      label,
      lines: [rentSummary(rent, noCoord)],
      basis: ['출처: 한국부동산원 상업용부동산 임대동향조사.'],
      grade: null,
    };
  }
  const bldType = defaultBldType(rent);
  if (bldType === null) return null;
  const rows = toRentRows(rent, bldType).filter((r) => r.metrics.some((m) => m.key === 'rent'));
  if (rows.length === 0) return null;
  const lead = rows[0];
  const metric = lead.metrics.find((m) => m.key === 'rent')!;
  const others = new Set(rows.map((r) => r.districtNm)).size - 1;
  return {
    key: 'rent',
    label,
    lines: [`${metric.label} ${metric.value}`],
    basis: [
      `상권 평균 · ${bldType}${lead.quarter ? ` · ${lead.quarter} 조사` : ''}`,
      `${lead.districtNm}${others > 0 ? ` 외 상권 ${others}곳` : ''} · 부동산원 조사구역 ${lead.regionNm}`,
    ],
    grade: { text: 'B등급 · 공식 표본조사', est: false },
  };
}

// ── 공시지가 ───────────────────────────────────────────────────────────────

function landTile(input: RoleSummaryInput): SummaryTile | null {
  const v = input.landPrice;
  if (v === null) return null;
  return {
    key: 'land',
    label: '개별공시지가',
    lines: [`땅 1㎡당 ${formatLandPriceAmount(v.land_price)}`],
    basis: [`${v.land_price_year}년 공시 ${LAND_PRICE_NOTE}`],
    grade: { text: LAND_PRICE_BADGE, est: false },
  };
}

// ── 업종 비중(속한 상권 블록 · 대분류) ─────────────────────────────────────────

/** 업종 타일이 보일 막대 — 칩이면 그 대분류 하나(없으면 null 자리), 「전체」면 그 상권 블록의 앞 1~2개(서버가 점포 수 순으로 준다). */
function industryPicks(input: RoleSummaryInput): {
  lead: IndustryMix['districts'][number];
  others: number;
  bars: Array<{ nm: string; bar: MixBar | null }>;
} | null {
  const { mix, chip } = input;
  if (mix === null || mix.districts.length === 0) return null;
  const lead = mix.districts[0];
  const all = toBars(lead);
  const match = chipMatch(chip);
  const bars = match
    ? [{ nm: match.catLNm, bar: all.find((b) => b.cd === match.catL) ?? null }]
    : all.slice(0, 2).map((b) => ({ nm: b.nm || b.cd, bar: b }));
  return { lead, others: mix.districts.length - 1, bars };
}

function industryTile(input: RoleSummaryInput): SummaryTile | null {
  const picks = industryPicks(input);
  if (picks === null) return null;
  const { lead, others, bars } = picks;
  const { mix, median, chip } = input;
  const med = medianViewOf(median, lead.district_id, mix!.snapshot_ym);
  const match = chipMatch(chip);
  const lines =
    lead.cats.length === 0
      ? ['이 상권 안에 등록된 점포가 없습니다.']
      : bars.map(({ nm, bar }) => {
          if (bar === null) return `${nm} 0곳`;
          const medLine = med?.lines.get(bar.cd);
          return `${nm} ${bar.pct.toFixed(1)}%${medLine ? ` · ${medLine}` : ''}`;
        });
  const basis = [
    `${districtLabel(lead)} 안 점포 ${lead.total.toLocaleString('ko-KR')}곳${others > 0 ? ` · 외 상권 ${others}곳` : ''}`,
    ...(match ? [`고른 업종(${chip})은 ${match.catLNm} 대분류에 듭니다`] : []),
    ...(match?.note ? [match.note] : []),
    ...(med?.note ? [med.note] : []),
    ...(med?.tooSmall ? [med.tooSmall] : []),
  ];
  return {
    key: 'industry',
    label: match ? `업종 비중 · ${match.catLNm}(대분류)` : '업종 비중 (상위 2개)',
    lines,
    basis,
    grade: med?.note ? { text: MEDIAN_BADGE, est: true } : null,
  };
}

// ── 개업·폐업(서울시 공표) ──────────────────────────────────────────────────

function openCloseTile(input: RoleSummaryInput): SummaryTile | null {
  const rows = input.openClose;
  if (rows === null) return null;
  const label = '개업·폐업 (서울시 공표)';
  const lead = rows.find((r) => r.status === 'ok');
  const notOk = rows.some((r) => r.status !== 'ok' && r.status !== 'no_data');
  if (notOk || lead === undefined) {
    // 대상 아님(서울 밖·상권 밖·좌표 없음)·자료 없는 분기 — 카드 요약 글 그대로.
    return { key: 'openclose', label, lines: [openCloseSummary(rows, input.building.pnu)], basis: [], grade: null };
  }
  const latest = latestOf(lead);
  const quarter = openCloseQuarterLabel(lead.latest_quarter);
  if (!latest || !quarter) return null;
  const noRate = latest.opbiz_rt === null || latest.clsbiz_rt === null;
  const others = rows.filter((r) => r.status === 'ok' || r.status === 'no_data').length - 1;
  const small = latest.similr_induty_stor_co < OPEN_CLOSE_MIN_SAMPLE;
  return {
    key: 'openclose',
    label,
    lines: [
      countRateText('개업', latest.opbiz_stor_co, noRate ? null : latest.opbiz_rt),
      countRateText('폐업', latest.clsbiz_stor_co, noRate ? null : latest.clsbiz_rt),
    ],
    basis: [
      `${districtName(lead)}${others > 0 ? ` 외 상권 ${others}곳` : ''} · ${quarter}`,
      storeTotalText(latest.similr_induty_stor_co),
      ...(small
        ? [
            `표본 ${formatStoreCount(latest.similr_induty_stor_co)}(점포 · 프랜차이즈 포함) — ${OPEN_CLOSE_MIN_SAMPLE}곳이 안 돼 비율은 적지 않습니다.`,
          ]
        : []),
    ],
    grade: null,
  };
}

// ── 1층 점포 수(층 목록) ─────────────────────────────────────────────────────

function floor1Tile(input: RoleSummaryInput): SummaryTile {
  const { floors, stats } = input;
  const f1 = floors.find((f) => f.floor_no === 1);
  const value = f1 === undefined ? '–' : f1.store_cnt != null ? `점포 ${f1.store_cnt}` : '—';
  const head = floors[0];
  return {
    key: 'floor1',
    label: '1층 점포 수 (층 목록)',
    lines: [value],
    basis: [
      floorUnknownNote(stats),
      ...(head.bld_cnt_in_pnu > 1
        ? [`이 땅에 건물이 ${head.bld_cnt_in_pnu}동 있어 옆 동 점포가 섞여 보일 수 있습니다`]
        : []),
    ],
    grade: { text: 'D등급 · 간접 추론', est: false },
  };
}

// ── 중개사: 소유 구조 · 대장 호수 ─────────────────────────────────────────────

/**
 * 소유 구조 한 줄 — `describeOwnership` 그대로. 링크로 들어온 건물은 검색 줄 칸이 없으므로 층 목록 머리(건축물대장)의 칸을
 * 덮어 넣어 부른다(메인 ㉥ · 계산 0). 최고층은 층별 화면 머리와 같은 규칙(`buildingFromFloorRows` — 옥탑 제외).
 */
function ownershipText(input: RoleSummaryInput): string | null {
  const head = input.floors[0];
  return describeOwnership({
    ...input.building,
    is_jiphap: head.is_jiphap,
    approve_date: head.approve_date,
    parking_cnt: head.parking_cnt,
    elevator_ride: head.elevator_ride,
    elevator_emgen: head.elevator_emgen,
    ho_cnt: head.ho_cnt,
    bld_main_use: head.bld_main_use,
    max_floor: buildingFromFloorRows(input.floors)?.max_floor ?? null,
  });
}

function ownerTile(input: RoleSummaryInput): SummaryTile | null {
  const text = ownershipText(input);
  if (text === null) return null;
  return { key: 'owner', label: '소유 구조', lines: [text], basis: ['출처: 건축물대장'], grade: null };
}

function hoTile(input: RoleSummaryInput): SummaryTile | null {
  const head = input.floors[0];
  const ho = describeHoCnt(head.is_jiphap, head.ho_cnt, head.bld_main_use);
  if (ho === null) return null;
  return {
    key: 'ho',
    label: '대장 호수',
    lines: [ho],
    basis: ['출처: 건축물대장 · 층 목록의 「호실 N칸」과 세는 대상이 다릅니다'],
    grade: null,
  };
}

// ── 한 줄 답(사실 문장만) ────────────────────────────────────────────────────

function investorAnswer(input: RoleSummaryInput): string | null {
  const parts: string[] = [];
  const pick = pickBand(input);
  if (pick?.kind === 'gate') parts.push('이 구는 아직 참고 시세를 내지 않습니다.');
  if (pick?.kind === 'group') {
    const t = bandText(pick.group);
    if (t.kind === 'value') parts.push(`${pick.group.label} 참고 시세는 ${t.val}입니다.`);
  }
  if (input.txs !== null) {
    parts.push(`이 땅 신고 거래는 ${input.txs.length.toLocaleString('ko-KR')}건${txCapTail(input.txs.length)}입니다.`);
  }
  return parts.length > 0 ? parts.join(' ') : null;
}

function founderAnswer(input: RoleSummaryInput): string | null {
  const parts: string[] = [];
  const picks = industryPicks(input);
  const first = picks?.bars[0];
  if (picks && first && first.bar !== null) {
    const med = medianViewOf(input.median, picks.lead.district_id, input.mix!.snapshot_ym);
    const medLine = med?.lines.get(first.bar.cd);
    const head = `${districtLabel(picks.lead)} 안 ${first.nm} 업종 비중은 ${first.bar.pct.toFixed(1)}%`;
    parts.push(medLine ? `${head}이고, 비교값은 ${medLine}입니다.` : `${head}입니다.`);
  }
  const f1 = input.floors.find((f) => f.floor_no === 1);
  if (f1 && f1.store_cnt != null) parts.push(`이 건물 1층에 적힌 점포는 ${f1.store_cnt}곳입니다.`);
  return parts.length > 0 ? parts.join(' ') : null;
}

function brokerAnswer(input: RoleSummaryInput): string {
  const head = input.floors[0];
  const kind = formatJiphap(head.is_jiphap) ?? `건물 종류 ${UNKNOWN_SPEC}`;
  const ho = describeHoCnt(head.is_jiphap, head.ho_cnt, head.bld_main_use);
  const who = `${kind}${ho !== null ? `, 대장 호수 ${ho}` : ''}`;
  const { txs } = input;
  if (txs === null) return `${who}입니다.`;
  if (txs.length === 0) return `${who}이며, 이 땅에서 신고된 거래는 0건입니다.`;
  return `${who}이며, 이 땅 최근 신고 거래는 ${formatYearMonth(txs[0].contract_ym)}입니다.`;
}

// ── 묶기 ───────────────────────────────────────────────────────────────────

/**
 * 역할 → 요약 판. 역할이 없거나 층이 없으면 null(판 없음 — 지금 화면 그대로).
 * ⛔ 층 행이 이 건물 것이 아니면 null — 건물이 바뀐 첫 그림에는 층·실거래·시세 상태가 아직 앞 건물 것이다(층별 화면의
 *    각 effect 가 그 뒤에 비운다). 그 한 순간에도 앞 건물 값을 새 건물 이름 밑에 그리지 않는다.
 */
export function roleSummaryView(input: RoleSummaryInput): RoleSummaryView | null {
  const { role } = input;
  if (role === null || input.floors.length === 0) return null;
  if (input.floors[0].bld_id !== input.building.bld_id) return null;
  const keep = (ts: Array<SummaryTile | null>) => ts.filter((t): t is SummaryTile => t !== null);
  if (role === '투자자') {
    return {
      role,
      question: ROLE_QUESTIONS[role],
      tiles: keep([bandTile(input), txTile(input), rentTile(input), landTile(input)]),
      answer: investorAnswer(input),
    };
  }
  if (role === '창업자') {
    return {
      role,
      question: ROLE_QUESTIONS[role],
      tiles: keep([industryTile(input), openCloseTile(input), rentTile(input), floor1Tile(input)]),
      answer: founderAnswer(input),
    };
  }
  return {
    role,
    question: ROLE_QUESTIONS[role],
    tiles: keep([ownerTile(input), hoTile(input), tx3Tile(input)]),
    answer: brokerAnswer(input),
  };
}
