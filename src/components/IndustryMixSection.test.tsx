import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import type { IndustryDetail, IndustryMix } from '../types';

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
