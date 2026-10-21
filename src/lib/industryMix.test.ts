import { describe, it, expect } from 'vitest';
import type {
  IndustryDistrict,
  IndustryFloors,
  IndustryMedian,
  IndustryMedianM,
  IndustryMedianPop,
  IndustryMix,
  IndustryScope,
} from '../types';
import {
  basementUnknownCounted,
  catOptions,
  districtLabel,
  districtSources,
  FLOOR_BAND_LABELS,
  FLOOR_BAND_ORDER,
  FLOOR_BAND_TONE,
  floorLine,
  floorScopeByKey,
  floorStack,
  isCat,
  isDistrict,
  isFloorScope,
  isIndustryDetail,
  isIndustryFloors,
  isIndustryMedian,
  isIndustryMedianM,
  isIndustryMix,
  isScope,
  MEDIAN_BADGE,
  medianLine,
  medianMarkPct,
  medianMNote,
  medianMTooSmall,
  medianMViewOf,
  medianNote,
  medianTooSmall,
  medianViewOf,
  sameCatMs,
  sidoNameOf,
  toBars,
} from './industryMix';

function scope(over: Partial<IndustryScope> = {}): IndustryScope {
  return {
    total: 10,
    cats: [
      { cd: 'I2', nm: '음식', n: 6 },
      { cd: 'G2', nm: '소매', n: 4 },
    ],
    ...over,
  };
}

function district(over: Partial<IndustryDistrict> = {}): IndustryDistrict {
  return {
    district_id: 'D1',
    name: '강남역',
    type: '발달상권',
    source_nm: '서울특별시 상권분석서비스',
    total: 10,
    cats: [{ cd: 'I2', nm: '음식', n: 10 }],
    ...over,
  };
}

function mix(over: Partial<IndustryMix> = {}): IndustryMix {
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    districts: [district()],
    radius: scope(),
    ...over,
  };
}

describe('toBars — 막대 몫', () => {
  it('그 스코프의 total 을 분모로 쓴다', () => {
    const bars = toBars(scope());
    expect(bars.map((b) => b.pct)).toEqual([60, 40]);
  });

  it('total 이 0 이면 NaN 대신 0% 를 준다', () => {
    // 0으로 나눈 NaN이 style.width 로 들어가면 막대가 통째로 사라진다 — 화면이
    // "0곳"이 아니라 "칸 자체가 없음"처럼 보인다.
    const bars = toBars({ total: 0, cats: [{ cd: 'I2', nm: '음식', n: 0 }] });
    expect(bars[0].pct).toBe(0);
    expect(Number.isNaN(bars[0].pct)).toBe(false);
  });

  it('원래 칸(cd·nm·n)을 그대로 지닌다', () => {
    expect(toBars(scope())[0]).toMatchObject({ cd: 'I2', nm: '음식', n: 6 });
  });
});

describe('catOptions — 셀렉트 목록', () => {
  it('스코프 한쪽에만 있는 업종도 고를 수 있다', () => {
    // 상권에는 있고 반경에는 없는 업종이 실제로 있다. 한쪽만 보면 그 업종이 목록에서
    // 사라져 사용자가 영영 고를 수 없게 된다.
    const m = mix({
      districts: [district({ cats: [{ cd: 'P1', nm: '교육', n: 3 }] })],
      radius: { total: 5, cats: [{ cd: 'I2', nm: '음식', n: 5 }] },
    });
    expect(catOptions(m).map((o) => o.cd).sort()).toEqual(['I2', 'P1']);
  });

  it('중복 업종을 한 번만 낸다', () => {
    const m = mix({
      districts: [district({ cats: [{ cd: 'I2', nm: '음식', n: 3 }] })],
      radius: { total: 5, cats: [{ cd: 'I2', nm: '음식', n: 5 }] },
    });
    expect(catOptions(m)).toEqual([{ cd: 'I2', nm: '음식' }]);
  });

  it('많은 순으로 내고, 같으면 코드순이라 순서가 흔들리지 않는다', () => {
    const m = mix({
      districts: [],
      radius: {
        total: 9,
        cats: [
          { cd: 'G2', nm: '소매', n: 3 },
          { cd: 'I2', nm: '음식', n: 3 },
          { cd: 'P1', nm: '교육', n: 3 },
        ],
      },
    });
    expect(catOptions(m).map((o) => o.cd)).toEqual(['G2', 'I2', 'P1']);
  });

  it('개수(rank)를 밖으로 내보내지 않는다', () => {
    // 그 수는 여러 스코프의 **합**이라 어느 스코프의 점포 수도 아니다. 화면에 새어
    // 나가면 겹쳐 센 수를 사실처럼 보여주게 된다.
    for (const o of catOptions(mix())) {
      expect(Object.keys(o).sort()).toEqual(['cd', 'nm']);
    }
  });

  it('radius 가 null 이어도 상권 것만으로 목록을 만든다', () => {
    expect(catOptions(mix({ radius: null })).map((o) => o.cd)).toEqual(['I2']);
  });
});

describe('districtLabel', () => {
  it('이름과 종류를 잇는다', () => {
    expect(districtLabel(district())).toBe('강남역(발달상권)');
  });

  it('종류가 없으면 이름만 낸다', () => {
    expect(districtLabel(district({ type: null }))).toBe('강남역');
  });

  it('이름이 없어도 빈 제목을 만들지 않는다', () => {
    expect(districtLabel(district({ name: null, type: null }))).toBe('(이름 없는 상권)');
  });
});

describe('districtSources — 출처는 자료에서 온다', () => {
  it('중복을 없애고 정렬해서 준다', () => {
    const got = districtSources([
      district({ district_id: 'A', source_nm: '서울특별시 상권분석서비스' }),
      district({ district_id: 'B', source_nm: '서울특별시 상권분석서비스' }),
      district({ district_id: 'C', source_nm: '소상공인시장진흥공단' }),
    ]);
    expect(got).toEqual(['서울특별시 상권분석서비스', '소상공인시장진흥공단']);
  });

  it('출처가 없으면 빈 목록이다 — 지어내지 않는다', () => {
    expect(districtSources([district({ source_nm: null })])).toEqual([]);
    expect(districtSources([])).toEqual([]);
  });
});

describe('모양 검사 — 화이트스크린 막는 유일한 방어선', () => {
  // 곁다리 섹션이 렌더 중에 터지면 층별 화면이 통째로 오류 안내로 바뀌므로, 서버 응답을
  // 믿기 전에 모양을 본다.
  // ⓘ 정정 2026-09-01 — 원래 "이 레포에는 ErrorBoundary 가 하나도 없다"고 적혀 있었는데
  //   2026-08-24 에 그물이 셋 생겼다. 그물은 **터진 뒤**를 수습할 뿐이라 이 검사의
  //   값어치는 그대로다(여기서 걸러야 그 섹션만 빠지고 나머지가 산다).

  it('제대로 된 스코프를 통과시킨다', () => {
    expect(isScope(scope())).toBe(true);
    expect(isScope({ total: 0, cats: [] })).toBe(true);
  });

  it('객체가 아니면 막는다', () => {
    for (const bad of [null, undefined, 'x', 3, []]) expect(isScope(bad)).toBe(false);
  });

  it('total 이 숫자가 아니면 막는다 — toLocaleString 에서 터진다', () => {
    expect(isScope({ total: '10', cats: [] })).toBe(false);
    expect(isScope({ cats: [] })).toBe(false);
  });

  it('cats 가 배열이 아니면 막는다 — map 에서 터진다', () => {
    expect(isScope({ total: 1, cats: null })).toBe(false);
    expect(isScope({ total: 1 })).toBe(false);
  });

  it('칸 하나가 망가져도 막는다 — n.toLocaleString() 이 곧 화이트스크린이다', () => {
    expect(isScope({ total: 1, cats: [{ cd: 'I2', nm: '음식', n: '5' }] })).toBe(false);
    expect(isScope({ total: 1, cats: [{ nm: '음식', n: 5 }] })).toBe(false);
  });

  it('칸의 이름은 없어도 된다 — 화면이 코드로 대신 적는다', () => {
    expect(isCat({ cd: 'I2', nm: null, n: 5 })).toBe(true);
    expect(isCat({ cd: 'I2', n: 5 })).toBe(true);
  });

  it('상권 묶음은 district_id 까지 있어야 한다 — 화면이 key 로 쓴다', () => {
    expect(isDistrict(district())).toBe(true);
    expect(isDistrict(scope())).toBe(false);
  });

  it('제대로 된 응답을 통과시킨다', () => {
    expect(isIndustryMix(mix())).toBe(true);
    expect(isIndustryDetail({ ...mix(), cat_l_cd: 'I2' })).toBe(true);
  });

  it('radius 가 null 인 것은 **정상**이다 — 못 쟀다는 뜻이라 빈 집계와 다르다', () => {
    expect(isIndustryMix(mix({ radius: null }))).toBe(true);
  });

  it('radius_m 이 없으면 막는다 — 화면이 반경 길이를 서버에서 받는다', () => {
    const bad = { ...mix() } as Record<string, unknown>;
    delete bad.radius_m;
    expect(isIndustryMix(bad)).toBe(false);
  });

  it('PostgREST 오류 객체를 막는다 (마이그레이션 적용 전 라이브)', () => {
    expect(isIndustryMix({ code: 'PGRST202', message: 'function does not exist' })).toBe(false);
  });

  it('다른 함수의 응답을 막는다 (상권 줄 응답이 흘러드는 경우)', () => {
    // 목이 함수 이름으로 갈라 답하지 않으면 실제로 이런 일이 난다.
    expect(isIndustryMix({ covered: true, districts: [{ name: '역삼역', type: '발달상권' }] })).toBe(
      false,
    );
  });

  it('상세는 cat_l_cd 가 없으면 막는다 — 늦게 온 답을 버리는 유일한 근거다', () => {
    expect(isIndustryDetail(mix())).toBe(false);
  });
});

// ── 업종별 층 분포 (물결 2-2) ─────────────────────────────────────────────────

/** 지시서 예시값 그대로 — 지하 4 · 1층 700 · 2층 150 · 3층 이상 80 · 층 미상 300 (총 1,234 → 미상 24%). */
const BANDS = { b: 4, '1': 700, '2': 150, '3+': 80, na: 300 };

function floors(over: Partial<IndustryFloors> = {}): IndustryFloors {
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    cat_l_cd: 'I2',
    cat_m_cds: null,
    districts: [{ district_id: 'D1', name: '강남역', total: 1234, bands: { ...BANDS } }],
    radius: { total: 1234, bands: { ...BANDS } },
    ...over,
  };
}

describe('업종별 층 분포 — 층 줄 글자', () => {
  it('예시값 그대로 한 줄 — 지하부터 위로, 층 미상은 끝에 괄호 %', () => {
    expect(floorLine('음식', { total: 1234, bands: { ...BANDS } })).toBe(
      '층별 음식: 지하 4곳 · 1층 700곳 · 2층 150곳 · 3층 이상 80곳 · 층 미상 300곳 (24%)',
    );
  });

  it('칩 줄은 이름표만 다르다', () => {
    expect(floorLine('고른 업종(카페)', { total: 10, bands: { b: 0, '1': 6, '2': 1, '3+': 1, na: 2 } })).toBe(
      '층별 고른 업종(카페): 지하 0곳 · 1층 6곳 · 2층 1곳 · 3층 이상 1곳 · 층 미상 2곳 (20%)',
    );
  });

  it('천 단위 쉼표', () => {
    expect(floorLine('음식', { total: 12000, bands: { b: 0, '1': 10000, '2': 0, '3+': 0, na: 2000 } })).toContain(
      '1층 10,000곳',
    );
  });

  it('total 0 이면 줄을 안 그린다(null)', () => {
    expect(floorLine('음식', { total: 0, bands: { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 } })).toBeNull();
  });

  it('차례·이름표 다섯이 고정이다', () => {
    expect([...FLOOR_BAND_ORDER]).toEqual(['b', '1', '2', '3+', 'na']);
    expect(FLOOR_BAND_ORDER.map((k) => FLOOR_BAND_LABELS[k])).toEqual(['지하', '1층', '2층', '3층 이상', '층 미상']);
  });
});

describe('업종별 층 분포 — 응답 모양 검사', () => {
  it('제대로 된 응답 · radius null · 칩 중분류 배열을 통과시킨다', () => {
    expect(isIndustryFloors(floors())).toBe(true);
    expect(isIndustryFloors(floors({ radius: null }))).toBe(true);
    expect(isIndustryFloors(floors({ cat_m_cds: ['I212'] }))).toBe(true);
  });

  it('열쇠 하나라도 빠지면 막는다 — 빠진 묶음을 0 으로 채우면 모르는 것을 없음이라 적는다', () => {
    for (const k of FLOOR_BAND_ORDER) {
      const bands: Record<string, number> = { ...BANDS };
      delete bands[k];
      expect(isFloorScope({ total: 1, bands }), k).toBe(false);
      expect(isIndustryFloors(floors({ radius: { total: 1, bands } as never })), k).toBe(false);
    }
  });

  it('음수·소수·글자 개수를 막는다', () => {
    expect(isFloorScope({ total: 1, bands: { ...BANDS, na: -1 } })).toBe(false);
    expect(isFloorScope({ total: 1, bands: { ...BANDS, b: 1.5 } })).toBe(false);
    expect(isFloorScope({ total: '1', bands: { ...BANDS } })).toBe(false);
    expect(isFloorScope({ total: 1, bands: null })).toBe(false);
  });

  it('cat_l_cd·cat_m_cds·district_id 가 이상하면 막는다', () => {
    expect(isIndustryFloors({ ...floors(), cat_l_cd: undefined })).toBe(false);
    expect(isIndustryFloors({ ...floors(), cat_m_cds: [1] })).toBe(false);
    expect(isIndustryFloors({ ...floors(), cat_m_cds: 'I212' })).toBe(false);
    expect(
      isIndustryFloors(floors({ districts: [{ name: '강남역', total: 1, bands: { ...BANDS } } as never] })),
    ).toBe(false);
  });

  it('다른 함수의 응답·오류 객체를 막는다', () => {
    expect(isIndustryFloors({ code: 'PGRST202', message: 'function does not exist' })).toBe(false);
    expect(isIndustryFloors({ ...mix(), cat_l_cd: 'I2' })).toBe(false);
  });

  // 물결 2-2c — basement_unknown_counted 는 선택 칸: 없거나 모양이 틀려도 응답을 버리지 않고, 정확히 true 일 때만 참.
  it.each([
    ['없음', undefined, false],
    ['true', true, true],
    ['false', false, false],
    ['null', null, false],
    ["'true'(글자)", 'true', false],
    ['1(숫자)', 1, false],
  ])('2-2c counted %s → 응답은 통과 · basementUnknownCounted = %s', (_label, value, want) => {
    const x = value === undefined ? floors() : { ...floors(), basement_unknown_counted: value };
    expect(isIndustryFloors(x)).toBe(true);
    expect(basementUnknownCounted(x as IndustryFloors)).toBe(want);
  });

  it('2-2c basementUnknownCounted(null) 은 거짓', () => {
    expect(basementUnknownCounted(null)).toBe(false);
  });
});

describe('업종별 층 분포 — 늦게 온 답 · 블록 열쇠', () => {
  it('중분류 목록은 순서와 무관하게 견주고, null 은 null 하고만 같다', () => {
    expect(sameCatMs(['I212', 'P105'], ['P105', 'I212'])).toBe(true);
    expect(sameCatMs(null, null)).toBe(true);
    expect(sameCatMs(null, [])).toBe(false);
    expect(sameCatMs(['I212'], ['I201'])).toBe(false);
  });

  it('상권은 district_id, 반경은 __radius__ 열쇠로 찾는다', () => {
    const m = floorScopeByKey(floors());
    expect([...m.keys()]).toEqual(['D1', '__radius__']);
    expect(floorScopeByKey(floors({ radius: null })).has('__radius__')).toBe(false);
    expect(floorScopeByKey(null).size).toBe(0);
  });
});

// ── 업종 비중 비교 (물결 2-3 · 결정 0036 결정 18 ㉓~㉖) ─────────────────────────

const GOL: IndustryMedianPop = { scope: 'type', sido_cd: '11', district_type: '골목상권', n: 999 };
const SEOUL_ALL: IndustryMedianPop = { scope: 'all', sido_cd: '11', district_type: null, n: 1502 };
const DJ: IndustryMedianPop = { scope: 'type', sido_cd: '30', district_type: '주요상권', n: 37 };

function median(over: Partial<IndustryMedian> = {}): IndustryMedian {
  return {
    snapshot_ym: '202606',
    min_total: 30,
    min_pop: 30,
    districts: [
      {
        district_id: 'D1',
        type: '골목상권',
        total: 215,
        pop: GOL,
        cats: [
          { cd: 'I2', nm: '음식', med_pct: 25 },
          { cd: 'I1', nm: '숙박', med_pct: 1.8 },
        ],
      },
      { district_id: 'D2', type: '전통시장', total: 12, pop: null, cats: [] },
    ],
    ...over,
  };
}

describe('업종 비중 비교 — 글 함수(예시값 글자 그대로)', () => {
  it('같은 종류 · 시·도 전체 · 대전', () => {
    expect(medianLine('서울', GOL, 25)).toBe('서울 골목상권 가운데 25.0%');
    expect(medianLine('서울', SEOUL_ALL, 25.9)).toBe('서울 상권 전체 가운데 25.9%');
    expect(medianLine('대전', DJ, 36.2)).toBe('대전 주요상권 가운데 36.2%');
    expect(medianLine('서울', GOL, 1.8)).toBe('서울 골목상권 가운데 1.8%');
  });

  it('지역 표에 없는 sido_cd 면 지역 글자를 뺀다', () => {
    expect(sidoNameOf('11')).toBe('서울');
    expect(sidoNameOf('30')).toBe('대전');
    expect(sidoNameOf('99')).toBeNull();
    expect(medianLine(null, { ...GOL, sido_cd: '99' }, 25)).toBe('골목상권 가운데 25.0%');
    expect(medianNote(null, { ...SEOUL_ALL, sido_cd: '99' }, 30)).toContain('가운데값은 상권 전체 1,502곳');
  });

  it('설명 줄은 모집단 곳 수와 서버의 기준(30)을 적는다', () => {
    expect(medianNote('대전', DJ, 30)).toBe(
      '가운데값은 대전 주요상권 37곳(점포 30곳 이상 상권)의 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.',
    );
    expect(medianNote('서울', SEOUL_ALL, 30)).toContain('서울 상권 전체 1,502곳(점포 30곳 이상 상권)');
    // 기준은 서버 값 — 화면에 30 을 박지 않는다.
    expect(medianNote('서울', GOL, 40)).toContain('(점포 40곳 이상 상권)');
    expect(MEDIAN_BADGE).toBe('C등급 · 비교값');
  });

  it('점포가 기준 미만이면 사실 한 줄 · 0곳·기준 이상이면 없음', () => {
    expect(medianTooSmall(12, 30)).toBe('점포 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.');
    expect(medianTooSmall(29, 30)).not.toBeNull();
    expect(medianTooSmall(30, 30)).toBeNull();
    expect(medianTooSmall(0, 30)).toBeNull();
    expect(medianTooSmall(12, 40)).toBe('점포 12곳 — 40곳이 안 돼 비교값은 적지 않습니다.');
  });

  it('판단 낱말·금칙어가 글 함수에 없다', () => {
    const texts = [
      medianLine('서울', GOL, 25),
      medianLine('서울', SEOUL_ALL, 25.9),
      medianNote('서울', GOL, 30),
      medianTooSmall(12, 30) ?? '',
      MEDIAN_BADGE,
    ].join(' ');
    for (const w of ['많', '적다', '적습', '높', '낮', '%p', '배', '적정가', '감정가', '평가액']) {
      expect(texts).not.toContain(w);
    }
  });
});

describe('업종 비중 비교 — 모양 검사(틀리면 통째로 버림)', () => {
  it('정상 응답 · 빈 상권 목록', () => {
    expect(isIndustryMedian(median())).toBe(true);
    expect(isIndustryMedian(median({ districts: [] }))).toBe(true);
    expect(isIndustryMedian(median({ snapshot_ym: null }))).toBe(true);
  });

  it.each([
    ['null', null],
    ['배열', []],
    ['min_total 없음', { ...median(), min_total: undefined }],
    ['min_total 0', { ...median(), min_total: 0 }],
    ['min_pop 소수', { ...median(), min_pop: 30.5 }],
    ['districts 객체', { ...median(), districts: {} }],
  ])('겉모양 이상: %s', (_name, x) => {
    expect(isIndustryMedian(x)).toBe(false);
  });

  const bad = (patch: Record<string, unknown>) =>
    median({ districts: [{ ...median().districts[0], ...patch } as never] });

  it.each([
    ['med_pct 글자', { cats: [{ cd: 'I2', nm: '음식', med_pct: '25.0' }] }],
    ['med_pct 음수', { cats: [{ cd: 'I2', nm: '음식', med_pct: -1 }] }],
    ['med_pct 100 초과', { cats: [{ cd: 'I2', nm: '음식', med_pct: 100.1 }] }],
    ['med_pct NaN', { cats: [{ cd: 'I2', nm: '음식', med_pct: Number.NaN }] }],
    ['cd 없음', { cats: [{ nm: '음식', med_pct: 25 }] }],
    ['cats 없음', { cats: undefined }],
    ['total 소수', { total: 12.5 }],
    ['district_id 숫자', { district_id: 7 }],
    ['pop 이상한 범위', { pop: { ...GOL, scope: 'radius' } }],
    ['type 인데 종류 없음', { pop: { ...GOL, district_type: null } }],
    ['type 인데 종류 빈 글자', { pop: { ...GOL, district_type: '' } }],
    ['all 인데 종류 있음', { pop: { ...SEOUL_ALL, district_type: '골목상권' } }],
    ['pop n 0', { pop: { ...GOL, n: 0 } }],
    ['pop null 인데 cats 있음', { pop: null }],
  ])('상권 줄 이상: %s', (_name, patch) => {
    expect(isIndustryMedian(bad(patch))).toBe(false);
  });
});

describe('업종 비중 비교 — 상권 블록 글 묶음', () => {
  it('모집단이 있으면 줄마다 글 + 설명 줄', () => {
    const v = medianViewOf(median(), 'D1', '202606')!;
    expect(v.lines.get('I2')).toBe('서울 골목상권 가운데 25.0%');
    expect(v.lines.get('I1')).toBe('서울 골목상권 가운데 1.8%');
    expect(v.lines.has('G2')).toBe(false); // 가운데값 줄이 없는 업종은 그 줄만 비교 글 없음
    expect(v.note).toContain('서울 골목상권 999곳(점포 30곳 이상 상권)');
    expect(v.tooSmall).toBeNull();
  });

  it('점포가 기준 미만이면 사실 한 줄만', () => {
    const v = medianViewOf(median(), 'D2', '202606')!;
    expect(v.lines.size).toBe(0);
    expect(v.note).toBeNull();
    expect(v.tooSmall).toBe('점포 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.');
  });

  it('응답 없음 · 그 상권 줄 없음 · 분기 다름 · 점포 0곳이면 null(비교 글 0)', () => {
    expect(medianViewOf(null, 'D1', '202606')).toBeNull();
    expect(medianViewOf(median(), 'D9', '202606')).toBeNull();
    expect(medianViewOf(median(), 'D1', '202603')).toBeNull();
    const zero = median({ districts: [{ district_id: 'D3', type: '골목상권', total: 0, pop: null, cats: [] }] });
    expect(medianViewOf(zero, 'D3', '202606')).toBeNull();
  });
});

// ── 업종 비중 비교 · 중분류 (물결 2-3b · 결정 0036 결정 18 ㉗~㉚) ─────────────────────

const GOL_I2: IndustryMedianPop = { scope: 'type', sido_cd: '11', district_type: '골목상권', n: 526 };

function medianM(over: Partial<IndustryMedianM> = {}): IndustryMedianM {
  return {
    snapshot_ym: '202606',
    cat_l_cd: 'I2',
    min_total: 30,
    min_pop: 30,
    districts: [
      {
        district_id: 'D1',
        type: '골목상권',
        total: 120,
        pop: GOL_I2,
        cats: [
          { cd: 'I201', nm: '한식', med_pct: 38.1 },
          { cd: 'I210', nm: '기타 간이', med_pct: 20.6 },
          { cd: 'I212', nm: '비알코올', med_pct: 15.2 },
          { cd: 'I205', nm: '동남아시아', med_pct: 0 },
        ],
      },
      { district_id: 'D2', type: '전통시장', total: 12, pop: null, cats: [] },
    ],
    ...over,
  };
}

describe('업종 비중 비교 · 중분류 — 글 함수(👤 ㉚ 미리보기 글자 그대로)', () => {
  it('설명 줄 — 그 대분류 30곳 이상 상권 곳 수와 대분류 이름', () => {
    expect(medianMNote('서울', GOL_I2, '음식', 30)).toBe(
      '가운데값은 서울 골목상권 가운데 음식 가게가 30곳 이상인 526곳의 음식 안 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.',
    );
    // 종류가 30곳 미만이면 시·도 전체 — '상권 전체'(형제 medianLine·medianNote 와 같은 규칙).
    expect(medianMNote('서울', { ...SEOUL_ALL, n: 540 }, '음식', 30)).toBe(
      '가운데값은 서울 상권 전체 가운데 음식 가게가 30곳 이상인 540곳의 음식 안 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.',
    );
    // 기준은 서버 값 · 지역 표에 없으면 지역 글자를 뺀다 · 천 단위 쉼표.
    expect(medianMNote(null, { ...GOL_I2, sido_cd: '99', n: 1234 }, '소매', 40)).toBe(
      '가운데값은 골목상권 가운데 소매 가게가 40곳 이상인 1,234곳의 소매 안 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.',
    );
  });

  it('줄마다의 비교 글은 형제 medianLine 그대로', () => {
    expect(medianLine('서울', GOL_I2, 15.2)).toBe('서울 골목상권 가운데 15.2%');
    expect(medianLine('서울', GOL_I2, 0)).toBe('서울 골목상권 가운데 0.0%');
  });

  it('그 대분류 가게가 기준 미만이면 사실 한 줄 · 0곳·기준 이상이면 없음', () => {
    expect(medianMTooSmall('음식', 12, 30)).toBe('음식 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.');
    expect(medianMTooSmall('음식', 29, 30)).not.toBeNull();
    expect(medianMTooSmall('음식', 30, 30)).toBeNull();
    expect(medianMTooSmall('음식', 0, 30)).toBeNull();
    expect(medianMTooSmall('숙박', 1200, 1500)).toBe('숙박 1,200곳 — 1,500곳이 안 돼 비교값은 적지 않습니다.');
  });

  it('판단 낱말·금칙어가 글 함수에 없다', () => {
    const texts = [
      medianMNote('서울', GOL_I2, '음식', 30),
      medianMNote('서울', SEOUL_ALL, '음식', 30),
      medianMTooSmall('음식', 12, 30) ?? '',
    ].join(' ');
    for (const w of ['많', '적다', '적습', '높', '낮', '%p', '배', '적정가', '감정가', '평가액']) {
      expect(texts).not.toContain(w);
    }
  });
});

describe('업종 비중 비교 · 중분류 — 모양 검사(틀리면 통째로 버림)', () => {
  it('정상 응답 · 빈 상권 목록', () => {
    expect(isIndustryMedianM(medianM())).toBe(true);
    expect(isIndustryMedianM(medianM({ districts: [] }))).toBe(true);
  });

  it.each([
    ['cat_l_cd 없음', { ...medianM(), cat_l_cd: undefined }],
    ['cat_l_cd 숫자', { ...medianM(), cat_l_cd: 2 }],
    ['형제 모양 이상(min_total 0)', { ...medianM(), min_total: 0 }],
    ['형제 모양 이상(med_pct 100 초과)', medianM({ districts: [{ ...medianM().districts[0], cats: [{ cd: 'I201', nm: '한식', med_pct: 101 }] }] })],
    ['pop null 인데 cats 있음', medianM({ districts: [{ ...medianM().districts[0], pop: null }] })],
  ])('이상: %s', (_name, x) => {
    expect(isIndustryMedianM(x)).toBe(false);
  });
});

describe('업종 비중 비교 · 중분류 — 상세 상권 블록 글 묶음', () => {
  it('모집단이 있으면 중분류 줄마다 글 + 설명 줄', () => {
    const v = medianMViewOf(medianM(), 'D1', '202606', 'I2', '음식')!;
    expect(v.lines.get('I212')).toBe('서울 골목상권 가운데 15.2%');
    expect(v.lines.get('I201')).toBe('서울 골목상권 가운데 38.1%');
    expect(v.lines.get('I205')).toBe('서울 골목상권 가운데 0.0%'); // 0 포함 — 0 도 값이다
    expect(v.lines.has('I299')).toBe(false); // 가운데값 줄이 없는 중분류는 그 줄만 비교 글 없음
    expect(v.note).toBe(
      '가운데값은 서울 골목상권 가운데 음식 가게가 30곳 이상인 526곳의 음식 안 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.',
    );
    expect(v.tooSmall).toBeNull();
  });

  it('그 대분류 가게가 기준 미만이면 사실 한 줄만', () => {
    const v = medianMViewOf(medianM(), 'D2', '202606', 'I2', '음식')!;
    expect(v.lines.size).toBe(0);
    expect(v.note).toBeNull();
    expect(v.tooSmall).toBe('음식 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.');
  });

  it('응답 없음 · 상권 줄 없음 · 분기 다름 · 대분류 다름 · 0곳이면 null(비교 글 0)', () => {
    expect(medianMViewOf(null, 'D1', '202606', 'I2', '음식')).toBeNull();
    expect(medianMViewOf(medianM(), 'D9', '202606', 'I2', '음식')).toBeNull();
    expect(medianMViewOf(medianM(), 'D1', '202603', 'I2', '음식')).toBeNull();
    // 대분류를 바꾼 첫 렌더 — 옛 대분류(I2)의 답이 새 대분류(G2) 블록에 서지 않는다.
    expect(medianMViewOf(medianM(), 'D1', '202606', 'G2', '소매')).toBeNull();
    const zero = medianM({ districts: [{ district_id: 'D3', type: '골목상권', total: 0, pop: null, cats: [] }] });
    expect(medianMViewOf(zero, 'D3', '202606', 'I2', '음식')).toBeNull();
  });
});

// ── 그림 (결정 0038 E) ─────────────────────────────────────────────────────────

describe('그림 — 가운데값 ▲ 자리', () => {
  it('글 묶음에 숫자(pcts)가 글(lines)과 같은 열쇠로 든다 — 대분류·중분류 둘 다', () => {
    const v = medianViewOf(median(), 'D1', '202606')!;
    expect([...v.pcts.keys()]).toEqual([...v.lines.keys()]);
    expect(v.pcts.get('I2')).toBe(25.0);
    const m = medianMViewOf(medianM(), 'D1', '202606', 'I2', '음식')!;
    expect([...m.pcts.keys()]).toEqual([...m.lines.keys()]);
    expect(m.pcts.get('I212')).toBe(15.2);
    expect(m.pcts.get('I205')).toBe(0); // 0 도 값이다(▲ 는 0% 자리)
  });

  it('점포가 기준 미만인 상권은 숫자도 없다(▲ 0)', () => {
    expect(medianViewOf(median(), 'D2', '202606')!.pcts.size).toBe(0);
    expect(medianMViewOf(medianM(), 'D2', '202606', 'I2', '음식')!.pcts.size).toBe(0);
  });

  it('medianMarkPct — 막대와 같은 0~100 자 · 없음·범위 밖이면 null', () => {
    expect(medianMarkPct(25)).toBe(25);
    expect(medianMarkPct(0)).toBe(0);
    expect(medianMarkPct(100)).toBe(100);
    expect(medianMarkPct(null)).toBeNull();
    expect(medianMarkPct(undefined)).toBeNull();
    expect(medianMarkPct(Number.NaN)).toBeNull();
    expect(medianMarkPct(-0.1)).toBeNull();
    expect(medianMarkPct(100.1)).toBeNull();
  });
});

describe('그림 — 층 묶음 쌓은 막대', () => {
  const sc = (bands: Record<string, number>, total = Object.values(bands).reduce((a, b) => a + b, 0)) =>
    ({ total, bands }) as unknown as Parameters<typeof floorStack>[0];

  it('차례는 FLOOR_BAND_ORDER 고정 · 폭 = 곳 수 ÷ 합 · 합 100', () => {
    const cells = floorStack(sc({ na: 25, '3+': 9, '2': 24, '1': 90, b: 2 }))!;
    expect(cells.map((c) => c.key)).toEqual(['b', '1', '2', '3+', 'na']);
    expect(cells.map((c) => Number(c.pct.toFixed(4)))).toEqual([1.3333, 60, 16, 6, 16.6667]);
    expect(cells.reduce((a, c) => a + c.pct, 0)).toBeCloseTo(100, 9);
  });

  it('지하 → 3층 이상은 호박 진하기 4단(옅음 → 짙음) · 층 미상은 회색', () => {
    const cells = floorStack(sc({ b: 1, '1': 1, '2': 1, '3+': 1, na: 1 }))!;
    expect(cells.map((c) => c.tone)).toEqual(['--fact-1', '--fact-2', '--fact-3', '--fact-4', '--viz-na']);
    expect(FLOOR_BAND_TONE.na).toBe('--viz-na');
  });

  it('0곳 묶음은 칸 없음(최소 폭 강제 금지) · 한 묶음뿐이면 100%', () => {
    expect(floorStack(sc({ b: 0, '1': 36, '2': 9, '3+': 3, na: 12 }))!.map((c) => c.key)).toEqual([
      '1',
      '2',
      '3+',
      'na',
    ]);
    expect(floorStack(sc({ b: 0, '1': 0, '2': 0, '3+': 0, na: 7 }))).toEqual([
      { key: 'na', pct: 100, tone: '--viz-na' },
    ]);
  });

  it('total 0 이거나 다섯 묶음 합 0 이면 null(층 줄도 안 서는 범위)', () => {
    const zero = { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 };
    expect(floorStack(sc(zero))).toBeNull();
    expect(floorStack(sc(zero, 5))).toBeNull();
    expect(floorStack(sc({ b: 1, '1': 1, '2': 1, '3+': 1, na: 1 }, 0))).toBeNull();
  });
});
