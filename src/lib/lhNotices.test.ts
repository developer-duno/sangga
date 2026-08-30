import { describe, it, expect } from 'vitest';
import {
  closeText,
  isHttpUrl,
  isLhNotice,
  isLhNoticeList,
  latestCollectedAt,
  lhSummary,
  monthDay,
  sidoOf,
} from './lhNotices';
import type { LhNotice } from '../types';

/**
 * LH 공고 카드의 순수 계산.
 *
 * 여기서 특히 지키는 것 셋
 * ------------------------
 *  ① **시도 코드 두 자리** — 다섯 자리를 그대로 서버에 보내면 라이브에서 조용히 빈손이
 *     되는데(에러가 아니다) 목(mock)은 인자 값을 안 보므로 시험은 전부 초록이다.
 *  ② **시간대** — 시각이 붙은 값은 보는 사람 시계로, 날짜만 있는 값은 적힌 그대로.
 *     섞으면 자정 언저리에 하루가 어긋난다(수집일이 하루 전, 마감일이 하루 당겨짐).
 *  ③ **모양 검사** — 뜻밖의 답이 렌더로 흘러 들어가면 입구에서 터진다.
 */

function notice(over: Partial<LhNotice> = {}): LhNotice {
  return {
    pan_id: '2026-0001',
    pan_nm: '서울강남 A1블록 단지내상가 입찰공고',
    kind_nm: '분양 입찰',
    pan_ss: '공고중',
    notice_date: '2026-08-20',
    close_date: '2026-09-17',
    dtl_url: 'https://apply.lh.or.kr/notice/2026-0001',
    collected_at: '2026-08-27T04:12:33.123456+00:00',
    ...over,
  };
}

describe('sidoOf — 고른 구에서 시도 두 자리', () => {
  it('다섯 자리 구 코드의 앞 두 자리를 준다', () => {
    expect(sidoOf('11680')).toBe('11');
    expect(sidoOf('30170')).toBe('30');
  });

  it('다섯 자리 숫자가 아니면 null 이다 (뜻 모를 값을 서버에 보내지 않는다)', () => {
    expect(sidoOf(null)).toBeNull();
    expect(sidoOf(undefined)).toBeNull();
    expect(sidoOf('')).toBeNull();
    expect(sidoOf('11')).toBeNull();
    expect(sidoOf('1168010100')).toBeNull();
    expect(sidoOf('서울')).toBeNull();
  });
});

describe('monthDay — 날짜 한 조각', () => {
  it('날짜만 있는 값은 적힌 그대로 읽는다', () => {
    expect(monthDay('2026-09-17')).toBe('9월 17일');
    // 앞자리 0 을 떼고 적는다('09월 07일'이 아니다).
    expect(monthDay('2026-01-07')).toBe('1월 7일');
  });

  it('★ 시각이 붙은 값은 보는 사람의 시계로 옮겨 적는다', () => {
    /*
      **자정 양쪽**을 둘 다 찔러 본다. 글자의 앞 열 자리(UTC 날짜)만 잘라 읽는 구현은
      여기서 하루가 어긋나는데, 어느 쪽으로 어긋나는지가 시간대 부호에 달려 있다:
        · 한국(+9)처럼 앞선 곳 — 현지 00:30 은 UTC 로 **전날**이다
        · 미주(-5)처럼 뒤진 곳 — 현지 23:30 은 UTC 로 **다음 날**이다
      그래서 한쪽만 보면 돌리는 곳에 따라 시험이 눈을 감는다(2026-08-28 실측: 23:30 하나만
      두었더니 한국 PC 에서 통과해 버렸다). 두 시각을 다 보면 UTC 가 아닌 어디서든 걸린다.
      ⚠️ 기대값은 **현지 시계로 지은 그 날짜**다 — 시험에 시각을 박아 넣지 않는다(글로벌 규칙).
      ⓘ CI(UTC)에서는 원리적으로 어긋날 수가 없어(UTC 날짜 = 현지 날짜) 이 줄이 잠든다.
        그래도 그곳에서는 잘라 읽는 구현이 실제로도 맞는 답을 낸다 — 사용자가 겪는 결함이
        아니다. 이 결함은 시간대가 있는 사람의 화면에서만 나고, 그때 이 시험이 깨어난다.
    */
    for (const hour of [0, 23]) {
      const at = new Date(2026, 7, 27, hour, 30);
      expect(monthDay(at.toISOString()), `현지 ${hour}시 30분`).toBe(
        `${at.getMonth() + 1}월 ${at.getDate()}일`,
      );
    }
  });

  it('읽을 수 없으면 null 이다 (없는 날짜를 지어내지 않는다)', () => {
    expect(monthDay(null)).toBeNull();
    expect(monthDay(undefined)).toBeNull();
    expect(monthDay('')).toBeNull();
    expect(monthDay('추후 공고')).toBeNull();
  });
});

describe('latestCollectedAt — 가장 최근에 받아 둔 시각', () => {
  it('가장 최신의 **원본 문자열**을 준다 (표기 방식을 우리가 바꾸지 않는다)', () => {
    const rows = [
      notice({ pan_id: 'a', collected_at: '2026-08-25T10:00:00+00:00' }),
      notice({ pan_id: 'b', collected_at: '2026-08-27T01:00:00+00:00' }),
      notice({ pan_id: 'c', collected_at: '2026-08-26T23:00:00+00:00' }),
    ];
    expect(latestCollectedAt(rows)).toBe('2026-08-27T01:00:00+00:00');
  });

  it('★ 글자 순서가 아니라 실제 시각으로 견준다', () => {
    // 같은 순간을 다르게 적은 두 값 + 그보다 한 시간 뒤. 글자로 비교하면 'Z' 로 시작하는
    // 쪽이 뒤로 밀려 엉뚱한 줄이 뽑힌다.
    const rows = [
      notice({ pan_id: 'a', collected_at: '2026-08-27T13:00:00+09:00' }), // = 04:00Z
      notice({ pan_id: 'b', collected_at: '2026-08-27T05:00:00Z' }),
    ];
    expect(latestCollectedAt(rows)).toBe('2026-08-27T05:00:00Z');
  });

  it('하나도 못 읽거나 빈 목록이면 null 이다', () => {
    expect(latestCollectedAt([])).toBeNull();
    expect(latestCollectedAt([notice({ collected_at: '알 수 없음' })])).toBeNull();
  });
});

describe('lhSummary — 접혀 있어도 보이는 한 줄', () => {
  it('건수와 수집일을 함께 적는다 (낡음을 감추지 않는다)', () => {
    const at = new Date(2026, 7, 27, 9, 0);
    const rows = [
      notice({ pan_id: 'a', collected_at: at.toISOString() }),
      notice({ pan_id: 'b', collected_at: new Date(2026, 7, 25, 9, 0).toISOString() }),
    ];
    expect(lhSummary(rows)).toBe('2건 · 8월 27일 수집 기준');
  });

  it('수집 시각을 못 읽으면 그 조각만 뺀다 (건수는 남긴다)', () => {
    expect(lhSummary([notice({ collected_at: '알 수 없음' })])).toBe('1건');
  });

  it('천 단위에는 쉼표가 붙는다', () => {
    const rows = Array.from({ length: 1000 }, (_, i) =>
      notice({ pan_id: `p${i}`, collected_at: '알 수 없음' }),
    );
    expect(lhSummary(rows)).toBe('1,000건');
  });
});

describe('closeText — 마감일', () => {
  /*
    ⚠️ 여기서는 **연도를 박아 넣지 않는다.** 마감 연도가 올해인지 아닌지로 문장이 갈리므로,
       '2026-09-17' 같은 고정 값을 쓰면 해가 바뀌는 순간 코드는 그대로인데 시험만 빨개진다
       (오늘 main 에서 같은 종류를 수습한 커밋 ad15391 — 감시 그물 시험의 고정 날짜).
       그래서 전부 "지금 해" 기준의 상대값으로 짓는다.
  */
  const thisYear = new Date().getFullYear();

  it('올해 마감이면 연도를 빼고 "~9월 17일" (올해임을 굳이 말하지 않는다)', () => {
    expect(closeText(`${thisYear}-09-17`)).toBe('~9월 17일');
  });

  it('★ 내년 마감이면 연도를 함께 적는다 (이미 지난 날짜처럼 보이지 않게)', () => {
    // 2026-08-30 라이브 실측: 마감 2027-06-30 인 청주모충2 공고가 "~6월 30일"로 보여
    // 두 달 전에 끝난 것처럼 읽혔다. 이 줄이 그 사고의 재현이다.
    expect(closeText(`${thisYear + 1}-06-30`)).toBe(`~${thisYear + 1}년 6월 30일`);
  });

  it('지난해 마감도 연도를 함께 적는다 (낡은 공고가 올해 것처럼 보이지 않게)', () => {
    expect(closeText(`${thisYear - 1}-12-31`)).toBe(`~${thisYear - 1}년 12월 31일`);
  });

  it('★ 시각이 붙은 값의 연도도 보는 사람의 시계로 읽는다', () => {
    // 한낮 시각이라 어느 시간대에서 돌려도 날짜가 밀리지 않는다 — 여기서 보려는 것은
    // "연도를 월·일과 같은 시계로 읽는가"이지 자정 언저리의 하루 어긋남이 아니다.
    const at = new Date(thisYear + 1, 5, 30, 12, 0);
    expect(closeText(at.toISOString())).toBe(
      `~${at.getFullYear()}년 ${at.getMonth() + 1}월 ${at.getDate()}일`,
    );
  });

  it('마감일이 없으면 "마감일 미정" (0월 0일 같은 값을 지어내지 않는다)', () => {
    expect(closeText(null)).toBe('마감일 미정');
    expect(closeText('')).toBe('마감일 미정');
  });
});

describe('isHttpUrl — 링크로 만들어도 되는 주소인가', () => {
  it('http·https 만 참이다', () => {
    expect(isHttpUrl('https://apply.lh.or.kr/x')).toBe(true);
    expect(isHttpUrl('http://apply.lh.or.kr/x')).toBe(true);
    expect(isHttpUrl('HTTPS://APPLY.LH.OR.KR/x')).toBe(true);
  });

  it('★ 누르는 순간 남의 코드가 도는 주소는 막는다', () => {
    expect(isHttpUrl('javascript:alert(1)')).toBe(false);
    expect(isHttpUrl('data:text/html,<script>alert(1)</script>')).toBe(false);
    expect(isHttpUrl('/notice/1')).toBe(false);
    expect(isHttpUrl(null)).toBe(false);
    expect(isHttpUrl(undefined)).toBe(false);
  });
});

describe('isLhNotice / isLhNoticeList — 서버 응답의 모양', () => {
  it('정상 응답을 통과시킨다', () => {
    expect(isLhNotice(notice())).toBe(true);
    expect(isLhNoticeList([notice(), notice({ pan_id: 'b' })])).toBe(true);
    // 빈 배열은 **정상**이다 — "지금 열린 공고가 없다"는 뜻이다.
    expect(isLhNoticeList([])).toBe(true);
  });

  it('날짜 둘은 없어도 된다 (마감일이 안 정해진 공고가 있다)', () => {
    expect(isLhNotice(notice({ notice_date: null, close_date: null }))).toBe(true);
  });

  it('★ 뜻밖의 답은 거른다', () => {
    // 마이그레이션 적용 전 라이브가 주는 오류 객체.
    expect(isLhNoticeList({ code: 'PGRST202', message: 'function does not exist' })).toBe(false);
    expect(isLhNoticeList(null)).toBe(false);
    expect(isLhNoticeList('공고 없음')).toBe(false);
    // 한 줄만 상해도 통째로 거른다 — 그리다 터지는 것보다 안 그리는 편이 낫다.
    expect(isLhNoticeList([notice(), { pan_id: 'b' }])).toBe(false);
  });

  it('★ 글자여야 하는 칸이 숫자로 오면 거른다 (그리다 터지는 자리다)', () => {
    expect(isLhNotice({ ...notice(), pan_nm: 12345 })).toBe(false);
    expect(isLhNotice({ ...notice(), kind_nm: null })).toBe(false);
    expect(isLhNotice({ ...notice(), dtl_url: undefined })).toBe(false);
  });
});
