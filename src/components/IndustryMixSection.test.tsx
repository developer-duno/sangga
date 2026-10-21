import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { IndustryDetail, IndustryFloors, IndustryMedian, IndustryMedianM, IndustryMix } from '../types';

/**
 * "둘레의 업종 분포" 섹션 테스트(결정 0014).
 *
 * 이 화면에서 조용히 틀리기 쉬운 것 셋을 특히 지킨다:
 *  ① 못 읽었을 때 **아무 말도 안 하는가** — 마이그레이션 적용 전 라이브가 그 상태다.
 *     여기서 "업종 없음"이라 적으면 모르는 것을 없는 것이라 말하게 된다.
 *  ② 기준 분기·반경 길이를 **서버가 준 값**으로 적는가 — 글자로 박으면 자료가 바뀌는 날
 *     코드를 한 줄도 안 고쳤는데 문구만 거짓말이 된다.
 *  ③ 늦게 도착한 상세를 **버리는가** — 사용자가 그 사이 다른 업종을 골랐으면 그 답은
 *     엉뚱한 목록이다.
 */

const responses = {
  mix: { data: null as unknown, error: null as unknown },
  detail: { data: null as unknown, error: null as unknown },
  /** true 면 상세 응답을 영영 안 준다 — "아직 안 옴" 상태를 보려고 둔 스위치다. */
  detailPending: false,
  /**
   * 서버 함수 count_nearby_permits 의 응답(둘레에 새로 올라오는 상가 건물).
   *
   * 기본값을 **함수 없음**으로 둔다 — 마이그레이션 적용 전 라이브가 그 상태이고, 그러면
   * 이 파일의 다른 시험들이 보는 화면이 그대로 유지된다(그 줄만 없다).
   */
  permits: { data: null as unknown, error: { message: 'PGRST202' } as unknown },
  /**
   * 서버 함수 list_industry_floors 의 응답(물결 2-2 업종별 층 분포). 기본값 = **함수 없음** —
   * 마이그레이션 적용 전 라이브 상태이고, 다른 시험들이 보는 화면이 그대로다(층 줄만 없다).
   * 함수를 넣으면 인자로 갈라 답한다 — 대분류 줄과 칩 줄이 다른 답을 받게.
   */
  floors: null as null | ((args: { p_cat_l: string; p_cat_m: string[] | null }) => { data: unknown; error: unknown }),
  /** true 면 층 응답을 영영 안 준다 — "아직 안 옴" 상태. */
  floorsPending: false,
  /**
   * 서버 함수 list_industry_median 의 응답(물결 2-3 업종 비중 비교). 기본값 = **함수 없음** — 마이그레이션 적용 전
   * 라이브 상태이고, 다른 시험들이 보는 화면이 그대로다(비교 글만 없다). 필지로 갈라 답할 수 있게 함수로 둔다.
   */
  median: (() => ({ data: null, error: { message: 'PGRST202' } })) as (pnu: string) => Promise<unknown> | {
    data: unknown;
    error: unknown;
  },
  /**
   * 서버 함수 list_industry_median_m 의 응답(물결 2-3b 중분류 비교). 기본값 = **함수 없음** — 마이그레이션 적용 전
   * 라이브 상태이고, 다른 시험들이 보는 상세 블록이 그대로다(중분류 비교 글만 없다). 인자로 갈라 답할 수 있게 함수로 둔다.
   */
  medianM: (() => ({ data: null, error: { message: 'PGRST202' } })) as (args: {
    p_pnu: string;
    p_cat_l: string;
  }) => Promise<unknown> | { data: unknown; error: unknown },
};

/** 마지막 rpc 호출들. "인자 이름을 p_pnu·p_cat 으로 보내는가"를 여기서 확인한다. */
const rpcCalls: Array<{ fn: string; args: unknown }> = [];

vi.mock('../lib/supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      if (fn === 'list_industry_detail') {
        return responses.detailPending
          ? new Promise(() => {})
          : Promise.resolve(responses.detail);
      }
      // ⚠️ 갈라 답해야 한다. 안 그러면 분포 응답(업종 객체)이 인허가 줄로 흘러들어
      //    "늘 미표시"가 되고, 그 상태로도 아래 시험 대부분이 초록이라 아무도 모른다.
      if (fn === 'count_nearby_permits') return Promise.resolve(responses.permits);
      if (fn === 'list_industry_median') {
        return Promise.resolve(responses.median((args as { p_pnu: string }).p_pnu));
      }
      if (fn === 'list_industry_median_m') {
        return Promise.resolve(responses.medianM(args as { p_pnu: string; p_cat_l: string }));
      }
      if (fn === 'list_industry_floors') {
        if (responses.floorsPending) return new Promise(() => {});
        return Promise.resolve(
          responses.floors
            ? responses.floors(args as { p_cat_l: string; p_cat_m: string[] | null })
            : { data: null, error: { message: 'PGRST202' } },
        );
      }
      return Promise.resolve(responses.mix);
    },
  },
}));

const { IndustryMixSection } = await import('./IndustryMixSection');

function mix(over: Partial<IndustryMix> = {}): IndustryMix {
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    districts: [
      {
        district_id: '3120189',
        name: '강남역',
        type: '발달상권',
        source_nm: '서울특별시 상권분석서비스',
        total: 100,
        cats: [
          { cd: 'I2', nm: '음식', n: 60 },
          { cd: 'G2', nm: '소매', n: 40 },
        ],
      },
    ],
    radius: {
      total: 200,
      cats: [
        { cd: 'I2', nm: '음식', n: 150 },
        { cd: 'G2', nm: '소매', n: 50 },
      ],
    },
    ...over,
  };
}

function detail(over: Partial<IndustryDetail> = {}): IndustryDetail {
  return {
    snapshot_ym: '202606',
    radius_m: 500,
    cat_l_cd: 'I2',
    districts: [
      {
        district_id: '3120189',
        name: '강남역',
        total: 60,
        cats: [
          { cd: 'I201', nm: '한식', n: 40 },
          { cd: 'I202', nm: '중식', n: 20 },
        ],
      },
    ],
    radius: { total: 150, cats: [{ cd: 'I201', nm: '한식', n: 150 }] },
    ...over,
  };
}

beforeEach(() => {
  rpcCalls.length = 0;
  responses.mix = { data: mix(), error: null };
  responses.detail = { data: detail(), error: null };
  responses.detailPending = false;
  responses.permits = { data: null, error: { message: 'PGRST202' } };
  responses.floors = null;
  responses.floorsPending = false;
  responses.median = () => ({ data: null, error: { message: 'PGRST202' } });
  responses.medianM = () => ({ data: null, error: { message: 'PGRST202' } });
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('IndustryMixSection — 못 읽었을 때', () => {
  it('오류면 섹션을 통째로 감춘다 (마이그레이션 적용 전 라이브)', async () => {
    responses.mix = { data: null, error: { message: 'PGRST202' } };
    const { container } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await waitFor(() => expect(container.querySelector('.mix')).toBeNull());
    // "업종 없음"이라고 적지 않는다 — 없는 것과 모르는 것은 다르다.
    expect(screen.queryByText(/둘레의 업종 분포/)).toBeNull();
  });

  it('상권도 없고 반경도 못 쟀으면(좌표 없음) 빈 제목만 남기지 않는다', async () => {
    responses.mix = { data: mix({ districts: [], radius: null }), error: null };
    const { container } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await waitFor(() => expect(container.querySelector('.mix')).toBeNull());
  });

  it('상권 경계 밖이어도 반경만으로 보여준다', async () => {
    responses.mix = { data: mix({ districts: [] }), error: null };
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/반경 500m 안/)).toBeTruthy();
  });
});

describe('IndustryMixSection — 두 스코프', () => {
  it('상권과 반경을 각각 총수와 함께 보여준다', async () => {
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/강남역\(발달상권\) 안/)).toBeTruthy();
    expect(screen.getByText(/반경 500m 안/)).toBeTruthy();
    // 총수를 함께 적는다 — 몫(%)만 있으면 60%가 6곳인지 6,000곳인지 알 수 없다.
    expect(screen.getByText('100곳')).toBeTruthy();
    expect(screen.getByText('200곳')).toBeTruthy();
  });

  it('몫은 스코프마다 자기 분모로 잰다', async () => {
    const { container } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await screen.findByText(/강남역/);
    const pcts = [...container.querySelectorAll('.mix__pct')].map((e) => e.textContent);
    // 상권 60/100·40/100, 반경 150/200·50/200 — 두 분모를 합치지 않는다.
    expect(pcts).toEqual(['60.0%', '40.0%', '75.0%', '25.0%']);
  });

  it('반경 길이를 서버가 준 값으로 적는다 (화면에 500 을 박지 않는다)', async () => {
    responses.mix = { data: mix({ radius_m: 300 }), error: null };
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/반경 300m 안/)).toBeTruthy();
    expect(screen.queryByText(/반경 500m 안/)).toBeNull();
  });

  it('기준 분기를 서버가 준 값으로 적는다', async () => {
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/2026년 2분기 기준/)).toBeTruthy();
  });

  it('출처를 자료에서 읽어 적는다 (공공누리 1유형 의무)', async () => {
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/소상공인시장진흥공단 상가\(상권\)정보/)).toBeTruthy();
    expect(screen.getByText(/서울특별시 상권분석서비스/)).toBeTruthy();
  });

  it('상권끼리 더하지 말라고 못 박는다 (겹쳐 세기)', async () => {
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/서로 더하면 안 됩니다/)).toBeTruthy();
  });

  it('이 건물만이 아니라 둘레라고 먼저 말한다', async () => {
    // 층 목록의 점포 칸과 세는 대상이 달라, 안 갈라 말하면 두 숫자를 견주게 된다.
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText(/이 건물만이 아니라 이 땅 둘레의 가게들입니다/)).toBeTruthy();
  });
});

describe('IndustryMixSection — 업종 골라보기', () => {
  it('고르면 중분류와 "같은 업종 N곳"을 낸다', async () => {
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });

    // 한식은 상권·반경 **양쪽**에 나온다 — 스코프마다 따로 세므로 두 줄이 맞다.
    expect(await screen.findAllByText('한식')).toHaveLength(2);
    // 중식은 상권에만 있다(반경 픽스처에 없다) — 없는 스코프에 지어내지 않는다.
    expect(screen.getAllByText('중식')).toHaveLength(1);
    // 경쟁 카운트 — 스코프마다 따로 센다.
    expect(screen.getByText('음식 60곳')).toBeTruthy();
    expect(screen.getByText('음식 150곳')).toBeTruthy();
  });

  it('인자를 p_pnu·p_cat 이름으로 보낸다', async () => {
    // 목(mock)은 인자 이름을 안 보므로, 틀려도 테스트는 초록이고 라이브에서만
    // PGRST202 가 난다 — 그래서 이름 자체를 시험한다.
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });

    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_detail')).toBe(true));
    expect(rpcCalls.find((c) => c.fn === 'list_industry_mix')!.args).toEqual({
      p_pnu: '1168010100100010000',
    });
    expect(rpcCalls.find((c) => c.fn === 'list_industry_detail')!.args).toEqual({
      p_pnu: '1168010100100010000',
      p_cat: 'I2',
    });
  });

  it('아직 안 왔으면 0곳이라고 적지 않는다', async () => {
    responses.detailPending = true;
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });

    expect(await screen.findByText(/음식 상세를 불러오는 중/)).toBeTruthy();
    expect(screen.queryByText('음식 0곳')).toBeNull();
  });

  it('다른 업종의 답이 늦게 오면 버린다', async () => {
    // 서버가 물어본 업종을 그대로 되돌려 주므로 화면이 갈라낼 수 있다. 이걸 안 하면
    // 제목은 '소매'인데 목록은 '한식'인 상태가 조용히 만들어진다.
    responses.detail = { data: detail({ cat_l_cd: 'I2' }), error: null };
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'G2' } });

    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_detail')).toBe(true));
    // 'I2' 의 답이 왔지만 지금 고른 것은 'G2' 라 그리지 않는다.
    await waitFor(() => expect(screen.queryByText('한식')).toBeNull());
    expect(await screen.findByText(/소매 상세를 불러오는 중/)).toBeTruthy();
  });

  it('상세를 못 읽으면 못 읽었다고 말한다 — 물레방아를 영원히 돌리지 않는다', async () => {
    // ⛔ 회귀 방지: 실패 시 상태를 안 바꾸면 detail 이 null 로 남아 "불러오는 중…"이
    //    영영 돌아간다. 사용자는 느린 것으로 알고 계속 기다린다.
    responses.detail = { data: null, error: { message: 'boom' } };
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });

    expect(await screen.findByText('음식 상세를 불러오지 못했습니다.')).toBeTruthy();
    expect(screen.queryByText(/음식 상세를 불러오는 중/)).toBeNull();
    // "0곳"이라고 적지도 않는다 — 모르는 것을 없는 것이라 말하게 된다.
    expect(screen.queryByText('음식 0곳')).toBeNull();
    // 위쪽 분포는 그대로 남는다(상세만 접는다).
    expect(screen.getByText(/강남역\(발달상권\) 안/)).toBeTruthy();
  });

  it('상세 모양이 뜻밖이어도 못 읽었다고 말한다 (오류 객체가 200 으로 올 때)', async () => {
    responses.detail = { data: { code: 'PGRST202' }, error: null };
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });

    expect(await screen.findByText('음식 상세를 불러오지 못했습니다.')).toBeTruthy();
    expect(screen.getByText(/강남역\(발달상권\) 안/)).toBeTruthy();
  });

  it('다른 업종을 다시 고르면 실패 표시가 사라진다', async () => {
    // 실패 상태가 눌어붙으면, 다음에 고른 업종이 정상이어도 "못 읽었다"가 남는다.
    responses.detail = { data: null, error: { message: 'boom' } };
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });
    await screen.findByText('음식 상세를 불러오지 못했습니다.');

    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    fireEvent.change(select, { target: { value: 'G2' } });
    await waitFor(() => expect(screen.queryByText(/불러오지 못했습니다/)).toBeNull());
  });

  it('같은 업종이 많다고 나쁜 자리는 아니라고 덧붙인다', async () => {
    render(<IndustryMixSection pnu="1168010100100010000" />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });
    expect(await screen.findByText(/같은 업종이 많다고 나쁜 자리는 아닙니다/)).toBeTruthy();
  });
});

describe('IndustryMixSection — 둘레에 새로 올라오는 건물', () => {
  /** 서버가 주는 한 행. 기본은 3동 중 2동 착공 = 허가만 1동. */
  function permits(over: Record<string, unknown> = {}) {
    return { data: { total_cnt: 3, started_cnt: 2, base_ym: '202607', ...over }, error: null };
  }

  it('동수·허가만·착공·기준월을 한 줄로 낸다', async () => {
    responses.permits = permits();
    render(<IndustryMixSection pnu="1168010100100010000" />);

    expect(await screen.findByText('새로 올라오는 상가 건물 3동')).toBeTruthy();
    // 기준월은 서버가 준 값이다 — 화면에 글자로 박으면 자료가 바뀌는 날 거짓말이 된다.
    expect(screen.getByText(/허가만 1동 · 착공 2동 \(2026년 7월 인허가 기준\)/)).toBeTruthy();
    // ⛔ 앞일을 단정하지 않는다. 허가는 받고도 안 짓는 일이 흔하다.
    expect(screen.getByText(/허가를 받았다고 모두 지어지는 것은 아닙니다/)).toBeTruthy();
    const text = document.body.textContent ?? '';
    for (const banned of ['예정', '곧 완공', '들어설']) expect(text).not.toContain(banned);
  });

  it("'허가만'은 전체에서 착공을 뺀 값이다", async () => {
    // ⛔ 회귀 방지: 이 뺄셈이 틀리면 화면의 두 수를 더해도 전체가 안 나오는데, 사람은
    //    그걸 "이 서비스 자료가 이상하다"로 읽는다.
    responses.permits = permits({ total_cnt: 7, started_cnt: 2 });
    render(<IndustryMixSection pnu="1168010100100010000" />);

    expect(await screen.findByText('새로 올라오는 상가 건물 7동')).toBeTruthy();
    expect(screen.getByText(/허가만 5동 · 착공 2동/)).toBeTruthy();
  });

  it('0동이면 그 줄만 조용히 빠진다 (카드는 그대로 선다)', async () => {
    responses.permits = permits({ total_cnt: 0, started_cnt: 0 });
    render(<IndustryMixSection pnu="1168010100100010000" />);

    await screen.findByText(/강남역\(발달상권\) 안/);
    await waitFor(() => expect(screen.queryByText(/새로 올라오는 상가 건물/)).toBeNull());
    // "0동"이나 "새로 짓는 건물 없음"이라 적지 않는다 — 모르는 것과 없는 것이 뒤섞인다.
    expect(screen.queryByText(/인허가 기준/)).toBeNull();
  });

  it('함수가 아직 없어도(PGRST202) 카드의 나머지는 그대로다', async () => {
    responses.permits = { data: null, error: { message: 'PGRST202' } };
    const { container } = render(<IndustryMixSection pnu="1168010100100010000" />);

    expect(await screen.findByText(/강남역\(발달상권\) 안/)).toBeTruthy();
    expect(screen.getByText(/반경 500m 안/)).toBeTruthy();
    expect(screen.getByLabelText('업종 골라보기')).toBeTruthy();
    expect(container.querySelector('.mix__permits')).toBeNull();
  });

  it('인자를 p_pnu 이름으로 보낸다', async () => {
    // 목(mock)은 인자 이름을 안 보므로, 틀려도 테스트는 초록이고 라이브에서만 PGRST202 가
    // 난다 — 그래서 이름 자체를 시험한다.
    responses.permits = permits();
    render(<IndustryMixSection pnu="1168010100100010000" />);
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'count_nearby_permits')).toBe(true));
    expect(rpcCalls.find((c) => c.fn === 'count_nearby_permits')!.args).toEqual({
      p_pnu: '1168010100100010000',
    });
  });

  it('오래 멈춰 있는 것이 있으면 한 줄을 더 적는다 (결재 2026-09-05)', async () => {
    // ⛔ 숫자를 빼는 것이 아니라 **사실을 덧붙이는 것**이다 — 7동은 그대로 7동이다.
    responses.permits = permits({ total_cnt: 7, started_cnt: 2, stale_cnt: 3 });
    render(<IndustryMixSection pnu="1168010100100010000" />);

    expect(await screen.findByText('새로 올라오는 상가 건물 7동')).toBeTruthy();
    expect(
      screen.getByText(
        /그중 3동은 허가 후 2년 넘게 착공하지 않았습니다\(건축법상 허가가 실효됐을 수 있습니다\)\./,
      ),
    ).toBeTruthy();
    // ⛔ 실효를 **단정**하지 않는다 — 원본에 실효 칸이 없다.
    const text = document.body.textContent ?? '';
    for (const banned of ['실효됐습니다', '실효된 허가', '취소됐']) {
      expect(text).not.toContain(banned);
    }
  });

  it('멈춘 것이 0동이거나 서버가 그 칸을 안 주면 그 문장만 빠진다', async () => {
    // 0동 — '0동이 멈춰 있습니다'는 읽는 사람에게 아무 뜻이 없다.
    responses.permits = permits({ total_cnt: 7, started_cnt: 2, stale_cnt: 0 });
    const { unmount } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await screen.findByText('새로 올라오는 상가 건물 7동');
    expect(screen.queryByText(/2년 넘게 착공하지 않았습니다/)).toBeNull();
    unmount();

    // 2026-09-05b 를 아직 안 올린 라이브 — 옛 응답이 새 화면을 깨뜨리면 안 된다.
    responses.permits = permits({ total_cnt: 7, started_cnt: 2 });
    render(<IndustryMixSection pnu="1168010100100010000" />);
    expect(await screen.findByText('새로 올라오는 상가 건물 7동')).toBeTruthy();
    expect(screen.getByText(/허가만 5동 · 착공 2동/)).toBeTruthy();
    expect(screen.queryByText(/2년 넘게 착공하지 않았습니다/)).toBeNull();
  });

  it('필지가 바뀌면 앞 건물의 인허가 수를 지운다', async () => {
    responses.permits = permits();
    const { rerender } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await screen.findByText('새로 올라오는 상가 건물 3동');

    responses.permits = { data: null, error: { message: 'PGRST202' } };
    rerender(<IndustryMixSection pnu="1111010100100010000" />);
    // 앞 건물의 수가 새 건물 밑에 잠깐이라도 붙어 있으면 그 순간이 그대로 틀린 정보다.
    await waitFor(() => expect(screen.queryByText(/새로 올라오는 상가 건물/)).toBeNull());
  });
});

describe('IndustryMixSection — 금칙어·노출면', () => {
  it('절대 규칙 2 금칙어를 쓰지 않는다', async () => {
    const { container } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await screen.findByText(/강남역/);
    const text = container.textContent ?? '';
    for (const banned of ['적정가', '평가액', '감정가', '가치평가', '시세']) {
      expect(text).not.toContain(banned);
    }
  });

  it('필지가 바뀌면 앞 건물의 분포를 지운다', async () => {
    const { container, rerender } = render(<IndustryMixSection pnu="1168010100100010000" />);
    await screen.findByText(/강남역/);

    responses.mix = {
      data: mix({ districts: [], radius: { total: 7, cats: [{ cd: 'P1', nm: '교육', n: 7 }] } }),
      error: null,
    };
    rerender(<IndustryMixSection pnu="1111010100100010000" />);

    // 앞 건물의 상권이 잠깐이라도 새 건물 밑에 붙어 있으면 그 순간이 그대로 틀린 정보다.
    await waitFor(() => expect(screen.queryByText(/강남역/)).toBeNull());
    // ⚠️ 막대 칸으로 좁혀 찾는다 — 셀렉트의 <option> 에도 같은 업종 이름이 있어
    //    그냥 찾으면 "여러 개가 걸렸다"로 실패한다.
    await waitFor(() =>
      expect([...container.querySelectorAll('.mix__cat')].map((e) => e.textContent)).toEqual([
        '교육',
      ]),
    );
  });
});

/**
 * 창업자 업종 칩(👤 결정 0036 결정 18 ⑨) — 칩을 고른 채 건물을 열면 카드가 그 대분류를 **미리 고른
 * 채** 열리고, 짝 중분류 줄이 굵다. 칩을 바꾸면 열린 카드도 따라 바뀐다(첫 렌더 함정).
 */
describe('IndustryMixSection — 창업자 업종 칩', () => {
  const PNU = '1168010100100010000';
  /** 카페 짝 중분류(I212)가 든 상세. */
  function cafeDetail() {
    return detail({
      districts: [
        {
          district_id: '3120189',
          name: '강남역',
          total: 60,
          cats: [
            { cd: 'I201', nm: '한식', n: 40 },
            { cd: 'I212', nm: '비알코올', n: 20 },
          ],
        },
      ],
      radius: { total: 150, cats: [{ cd: 'I212', nm: '비알코올', n: 150 }] },
    });
  }
  function hitNames(container: HTMLElement) {
    return [...container.querySelectorAll('.mix__detail li.mix__hit .mix__cat')].map((e) => e.textContent);
  }

  it('★ 카페 칩이면 음식(I2)을 미리 고른 채 열리고 비알코올(I212) 줄만 굵다', async () => {
    responses.detail = { data: cafeDetail(), error: null };
    const { container } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    const select = (await screen.findByLabelText('업종 골라보기')) as HTMLSelectElement;
    expect(select.value).toBe('I2');
    await waitFor(() =>
      expect(rpcCalls.find((c) => c.fn === 'list_industry_detail')?.args).toEqual({ p_pnu: PNU, p_cat: 'I2' }),
    );
    await screen.findByText('음식 60곳');
    expect(hitNames(container)).toEqual(['비알코올', '비알코올']);
    // 양성 대조 — 짝이 아닌 한식 줄은 굵지 않다(그려져는 있다).
    expect([...container.querySelectorAll('.mix__detail li .mix__cat')].map((e) => e.textContent)).toContain('한식');
  });

  it('전체 칩(또는 안 줌)이면 아무것도 미리 고르지 않는다 — 지금 화면 그대로', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} chip="전체" />);
    const select = (await screen.findByLabelText('업종 골라보기')) as HTMLSelectElement;
    expect(select.value).toBe('');
    expect(rpcCalls.some((c) => c.fn === 'list_industry_detail')).toBe(false);
    expect(container.querySelector('.mix__hit')).toBeNull();
  });

  it('★ 칩을 바꾸면 열린 카드의 고른 대분류도 따라 바뀐다(같은 필지 · 다시 그리기)', async () => {
    const { rerender } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    const select = (await screen.findByLabelText('업종 골라보기')) as HTMLSelectElement;
    expect(select.value).toBe('I2');

    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    rerender(<IndustryMixSection pnu={PNU} chip="편의점" />);
    expect((screen.getByLabelText('업종 골라보기') as HTMLSelectElement).value).toBe('G2');
    await waitFor(() =>
      expect(rpcCalls.filter((c) => c.fn === 'list_industry_detail').map((c) => (c.args as { p_cat: string }).p_cat)).toContain('G2'),
    );

    rerender(<IndustryMixSection pnu={PNU} chip="전체" />);
    expect((screen.getByLabelText('업종 골라보기') as HTMLSelectElement).value).toBe('');
  });

  it('카드 안에서 손님이 다른 대분류를 고르면 그 선택이 이긴다', async () => {
    const { rerender } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    const select = (await screen.findByLabelText('업종 골라보기')) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'G2' } });
    expect(select.value).toBe('G2');
    // 칩이 그대로인 채 다시 그려져도(자료 도착 등) 손님 선택이 남는다.
    rerender(<IndustryMixSection pnu={PNU} chip="카페" />);
    expect((screen.getByLabelText('업종 골라보기') as HTMLSelectElement).value).toBe('G2');
  });

  it('★ 편의점 칩일 때만 설명 한 줄 — 카페 칩에는 없다(양성 대조)', async () => {
    const NOTE = '종합 소매에는 편의점과 슈퍼마켓이 함께 들어 있습니다';
    const { rerender } = render(<IndustryMixSection pnu={PNU} chip="편의점" />);
    expect(await screen.findByText(NOTE)).toBeTruthy();
    rerender(<IndustryMixSection pnu={PNU} chip="카페" />);
    await screen.findByLabelText('업종 골라보기');
    expect(screen.queryByText(NOTE)).toBeNull();
  });

  it('그 필지 둘레에 그 대분류가 없으면 지금 "없음" 처리 그대로 — 이름은 코드가 아니라 대분류 이름', async () => {
    // 둘레에 교육(P1)이 아예 없다 → 고르개 목록에도 없다. 상세는 빈 답.
    responses.detail = {
      data: detail({
        cat_l_cd: 'P1',
        districts: [{ district_id: '3120189', name: '강남역', total: 0, cats: [] }],
        radius: { total: 0, cats: [] },
      }),
      error: null,
    };
    render(<IndustryMixSection pnu={PNU} chip="학원" />);
    expect((await screen.findAllByText('이 안에 교육 가게가 없습니다.')).length).toBe(2);
    expect(screen.queryByText(/P1/)).toBeNull();
  });
});

describe('IndustryMixSection — 창업자 업종 칩 (검사 뒤 보완)', () => {
  const PNU = '1168010100100010000';

  it('★ F1 같은 대분류 칩끼리 바꿔도 칩이 이긴다 — 카페 → 손님이 G2 → 한식 = I2 + 한식(I201) 줄 굵게', async () => {
    const { container, rerender } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    const select = (await screen.findByLabelText('업종 골라보기')) as HTMLSelectElement;
    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    fireEvent.change(select, { target: { value: 'G2' } });
    expect(select.value).toBe('G2');

    responses.detail = { data: detail(), error: null };
    rerender(<IndustryMixSection pnu={PNU} chip="한식" />);
    expect((screen.getByLabelText('업종 골라보기') as HTMLSelectElement).value).toBe('I2');
    await screen.findByText('음식 60곳');
    expect(
      [...container.querySelectorAll('.mix__detail li.mix__hit .mix__cat')].map((e) => e.textContent),
    ).toEqual(['한식', '한식']);
  });

  it('★ F3 편의점 칩이어도 손님이 다른 대분류를 고르면 설명 줄이 없다(고르기 전엔 있다 — 양성 대조)', async () => {
    const NOTE = '종합 소매에는 편의점과 슈퍼마켓이 함께 들어 있습니다';
    render(<IndustryMixSection pnu={PNU} chip="편의점" />);
    expect(await screen.findByText(NOTE)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(screen.queryByText(NOTE)).toBeNull();
  });
});

// ── 업종별 층 분포 (물결 2-2 · 결정 0036 결정 18 ⑲~㉑) ─────────────────────────

describe('IndustryMixSection — 업종별 층 분포', () => {
  const PNU = '1168010100100010000';
  // 대분류 답의 bands 합 = 그 블록 총수(상권 '음식 60곳' · 반경 '150곳') — e2e/fixtures.ts 의 industryFloors() 와 같은 숫자.
  const LINE_D = '층별 음식: 지하 0곳 · 1층 36곳 · 2층 9곳 · 3층 이상 3곳 · 층 미상 12곳 (20%)';
  const LINE_R = '층별 음식: 지하 2곳 · 1층 90곳 · 2층 24곳 · 3층 이상 9곳 · 층 미상 25곳 (17%)';
  const CHIP_D = '층별 고른 업종(카페): 지하 0곳 · 1층 15곳 · 2층 3곳 · 3층 이상 0곳 · 층 미상 2곳 (10%)';
  const WHY_TEXT =
    "층 미상 — 원본에 층이 비어 있거나 숫자 없이 '지하'라고만 적힌 가게입니다(지하라고만 적힌 가게는 아직 지하 칸에 세지 못했습니다).";
  // 층 줄 안의 '층 미상 N곳' 과 섞이지 않게 설명 문장에만 있는 말로 찾는다.
  const WHY = /원본에 층이 비어 있거나/;

  function floors(catL: string, catM: string[] | null): IndustryFloors {
    if (catM === null) {
      return {
        snapshot_ym: '202606',
        radius_m: 500,
        cat_l_cd: catL,
        cat_m_cds: null,
        districts: [
          { district_id: '3120189', name: '강남역', total: 60, bands: { b: 0, '1': 36, '2': 9, '3+': 3, na: 12 } },
        ],
        radius: { total: 150, bands: { b: 2, '1': 90, '2': 24, '3+': 9, na: 25 } },
      };
    }
    return {
      snapshot_ym: '202606',
      radius_m: 500,
      cat_l_cd: catL,
      cat_m_cds: catM,
      districts: [{ district_id: '3120189', name: '강남역', total: 20, bands: { b: 0, '1': 15, '2': 3, '3+': 0, na: 2 } }],
      radius: { total: 0, bands: { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 } },
    };
  }

  beforeEach(() => {
    responses.floors = ({ p_cat_l, p_cat_m }) => ({ data: floors(p_cat_l, p_cat_m), error: null });
  });

  it('★ 대분류를 고르면 상권·반경 블록마다 층 줄 한 줄 + 「층 미상」 설명', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    // 고르기 전에는 층 함수를 부르지도 않고 설명 줄도 없다.
    await screen.findByLabelText('업종 골라보기');
    expect(rpcCalls.some((c) => c.fn === 'list_industry_floors')).toBe(false);
    expect(screen.queryByText(WHY)).toBeNull();

    fireEvent.change(screen.getByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText(LINE_D)).toBeTruthy();
    expect(screen.getByText(LINE_R)).toBeTruthy();
    expect(container.querySelectorAll('.mix__detail .mix__block .mix__floors')).toHaveLength(2);
    expect(container.querySelector('.mix__floors--chip')).toBeNull();
    // 👤 2026-10-09 08:1x 문구 그대로(원본 탓으로 돌리거나 '층별 숫자에 없다'고 적지 않는다 — 같은 줄에 '층 미상 N곳' 이 있다).
    expect(container.querySelector('.mix__why li:nth-child(3)')?.textContent).toBe(WHY_TEXT);
    expect(rpcCalls.filter((c) => c.fn === 'list_industry_floors').map((c) => c.args)).toEqual([
      { p_pnu: PNU, p_cat_l: 'I2', p_cat_m: null },
    ]);
  });

  // 물결 2-2c — 👤 2026-10-13 D2' 문구 글자 그대로. basement_unknown_counted === true 일 때만 바뀐다.
  const WHY_NA_NEW = '층 미상 — 원본에 층이 비어 있거나 읽을 수 없는 가게입니다.';
  const WHY_B_NEW = "지하 — 몇 층인지 없이 '지하'라고만 적힌 가게도 지하에 셉니다.";

  it('★ 2-2c 지하 칸에 센 분기(counted true)면 설명이 새 두 항목 — 옛 문구는 없다', async () => {
    responses.floors = ({ p_cat_l, p_cat_m }) => ({
      data: { ...floors(p_cat_l, p_cat_m), basement_unknown_counted: true },
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText(LINE_D)).toBeTruthy();
    const items = [...container.querySelectorAll('.mix__why li')].map((li) => li.textContent);
    expect(items.slice(2)).toEqual([WHY_NA_NEW, WHY_B_NEW]);
    expect(items).not.toContain(WHY_TEXT);
  });

  it.each([
    ['false', false],
    ['문자열(모양 틀림)', 'true'],
    ['숫자(모양 틀림)', 1],
  ])('2-2c counted 가 %s 면 옛 문구 그대로 — 응답은 버리지 않는다(층 줄은 선다)', async (_label, value) => {
    responses.floors = ({ p_cat_l, p_cat_m }) => ({
      data: { ...floors(p_cat_l, p_cat_m), basement_unknown_counted: value },
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText(LINE_D)).toBeTruthy();
    const items = [...container.querySelectorAll('.mix__why li')].map((li) => li.textContent);
    expect(items.slice(2)).toEqual([WHY_TEXT]);
    expect(screen.queryByText(/읽을 수 없는/)).toBeNull();
  });

  it('★ 창업자 카페 칩이면 짝 중분류(I212) 층 줄이 한 줄 더 — total 0 인 범위(반경)엔 칩 줄이 없다', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    expect(await screen.findByText(CHIP_D)).toBeTruthy();
    expect(await screen.findByText(LINE_D)).toBeTruthy();
    expect(container.querySelectorAll('.mix__floors--chip')).toHaveLength(1);
    const asked = rpcCalls.filter((c) => c.fn === 'list_industry_floors').map((c) => c.args);
    expect(asked).toContainEqual({ p_pnu: PNU, p_cat_l: 'I2', p_cat_m: null });
    expect(asked).toContainEqual({ p_pnu: PNU, p_cat_l: 'I2', p_cat_m: ['I212'] });
  });

  it('학원 칩은 짝 코드 여럿을 한 번에 묻는다', async () => {
    render(<IndustryMixSection pnu={PNU} chip="학원" />);
    const chipCalls = () =>
      rpcCalls.filter((c) => c.fn === 'list_industry_floors' && (c.args as { p_cat_m: unknown }).p_cat_m !== null);
    await waitFor(() => expect(chipCalls()).toHaveLength(1));
    expect((chipCalls()[0].args as { p_cat_m: string[] }).p_cat_m.length).toBeGreaterThanOrEqual(2);
  });

  it('★ 층 함수가 실패하면 층 줄·설명만 없고 카드·상세는 그대로(0곳·불러오는 중 금지)', async () => {
    responses.floors = () => ({ data: null, error: { message: 'PGRST202' } });
    render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 60곳')).toBeTruthy();
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_floors')).toBe(true));
    expect(screen.queryByText(/층별 음식/)).toBeNull();
    expect(screen.queryByText(WHY)).toBeNull();
    expect(screen.queryByText(/층.*불러오는 중/)).toBeNull();
  });

  it('모양이 어긋난 답(열쇠 빠짐)도 그 답만 버린다', async () => {
    responses.floors = ({ p_cat_l }) => {
      const bad = floors(p_cat_l, null) as unknown as { radius: { bands: Record<string, number> } };
      delete bad.radius.bands.na;
      return { data: bad, error: null };
    };
    render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 60곳')).toBeTruthy();
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_floors')).toBe(true));
    expect(screen.queryByText(/층별/)).toBeNull();
  });

  it('★ 다른 업종의 층 답이 늦게 오면 버린다', async () => {
    // 'G2' 를 물었는데 'I2' 답이 온 꼴 — 그대로 그리면 '소매' 블록 밑에 음식 층 줄이 선다.
    responses.floors = () => ({ data: floors('I2', null), error: null });
    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'G2' } });
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_floors')).toBe(true));
    await screen.findByText('소매 60곳');
    expect(screen.queryByText(/층별/)).toBeNull();
    expect(screen.queryByText(WHY)).toBeNull();
  });

  it('칩 짝이 다른 답(중분류 다름)도 버린다', async () => {
    responses.floors = ({ p_cat_l, p_cat_m }) => ({
      data: floors(p_cat_l, p_cat_m === null ? null : ['I201']),
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    expect(await screen.findByText(LINE_D)).toBeTruthy();
    expect(container.querySelector('.mix__floors--chip')).toBeNull();
  });

  it('층 답이 아직 안 왔으면 줄도 설명도 없다', async () => {
    responses.floorsPending = true;
    render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 60곳')).toBeTruthy();
    expect(screen.queryByText(/층별/)).toBeNull();
    expect(screen.queryByText(WHY)).toBeNull();
  });

  it('업종 고르기를 풀면 층 줄·설명이 사라진다', async () => {
    render(<IndustryMixSection pnu={PNU} />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });
    expect(await screen.findByText(LINE_D)).toBeTruthy();
    fireEvent.change(select, { target: { value: '' } });
    await waitFor(() => expect(screen.queryByText(LINE_D)).toBeNull());
    expect(screen.queryByText(WHY)).toBeNull();
  });

  it('★ 카페 칩을 고른 채 손님이 다른 대분류(G2)를 고르면 칩 줄이 없고 칩 짝(p_cat_m)을 묻지도 않는다', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    // 양성 대조 — 칩의 대분류(I2)에서는 칩 줄이 선다.
    expect(await screen.findByText(CHIP_D)).toBeTruthy();

    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    rpcCalls.length = 0;
    fireEvent.change(screen.getByLabelText('업종 골라보기'), { target: { value: 'G2' } });
    // 대분류 줄은 소매 이름표로 선다(고른 업종을 따라간다).
    expect(
      await screen.findByText('층별 소매: 지하 0곳 · 1층 36곳 · 2층 9곳 · 3층 이상 3곳 · 층 미상 12곳 (20%)'),
    ).toBeTruthy();
    expect(container.querySelector('.mix__floors--chip')).toBeNull();
    expect(screen.queryByText(/고른 업종\(카페\)/)).toBeNull();
    const asked = rpcCalls.filter((c) => c.fn === 'list_industry_floors').map((c) => c.args);
    expect(asked).toEqual([{ p_pnu: PNU, p_cat_l: 'G2', p_cat_m: null }]);
  });

  it('★ 대분류를 바꾼 첫 렌더에도 옛 업종의 층 숫자가 새 이름표로 그려지지 않는다(그릴 때 견줌)', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });
    expect(await screen.findByText(LINE_D)).toBeTruthy();

    // 새 답은 영영 안 온다 — 이 사이에 한 번이라도 '층별 소매' 줄이 붙었다 떨어지면 그게 깜빡임이다.
    // 최종 화면만 보면 effect 가 이미 지운 뒤라 못 본다 → DOM 에 붙은 모든 마디를 기록으로 본다.
    responses.floorsPending = true;
    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    // React 는 같은 자리의 글자를 마디 교체가 아니라 글자 바꾸기로 고칠 수 있다 — 붙은 마디·떨어진 마디
    // (떨어진 마디는 마지막 글자를 쥐고 있다)·바뀐 글자 마디를 모두 본다.
    const seen: string[] = [];
    const keep = (recs: MutationRecord[]) => {
      for (const r of recs) {
        r.addedNodes.forEach((n) => seen.push(n.textContent ?? ''));
        r.removedNodes.forEach((n) => seen.push(n.textContent ?? ''));
        if (r.type === 'characterData') seen.push(r.target.textContent ?? '');
      }
    };
    const obs = new MutationObserver(keep);
    obs.observe(container, { childList: true, subtree: true, characterData: true });
    fireEvent.change(select, { target: { value: 'G2' } });
    await screen.findByText('소매 60곳');
    keep(obs.takeRecords());
    obs.disconnect();
    expect(seen.some((t) => t.includes('층별 소매'))).toBe(false);
    expect(container.querySelector('.mix__floors')).toBeNull();
  });

  it('★ 모든 범위가 0곳이면 층 줄이 하나도 없고 「층 미상」 설명도 없다(답은 왔다)', async () => {
    const zero = { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 };
    responses.floors = ({ p_cat_l, p_cat_m }) => ({
      data: {
        ...floors(p_cat_l, p_cat_m),
        districts: [{ district_id: '3120189', name: '강남역', total: 0, bands: zero }],
        radius: { total: 0, bands: zero },
      },
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 60곳')).toBeTruthy();
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_floors')).toBe(true));
    // 답이 상태에 들어갈 때까지 한 박자 기다린다 — 안 기다리면 '아직 안 옴'과 같은 화면이라 이 시험이 아무것도 안 본다.
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.querySelectorAll('.mix__floors')).toHaveLength(0);
    expect(container.querySelectorAll('.mix__why li')).toHaveLength(2);
    expect(screen.queryByText(WHY)).toBeNull();
  });
});

// ── 업종 비중 비교 (물결 2-3 · 결정 0036 결정 18 ㉓~㉖) ─────────────────────────

/** 서버가 내는 가운데값 응답 — 기본은 '강남역(발달상권)' 하나 · 같은 종류 249곳. */
function median(over: Partial<IndustryMedian> = {}): IndustryMedian {
  return {
    snapshot_ym: '202606',
    min_total: 30,
    min_pop: 30,
    districts: [
      {
        district_id: '3120189',
        type: '발달상권',
        total: 100,
        pop: { scope: 'type', sido_cd: '11', district_type: '발달상권', n: 249 },
        cats: [
          { cd: 'I2', nm: '음식', med_pct: 26.5 },
          { cd: 'G2', nm: '소매', med_pct: 16 },
        ],
      },
    ],
    ...over,
  };
}

const NOTE_GANGNAM =
  '가운데값은 서울 발달상권 249곳(점포 30곳 이상 상권)의 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.';

/** 블록마다 비교 글 — [블록 제목, 그 블록의 .mix__med 글들, 설명 줄 글들]. */
function medTexts(container: HTMLElement) {
  return [...container.querySelectorAll('.mix__block')].map((b) => [
    b.querySelector('.mix__sub')?.textContent ?? '',
    [...b.querySelectorAll('.mix__med')].map((e) => e.textContent),
    [...b.querySelectorAll('.mix__med-note')].map((e) => e.textContent),
  ]);
}

describe('IndustryMixSection — 업종 비중 비교 (물결 2-3)', () => {
  const PNU = '1168010100100010000';

  it('상권 블록 줄마다 비교 글 + 배지 C 설명 줄 · 반경 블록엔 없다 · 인자는 p_pnu 하나', async () => {
    responses.median = () => ({ data: median(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    expect(await screen.findByText('서울 발달상권 가운데 26.5%')).toBeTruthy();
    expect(screen.getByText('서울 발달상권 가운데 16.0%')).toBeTruthy();
    expect(medTexts(container)).toEqual([
      ['강남역(발달상권) 안 100곳', ['서울 발달상권 가운데 26.5%', '서울 발달상권 가운데 16.0%'], [`C등급 · 비교값${NOTE_GANGNAM}`]],
      ['반경 500m 안 200곳', [], []],
    ]);
    const badge = container.querySelector('.mix__med-note .grade__badge');
    expect(badge?.textContent).toBe('C등급 · 비교값');
    expect(badge?.classList.contains('grade__badge--est')).toBe(true);
    // 비교 글은 그 막대 줄(li) 안 — 종이에서 줄과 갈리지 않는다.
    expect(screen.getByText('서울 발달상권 가운데 26.5%').closest('li')?.querySelector('.mix__cat')?.textContent).toBe('음식');
    expect(rpcCalls.find((c) => c.fn === 'list_industry_median')!.args).toEqual({ p_pnu: PNU });
  });

  it('가운데값 줄이 없는 업종은 그 줄만 비교 글이 없다', async () => {
    const m = median();
    m.districts[0].cats = [{ cd: 'I2', nm: '음식', med_pct: 26.5 }];
    responses.median = () => ({ data: m, error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    expect(await screen.findByText('서울 발달상권 가운데 26.5%')).toBeTruthy();
    const rows = [...container.querySelectorAll('.mix__block')][0].querySelectorAll('.mix__bars li');
    expect([...rows].map((li) => li.querySelector('.mix__med')?.textContent ?? null)).toEqual([
      '서울 발달상권 가운데 26.5%',
      null,
    ]);
  });

  it('종류가 30곳 미만이면 「서울 상권 전체」 · 대전은 「대전 주요상권」(곳 수 병기)', async () => {
    responses.mix = {
      data: mix({
        districts: [
          { ...mix().districts[0], district_id: 'T', name: '명동', type: '관광특구' },
          { ...mix().districts[0], district_id: 'DJ', name: '대전역', type: '주요상권', source_nm: '소상공인시장진흥공단' },
        ],
      }),
      error: null,
    };
    responses.median = () => ({
      data: median({
        districts: [
          { district_id: 'T', type: '관광특구', total: 100,
            pop: { scope: 'all', sido_cd: '11', district_type: null, n: 1502 },
            cats: [{ cd: 'I2', nm: '음식', med_pct: 25.9 }] },
          { district_id: 'DJ', type: '주요상권', total: 100,
            pop: { scope: 'type', sido_cd: '30', district_type: '주요상권', n: 37 },
            cats: [{ cd: 'I2', nm: '음식', med_pct: 36.2 }] },
        ],
      }),
      error: null,
    });
    render(<IndustryMixSection pnu={PNU} />);
    expect(await screen.findByText('서울 상권 전체 가운데 25.9%')).toBeTruthy();
    expect(screen.getByText('대전 주요상권 가운데 36.2%')).toBeTruthy();
    expect(screen.getByText(/가운데값은 서울 상권 전체 1,502곳\(점포 30곳 이상 상권\)/)).toBeTruthy();
    expect(screen.getByText(/가운데값은 대전 주요상권 37곳\(점포 30곳 이상 상권\)/)).toBeTruthy();
  });

  it('점포가 기준 미만인 상권은 사실 한 줄만 — 기준은 서버 값(min_total)', async () => {
    responses.mix = {
      data: mix({ districts: [{ ...mix().districts[0], total: 12, cats: [{ cd: 'I2', nm: '음식', n: 12 }] }] }),
      error: null,
    };
    responses.median = () => ({
      data: median({ min_total: 40, districts: [{ district_id: '3120189', type: '발달상권', total: 12, pop: null, cats: [] }] }),
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    expect(await screen.findByText('점포 12곳 — 40곳이 안 돼 비교값은 적지 않습니다.')).toBeTruthy();
    expect(container.querySelectorAll('.mix__med')).toHaveLength(0);
    expect(container.querySelector('.grade__badge--est')).toBeNull();
  });

  it.each([
    ['함수 없음(PGRST202)', () => ({ data: null, error: { message: 'PGRST202' } })],
    ['모양 이상(med_pct 글자)', () => ({
      data: median({ districts: [{ ...median().districts[0], cats: [{ cd: 'I2', nm: '음식', med_pct: '26.5' as never }] }] }),
      error: null,
    })],
    ['분기 다름', () => ({ data: median({ snapshot_ym: '202603' }), error: null })],
  ])('★ %s → 비교 글·설명 줄 0 · 카드·막대·총수는 지금 그대로', async (_name, answer) => {
    // 기준 화면(비교 글 없는 지금 화면)의 글자를 먼저 잰다.
    const base = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText(/강남역\(발달상권\) 안/);
    await act(() => new Promise((r) => setTimeout(r, 0)));
    const before = base.container.textContent;
    base.unmount();

    responses.median = answer as typeof responses.median;
    const warn = vi.mocked(console.warn);
    warn.mockClear();
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText(/강남역\(발달상권\) 안/);
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_median')).toBe(true));
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.querySelectorAll('.mix__med, .mix__med-note')).toHaveLength(0);
    expect(container.textContent).toBe(before);
    expect(container.textContent).not.toContain('불러오는 중');
    if (_name !== '분기 다름') {
      expect(warn.mock.calls.some((c) => String(c[0]).includes('업종 비중 비교 조회 실패'))).toBe(true);
    }
  });

  it('★ 필지가 바뀐 뒤 늦게 온 앞 필지의 답은 버린다', async () => {
    const A = PNU;
    const B = '1111010100100010000';
    let resolveA!: (r: unknown) => void;
    const lateA = new Promise((r) => {
      resolveA = r;
    });
    responses.median = (pnu) =>
      pnu === A
        ? (lateA as Promise<unknown>)
        : {
            data: median({ districts: [{ ...median().districts[0], cats: [{ cd: 'I2', nm: '음식', med_pct: 22.2 }] }] }),
            error: null,
          };
    const { container, rerender } = render(<IndustryMixSection pnu={A} />);
    await screen.findByText(/강남역/);
    rerender(<IndustryMixSection pnu={B} />);
    expect(await screen.findByText('서울 발달상권 가운데 22.2%')).toBeTruthy();
    await act(async () => {
      resolveA({
        data: median({ districts: [{ ...median().districts[0], cats: [{ cd: 'I2', nm: '음식', med_pct: 99.9 }] }] }),
        error: null,
      });
    });
    expect(container.textContent).not.toContain('99.9%');
    expect(container.textContent).toContain('서울 발달상권 가운데 22.2%');
  });

  it('비교 글에 판단 낱말·금칙어가 없다 · 접힌 요약에는 값을 안 넣는다', async () => {
    responses.median = () => ({ data: median(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText('서울 발달상권 가운데 26.5%');
    const texts = [...container.querySelectorAll('.mix__med, .mix__med-note')].map((e) => e.textContent).join(' ');
    for (const w of ['많', '적다', '적습', '높', '낮', '%p', '배', '적정가', '감정가', '평가액']) {
      expect(texts).not.toContain(w);
    }
    const summary = container.querySelector('.card__summary');
    expect(summary).not.toBeNull();
    expect(summary!.textContent).not.toContain('가운데');
  });

  it('카드 아래 A등급 문장은 막대와 곳 수로 범위를 좁힌다(👤 10-12) — 배지는 그대로', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText(/강남역\(발달상권\) 안/);
    const grade = container.querySelector('.grade')!;
    expect(grade.querySelector('.grade__badge')?.textContent).toBe('A등급 · 실측 집계');
    expect(grade.textContent).toBe(
      'A등급 · 실측 집계막대와 곳 수는 어림한 값이 아니라 등록된 점포를 그대로 센 값입니다(가운데값은 C등급 · 비교값). 다만 아래 까닭으로 실제와 다를 수 있습니다.',
    );
  });
});

// ── 업종 비중 비교 · 중분류 (물결 2-3b · 결정 0036 결정 18 ㉗~㉚) ─────────────────────

/** 서버가 내는 중분류 가운데값 응답 — 기본은 '강남역(발달상권)' 음식 60곳 · 같은 종류 음식 30곳 이상 241곳. */
function medianM(over: Partial<IndustryMedianM> = {}): IndustryMedianM {
  return {
    snapshot_ym: '202606',
    cat_l_cd: 'I2',
    min_total: 30,
    min_pop: 30,
    districts: [
      {
        district_id: '3120189',
        type: '발달상권',
        total: 60,
        pop: { scope: 'type', sido_cd: '11', district_type: '발달상권', n: 241 },
        cats: [
          { cd: 'I201', nm: '한식', med_pct: 37.3 },
          { cd: 'I202', nm: '중식', med_pct: 3.8 },
        ],
      },
    ],
    ...over,
  };
}

const NOTE_M =
  '가운데값은 서울 발달상권 가운데 음식 가게가 30곳 이상인 241곳의 음식 안 업종 비중을 크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.';

/** 상세 블록마다 — [블록 제목, 그 블록의 .mix__med 글들, 설명 줄 글들]. */
function detailMedTexts(container: HTMLElement) {
  return [...container.querySelectorAll('.mix__detail .mix__block')].map((b) => [
    b.querySelector('.mix__sub')?.textContent ?? '',
    [...b.querySelectorAll('.mix__med')].map((e) => e.textContent),
    [...b.querySelectorAll('.mix__med-note')].map((e) => e.textContent),
  ]);
}

describe('IndustryMixSection — 업종 비중 비교 · 중분류 (물결 2-3b)', () => {
  const PNU = '1168010100100010000';

  it('★ 대분류를 고르면 상세 상권 블록 중분류 줄마다 비교 글 + 배지 C 설명 줄 · 반경 블록엔 없다 · 인자 {p_pnu, p_cat_l}', async () => {
    responses.medianM = () => ({ data: medianM(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    // 고르기 전에는 부르지도 않는다(따로 부름 — 대분류를 골라야 인자가 정해진다).
    await screen.findByLabelText('업종 골라보기');
    expect(rpcCalls.some((c) => c.fn === 'list_industry_median_m')).toBe(false);

    fireEvent.change(screen.getByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('서울 발달상권 가운데 37.3%')).toBeTruthy();
    expect(detailMedTexts(container)).toEqual([
      ['강남역(발달상권) 안 음식 60곳', ['서울 발달상권 가운데 37.3%', '서울 발달상권 가운데 3.8%'], [`C등급 · 비교값${NOTE_M}`]],
      ['반경 500m 안 음식 150곳', [], []],
    ]);
    const badge = container.querySelector('.mix__detail .mix__med-note .grade__badge');
    expect(badge?.textContent).toBe('C등급 · 비교값');
    expect(badge?.classList.contains('grade__badge--est')).toBe(true);
    // 비교 글은 그 중분류 막대 줄(li) 안 — 종이에서 줄과 갈리지 않는다.
    expect(screen.getByText('서울 발달상권 가운데 37.3%').closest('li')?.querySelector('.mix__cat')?.textContent).toBe('한식');
    expect(rpcCalls.filter((c) => c.fn === 'list_industry_median_m').map((c) => c.args)).toEqual([
      { p_pnu: PNU, p_cat_l: 'I2' },
    ]);
  });

  it('그 대분류 가게가 기준 미만인 상권은 사실 한 줄만 — 기준은 서버 값(min_total)', async () => {
    responses.detail = {
      data: detail({ districts: [{ district_id: '3120189', name: '강남역', total: 12, cats: [{ cd: 'I201', nm: '한식', n: 12 }] }] }),
      error: null,
    };
    responses.medianM = () => ({
      data: medianM({ min_total: 40, districts: [{ district_id: '3120189', type: '발달상권', total: 12, pop: null, cats: [] }] }),
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 12곳 — 40곳이 안 돼 비교값은 적지 않습니다.')).toBeTruthy();
    expect(container.querySelectorAll('.mix__detail .mix__med')).toHaveLength(0);
    expect(container.querySelector('.mix__detail .grade__badge--est')).toBeNull();
  });

  it('가운데값 줄이 없는 중분류는 그 줄만 비교 글이 없다', async () => {
    const m = medianM();
    m.districts[0].cats = [{ cd: 'I201', nm: '한식', med_pct: 37.3 }];
    responses.medianM = () => ({ data: m, error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('서울 발달상권 가운데 37.3%')).toBeTruthy();
    const rows = container.querySelectorAll('.mix__detail .mix__block')[0].querySelectorAll('.mix__bars li');
    expect([...rows].map((li) => li.querySelector('.mix__med')?.textContent ?? null)).toEqual([
      '서울 발달상권 가운데 37.3%',
      null,
    ]);
  });

  it.each([
    ['함수 없음(PGRST202)', () => ({ data: null, error: { message: 'PGRST202' } }), true],
    ['모양 이상(cat_l_cd 없음)', () => ({ data: { ...medianM(), cat_l_cd: undefined }, error: null }), true],
    ['분기가 상세와 다름', () => ({ data: medianM({ snapshot_ym: '202603' }), error: null }), false],
    ['물어본 것과 다른 대분류의 답', () => ({ data: medianM({ cat_l_cd: 'G2' }), error: null }), false],
  ])('★ %s → 중분류 비교 글·설명 줄 0 · 상세 블록·막대·총수는 지금 그대로', async (_name, answer, warns) => {
    // 기준 화면(비교 글 없는 지금 상세)의 글자를 먼저 잰다.
    const base = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    await screen.findByText('음식 60곳');
    await act(() => new Promise((r) => setTimeout(r, 0)));
    const before = base.container.textContent;
    base.unmount();

    responses.medianM = answer as typeof responses.medianM;
    const warn = vi.mocked(console.warn);
    warn.mockClear();
    rpcCalls.length = 0;
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    await screen.findByText('음식 60곳');
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_median_m')).toBe(true));
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.querySelectorAll('.mix__med, .mix__med-note')).toHaveLength(0);
    expect(container.textContent).toBe(before);
    expect(container.textContent).not.toContain('불러오는 중');
    expect(warn.mock.calls.some((c) => String(c[0]).includes('업종 중분류 비중 비교 조회 실패'))).toBe(warns);
  });

  it('★ 중분류 비교만 실패해도 층 줄·「층 미상」 설명은 그대로 선다(층 함수는 답했다)', async () => {
    // 층 함수는 답하고(대분류 줄만 — 상권·반경 블록 각각), 중분류 비교만 함수 없음(PGRST202).
    responses.floors = ({ p_cat_l }) => ({
      data: {
        snapshot_ym: '202606',
        radius_m: 500,
        cat_l_cd: p_cat_l,
        cat_m_cds: null,
        districts: [
          { district_id: '3120189', name: '강남역', total: 60, bands: { b: 0, '1': 36, '2': 9, '3+': 3, na: 12 } },
        ],
        radius: { total: 150, bands: { b: 2, '1': 90, '2': 24, '3+': 9, na: 25 } },
      },
      error: null,
    });
    // 실패는 층 답보다 **늦게** 온다 — 먼저 오면 지워 봐야 지울 층 줄이 아직 없어 아무것도 못 본다.
    responses.medianM = () =>
      new Promise((r) => setTimeout(() => r({ data: null, error: { message: 'PGRST202' } }), 30)) as Promise<unknown>;
    const warn = vi.mocked(console.warn);
    warn.mockClear();
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(
      await screen.findByText('층별 음식: 지하 0곳 · 1층 36곳 · 2층 9곳 · 3층 이상 3곳 · 층 미상 12곳 (20%)'),
    ).toBeTruthy();
    // 늦은 실패가 실제로 도착한 뒤에 본다.
    await waitFor(() =>
      expect(warn.mock.calls.some((c) => String(c[0]).includes('업종 중분류 비중 비교 조회 실패'))).toBe(true),
    );
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.querySelectorAll('.mix__detail .mix__floors')).toHaveLength(2);
    expect(container.querySelectorAll('.mix__why li')).toHaveLength(3);
    expect(container.querySelectorAll('.mix__med, .mix__med-note')).toHaveLength(0);
  });

  it('★ 다른 대분류로 바꾼 뒤 늦게 온 앞 대분류의 답은 버린다', async () => {
    let resolveI2!: (r: unknown) => void;
    const lateI2 = new Promise((r) => {
      resolveI2 = r;
    });
    responses.medianM = ({ p_cat_l }) =>
      p_cat_l === 'I2' ? (lateI2 as Promise<unknown>) : { data: null, error: { message: 'PGRST202' } };
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_median_m')).toBe(true));
    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    fireEvent.change(select, { target: { value: 'G2' } });
    await screen.findByText('소매 60곳');
    await act(async () => {
      resolveI2({ data: medianM(), error: null });
    });
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.textContent).not.toContain('37.3%');
    expect(container.querySelectorAll('.mix__detail .mix__med, .mix__detail .mix__med-note')).toHaveLength(0);
  });

  it('★ 필지가 바뀐 뒤 늦게 온 앞 필지의 답은 버린다', async () => {
    const B = '1111010100100010000';
    let resolveA!: (r: unknown) => void;
    const lateA = new Promise((r) => {
      resolveA = r;
    });
    responses.medianM = ({ p_pnu }) =>
      p_pnu === PNU
        ? (lateA as Promise<unknown>)
        : {
            data: medianM({ districts: [{ ...medianM().districts[0], cats: [{ cd: 'I201', nm: '한식', med_pct: 22.2 }] }] }),
            error: null,
          };
    const { container, rerender } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_median_m')).toBe(true));
    rerender(<IndustryMixSection pnu={B} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('서울 발달상권 가운데 22.2%')).toBeTruthy();
    await act(async () => {
      resolveA({ data: medianM(), error: null });
    });
    expect(container.textContent).not.toContain('37.3%');
    expect(container.textContent).toContain('서울 발달상권 가운데 22.2%');
  });

  it('★ 대분류를 바꾼 첫 렌더에도 옛 대분류의 비교 글이 새 블록에 그려지지 않는다(그릴 때 견줌)', async () => {
    responses.medianM = ({ p_cat_l }) =>
      p_cat_l === 'I2' ? { data: medianM(), error: null } : (new Promise(() => {}) as Promise<unknown>);
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    const select = await screen.findByLabelText('업종 골라보기');
    fireEvent.change(select, { target: { value: 'I2' } });
    expect(await screen.findByText('서울 발달상권 가운데 37.3%')).toBeTruthy();

    // 소매 상세도 같은 중분류 코드(I201)를 갖는다 — 그릴 때 견주지 않으면 옛 음식 가운데값이 소매 블록 줄에 붙는다.
    responses.detail = { data: detail({ cat_l_cd: 'G2' }), error: null };
    const seen: string[] = [];
    const keep = (recs: MutationRecord[]) => {
      for (const r of recs) {
        r.addedNodes.forEach((n) => seen.push(n.textContent ?? ''));
        r.removedNodes.forEach((n) => seen.push(n.textContent ?? ''));
        if (r.type === 'characterData') seen.push(r.target.textContent ?? '');
      }
    };
    const obs = new MutationObserver(keep);
    obs.observe(container, { childList: true, subtree: true, characterData: true });
    fireEvent.change(select, { target: { value: 'G2' } });
    await screen.findByText('소매 60곳');
    keep(obs.takeRecords());
    obs.disconnect();
    // 떨어져 나간 옛 마디(음식 상세)는 옛 글을 쥐고 있다 — '소매' 블록과 함께 붙은 마디만 본다.
    expect(seen.some((t) => t.includes('소매 60곳') && t.includes('37.3%'))).toBe(false);
    expect(seen.some((t) => t.includes('소매 가게가 30곳 이상인'))).toBe(false);
    expect(container.querySelectorAll('.mix__detail .mix__med, .mix__detail .mix__med-note')).toHaveLength(0);
  });

  it('창업자 카페 칩 — 짝 중분류(I212) 줄이 굵은 채로 비교 글도 같은 줄 안에', async () => {
    responses.detail = {
      data: detail({
        districts: [
          {
            district_id: '3120189',
            name: '강남역',
            total: 60,
            cats: [
              { cd: 'I201', nm: '한식', n: 40 },
              { cd: 'I212', nm: '비알코올', n: 20 },
            ],
          },
        ],
      }),
      error: null,
    };
    responses.medianM = () => ({
      data: medianM({ districts: [{ ...medianM().districts[0], cats: [{ cd: 'I212', nm: '비알코올', med_pct: 16 }] }] }),
      error: null,
    });
    render(<IndustryMixSection pnu={PNU} chip="카페" />);
    const line = await screen.findByText('서울 발달상권 가운데 16.0%');
    const li = line.closest('li')!;
    expect(li.classList.contains('mix__hit')).toBe(true);
    expect(li.querySelector('.mix__cat strong')?.textContent).toBe('비알코올');
  });

  it('비교 글에 판단 낱말·금칙어가 없다 · 접힌 요약에는 값을 안 넣는다', async () => {
    responses.medianM = () => ({ data: medianM(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    await screen.findByText('서울 발달상권 가운데 37.3%');
    const texts = [...container.querySelectorAll('.mix__detail .mix__med, .mix__detail .mix__med-note')]
      .map((e) => e.textContent)
      .join(' ');
    expect(texts).toContain('가운데값은');
    for (const w of ['많', '적다', '적습', '높', '낮', '%p', '배', '적정가', '감정가', '평가액']) {
      expect(texts).not.toContain(w);
    }
    expect(container.querySelector('.card__summary')!.textContent).not.toContain('가운데');
  });
});

// ── 그림 (결정 0038 E — ▲ 가운데값 눈금 · 층 묶음 쌓은 막대) ─────────────────────────
// 그림이 깨져도 글자 시험은 초록이다(§2-10) — 자리(left %)·폭(width %)·칸 수·차례·낭독기 숨김을 숫자로 본다.

/** 블록마다 — [블록 제목, 줄마다 ▲ 의 left(없으면 null)]. */
function markLefts(container: HTMLElement, sel = '.mix__block') {
  return [...container.querySelectorAll(sel)].map((b) => [
    b.querySelector('.mix__sub')?.textContent ?? '',
    [...b.querySelectorAll('.mix__bars li')].map(
      (li) => (li.querySelector('.mix__mark') as HTMLElement | null)?.style.left ?? null,
    ),
  ]);
}

describe('IndustryMixSection — 그림 ▲ 가운데값 눈금 (결정 0038 E)', () => {
  const PNU = '1168010100100010000';

  it('★ 비교 글이 있는 상권 막대 줄마다 ▲ — left = med_pct% · 반경 블록엔 없다 · 비교 글 줄은 그대로', async () => {
    responses.median = () => ({ data: median(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText('서울 발달상권 가운데 26.5%');
    expect(markLefts(container)).toEqual([
      ['강남역(발달상권) 안 100곳', ['26.5%', '16%']],
      ['반경 500m 안 200곳', [null, null]],
    ]);
    const mark = container.querySelector('.mix__mark') as HTMLElement;
    // 막대 칸 안(같은 0~100 자) · 추정 색 토큰 · 낭독기에서 뺀다(옆 글과 같은 내용).
    expect(mark.parentElement?.classList.contains('mix__bar')).toBe(true);
    expect(mark.style.borderBottomColor).toBe('var(--est-ink)');
    expect(mark.getAttribute('aria-hidden')).toBe('true');
    expect(mark.textContent).toBe('');
    // 글 줄(비교 글)은 한 글자도 안 바뀐다.
    expect(medTexts(container)[0][1]).toEqual(['서울 발달상권 가운데 26.5%', '서울 발달상권 가운데 16.0%']);
  });

  it('▲ 는 막대 폭(bar.pct)이 아니라 가운데값 자리에 선다(같은 줄의 채움 막대와 다른 값)', async () => {
    responses.median = () => ({ data: median(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText('서울 발달상권 가운데 26.5%');
    const li = container.querySelector('.mix__block .mix__bars li')!;
    expect((li.querySelector('.mix__fill') as HTMLElement).style.width).toBe('60%');
    expect((li.querySelector('.mix__mark') as HTMLElement).style.left).toBe('26.5%');
  });

  it('가운데값 줄이 없는 업종 · 비교 함수 없음 · 점포 기준 미만 상권이면 그 줄에 ▲ 없음', async () => {
    const m = median();
    m.districts[0].cats = [{ cd: 'I2', nm: '음식', med_pct: 26.5 }];
    responses.median = () => ({ data: m, error: null });
    const { container, unmount } = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText('서울 발달상권 가운데 26.5%');
    expect(markLefts(container)[0]).toEqual(['강남역(발달상권) 안 100곳', ['26.5%', null]]);
    unmount();

    responses.median = () => ({ data: null, error: { message: 'PGRST202' } });
    const second = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText('반경 500m 안');
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(second.container.querySelectorAll('.mix__mark')).toHaveLength(0);
    second.unmount();

    responses.median = () => ({
      data: median({ districts: [{ district_id: '3120189', type: '발달상권', total: 12, pop: null, cats: [] }] }),
      error: null,
    });
    responses.mix = {
      data: mix({
        districts: [{ ...mix().districts[0], total: 12, cats: [{ cd: 'I2', nm: '음식', n: 12 }] }],
      }),
      error: null,
    };
    const third = render(<IndustryMixSection pnu={PNU} />);
    await screen.findByText('점포 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.');
    expect(third.container.querySelectorAll('.mix__mark')).toHaveLength(0);
  });

  it('★ 상세 상권 블록(중분류)에도 비교 글이 있으면 ▲ · 반경 블록엔 없다', async () => {
    responses.medianM = () => ({ data: medianM(), error: null });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    await screen.findByText('서울 발달상권 가운데 37.3%');
    expect(markLefts(container, '.mix__detail .mix__block')).toEqual([
      ['강남역(발달상권) 안 음식 60곳', ['37.3%', '3.8%']],
      ['반경 500m 안 음식 150곳', [null]],
    ]);
  });
});

describe('IndustryMixSection — 그림 층 묶음 쌓은 막대 (결정 0038 E)', () => {
  const PNU = '1168010100100010000';
  const LINE_D = '층별 음식: 지하 0곳 · 1층 36곳 · 2층 9곳 · 3층 이상 3곳 · 층 미상 12곳 (20%)';
  const CHIP_D = '층별 고른 업종(카페): 지하 0곳 · 1층 15곳 · 2층 3곳 · 3층 이상 0곳 · 층 미상 2곳 (10%)';

  function floors(catL: string, catM: string[] | null): IndustryFloors {
    if (catM === null) {
      return {
        snapshot_ym: '202606',
        radius_m: 500,
        cat_l_cd: catL,
        cat_m_cds: null,
        districts: [
          { district_id: '3120189', name: '강남역', total: 60, bands: { b: 0, '1': 36, '2': 9, '3+': 3, na: 12 } },
        ],
        radius: { total: 150, bands: { b: 2, '1': 90, '2': 24, '3+': 9, na: 25 } },
      };
    }
    return {
      snapshot_ym: '202606',
      radius_m: 500,
      cat_l_cd: catL,
      cat_m_cds: catM,
      districts: [{ district_id: '3120189', name: '강남역', total: 20, bands: { b: 0, '1': 15, '2': 3, '3+': 0, na: 2 } }],
      radius: { total: 0, bands: { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 } },
    };
  }

  /** 층 줄 글 바로 앞 형제 막대의 칸 — [묶음 열쇠, width, background]. 막대가 없으면 null. */
  function stackBefore(p: Element) {
    const bar = p.previousElementSibling as HTMLElement | null;
    if (!bar || !bar.classList.contains('mix__stack')) return null;
    return [...bar.querySelectorAll<HTMLElement>('.mix__stack-cell')].map((c) => [
      c.dataset.band,
      c.style.width,
      c.style.backgroundColor,
    ]);
  }

  beforeEach(() => {
    responses.floors = ({ p_cat_l, p_cat_m }) => ({ data: floors(p_cat_l, p_cat_m), error: null });
  });

  it('★ 층 줄 글 바로 위에 막대 한 줄 — 차례 고정 · 0곳 묶음 칸 없음 · 폭 = 곳 수 ÷ 합 · 호박 진하기 + 층 미상 회색', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    const line = await screen.findByText(LINE_D);
    expect(stackBefore(line)).toEqual([
      ['1', '60%', 'var(--fact-2)'],
      ['2', '15%', 'var(--fact-3)'],
      ['3+', '5%', 'var(--fact-4)'],
      ['na', '20%', 'var(--viz-na)'],
    ]);
    const radius = [...container.querySelectorAll('.mix__floors')][1];
    const cells = stackBefore(radius)!;
    expect(cells.map((c) => c[0])).toEqual(['b', '1', '2', '3+', 'na']);
    expect(cells[0][2]).toBe('var(--fact-1)');
    // 막대 수 = 층 줄 수 · 낭독기에서 뺀다 · 칸 안 글자 0(비율을 글자로 새로 내지 않는다).
    const bars = container.querySelectorAll('.mix__stack');
    expect(bars).toHaveLength(container.querySelectorAll('.mix__floors').length);
    for (const b of bars) {
      expect(b.getAttribute('aria-hidden')).toBe('true');
      expect(b.textContent).toBe('');
    }
    // 글 줄은 그대로.
    expect(line.textContent).toBe(LINE_D);
  });

  it('★ 창업자 카페 칩 줄 위에도 막대 — total 0 인 반경엔 칩 줄도 막대도 없다', async () => {
    const { container } = render(<IndustryMixSection pnu={PNU} chip="카페" />);
    const chip = await screen.findByText(CHIP_D);
    await screen.findByText(LINE_D);
    expect(stackBefore(chip)).toEqual([
      ['1', '75%', 'var(--fact-2)'],
      ['2', '15%', 'var(--fact-3)'],
      ['na', '10%', 'var(--viz-na)'],
    ]);
    expect(container.querySelectorAll('.mix__stack')).toHaveLength(3); // 대분류 둘 + 칩 하나
  });

  it('층 함수가 실패하면 층 줄도 막대도 없다(0 으로 그리지 않는다)', async () => {
    responses.floors = () => ({ data: null, error: { message: 'PGRST202' } });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 60곳')).toBeTruthy();
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.querySelectorAll('.mix__stack')).toHaveLength(0);
    expect(container.querySelectorAll('.mix__floors')).toHaveLength(0);
  });

  it('모든 범위가 0곳이면 막대도 없다', async () => {
    const zero = { b: 0, '1': 0, '2': 0, '3+': 0, na: 0 };
    responses.floors = ({ p_cat_l, p_cat_m }) => ({
      data: {
        ...floors(p_cat_l, p_cat_m),
        districts: [{ district_id: '3120189', name: '강남역', total: 0, bands: zero }],
        radius: { total: 0, bands: zero },
      },
      error: null,
    });
    const { container } = render(<IndustryMixSection pnu={PNU} />);
    fireEvent.change(await screen.findByLabelText('업종 골라보기'), { target: { value: 'I2' } });
    expect(await screen.findByText('음식 60곳')).toBeTruthy();
    await waitFor(() => expect(rpcCalls.some((c) => c.fn === 'list_industry_floors')).toBe(true));
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(container.querySelectorAll('.mix__stack')).toHaveLength(0);
  });
});
