import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  hasMoreStores,
  isMissingFunction,
  isStoreHitList,
  matchedLabel,
  readStoreAnswer,
  storeToHit,
} from './storeSearch';
import type { StoreHit } from '../types';

/**
 * 상호명 검색의 순수 계산(결정 0028).
 *
 * 여기서 지키는 것은 대부분 **"한 줄 때문에 목록 전체가 사라지지 않는가"** 다 — LH 공고에서
 * 실제로 났던 사고이고, `.every()` 구조라 조용히 통째로 없어진다(에러가 아니다).
 */

function store(over: Partial<StoreHit> = {}): StoreHit {
  return {
    pnu: '1168010100100010000',
    bld_id: '1168010100100010000_1024110',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    jibun_addr: '서울 강남구 역삼동 823-4',
    lat: 37.5,
    lng: 127.03,
    bld_cnt_in_pnu: 1,
    floor_cnt: 5,
    min_floor: 1,
    max_floor: 5,
    has_roof: false,
    matched_names: ['스타벅스역삼점'],
    match_store_cnt: 1,
    total_parcel_cnt: 1,
    total_store_cnt: 1,
    too_broad: false,
    store_snapshot_ym: '202606',
    ...over,
  };
}

afterEach(() => vi.restoreAllMocks());

describe('isStoreHitList — 모양 검사', () => {
  it('보통 줄을 받는다', () => {
    expect(isStoreHitList([store()])).toBe(true);
  });

  it('빈 배열도 정상이다 — "그 이름의 가게가 이 구에 없다"는 답이다', () => {
    expect(isStoreHitList([])).toBe(true);
  });

  it('“너무 넓다” 한 줄(나머지 칸이 전부 비어 있음)을 거부하지 않는다', () => {
    // ⛔ 이 줄을 거부하면 안내가 통째로 사라져 화면이 **아무 말도 안 하게** 된다.
    const broad: StoreHit = {
      pnu: '-',
      bld_id: null,
      bld_nm: null,
      road_addr: null,
      jibun_addr: null,
      lat: null,
      lng: null,
      bld_cnt_in_pnu: null,
      floor_cnt: null,
      min_floor: null,
      max_floor: null,
      has_roof: null,
      matched_names: null,
      match_store_cnt: null,
      total_parcel_cnt: 0,
      total_store_cnt: 33630,
      too_broad: true,
      store_snapshot_ym: null,
    };
    expect(isStoreHitList([broad])).toBe(true);
  });

  it('일치 상호가 없는 줄 하나가 목록 전체를 날리지 않는다', () => {
    // LH 공고 사고와 같은 자리 — `.every()` 라 한 줄이 통째를 거부한다.
    expect(isStoreHitList([store(), store({ pnu: 'x', matched_names: null })])).toBe(true);
  });

  it('칸 자체가 없어도(undefined) 받는다 — 서버가 안 보낸 것과 null 은 같은 뜻이다', () => {
    const row = store();
    delete (row as Record<string, unknown>).matched_names;
    delete (row as Record<string, unknown>).jibun_addr;
    expect(isStoreHitList([row])).toBe(true);
  });

  it('땅을 가리키는 열쇠(pnu)와 전체 규모가 없으면 거부한다', () => {
    expect(isStoreHitList([store({ pnu: undefined as unknown as string })])).toBe(false);
    expect(
      isStoreHitList([store({ total_parcel_cnt: undefined as unknown as number })]),
    ).toBe(false);
    expect(isStoreHitList([store({ too_broad: undefined as unknown as boolean })])).toBe(false);
  });

  it('상호 목록에 글자가 아닌 것이 섞이면 거부한다', () => {
    expect(isStoreHitList([store({ matched_names: [1] as unknown as string[] })])).toBe(false);
  });

  it('배열이 아닌 답(오류 객체 등)은 거부한다', () => {
    expect(isStoreHitList({ code: 'PGRST202' })).toBe(false);
    expect(isStoreHitList(null)).toBe(false);
  });
});

describe('readStoreAnswer — 서버 답을 구역 상태로', () => {
  const ok = (data: unknown) =>
    ({ status: 'fulfilled', value: { data, error: null } }) as const;
  const bad = (error: unknown) =>
    ({ status: 'fulfilled', value: { data: null, error } }) as const;

  it('땅 목록이 오면 그린다', () => {
    expect(readStoreAnswer(ok([store()]), '스타벅스')).toEqual({
      at: 'done',
      rows: [store()],
    });
  });

  it('0건이면 구역 자체가 없다', () => {
    expect(readStoreAnswer(ok([]), '없는가게')).toEqual({ at: 'hidden' });
  });

  it('함수가 아직 없으면(PGRST202) 조용히 생략한다 — 사용자가 할 수 있는 일이 없다', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(readStoreAnswer(bad({ code: 'PGRST202' }), '스타벅스')).toEqual({ at: 'hidden' });
  });

  it('그 밖의 실패는 생략하지 않고 실패라고 말한다', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(readStoreAnswer(bad({ code: '42501' }), '스타벅스')).toEqual({ at: 'failed' });
  });

  it('질의가 통째로 거절돼도(rejected) 실패로 다룬다 — 다른 구역은 살아야 한다', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(
      readStoreAnswer({ status: 'rejected', reason: new Error('끊김') }, '스타벅스'),
    ).toEqual({ at: 'failed' });
  });

  it('모양이 뜻밖이면 실패로 다룬다 — 렌더로 흘려보내지 않는다', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(readStoreAnswer(ok([{ 엉뚱: true }]), '스타벅스')).toEqual({ at: 'failed' });
  });

  it('“너무 넓다”는 0건이 아니라 별도 상태로 가른다', () => {
    const broad = store({ too_broad: true, total_store_cnt: 33630, matched_names: null });
    expect(readStoreAnswer(ok([broad]), '카페')).toEqual({
      at: 'broad',
      word: '카페',
      count: 33630,
    });
  });
});

describe('matchedLabel — 일치한 상호 줄', () => {
  it('상호를 가운뎃점으로 잇는다', () => {
    expect(matchedLabel(store({ matched_names: ['가', '나'], match_store_cnt: 2 }))).toBe('가 · 나');
  });

  it('서버가 준 3개보다 많이 걸렸으면 "외 N곳"을 적는다', () => {
    // 안 적으면 3곳뿐인 것으로 읽힌다.
    expect(matchedLabel(store({ matched_names: ['가', '나', '다'], match_store_cnt: 1203 }))).toBe(
      '가 · 나 · 다 외 1,200곳',
    );
  });

  it('적을 상호가 없으면 null 이다 — 빈 줄을 그리지 않는다', () => {
    expect(matchedLabel(store({ matched_names: null }))).toBeNull();
    expect(matchedLabel(store({ matched_names: [] }))).toBeNull();
    expect(matchedLabel(store({ matched_names: ['  '] }))).toBeNull();
  });

  it('가게 수가 안 오면 "외 N곳"을 지어내지 않는다', () => {
    expect(matchedLabel(store({ matched_names: ['가'], match_store_cnt: null }))).toBe('가');
  });
});

describe('storeToHit — 땅 한 줄 → 건물 화면으로', () => {
  it('앞 12칸을 그대로 옮긴다', () => {
    const s = store();
    expect(storeToHit({ ...s, bld_id: s.bld_id! })).toEqual({
      bld_id: s.bld_id,
      pnu: s.pnu,
      bld_nm: s.bld_nm,
      road_addr: s.road_addr,
      jibun_addr: s.jibun_addr,
      lat: s.lat,
      lng: s.lng,
      bld_cnt_in_pnu: 1,
      floor_cnt: 5,
      min_floor: 1,
      max_floor: 5,
      has_roof: false,
    });
  });

  it('가게 수는 함께 넘기지 않는다 — 그건 땅의 값이지 건물의 값이 아니다', () => {
    const s = store({ match_store_cnt: 7, total_store_cnt: 9, matched_names: ['가'] });
    const hit = storeToHit({ ...s, bld_id: s.bld_id! }) as Record<string, unknown>;
    for (const leak of ['match_store_cnt', 'matched_names', 'total_store_cnt', 'too_broad']) {
      expect(hit[leak]).toBeUndefined();
    }
  });

  it('비어 있는 칸은 화면이 이미 다루는 값으로 채운다', () => {
    const s = store({ bld_cnt_in_pnu: null, floor_cnt: null, has_roof: null });
    const hit = storeToHit({ ...s, bld_id: s.bld_id! });
    expect(hit).toMatchObject({ bld_cnt_in_pnu: 1, floor_cnt: 0, has_roof: false });
  });
});

describe('hasMoreStores · isMissingFunction', () => {
  it('전체 수보다 손에 든 줄이 적으면 더 받을 것이 남았다', () => {
    expect(hasMoreStores([store({ total_parcel_cnt: 120 })])).toBe(true);
  });

  it('마지막 쪽이 딱 떨어져도 "더 보기"가 남지 않는다', () => {
    const rows = [store({ total_parcel_cnt: 2 }), store({ pnu: 'b', total_parcel_cnt: 2 })];
    expect(hasMoreStores(rows)).toBe(false);
  });

  it('빈 목록에는 더 보기가 없다', () => {
    expect(hasMoreStores([])).toBe(false);
  });

  it('함수 부재만 PGRST202 로 가른다', () => {
    expect(isMissingFunction({ code: 'PGRST202' })).toBe(true);
    expect(isMissingFunction({ code: '42501' })).toBe(false);
    expect(isMissingFunction(null)).toBe(false);
    expect(isMissingFunction(new Error('끊김'))).toBe(false);
  });
});
