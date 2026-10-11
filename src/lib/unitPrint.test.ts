import { describe, expect, it } from 'vitest';
import type { UnitFloorSummary } from '../types';
import {
  UNIT_PRINT_CONCURRENCY,
  UNIT_PRINT_FLOOR_CAP,
  runLimited,
  unitPrintCapText,
  unitPrintMoreText,
  unitPrintPlan,
} from './unitPrint';

/**
 * 호실 구성표 고르기(결정 0036 결정 8 · 물결 1-C2) — 어느 층을 부르나 · 동시 요청 상한.
 * ⛔ 주거·오피스텔·미상 층은 절대 안 부른다(결정 0032).
 */

function sum(floor_no: number | null, floor_kind: UnitFloorSummary['floor_kind'] = 'commercial'): UnitFloorSummary {
  return { floor_no, unit_cnt: 10, median_area_m2: null, min_area_m2: null, max_area_m2: null, floor_kind };
}

describe('unitPrintPlan', () => {
  const SUMMARY = [
    sum(-2),
    sum(-1, 'mixed'),
    sum(1),
    sum(2, 'residential'),
    sum(3, 'officetel'),
    sum(4),
    sum(5, 'unknown'),
    sum(99),
    sum(null),
  ];
  const STACK = [99, 5, 4, 3, 2, 1, -1, -2];

  it('넣지 않음·요약 없음이면 아무 층도 안 부른다', () => {
    expect(unitPrintPlan(SUMMARY, STACK, 'none').floors).toEqual([]);
    expect(unitPrintPlan(null, STACK, 'all').floors).toEqual([]);
  });

  it('지하~3층 = 지하 전부 + 1~3층 · 호 목록이 있는 층만(주거·오피스텔·미상 0)', () => {
    expect(unitPrintPlan(SUMMARY, STACK, 'low').floors).toEqual([-2, -1, 1]);
  });

  it('전부 = 아래층부터 · 층 목록에 없는 층(층 미상 묶음 포함)은 뺀다', () => {
    const p = unitPrintPlan(SUMMARY, STACK, 'all');
    expect(p.floors).toEqual([-2, -1, 1, 4, 99]);
    expect(p.capped).toBe(false);
    expect(unitPrintPlan(SUMMARY, [1, 4], 'all').floors).toEqual([1, 4]);
  });

  it('전부는 아래쪽 30개 층까지 — 넘으면 상한 안내', () => {
    const many = Array.from({ length: 40 }, (_, i) => sum(i + 1));
    const p = unitPrintPlan(many, many.map((m) => m.floor_no as number), 'all');
    expect(UNIT_PRINT_FLOOR_CAP).toBe(30);
    expect(p.floors).toHaveLength(30);
    expect(p.floors[0]).toBe(1);
    expect(p.floors[29]).toBe(30);
    expect(p.capped).toBe(true);
    expect(unitPrintCapText(p.listedCount)).toBe('호실 목록이 있는 층이 40개라 아래쪽 30개 층만 넣었습니다');
  });

  it('남은 호 한 줄', () => {
    expect(unitPrintMoreText(1234)).toBe('이 층은 1,234호 더 있습니다');
  });
});

describe('runLimited', () => {
  it('동시에 상한(4)까지만 · 하나가 던져도 나머지는 끝까지', async () => {
    let now = 0;
    let peak = 0;
    const done: number[] = [];
    await runLimited(
      Array.from({ length: 11 }, (_, i) => i),
      UNIT_PRINT_CONCURRENCY,
      async (i) => {
        now += 1;
        peak = Math.max(peak, now);
        await new Promise((r) => setTimeout(r, 2));
        now -= 1;
        if (i === 3) throw new Error('boom');
        done.push(i);
      },
    );
    expect(UNIT_PRINT_CONCURRENCY).toBe(4);
    expect(peak).toBe(4);
    expect(done.sort((a, b) => a - b)).toEqual([0, 1, 2, 4, 5, 6, 7, 8, 9, 10]);
  });

  it('멈춤 신호가 서면 새 일을 꺼내지 않는다', async () => {
    let stop = false;
    const seen: number[] = [];
    await runLimited([1, 2, 3, 4, 5, 6], 1, async (i) => {
      seen.push(i);
      if (i === 2) stop = true;
    }, () => stop);
    expect(seen).toEqual([1, 2]);
  });
});
