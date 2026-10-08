/**
 * 창업자 업종 칩과 그 짝짓기 표(👤 결정 0036 결정 1·18 ⑤⑨ · ⑫~⑮).
 *
 * 칩 하나가 두 카드를 움직이는데 두 카드의 업종 분류가 다르다 — 둘레 업종 분포는 소상공인시장진흥공단
 * 분류(대분류 → 중분류), 개업·폐업은 서울시 100업종이다. 그래서 칩마다 두 분류의 짝을 **이 표 한 곳**에
 * 적고, 두 카드는 이 표만 본다(카드마다 따로 적으면 한쪽만 고쳐지는 날 엉뚱한 줄이 굵어진다).
 *
 * ⛔ **칩은 화면만 바꾼다** — 이 기기 저장·주소·의견함 어디에도 싣지 않는다(새로고침 = 전체).
 *    상권 목록(지도)도 거르지 않는다(물결 2-2 에서 DB 와 함께).
 * ⛔ **칩 줄은 창업자에게만** 선다. 다른 역할로 바꾸면 칩은 전체로 돌아간다.
 * ⓘ 코드는 2026-10-09 운영 DB 실측(서울+대전 공개 분기 · 서울 개업·폐업 최신 분기)에서 골랐다.
 */

/** 칩 차례 그대로(결정 18 ⑤). 처음 값은 맨 뒤의 전체. */
export const FOUNDER_CHIPS = ['카페', '한식', '미용', '학원', '편의점', '전체'] as const;

export type FounderChip = (typeof FOUNDER_CHIPS)[number];

/** 아무 효과 없는 칩 — 지금 화면 그대로. */
export const FOUNDER_CHIP_ALL: FounderChip = '전체';

export type ChipMatch = {
  /** 소진공 대분류 코드 — 업종 분포 카드가 미리 고를 값. */
  readonly catL: string;
  /** 그 대분류 이름 — 둘레에 그 대분류가 없어 고르개 목록에 이름이 없을 때 코드 대신 쓴다. */
  readonly catLNm: string;
  /** 업종 분포 카드에서 굵게 할 중분류 코드. */
  readonly catM: readonly string[];
  /** 개업·폐업 카드에서 굵게 할 서울시 100업종 코드. */
  readonly seoul: readonly string[];
  /**
   * 그 코드의 서울시 업종 이름(2026-10-09 DB 실측) — 짝 업종 일부만 상위 표에 있을 때 빠진 것을 이름으로
   * 적는다(👤 F5). ⓘ 그 줄은 코드가 둘 이상인 칩(미용·학원)에서만 생기고, 그 이름은 모두 받침으로 끝나
   * 조사를 '은' 하나로 둔다(`founderChips.test.ts` 가 지킨다 · 코드가 하나인 '커피-음료'는 받침이 없지만
   * 그 줄이 생기지 않는다).
   */
  readonly seoulNm: Readonly<Record<string, string>>;
  /** 업종 분포 카드에 붙일 설명 한 줄(편의점만 — 중분류가 슈퍼마켓까지 함께 센다). */
  readonly note?: string;
};

export const CHIP_MATCH: Readonly<Record<Exclude<FounderChip, '전체'>, ChipMatch>> = {
  카페: {
    catL: 'I2',
    catLNm: '음식',
    catM: ['I212'],
    seoul: ['CS100010'],
    seoulNm: { CS100010: '커피-음료' },
  },
  한식: {
    catL: 'I2',
    catLNm: '음식',
    catM: ['I201'],
    seoul: ['CS100001'],
    seoulNm: { CS100001: '한식음식점' },
  },
  // ⑫ 미용 = 미용실·네일·피부 셋(서울시는 셋으로 가르고 소진공은 한 중분류다).
  미용: {
    catL: 'S2',
    catLNm: '수리·개인',
    catM: ['S207'],
    seoul: ['CS200028', 'CS200029', 'CS200030'],
    seoulNm: { CS200028: '미용실', CS200029: '네일숍', CS200030: '피부관리실' },
  },
  // ⑬ 학원 = 두 줄(입시·교과 + 예체능·외국어 등 기타 교육).
  학원: {
    catL: 'P1',
    catLNm: '교육',
    catM: ['P105', 'P106'],
    seoul: ['CS200001', 'CS200002', 'CS200003', 'CS200004', 'CS200005'],
    seoulNm: {
      CS200001: '일반교습학원',
      CS200002: '외국어학원',
      CS200003: '예술학원',
      CS200004: '컴퓨터학원',
      CS200005: '스포츠 강습',
    },
  },
  // ⑭ 편의점 = 소분류로 안 내려가고 '종합 소매' 줄을 굵게 + 설명 한 줄.
  편의점: {
    catL: 'G2',
    catLNm: '소매',
    catM: ['G204'],
    seoul: ['CS300002'],
    seoulNm: { CS300002: '편의점' },
    note: '종합 소매에는 편의점과 슈퍼마켓이 함께 들어 있습니다',
  },
};

/** 이 칩의 짝. 전체면 null(효과 없음). */
export function chipMatch(chip: FounderChip): ChipMatch | null {
  return chip === '전체' ? null : CHIP_MATCH[chip];
}
