import { describe, it, expect } from 'vitest';
import { printStamp } from './printStamp';

/**
 * 종이 머리글의 "언제 뽑았나".
 *
 * ⚠️ 여기에 **오늘 날짜를 박아 넣지 않는다.** 돌리는 날이 바뀌면 코드를 한 줄도 안 고쳤는데
 *    빨간불이 되고, 그건 남의 PR 을 막으며 터진다(이 저장소가 2026-08-02 에 이미 겪은 일).
 *    넣은 Date 로 나온 값만 견준다.
 */
describe('printStamp — 종이에 적을 시각', () => {
  it('`YYYY-MM-DD HH:MM` 한 모양으로 적는다', () => {
    // 월은 0부터라 7 = 8월이다.
    expect(printStamp(new Date(2026, 7, 25, 3, 20))).toBe('2026-08-25 03:20');
  });

  it('한 자리 수는 0을 채운다 (종이에서 자릿수가 흔들리지 않게)', () => {
    expect(printStamp(new Date(2026, 0, 2, 9, 5))).toBe('2026-01-02 09:05');
  });

  it('자정과 정오를 24시간제로 가른다', () => {
    expect(printStamp(new Date(2026, 11, 31, 0, 0))).toBe('2026-12-31 00:00');
    expect(printStamp(new Date(2026, 11, 31, 12, 0))).toBe('2026-12-31 12:00');
    expect(printStamp(new Date(2026, 11, 31, 23, 59))).toBe('2026-12-31 23:59');
  });

  it('지역 설정을 타지 않는다 — 어디서 뽑아도 같은 모양이다', () => {
    // `toLocaleString` 이었다면 "2026. 8. 25. 오전 3:20" 처럼 갈렸을 자리다.
    const stamp = printStamp(new Date(2026, 7, 25, 3, 20));
    expect(stamp).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it('시계를 스스로 읽지 않는다 — 같은 값을 넣으면 늘 같은 값이 나온다', () => {
    const at = new Date(2026, 7, 25, 3, 20);
    expect(printStamp(at)).toBe(printStamp(at));
  });
});
