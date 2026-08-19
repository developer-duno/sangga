import { describe, it, expect } from 'vitest';
import type { FloorRow, PriceBand } from '../types';
import {
  KNOWN_BAND_STATUS,
  describeStage,
  floorBandName,
  groupBands,
  isFarStage,
  isSinglePoint,
  toTotalWon,
} from './priceBand';

/**
 * 참고 매매 시세 밴드(Stage B · 결정 0013)의 순수 계산·어휘 테스트.
 *
 * 여기서 지키는 것은 셋이다:
 *  ① 없는 사실을 지어내지 않는다 (면적 0을 곱해 '0원'을 만들지 않는다)
 *  ② 근거 이름이 성격을 말한다 (L2는 "이 건물"이 아니라 "이 땅", L6는 층대 평균)
 *  ③ 같은 값을 층마다 뿌려 "층마다 따로 쟀다"는 착시를 주지 않는다
 */

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

function floor(floorNo: number, over: Partial<FloorRow> = {}): FloorRow {
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
    ...over,
  };
}

describe('KNOWN_BAND_STATUS — 서버가 주는 status 다섯', () => {
  it('다섯을 알고, 모르는 값은 모른다고 한다', () => {
    for (const s of ['ok', 'gate_fail', 'floor_1f', 'no_evidence', 'no_estimate']) {
      expect(KNOWN_BAND_STATUS.has(s)).toBe(true);
    }
    expect(KNOWN_BAND_STATUS.has('somethig_new')).toBe(false);
  });
});

describe('toTotalWon — ㎡당 단가 × 면적', () => {
  it('단가와 면적을 곱해 총액을 낸다', () => {
    expect(toTotalWon(16_265_452.18, 32.8)).toBeCloseTo(533_506_831.5, 1);
  });

  it('면적이 없으면 총액을 만들지 않는다', () => {
    expect(toTotalWon(16_265_452.18, null)).toBeNull();
  });

  it('면적이 0이면 "0원"을 만들지 않는다', () => {
    // 0을 곱해 0원을 적는 것은 없는 사실을 지어내는 것이다.
    expect(toTotalWon(16_265_452.18, 0)).toBeNull();
  });

  it('단가가 없으면 총액을 만들지 않는다', () => {
    expect(toTotalWon(null, 32.8)).toBeNull();
  });
});

describe('floorBandName — 층대 이름', () => {
  it('서버 price_floor_band 와 같은 자를 쓴다', () => {
    expect(floorBandName(-1)).toBe('지하');
    expect(floorBandName(1)).toBe('1층');
    expect(floorBandName(2)).toBe('2층');
    expect(floorBandName(3)).toBe('3층 이상');
    expect(floorBandName(17)).toBe('3층 이상');
    // ⚠️ Stage A 는 옥탑을 '3층이상'에 흡수하지만 Stage B 는 따로 센다(일부러 다르다).
    expect(floorBandName(99)).toBe('옥탑');
  });
});

describe('describeStage — 근거 단계를 사람 말로', () => {
  it('L2는 "이 건물"이 아니라 "이 땅"이다', () => {
    // 서버 조건이 `t.pnu = v_pnu` 라 한 땅에 여러 동이 있으면 옆 동 거래가 섞여 온다.
    const label = describeStage('L2', 2);
    expect(label).toContain('이 땅');
    expect(label).not.toContain('이 건물');
  });

  it('L4·L5는 거리로 말한다', () => {
    expect(describeStage('L4', 2)).toContain('100m');
    expect(describeStage('L5', 2)).toContain('500m');
  });

  it('L6은 같은 층이 아니라 그 층대의 평균임을 라벨이 말한다', () => {
    // 사용자가 라벨만 읽고도 "이 층 값이 아니라 동네 값"임을 알아야 한다.
    const label = describeStage('L6', 5);
    expect(label).toContain('이 동네');
    expect(label).toContain('3층 이상');
    expect(label).toContain('평균');
  });

  it('모르는 코드면 근거를 지어내지 않는다', () => {
    // 근거를 못 적으면 값도 못 낸다(절대 규칙 3).
    expect(describeStage('L9', 2)).toBeNull();
    expect(describeStage(null, 2)).toBeNull();
  });

  it('내부 번호(L2·L5)를 화면 문구에 흘리지 않는다', () => {
    for (const s of ['L2', 'L4', 'L5', 'L6']) {
      expect(describeStage(s, 3)).not.toContain(s);
    }
  });
});

describe('isFarStage / isSinglePoint — 표식 판정', () => {
  it('L5·L6만 "먼 근거"다', () => {
    expect(isFarStage('L5')).toBe(true);
    expect(isFarStage('L6')).toBe(true);
    expect(isFarStage('L2')).toBe(false);
    expect(isFarStage('L4')).toBe(false);
    expect(isFarStage(null)).toBe(false);
  });

  it('표본 1건이거나 폭이 0이면 밴드가 아니다', () => {
    expect(isSinglePoint(band({ n: 1 }))).toBe(true);
    // ⛔ 이 줄은 **폭 판정이지 건수 판정이 아니다**를 못 박는 줄이다. n=3 인데도 참인 이유는
    //    사분위 셋이 같아서지 거래가 한 건이어서가 아니다(unit_price 가 생성 컬럼이라 같은 층
    //    동일 단가 신고가 겹치면 라이브에서 실제로 이렇게 온다). 이 술어로 "1건뿐" 같은
    //    건수 문장을 찍으면 바로 밑 표본 수와 어긋난다 — 건수는 n 으로만 판단할 것.
    expect(isSinglePoint(band({ n: 3, p25: 100, p75: 100 }))).toBe(true);
    expect(isSinglePoint(band())).toBe(false);
  });
});

describe('groupBands — 같은 값은 한 줄로 묶는다', () => {
  it('연속한 층에서 값이 같으면 한 줄로 묶고 범위로 적는다', () => {
    // 라이브 실측: 강남 필지의 층 17개에 서로 다른 값이 3개뿐이었다. 사다리의 마지막
    // 칸(L6)이 층대별로 한 번만 계산되기 때문이다 — 층마다 뿌리면 착시를 준다.
    const floors = [floor(4), floor(3), floor(2)];
    const bands = [band({ floor_no: 2 }), band({ floor_no: 3 }), band({ floor_no: 4 })];
    const { listed } = groupBands(bands, floors);
    expect(listed).toHaveLength(1);
    expect(listed[0].label).toBe('2층~4층');
    expect(listed[0].floors.map((f) => f.floor_no)).toEqual([4, 3, 2]);
  });

  it('값이 다르면 층마다 줄이 갈린다 (거래가 쌓이면 저절로 갈라진다)', () => {
    const floors = [floor(3), floor(2)];
    const bands = [band({ floor_no: 2, stage: 'L5' }), band({ floor_no: 3, stage: 'L6', n: 1 })];
    const { listed } = groupBands(bands, floors);
    expect(listed).toHaveLength(2);
    expect(listed.map((g) => g.label)).toEqual(['3층', '2층']);
  });

  it('층이 중간에 비면 억지로 묶지 않는다', () => {
    // '2층~5층'이라고 적으면 이 건물에 없는 3·4층까지 덮는 말이 된다.
    const floors = [floor(5), floor(2)];
    const bands = [band({ floor_no: 2 }), band({ floor_no: 5 })];
    const { listed } = groupBands(bands, floors);
    expect(listed).toHaveLength(2);
    expect(listed.map((g) => g.label)).toEqual(['5층', '2층']);
  });

  it('층이 하나뿐이면 범위로 늘여 쓰지 않는다', () => {
    const { listed } = groupBands([band({ floor_no: 2 })], [floor(2)]);
    expect(listed).toHaveLength(1);
    expect(listed[0].label).toBe('2층');
  });

  it('지하·옥탑(no_evidence)은 줄이 아니라 각주로 뺀다', () => {
    const floors = [floor(99), floor(2), floor(-1)];
    const bands = [
      band({ floor_no: -1, status: 'no_evidence', stage: null, n: null }),
      band({ floor_no: 2 }),
      band({ floor_no: 99, status: 'no_evidence', stage: null, n: null }),
    ];
    const { listed, silent } = groupBands(bands, floors);
    expect(listed).toHaveLength(1);
    expect(silent.map((f) => f.floor_no)).toEqual([99, -1]);
  });

  it('이 건물에 없는 층(옆 동 층)과 floor_no=null 줄은 그리지 않는다', () => {
    // 서버는 **필지** 전체의 층을 준다 — 복수동 필지에서 옆 동 층이 섞여 온다.
    const floors = [floor(2)];
    const bands = [
      band({ floor_no: 2 }),
      band({ floor_no: 7 }),
      band({ floor_no: null, status: 'gate_fail' }),
    ];
    const { listed } = groupBands(bands, floors);
    expect(listed).toHaveLength(1);
    expect(listed[0].floors[0].floor_no).toBe(2);
  });

  it('모르는 status 는 그 층을 조용히 건너뛴다 (뜻을 지어내지 않는다)', () => {
    const { listed, silent } = groupBands(
      [band({ floor_no: 2, status: 'somethig_new' })],
      [floor(2)],
    );
    expect(listed).toHaveLength(0);
    expect(silent).toHaveLength(0);
  });

  it('밴드가 없으면 아무 줄도 만들지 않는다', () => {
    const { listed, silent } = groupBands([], [floor(2), floor(1)]);
    expect(listed).toHaveLength(0);
    expect(silent).toHaveLength(0);
  });
});
