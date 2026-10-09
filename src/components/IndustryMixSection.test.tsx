import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import type { IndustryDetail, IndustryFloors, IndustryMix } from '../types';

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
