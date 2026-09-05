import { describe, it, expect } from 'vitest';
import {
  describeError,
  describeRange,
  formatArea,
  formatApproveDate,
  formatEokBand,
  formatFloor,
  formatManWon,
  formatManWonBand,
  formatMonthKo,
  formatQuarter,
  formatWon,
  formatYearMonth,
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

describe('formatMonthKo — 기준월', () => {
  it('사람이 읽는 연·월로 바꾼다', () => {
    expect(formatMonthKo('202607')).toBe('2026년 7월');
  });

  it('한 자리 월의 앞 0을 뗀다', () => {
    expect(formatMonthKo('202601')).toBe('2026년 1월');
  });

  it('읽을 수 없으면 null — 부르는 쪽이 그 문구를 아예 안 만들 수 있게', () => {
    // '—'나 원본을 돌려주면 "(— 인허가 기준)"·"(202613 인허가 기준)"처럼 아무 뜻도 없는
    // 문장이 화면에 남는다.
    expect(formatMonthKo(null)).toBeNull();
    expect(formatMonthKo(undefined)).toBeNull();
    expect(formatMonthKo('')).toBeNull();
    expect(formatMonthKo('2026-07')).toBeNull();
    expect(formatMonthKo('202600')).toBeNull();
    expect(formatMonthKo('202613')).toBeNull();
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

// ── 추정 밴드의 금액 표기 (Stage B · 결정 0013) ─────────────────────────────

describe('formatEokBand — 추정 총액의 폭', () => {
  it('두 끝을 물결로 잇고 앞뒤에 공백을 두지 않는다', () => {
    expect(formatEokBand(244_860_844, 624_698_922)).toBe('2.4억~6.2억');
  });

  it('단위는 큰 쪽이 정하고 두 끝에 똑같이 적용한다', () => {
    // '9,800만~1.2억'처럼 섞으면 눈으로 견줄 수가 없다.
    expect(formatEokBand(98_000_000, 120_000_000)).toBe('1.0억~1.2억');
  });

  it('폭이 0이면 "안팎"으로 적는다 (같은 값을 두 번 적지 않는다)', () => {
    expect(formatEokBand(244_860_844, 244_860_844)).toBe('2.4억 안팎');
  });

  it('반올림하고 나서 같아져도 "안팎"이다', () => {
    // '2.4억~2.4억'은 사람이 "아주 정확하다"로 읽는데 사실은 정반대다.
    expect(formatEokBand(244_000_000, 244_900_000)).toBe('2.4억 안팎');
  });

  it('한쪽이라도 없으면 반쪽 밴드를 내지 않고 —', () => {
    expect(formatEokBand(244_860_844, null)).toBe('—');
    expect(formatEokBand(null, 624_698_922)).toBe('—');
  });

  it('뒤집힌 입력이 와도 작은 값이 앞에 온다', () => {
    expect(formatEokBand(624_698_922, 244_860_844)).toBe('2.4억~6.2억');
  });

  /*
    ↓ 아래 넷은 **단위를 정하는 가지들**이다. 값이 어느 자리에 있느냐에 따라 내부에서
      `eokText`·`manText`·`isEokScale` 중 어느 길로 가는지가 갈리는데, 이 밴드 함수의
      원래 시험 여섯은 전부 억 단위 한복판(2.4억~6.2억)만 다뤄 나머지 길이 비어 있었다.

      · 앞의 둘(123억 · 85만)은 쓰는 곳이 없어 지운 `formatEok` 의 시험에만 있던 경계다
        (2026-09-05). 함수만 지우고 경계를 함께 버리면 **살아 있는 가지가 조용히
        무방비**가 되므로 이 밴드 쪽으로 옮겼다.
      · 뒤의 둘(8,500만 · 1.0억)은 **원래 어디에도 없던** 경계다 — 지운 시험에도 없었고
        이 밴드 시험에도 없었다(2026-09-05 독립 검토가 `formatEokBand(` 호출 전수를
        훑어 찾아냈다). 옮긴 김에 함께 메운다.
  */
  it('100억 이상은 소수를 떼고 적는다', () => {
    // 그 자리에서 1천만원은 눈에 들어오지도 않는다.
    expect(formatEokBand(12_345_678_901, 12_345_678_901)).toBe('123억 안팎');
  });

  it('1천만원 미만은 만원 눈금 그대로 적는다', () => {
    expect(formatEokBand(850_000, 850_000)).toBe('85만 안팎');
  });

  it('억이 안 되는 큰 값은 **백만원 눈금으로 뭉갠다**', () => {
    // 1천만원 이상 ~ 1억 미만 구간. 만원 자리까지 적으면 30% 언저리로 빗나가는 값에
    // 없는 정밀도를 주장하게 되므로 백만원 자리에서 끊는다.
    //
    // ⚠️ 값을 `85_000_000` 으로 잡으면 **이 시험이 아무것도 못 지킨다** — 그 값은 만원
    //    눈금으로 세든 백만원 눈금으로 세든 똑같이 '8,500만'이라, 뭉개기를 없애 버려도
    //    초록이다(2026-09-05 실측). 그래서 두 눈금이 실제로 갈리는 값을 쓴다
    //    (만원 눈금이면 '8,543만', 백만원 눈금이면 '8,500만').
    expect(formatEokBand(85_432_100, 85_432_100)).toBe('8,500만 안팎');
  });

  it('단위 판정은 **백만원으로 반올림한 뒤에** 한다', () => {
    // 99,999,999원은 억이 아니라고 보고 만 단위로 뭉개면 '10,000만' 이라는 아무도 안
    // 쓰는 표기가 나온다. 그래서 반올림이 억 경계를 넘으면 단위도 함께 올라간다.
    expect(formatEokBand(99_999_999, 99_999_999)).toBe('1.0억 안팎');
  });
});

describe('formatManWonBand — ㎡당 단가의 폭', () => {
  it('만원 눈금으로 두 끝을 잇는다', () => {
    expect(formatManWonBand(7_465_269.63, 19_045_698.84)).toBe('747만~1,905만');
  });

  it('두 끝이 같으면 "안팎"으로 적는다', () => {
    expect(formatManWonBand(16_265_452.18, 16_265_452.18)).toBe('1,627만 안팎');
  });

  it('한쪽이라도 없으면 —', () => {
    expect(formatManWonBand(7_465_269, null)).toBe('—');
    expect(formatManWonBand(null, null)).toBe('—');
  });

  it('1만원 미만은 "0만"이 아니라 원으로 적는다', () => {
    expect(formatManWonBand(4_200, 9_100)).toBe('4,200원~9,100원');
  });

  it('뒤집힌 입력이 와도 작은 값이 앞에 온다', () => {
    expect(formatManWonBand(19_045_698.84, 7_465_269.63)).toBe('747만~1,905만');
  });
});
