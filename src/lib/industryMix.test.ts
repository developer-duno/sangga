import { describe, it, expect } from 'vitest';
import type { IndustryDistrict, IndustryMix, IndustryScope } from '../types';
import {
  catOptions,
  districtLabel,
  districtSources,
  isCat,
  isDistrict,
  isIndustryDetail,
  isIndustryMix,
  isScope,
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
  // 이 레포에는 ErrorBoundary 가 하나도 없다. 곁다리 섹션이 렌더 중에 터지면 층별 화면
  // 전체가 하얗게 죽으므로, 서버 응답을 믿기 전에 모양을 본다.

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
