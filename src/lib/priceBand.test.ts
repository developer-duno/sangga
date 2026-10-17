import { describe, it, expect, vi } from 'vitest';
import type { FloorRow, PriceBand } from '../types';
import {
  KNOWN_BAND_STATUS,
  bandAxisMaxWon,
  bandMark,
  bandPointsToSigunguTable,
  bandShowsValue,
  bandText,
  describeStage,
  floorBandName,
  groupBands,
  hasUseGroup,
  isFarStage,
  isSinglePoint,
  normalizePriceBands,
  toTotalWon,
  bandGroupLabel,
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
    // 건물 스펙 4칸(2026-08-24a) — 밴드 묶기는 이 넷을 안 보지만 타입이 요구한다.
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
    ...over,
  };
}

describe('KNOWN_BAND_STATUS — 서버가 주는 status 여덟', () => {
  it('여덟을 알고(결정 0040 의 셋 포함), 모르는 값은 모른다고 한다', () => {
    for (const s of [
      'ok',
      'gate_fail',
      'floor_1f',
      'no_evidence',
      'no_estimate',
      'floor_resid',
      'floor_officetel',
      'no_use',
    ]) {
      expect(KNOWN_BAND_STATUS.has(s)).toBe(true);
    }
    expect(KNOWN_BAND_STATUS.size).toBe(8);
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

// ── 그림: 층마다 가로 띠 (결정 0038 A) ────────────────────────────────────────────

describe('그림 — 참고 시세 띠', () => {
  /** 층 하나짜리 줄. */
  const group = (b: PriceBand, floorNo = b.floor_no ?? 2) => groupBands([{ ...b, floor_no: floorNo }], [floor(floorNo)]).listed[0];

  it('bandShowsValue — 값 글을 쓰는 줄만 참(BandBody 와 같은 조건)', () => {
    expect(bandShowsValue(group(band()))).toBe(true);
    expect(bandShowsValue(group(band({ status: 'floor_1f' }), 1))).toBe(false);
    expect(bandShowsValue(group(band({ status: 'no_estimate' })))).toBe(false);
    expect(bandShowsValue(group(band({ stage: 'L9' })))).toBe(false); // 근거를 말할 수 없으면 값도 없다
    expect(bandShowsValue(group(band({ p75: null })))).toBe(false);
    expect(bandShowsValue(group(band({ median: null })))).toBe(false);
    expect(bandShowsValue(group(band({ n: null })))).toBe(false);
  });

  it('bandAxisMaxWon — p75·가운데값 최대를 만원 단위로 1·2·2.5·5 올림(1,904.6만 → 2,000만)', () => {
    expect(bandAxisMaxWon([group(band())])).toBe(20_000_000);
    // 값 안 내는 줄은 상한에 안 낀다.
    expect(
      bandAxisMaxWon([group(band()), group(band({ status: 'no_estimate', p75: 900_000_000 }), 3)]),
    ).toBe(20_000_000);
    // 상한과 같은 값이면 한 칸 더 올리지 않는다.
    expect(bandAxisMaxWon([group(band({ p75: 20_000_000 }))])).toBe(20_000_000);
    expect(bandAxisMaxWon([group(band({ p75: 20_000_001 }))])).toBe(25_000_000);
    // 가운데값이 p75 보다 크게 온 줄(뜻밖의 값)도 축 밖으로 안 나간다.
    expect(bandAxisMaxWon([group(band({ p25: 1_000_000, p75: 2_000_000, median: 30_000_000 }))])).toBe(50_000_000);
  });

  it('bandAxisMaxWon — 값을 내는 줄이 없거나 값이 0 이면 null(띠·축 없음)', () => {
    expect(bandAxisMaxWon([])).toBeNull();
    expect(bandAxisMaxWon([group(band({ status: 'floor_1f' }), 1)])).toBeNull();
    expect(bandAxisMaxWon([group(band({ p25: 0, median: 0, p75: 0 }))])).toBeNull();
  });

  it('bandMark — 띠 = p25~p75 · 눈금 = 가운데값 · 축 0~상한 위 %', () => {
    const m = bandMark(group(band()), 20_000_000);
    expect(m.kind).toBe('band');
    if (m.kind !== 'band') return;
    expect(m.left).toBeCloseTo(37.3263, 3);
    expect(m.width).toBeCloseTo(57.9021, 3);
    expect(m.x).toBeCloseTo(81.3273, 3);
    expect(m.far).toBe(true); // L5 = 먼 근거 → 연한 띠
    expect((bandMark(group(band({ stage: 'L2' })), 20_000_000) as { far: boolean }).far).toBe(false);
  });

  it('bandMark — 1건뿐 · 모두 같은 값(p25 = p75) · p25 > p75 는 띠 없이 눈금만', () => {
    expect(bandMark(group(band({ n: 1 })), 20_000_000).kind).toBe('tick');
    expect(bandMark(group(band({ n: 6, p25: 10_000_000, median: 10_000_000, p75: 10_000_000 })), 20_000_000)).toEqual({
      kind: 'tick',
      x: 50,
      far: true,
    });
    expect(bandMark(group(band({ p25: 19_000_000, p75: 7_000_000 })), 20_000_000).kind).toBe('tick');
  });

  it('bandMark — 값을 안 내는 줄 · 상한 없음이면 none("–")', () => {
    expect(bandMark(group(band({ status: 'floor_1f' }), 1), 20_000_000)).toEqual({ kind: 'none' });
    expect(bandMark(group(band({ stage: null })), 20_000_000)).toEqual({ kind: 'none' });
    expect(bandMark(group(band()), null)).toEqual({ kind: 'none' });
  });
});

// ── 같은 용도 묶음 (결정 0040) ─────────────────────────────────────────────────

describe('결정 0040 — 용도 묶음 이름표·새 status·응답 모양 거르기', () => {
  const one = (b: PriceBand, floorNo = b.floor_no ?? 2) =>
    groupBands([{ ...b, floor_no: floorNo }], [floor(floorNo)]).listed[0];

  it('bandGroupLabel — 넷만 이름이 있고 모르는 값·없음은 null(지어내지 않는다)', () => {
    expect(bandGroupLabel('shop')).toBe('상가');
    expect(bandGroupLabel('office')).toBe('업무');
    expect(bandGroupLabel('lodging')).toBe('숙박');
    expect(bandGroupLabel('other')).toBe('기타');
    expect(bandGroupLabel('resid')).toBeNull();
    expect(bandGroupLabel('officetel')).toBeNull();
    expect(bandGroupLabel('mall')).toBeNull();
    expect(bandGroupLabel(null)).toBeNull();
    expect(bandGroupLabel(undefined)).toBeNull();
  });

  it('근거 줄 — 묶음이 오면 「업무 거래 5건」, 없으면(옛 서버) 지금처럼 「거래 5건」', () => {
    const office = bandText(one(band({ stage: 'L5', n: 5, use_group: 'office' })));
    expect(office.kind).toBe('value');
    if (office.kind === 'value') expect(office.sub).toContain('근거: 500m 안 같은 층 · 업무 거래 5건');
    const old = bandText(one(band({ stage: 'L5', n: 5 })));
    if (old.kind === 'value') {
      expect(old.sub).toContain('근거: 500m 안 같은 층 · 거래 5건');
      expect(old.sub).not.toMatch(/(상가|업무|숙박|기타) 거래/);
    }
    // 폭 0 줄(1건뿐)도 같은 근거 글을 쓴다
    const single = bandText(one(band({ stage: 'L2', n: 1, p25: 100, median: 100, p75: 100, use_group: 'shop' })));
    if (single.kind === 'value') expect(single.sub).toContain('상가 거래 1건');
  });

  it('모르는 묶음 글자는 이름 없이 「거래 N건」', () => {
    const t = bandText(one(band({ n: 7, use_group: 'mall' })));
    if (t.kind === 'value') {
      expect(t.sub).toContain('· 거래 7건');
      expect(t.sub).not.toContain('mall');
    }
  });

  it('새 status 셋의 사유 글 — 👤 결정 원문 그대로', () => {
    expect(bandText(one(band({ status: 'floor_resid', stage: null, n: null })))).toEqual({
      kind: 'none',
      text: '주거 층이라 상가 시세를 내지 않습니다.',
    });
    expect(bandText(one(band({ status: 'floor_officetel', stage: null, n: null })))).toEqual({
      kind: 'none',
      text: '오피스텔 층이라 상가 시세를 내지 않습니다.',
    });
    expect(bandText(one(band({ status: 'no_use', stage: null, n: null })))).toEqual({
      kind: 'none',
      text: '대장에 이 층의 용도가 없어 값을 내지 않습니다.',
    });
  });

  it('새 status 줄은 값도 띠도 없다', () => {
    for (const s of ['floor_resid', 'floor_officetel', 'no_use']) {
      expect(bandShowsValue(one(band({ status: s })))).toBe(false);
    }
  });

  it('값이 같아도 묶음이 다르면 한 줄로 묶지 않는다(이름표가 하나만 남지 않게 · 🟡19)', () => {
    const fl = [floor(4), floor(3)];
    const same = groupBands([band({ floor_no: 3, use_group: 'shop' }), band({ floor_no: 4, use_group: 'shop' })], fl);
    expect(same.listed).toHaveLength(1);
    const diff = groupBands([band({ floor_no: 3, use_group: 'shop' }), band({ floor_no: 4, use_group: 'office' })], fl);
    expect(diff.listed).toHaveLength(2);
  });

  it('normalizePriceBands — 모르는 status 는 빼고 경고 한 번 · use_group 이 글자가 아니면 그 칸만 null', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const rows = normalizePriceBands([
        band({ floor_no: 2, use_group: 'office' }),
        { ...band({ floor_no: 3 }), use_group: 7 as unknown as string },
        band({ floor_no: 4, status: 'somethig_new' }),
        band({ floor_no: 5 }),
      ]);
      expect(rows.map((r) => r.floor_no)).toEqual([2, 3, 5]);
      expect(rows[0].use_group).toBe('office');
      expect(rows[1].use_group).toBeNull();
      expect(rows[1].median).toBe(16_265_452.18);          // 줄은 살린다
      expect('use_group' in rows[2]).toBe(false);          // 옛 서버 꼴은 그대로
      expect(warn).toHaveBeenCalledTimes(1);
      expect(warn.mock.calls[0][0]).toBe('모르는 status 라 그 층은 그리지 않습니다');
      // 7 → null → 이름 없는 「거래 N건」
      const t = bandText(one(rows[1]));
      if (t.kind === 'value') expect(t.sub).toContain('· 거래 15건');
      expect(normalizePriceBands(null)).toEqual([]);
      expect(normalizePriceBands({})).toEqual([]);
    } finally {
      warn.mockRestore();
    }
  });

  it('hasUseGroup — 묶음 글자가 한 줄이라도 오면 참(옛 서버·null 만이면 거짓)', () => {
    expect(hasUseGroup([band({ use_group: 'shop' }), band()])).toBe(true);
    expect(hasUseGroup([band(), band({ use_group: null })])).toBe(false);
    expect(hasUseGroup([])).toBe(false);
  });

  it('bandPointsToSigunguTable — 상가이거나 묶음을 모르는 값 못 낸 층만 상가 표로 보낸다(㉨)', () => {
    expect(bandPointsToSigunguTable(band({ status: 'no_estimate', use_group: 'shop' }))).toBe(true);
    expect(bandPointsToSigunguTable(band({ status: 'no_estimate', use_group: 'office' }))).toBe(false);
    expect(bandPointsToSigunguTable(band({ status: 'no_estimate', use_group: 'lodging' }))).toBe(false);
    expect(bandPointsToSigunguTable(band({ status: 'no_estimate', use_group: 'other' }))).toBe(false);
    expect(bandPointsToSigunguTable(band({ status: 'no_estimate' }))).toBe(true); // 옛 서버
    expect(bandPointsToSigunguTable(band({ status: 'no_estimate', use_group: 'mall' }))).toBe(true);
    expect(bandPointsToSigunguTable(band({ status: 'floor_1f', use_group: null }))).toBe(true);
    expect(bandPointsToSigunguTable(band({ status: 'no_use', use_group: null }))).toBe(true);
    expect(bandPointsToSigunguTable(band({ status: 'floor_resid', use_group: null }))).toBe(false);
    expect(bandPointsToSigunguTable(band({ status: 'floor_officetel', use_group: null }))).toBe(false);
    expect(bandPointsToSigunguTable(band({ status: 'ok', use_group: 'shop' }))).toBe(false);
  });
});
