import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { PriceBandSection } from './PriceBandSection';
import { resetDataFreshnessCache } from '../lib/loadDataFreshness';
import type { FloorRow, PriceBand } from '../types';

/**
 * 참고 매매 시세 카드의 **그림**(결정 0038 A — 층마다 가로 띠 · 가운데값 눈금 · 축 눈금 글).
 *
 * 카드 글(값·근거·까닭)은 `FloorStack.test.tsx` 「참고 매매 시세」가 덮는다 — 여기서는 띠가 **서는 경우/안 서는 경우**와
 * 자리·폭(%)·색 토큰·낭독기 숨김, 그리고 글이 한 글자도 안 바뀌는지만 본다(그림이 깨져도 글자 시험은 초록이다 · §2-10).
 */

// 카드 머리 날짜 줄(S3)이 신선도 표를 묻는다 — 함수 없음으로 답한다(날짜 줄만 빠진다).
vi.mock('../lib/supabase', () => ({
  supabase: { rpc: () => Promise.resolve({ data: null, error: { message: 'PGRST202' } }) },
}));

function band(over: Partial<PriceBand> = {}): PriceBand {
  return {
    floor_no: 2,
    status: 'ok',
    stage: 'L5',
    n: 15,
    p25: 7_465_269.63,
    median: 16_265_452.18,
    p75: 19_045_698.84,
    median_area_m2: 32.8,
    window_from: '202408',
    ...over,
  };
}

const NO_VALUE = { stage: null, n: null, p25: null, median: null, p75: null, median_area_m2: null };

function floor(floorNo: number): FloorRow {
  return {
    bld_id: '1168010100-1',
    pnu: '1168010100100010000',
    floor_no: floorNo,
    floor_label: null,
    floor_area_m2: 300,
    floor_area_gross_m2: 340,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: '테스트빌딩',
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: 2,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
  } as FloorRow;
}

function renderCard(bands: PriceBand[], floorNos: number[]) {
  return render(
    <PriceBandSection
      bands={bands}
      basePrices={null}
      failed={false}
      floors={floorNos.map(floor)}
      hasTxStats={false}
      openFloor={null}
      onPickFloor={() => {}}
    />,
  );
}

/** 줄마다 — [층 이름, 그림 종류, 띠 left·width, 눈금 left]. */
function rowsOf(container: HTMLElement) {
  return [...container.querySelectorAll('.band__row')].map((li) => {
    const viz = li.querySelector<HTMLElement>('.band__viz');
    const range = li.querySelector<HTMLElement>('.band__range');
    const tick = li.querySelector<HTMLElement>('.band__tick');
    return [
      li.querySelector('.band__floor')?.textContent,
      viz === null ? null : viz.classList.contains('band__viz--none') ? 'none' : range ? 'band' : 'tick',
      range ? [range.style.left, range.style.width] : null,
      tick ? tick.style.left : null,
    ];
  });
}

/** 0.0001 자리로 자른 % 수. */
const pct = (s: string | null | undefined) => (s ? Number(parseFloat(s).toFixed(4)) : null);

beforeEach(() => resetDataFreshnessCache());
afterEach(() => cleanup());

describe('PriceBandSection — 그림 띠 (결정 0038 A)', () => {
  it('★ 값 나는 층은 띠 + 눈금 · 1층은 "–" · 축 0 ~ ㎡당 2,000만(p75 최대 1,904.6만 올림)', () => {
    const { container } = renderCard(
      [band({ floor_no: 1, status: 'floor_1f', ...NO_VALUE }), band({ floor_no: 2 })],
      [2, 1],
    );
    const rows = rowsOf(container);
    expect(rows.map((r) => [r[0], r[1]])).toEqual([
      ['2층', 'band'],
      ['1층', 'none'],
    ]);
    const [left, width] = rows[0][2] as string[];
    expect(pct(left)).toBeCloseTo(37.3263, 3);
    expect(pct(width)).toBeCloseTo(57.9021, 3);
    expect(pct(rows[0][3] as string)).toBeCloseTo(81.3273, 3);
    // 축 눈금 글은 그림 밖 HTML 한 줄 · 띠 목록 바로 아래.
    const axis = container.querySelector('.band__axis')!;
    expect(axis.textContent).toBe('0㎡당 2,000만');
    expect(axis.previousElementSibling?.classList.contains('band__rows')).toBe(true);
    expect(container.querySelectorAll('.band__axis')).toHaveLength(1);
  });

  it('추정 색(회청 토큰) · 먼 근거(L5)는 연한 띠 · 가까운 근거(L2)는 진한 띠', () => {
    const { container } = renderCard([band({ floor_no: 2 }), band({ floor_no: 3, stage: 'L2' })], [3, 2]);
    const [l2, l5] = [...container.querySelectorAll('.band__row')];
    expect(l5.querySelector('.band__viz')!.classList.contains('band__viz--far')).toBe(true);
    expect(l5.querySelector<HTMLElement>('.band__range')!.style.background).toBe('var(--est-line)');
    expect(l2.querySelector('.band__viz')!.classList.contains('band__viz--far')).toBe(false);
    expect(l2.querySelector<HTMLElement>('.band__range')!.style.background).toBe('var(--est-band)');
    for (const t of container.querySelectorAll<HTMLElement>('.band__tick')) expect(t.style.background).toBe('var(--est-ink)');
    for (const t of container.querySelectorAll<HTMLElement>('.band__track')) expect(t.style.background).toBe('var(--est-chip)');
  });

  it('거래 1건뿐 · 모두 같은 값은 띠 없이 눈금만', () => {
    const { container } = renderCard(
      [
        band({ floor_no: 2, n: 1, p25: 10_000_000, median: 10_000_000, p75: 10_000_000 }),
        band({ floor_no: 3, n: 6, p25: 12_000_000, median: 12_000_000, p75: 12_000_000 }),
      ],
      [3, 2],
    );
    const rows = rowsOf(container);
    expect(rows.map((r) => r[1])).toEqual(['tick', 'tick']);
    // 상한 = 1,200만 → 2,000만 · 1,200만 = 60% · 1,000만 = 50%.
    expect(rows.map((r) => pct(r[3] as string))).toEqual([60, 50]);
    expect(container.querySelector('.band__axis')!.textContent).toBe('0㎡당 2,000만');
  });

  it('근거를 표시할 수 없는 줄(모르는 근거 코드)과 표본 부족 줄은 "–" — 까닭 글은 그대로', () => {
    const { container } = renderCard(
      [band({ floor_no: 2 }), band({ floor_no: 3, stage: 'L9' }), band({ floor_no: 4, status: 'no_estimate', ...NO_VALUE })],
      [4, 3, 2],
    );
    expect(rowsOf(container).map((r) => [r[0], r[1]])).toEqual([
      ['4층', 'none'],
      ['3층', 'none'],
      ['2층', 'band'],
    ]);
    const rows = [...container.querySelectorAll('.band__row')];
    expect(rows[0].querySelector('.band__viz')!.textContent).toBe('–');
    expect(rows[0].querySelector('.band__none')!.textContent).toBe(
      '표본 부족 — 곁에서 참고할 만한 거래를 아직 찾지 못했습니다. 거래가 쌓이면 나올 수 있습니다.',
    );
    expect(rows[1].querySelector('.band__none')!.textContent).toBe('근거를 표시할 수 없어 값을 내지 않습니다');
  });

  it('★ 값을 내는 줄이 하나도 없으면 띠 칸·축 글 줄 자체가 없다(지금 모양 그대로)', () => {
    const { container } = renderCard(
      [band({ floor_no: 1, status: 'floor_1f', ...NO_VALUE }), band({ floor_no: 2, status: 'no_estimate', ...NO_VALUE })],
      [2, 1],
    );
    expect(container.querySelectorAll('.band__row')).toHaveLength(2);
    expect(container.querySelectorAll('.band__viz, .band__axis, .band__text, .band__hit--viz')).toHaveLength(0);
  });

  it('그림은 낭독기에서 빠지고(옆 글과 같은 내용) 단추 이름·글은 그대로', () => {
    const { container } = renderCard([band({ floor_no: 1, status: 'floor_1f', ...NO_VALUE }), band({ floor_no: 2 })], [2, 1]);
    for (const el of container.querySelectorAll('.band__viz, .band__axis')) expect(el.getAttribute('aria-hidden')).toBe('true');
    const row = container.querySelector('.band__row')!;
    expect(row.querySelector('.band__val')!.textContent).toBe('비슷한 호실 한 칸 32.8㎡ (10평) 기준 2.4억~6.2억');
    expect(row.querySelector('.band__sub')!.textContent).toBe(
      '㎡당 747만~1,905만 · 가운데값 ㎡당 1,627만 · 근거: 500m 안 같은 층 · 거래 15건 · 먼 근거',
    );
    // 띠 칸 안에는 글자가 없다(숫자는 눈금 글 줄과 옆 글에만).
    expect(row.querySelector('.band__viz')!.textContent).toBe('');
  });

  it('금지어 0 · 축 글에 비율을 새로 적지 않는다', () => {
    const { container } = renderCard([band({ floor_no: 2 })], [2]);
    const text = container.querySelector('.band')!.textContent ?? '';
    for (const w of ['적정가', '감정가', '평가액', '가치평가', '정확하지 않을 수']) expect(text).not.toContain(w);
    expect(container.querySelector('.band__axis')!.textContent).not.toContain('%');
  });
});
