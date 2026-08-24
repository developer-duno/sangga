import { describe, expect, it } from 'vitest';
import { buildAppSearch, buildShareUrl, isSameSearch, parseAppUrl } from './urlState';

/**
 * 여기서 특히 지키는 것
 * ---------------------
 * 주소는 **누구나 손으로 고칠 수 있는 입력**이다. 이상한 값을 그대로 믿으면 쓸데없는
 * 서버 요청이 나가고 화면은 "찾는 중"에서 멈춘 것처럼 보인다. 그래서 "형식에 안 맞는
 * 값을 조용히 버리는지"를 가장 집요하게 본다.
 *
 * 그리고 **읽기와 쓰기가 서로 짝이 맞는지**(왕복)를 본다 — 한쪽만 맞으면 링크를
 * 만들 수는 있는데 열면 안 되는, 사용자가 겪기 전엔 모르는 결함이 된다.
 */

const BLD = '1168010100107110006_10241100261590';
const SGG = '11680';

describe('parseAppUrl — 주소에서 읽기', () => {
  it('구와 건물을 둘 다 읽는다', () => {
    expect(parseAppUrl(`?sgg=${SGG}&bld=${BLD}`)).toEqual({ sigungu: SGG, bldId: BLD });
  });

  it('빈 주소는 둘 다 없음이다', () => {
    expect(parseAppUrl('')).toEqual({ sigungu: null, bldId: null });
    expect(parseAppUrl('?')).toEqual({ sigungu: null, bldId: null });
  });

  it('구만 있어도 읽는다 (건물을 아직 안 고른 상태)', () => {
    expect(parseAppUrl(`?sgg=${SGG}`)).toEqual({ sigungu: SGG, bldId: null });
  });

  it('모르는 값이 섞여 있어도 우리 것만 읽는다', () => {
    expect(parseAppUrl(`?utm_source=kakao&sgg=${SGG}&bld=${BLD}`)).toEqual({
      sigungu: SGG,
      bldId: BLD,
    });
  });

  it('형식이 아닌 구 코드는 버린다', () => {
    // 5자리 숫자가 아니면 시군구 코드일 수 없다.
    expect(parseAppUrl('?sgg=서울').sigungu).toBeNull();
    expect(parseAppUrl('?sgg=1168').sigungu).toBeNull();
    expect(parseAppUrl('?sgg=116801').sigungu).toBeNull();
  });

  it('형식이 아닌 건물 번호는 버린다', () => {
    expect(parseAppUrl('?bld=abc').bldId).toBeNull();
    expect(parseAppUrl('?bld=1168010100107110006').bldId).toBeNull(); // 밑줄 뒤가 없다
    expect(parseAppUrl(`?bld=${'9'.repeat(19)}_${'9'.repeat(64)}`).bldId).toBeNull(); // 너무 길다
  });

  it('버린 건물 번호 때문에 구까지 잃지는 않는다', () => {
    expect(parseAppUrl(`?sgg=${SGG}&bld=<script>`)).toEqual({ sigungu: SGG, bldId: null });
  });

  it('구가 깨졌어도 건물 번호 앞 5자리로 구를 되찾는다', () => {
    // 링크 하나가 통째로 버려지는 것보다, 되찾을 수 있으면 되찾는 편이 낫다.
    expect(parseAppUrl(`?sgg=xx&bld=${BLD}`)).toEqual({ sigungu: SGG, bldId: BLD });
    expect(parseAppUrl(`?bld=${BLD}`)).toEqual({ sigungu: SGG, bldId: BLD });
  });
});

describe('buildAppSearch — 주소로 쓰기', () => {
  it('둘 다 있으면 둘 다 담는다', () => {
    expect(buildAppSearch({ sigungu: SGG, bldId: BLD })).toBe(`?sgg=${SGG}&bld=${BLD}`);
  });

  it('담을 게 없으면 물음표조차 남기지 않는다', () => {
    expect(buildAppSearch({ sigungu: null, bldId: null })).toBe('');
  });

  it('구만 고른 상태도 그대로 담는다', () => {
    expect(buildAppSearch({ sigungu: SGG, bldId: null })).toBe(`?sgg=${SGG}`);
  });

  it('형식이 아닌 값은 담지 않는다', () => {
    // 화면 상태가 어쩌다 이상해져도 이상한 링크를 만들어 내보내지 않는다.
    expect(buildAppSearch({ sigungu: '서울', bldId: 'abc' })).toBe('');
  });
});

describe('읽기와 쓰기가 짝이 맞는다 (왕복)', () => {
  const cases: Array<{ sigungu: string | null; bldId: string | null }> = [
    { sigungu: SGG, bldId: BLD },
    { sigungu: SGG, bldId: null },
    { sigungu: null, bldId: null },
  ];

  it.each(cases)('%o 를 주소로 만들었다가 다시 읽으면 그대로다', (state) => {
    expect(parseAppUrl(buildAppSearch(state))).toEqual(state);
  });
});

describe('buildShareUrl — 남에게 보낼 주소', () => {
  it('온전한 주소를 만든다', () => {
    expect(
      buildShareUrl('https://sangga-one.vercel.app', '/', { sigungu: SGG, bldId: BLD }),
    ).toBe(`https://sangga-one.vercel.app/?sgg=${SGG}&bld=${BLD}`);
  });

  it('담을 게 없으면 첫 화면 주소가 된다', () => {
    expect(buildShareUrl('https://sangga-one.vercel.app', '/', { sigungu: null, bldId: null })).toBe(
      'https://sangga-one.vercel.app/',
    );
  });
});

describe('isSameSearch — 쓸데없이 다시 쓰지 않기', () => {
  it('같으면 같다고 한다', () => {
    expect(isSameSearch(`?sgg=${SGG}&bld=${BLD}`, { sigungu: SGG, bldId: BLD })).toBe(true);
  });

  it('빈 주소와 담을 것 없는 상태는 같다', () => {
    // 브라우저가 '?' 만 남겨 두는 경우가 있어 그것도 같은 것으로 본다.
    expect(isSameSearch('', { sigungu: null, bldId: null })).toBe(true);
    expect(isSameSearch('?', { sigungu: null, bldId: null })).toBe(true);
  });

  it('다르면 다르다고 한다', () => {
    expect(isSameSearch(`?sgg=${SGG}`, { sigungu: SGG, bldId: BLD })).toBe(false);
  });
});
