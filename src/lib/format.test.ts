import { describe, it, expect } from 'vitest';
import {
  describeError,
  describeRange,
  formatArea,
  formatApproveDate,
  formatFloor,
  formatManWon,
  formatQuarter,
  formatWon,
  formatYearMonth,
  floorSortKey,
  oneInEvery,
} from './format';
import type { BuildingHit } from '../types';

function hit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: '1168010100-1',
    pnu: '1168010100100010000',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 5,
    min_floor: 1,
    max_floor: 5,
    has_roof: false,
    ...over,
  };
}

/**
 * 표시 변환 단위 테스트.
 *
 * 층 표기 규칙(지상 n=n / 지하 n=-n / 옥탑=99 / 0 없음)은 DB CHECK 제약과 짝을 이룬다.
 * 여기서 부호를 잘못 다루면 지하가 지상으로 보이거나 그 반대가 된다.
 */

describe('formatFloor — 층 표기', () => {
  it('지상층은 "n층"', () => {
    expect(formatFloor(1, null)).toBe('1층');
    expect(formatFloor(15, null)).toBe('15층');
  });

  it('지하층은 부호를 떼고 "지하 n층"', () => {
    // 음수를 그대로 찍으면 "-1층"이 되어 사람이 읽을 수 없다.
    expect(formatFloor(-1, null)).toBe('지하 1층');
    expect(formatFloor(-7, null)).toBe('지하 7층');
  });

  it('99는 옥탑', () => {
    expect(formatFloor(99, null)).toBe('옥탑');
  });

  it('대장에 적힌 원본 이름표가 있으면 그걸 우선한다', () => {
    expect(formatFloor(1, '1층')).toBe('1층');
    expect(formatFloor(-1, '지1층')).toBe('지1층');
    expect(formatFloor(99, '옥탑1층')).toBe('옥탑1층');
  });

  it('이름표가 공백뿐이면 없는 것으로 본다', () => {
    expect(formatFloor(-2, '   ')).toBe('지하 2층');
    expect(formatFloor(-2, '')).toBe('지하 2층');
  });

  it('이름표 앞뒤 공백은 다듬는다', () => {
    expect(formatFloor(3, '  3층  ')).toBe('3층');
  });
});

describe('floorSortKey — 정렬 키', () => {
  it('옥탑이 가장 위, 지하가 가장 아래로 정렬된다', () => {
    const floors = [-2, 5, 99, 1, -1];
    const sorted = [...floors].sort((a, b) => floorSortKey(b) - floorSortKey(a));
    expect(sorted).toEqual([99, 5, 1, -1, -2]);
  });
});

describe('formatArea — 면적', () => {
  it('제곱미터와 평을 함께 보여준다', () => {
    expect(formatArea(330.5785)).toBe('330.6㎡ (100평)');
  });

  it('값이 없으면 —', () => {
    expect(formatArea(null)).toBe('—');
    expect(formatArea(undefined)).toBe('—');
    expect(formatArea(NaN)).toBe('—');
  });

  it('0은 —이 아니라 0으로 보여준다', () => {
    // 0㎡와 "면적 미상"은 다른 사실이다. 둘을 섞으면 화면이 거짓말을 한다.
    expect(formatArea(0)).toBe('0㎡ (0평)');
  });

  it('천 단위 구분 기호를 넣는다', () => {
    expect(formatArea(12345.6)).toBe('12,345.6㎡ (3,735평)');
  });
});

describe('formatQuarter — 분기 표기', () => {
  it('분기말 월을 분기 번호로 바꾼다', () => {
    // 상권정보는 3·6·9·12월(분기말) 기준으로 배포된다. 라이브 실측값은 '202603'.
    expect(formatQuarter('202603')).toBe('2026년 1분기');
    expect(formatQuarter('202606')).toBe('2026년 2분기');
    expect(formatQuarter('202609')).toBe('2026년 3분기');
    expect(formatQuarter('202612')).toBe('2026년 4분기');
  });

  it('분기말이 아닌 월도 속한 분기로 넣는다', () => {
    expect(formatQuarter('202601')).toBe('2026년 1분기');
    expect(formatQuarter('202607')).toBe('2026년 3분기');
  });

  it('값이 없으면 —', () => {
    expect(formatQuarter(null)).toBe('—');
    expect(formatQuarter(undefined)).toBe('—');
  });

  it('모르는 형식은 억지로 해석하지 않고 원본을 보여준다', () => {
    // 틀린 분기를 자신 있게 말하는 것보다 원본을 그대로 두는 편이 낫다.
    expect(formatQuarter('2026Q3')).toBe('2026Q3');
    expect(formatQuarter('202699')).toBe('202699');
    expect(formatQuarter('202600')).toBe('202600');
  });
});

describe('oneInEvery — "N곳 중 1곳"의 N', () => {
  it('비율을 사람이 감잡는 배수로 바꾼다', () => {
    expect(oneInEvery(32.9)).toBe(3);
    expect(oneInEvery(25)).toBe(4);
    expect(oneInEvery(50)).toBe(2);
  });

  it('0 이하이거나 값이 없으면 문구를 만들지 않는다', () => {
    // 1/0 = 무한대가 화면에 나가는 것을 막는다.
    expect(oneInEvery(0)).toBeNull();
    expect(oneInEvery(-5)).toBeNull();
    expect(oneInEvery(null)).toBeNull();
    expect(oneInEvery(undefined)).toBeNull();
    expect(oneInEvery(NaN)).toBeNull();
  });
});

describe('formatApproveDate — 사용승인일', () => {
  it('연-월만 남긴다', () => {
    expect(formatApproveDate('2003-05-14')).toBe('2003년 5월');
  });

  it('한 자리 월의 앞 0을 뗀다', () => {
    expect(formatApproveDate('1998-01-02')).toBe('1998년 1월');
  });

  it('값이 없으면 —', () => {
    expect(formatApproveDate(null)).toBe('—');
  });

  it('형식이 다르면 원본을 그대로 보여준다', () => {
    // 모르는 형식을 억지로 해석해 틀린 날짜를 만드는 것보다 원본이 낫다.
    expect(formatApproveDate('연도미상')).toBe('연도미상');
  });
});

// ── 1. 층 범위 표기 ─────────────────────────────────────────────────────────

describe('describeRange — 층 범위', () => {
  it('지상 건물은 "1층 ~ 5층"', () => {
    expect(describeRange(hit({ min_floor: 1, max_floor: 5 }))).toBe('1층 ~ 5층');
  });

  it('지하만 있는 건물의 위쪽 층도 지하로 읽는다', () => {
    // 예전에는 아래쪽만 부호를 처리하고 위쪽은 그대로 찍어 "지하 5층 ~ -1층"이 나왔다.
    // 강남에만 지하층뿐인 건물이 213개 있어 드문 예외가 아니다.
    expect(describeRange(hit({ min_floor: -5, max_floor: -1 }))).toBe('지하 5층 ~ 지하 1층');
  });

  it('지하와 지상에 걸치면 양쪽 다 사람 말로', () => {
    expect(describeRange(hit({ min_floor: -2, max_floor: 15 }))).toBe('지하 2층 ~ 15층');
  });

  it('층이 하나뿐이면 범위로 늘여 쓰지 않는다', () => {
    expect(describeRange(hit({ min_floor: 1, max_floor: 1 }))).toBe('1층');
    expect(describeRange(hit({ min_floor: -1, max_floor: -1 }))).toBe('지하 1층');
  });

  it('옥탑은 범위에 섞지 않고 뒤에 따로 붙인다', () => {
    // 옥탑을 범위에 넣으면 99가 최고층이 되어 "지하 2층 ~ 옥탑"이 되고,
    // 지상 최고층(19층)이라는 정보가 화면에서 사라진다.
    expect(describeRange(hit({ min_floor: -2, max_floor: 19, has_roof: true }))).toBe(
      '지하 2층 ~ 19층 + 옥탑',
    );
  });

  it('옥탑밖에 없으면 "옥탑만"', () => {
    expect(describeRange(hit({ min_floor: null, max_floor: null, has_roof: true }))).toBe('옥탑만');
  });

  it('층 정보가 아예 없으면 그렇다고 말한다', () => {
    expect(describeRange(hit({ min_floor: null, max_floor: null, has_roof: false }))).toBe(
      '층 정보 없음',
    );
  });
});

// ── 2. 오류 문구 ────────────────────────────────────────────────────────────

describe('describeError — 오류 안내', () => {
  it('함수 미적용(PGRST202)은 조치 방법까지 알려준다', () => {
    const msg = describeError({ code: 'PGRST202' });
    expect(msg).toContain('search_buildings');
  });

  it('타임아웃(57014)은 고장이 아니라 "검색어가 넓다"고 알려준다', () => {
    // 2026-08-11 실측: '동'·'1'·'서울' 은 수십만 건과 맞아 3초를 넘긴다.
    // "실패했습니다"로 뭉뚱그리면 사용자가 고장인 줄 알고 같은 검색을 반복한다.
    const msg = describeError({ code: '57014', message: 'canceling statement due to statement timeout' });
    expect(msg).toContain('너무 넓어');
    expect(msg).not.toContain('실패했습니다');
    expect(msg).not.toContain('statement');   // 내부 용어 노출 금지
  });

  it('그 밖의 오류에는 내부 표 이름을 노출하지 않는다', () => {
    const msg = describeError({
      code: '42501',
      message: 'permission denied for table building_floor',
    });
    expect(msg).not.toContain('building_floor');
    expect(msg).not.toContain('permission denied');
  });

  it('오류 객체가 아니어도 죽지 않는다', () => {
    expect(typeof describeError('그냥 문자열')).toBe('string');
    expect(typeof describeError(null)).toBe('string');
    expect(typeof describeError(undefined)).toBe('string');
  });
});

describe('formatWon — 실거래 금액 (Stage A · 결정 0012)', () => {
  it('억·만으로 끊어 읽게 만든다', () => {
    expect(formatWon(320_000_000)).toBe('3억 2,000만');
    expect(formatWon(1_250_000_000)).toBe('12억 5,000만');
  });

  it('억만 있거나 만만 있으면 그 조각만 쓴다', () => {
    expect(formatWon(200_000_000)).toBe('2억');
    expect(formatWon(85_000_000)).toBe('8,500만');
  });

  it('만원 미만은 버리지 않고 원으로 적는다', () => {
    // 빈 문자열이 나오면 "금액 없음"처럼 보인다 — 소액이어도 금액은 금액이다.
    expect(formatWon(7_000)).toBe('7,000원');
    expect(formatWon(0)).toBe('0원');
  });

  it('값이 없으면 —', () => {
    expect(formatWon(null)).toBe('—');
    expect(formatWon(undefined)).toBe('—');
    expect(formatWon(Number.NaN)).toBe('—');
  });
});

describe('formatManWon — ㎡당 단가', () => {
  it('만원 단위로 반올림한다', () => {
    expect(formatManWon(3_800_000)).toBe('380만');
    expect(formatManWon(22_500_000)).toBe('2,250만');
    expect(formatManWon(13_827_838.83)).toBe('1,383만');
  });

  it('1만원 미만은 "0만"이 아니라 원으로 적는다', () => {
    // 반올림이 0을 만들면 값이 없는 것처럼 보인다.
    expect(formatManWon(4_200)).toBe('4,200원');
  });

  it('값이 없으면 —', () => {
    expect(formatManWon(null)).toBe('—');
    expect(formatManWon(undefined)).toBe('—');
  });
});

describe('formatYearMonth — 계약 시점', () => {
  it('202605 를 2026-05 로 편다', () => {
    expect(formatYearMonth('202605')).toBe('2026-05');
    expect(formatYearMonth('202412')).toBe('2024-12');
  });

  it('분기로 뭉치지 않는다 (계약이 일어난 그 달이 사실이다)', () => {
    expect(formatYearMonth('202605')).not.toContain('분기');
  });

  it('형식이 다르면 억지로 해석하지 않고 원본을 준다', () => {
    expect(formatYearMonth('2026-05')).toBe('2026-05');
    expect(formatYearMonth('202613')).toBe('202613');
    expect(formatYearMonth('어쩌구')).toBe('어쩌구');
  });

  it('값이 없으면 —', () => {
    expect(formatYearMonth(null)).toBe('—');
    expect(formatYearMonth('')).toBe('—');
  });
});
