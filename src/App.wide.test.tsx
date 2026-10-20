import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { useEffect, useRef } from 'react';
import type { BuildingHit, FloorRow, OpenSigungu } from './types';
import { WIDE_QUERY } from './lib/useIsWide';

/**
 * PC 두 칸(결정 0039 Q5 · W5 · §4-13 · 👤 2026-10-21) — App 의 배선을 본다. jsdom 에는 `matchMedia` 가 없어 다른 App 시험은 전부
 * 두 칸이 아니다(한 열) — 여기서만 흉내 `matchMedia` 로 창 폭을 정한다. 칸의 자리(grid·sticky·56px)는 CSS 라 jsdom 은 못 본다 —
 * 그건 E2E(BV·BW)가 재고, 여기서는 이름표·그릴지 말지·`inert`·같은 노드·글자·CSS 규칙 자리를 본다.
 * 지도 알맹이(카카오)는 가짜 — 진짜처럼 `visible` 이 거짓이면 `hidden` 으로 숨기기만 하고, 숨었다 다시 보이면 「relayout」 을 한 번 센다
 * (진짜 relayout 배선은 `DistrictMap.test` 「카드 꼴도 숨겼다 보이면 relayout」이 본다). 입구 카드 둘도 가짜(자리만 본다).
 */

const rpc = vi.fn();
const from = vi.fn();
const relayout = vi.fn();

function makeQuery(result: { data: unknown; error: unknown }) {
  const q: Record<string, unknown> = {};
  for (const m of ['select', 'eq', 'order', 'limit']) q[m] = () => q;
  q.then = (cb: (r: unknown) => unknown) => Promise.resolve(result).then(cb);
  return q;
}

vi.mock('./lib/supabase', () => ({
  supabase: {
    rpc: (...args: unknown[]) => rpc(...args),
    from: (view: string) => from(view),
  },
}));

function FakeMap({ sigungu, visible = true }: { sigungu: string | null; visible?: boolean }) {
  const was = useRef(visible);
  useEffect(() => {
    const before = was.current;
    was.current = visible;
    if (visible && !before) relayout();
  }, [visible]);
  return sigungu ? (
    <section className="dmap" hidden={!visible}>
      <button type="button" className="dmap__toggle">
        지도 접기
      </button>
      가짜 지도
    </section>
  ) : null;
}

vi.mock('./components/DistrictMap', () => ({ DistrictMap: FakeMap }));
vi.mock('./components/LhNoticeSection', () => ({
  LhNoticeSection: () => <section className="card lh">가짜 LH 공고</section>,
}));
vi.mock('./components/TxFlowSection', () => ({
  TxFlowSection: () => <section className="card flow">가짜 단가 흐름</section>,
}));

const { default: App } = await import('./App');

const BLD = '1168010100100010000_1024110';
const EMPTY_RIGHT = '왼쪽에서 건물을 고르면 여기에 층별 화면이 섭니다';

function gu(over: Partial<OpenSigungu> = {}): OpenSigungu {
  return { sido_code: '11', sido_nm: '서울', sigungu_code: '11680', sigungu_nm: '강남구', building_cnt: 1, ...over };
}

function hit(over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: BLD,
    pnu: '1168010100100010000',
    bld_nm: '테스트빌딩',
    road_addr: '서울 강남구 테헤란로 1',
    bld_cnt_in_pnu: 1,
    floor_cnt: 1,
    min_floor: 1,
    max_floor: 1,
    has_roof: false,
    total_cnt: 1,
    ...over,
  };
}

function floorRow(): FloorRow {
  return {
    bld_id: BLD,
    pnu: '1168010100100010000',
    floor_no: 1,
    floor_label: null,
    floor_area_m2: 100,
    floor_area_gross_m2: 110,
    segment_cnt: 1,
    main_use: '소매점',
    uses: [],
    bld_nm: '테스트빌딩',
    approve_date: '2003-05-14',
    is_jiphap: true,
    road_addr: '서울 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: 1,
    stores: [],
    total_area_m2: 1234.5,
    far: 350.5,
    bcr: 59.9,
    parking_cnt: 12,
  };
}

/** 흉내 `matchMedia` — 창 폭(px)으로 질의 글자의 min/max-width 를 푼다. 인쇄는 늘 거짓. */
function mediaAt(width: number) {
  window.matchMedia = ((q: string) => {
    const min = /min-width:\s*(\d+)px/.exec(q);
    const max = /max-width:\s*(\d+)px/.exec(q);
    const matches = q !== 'print' && (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
    return { media: q, matches, addEventListener: () => {}, removeEventListener: () => {} };
  }) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  window.localStorage.setItem('sangga.viewerRole', '둘러보기');
  rpc.mockReset();
  from.mockReset();
  relayout.mockReset();
  from.mockImplementation((view: string) =>
    makeQuery(view === 'v_coverage_stats' ? { data: [], error: null } : { data: [floorRow()], error: null }),
  );
  rpc.mockImplementation((fn: string) => {
    if (fn === 'list_open_sigungu') return Promise.resolve({ data: [gu()], error: null });
    if (fn === 'search_buildings')
      return Promise.resolve({ data: [hit(), hit({ bld_id: `${BLD}9`, bld_nm: '둘째빌딩' })], error: null });
    return Promise.resolve({ data: [], error: null });
  });
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  delete (window as { matchMedia?: unknown }).matchMedia;
  vi.restoreAllMocks();
});

const entry = () => document.getElementById('entry-panel')!;
const app = () => document.querySelector('.app')!;

async function pickGu() {
  fireEvent.click(await screen.findByRole('button', { name: /^서울$/ }));
  fireEvent.click(await screen.findByRole('button', { name: /^강남구/ }));
}

async function searchAndOpen(name: RegExp = /테스트빌딩/) {
  const input = screen.getByLabelText('건물명 또는 주소');
  fireEvent.change(input, { target: { value: '테헤란로' } });
  fireEvent.submit(input.closest('form')!);
  fireEvent.click(await screen.findByRole('button', { name }));
  await screen.findByRole('heading', { name: '테스트빌딩' });
}

describe('PC 두 칸 (결정 0039 W5)', () => {
  it('★ 1280 — `.app--wide` · S1 바 DOM 0 · 탭 0 · 「왼쪽 칸 접기」 · 건물 없음 = 오른쪽 안내 글 그대로 + 입구 카드 둘(안내 뒤)', async () => {
    mediaAt(1280);
    const { container } = render(<App />);
    expect(app().classList.contains('app--wide')).toBe(true);
    expect(app().classList.contains('app--tabs')).toBe(false);
    expect(screen.queryByRole('navigation', { name: '화면 고르기' })).toBeNull();
    expect(screen.getByRole('button', { name: '왼쪽 칸 접기' }).getAttribute('aria-expanded')).toBe('true');
    // 「위에서 건물을…」 줄 대신 오른쪽 안내 한 줄(👤 「가」 — 글자 그대로).
    expect(screen.queryByText('위에서 건물을 검색해 선택해 주세요.')).toBeNull();
    expect(container.querySelector('.rpane-empty')!.textContent).toBe(EMPTY_RIGHT);
    await pickGu();
    const main = container.querySelector('.app__main')!;
    const kids = [...main.children].map((c) => c.className.split(' ')[0]);
    // DOM 차례 = 입구 → 안내 → LH → 단가 흐름(grid 자리만 바뀐다).
    expect(kids).toEqual(['entry', 'rpane-empty', 'card', 'card']);
    expect(main.querySelector('.lh')).not.toBeNull();
    expect(main.querySelector('.flow')).not.toBeNull();
    expect(container.querySelector('.entrybar')).toBeNull();
    expect(container.querySelector('.mapprint')).toBeNull(); // 건물 없음 = 인쇄 줄 없음
  });

  it('★ Q5 — 건물을 열어도 왼쪽(지도 포함)이 접히지 않는다 · 같은 지도 노드 · 바 0 · 안내·카드는 물러남 · 머리는 작게', async () => {
    mediaAt(1280);
    const { container } = render(<App />);
    await pickGu();
    const map = container.querySelector('section.dmap')!;
    expect(map).not.toBeNull();
    await searchAndOpen();
    expect(entry().hidden).toBe(false);
    expect(entry().hasAttribute('inert')).toBe(false);
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(map.hasAttribute('hidden')).toBe(false);
    expect(container.querySelector('.entrybar')).toBeNull();
    expect(container.querySelector('.rpane-empty')).toBeNull();
    expect(container.querySelector('.lh')).toBeNull();
    expect(app().classList.contains('app--wbld')).toBe(true);
    expect(app().classList.contains('app--folded')).toBe(true);
    // 다른 건물로 바꿔도 지도는 같은 노드(Q5 「건물을 바꿔도 지도가 사라지지 않음」).
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    fireEvent.click(await screen.findByRole('button', { name: /둘째빌딩/ }));
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(entry().hidden).toBe(false);
  });

  it('★ 「왼쪽 칸 접기」 — `.app--lcollapsed` · 왼쪽은 숨김 속성이 아니라 `inert`(언마운트 0) · 띠(펼치기·구 이름·지도) · 펼치면 같은 지도에 relayout 1회 · 검색어 그대로 · 커서', async () => {
    mediaAt(1280);
    const { container } = render(<App />);
    await pickGu();
    await searchAndOpen();
    const map = container.querySelector('section.dmap')!;
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    expect(input.value).toBe('테헤란로');

    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 접기' }));
    expect(app().classList.contains('app--lcollapsed')).toBe(true);
    expect(entry().hidden).toBe(false);
    expect(entry().hasAttribute('inert')).toBe(true);
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(map.hasAttribute('hidden')).toBe(true);
    const rail = container.querySelector('.lrail')!;
    expect(rail).not.toBeNull();
    expect(rail.querySelector('.lrail__place')!.textContent).toBe('서울 강남구');
    const open = screen.getByRole('button', { name: '왼쪽 칸 펼치기' });
    expect(open.getAttribute('aria-controls')).toBe('entry-panel');
    expect(document.activeElement).toBe(open);
    expect(relayout).not.toHaveBeenCalled();

    fireEvent.click(open);
    expect(app().classList.contains('app--lcollapsed')).toBe(false);
    expect(entry().hasAttribute('inert')).toBe(false);
    expect(container.querySelector('.lrail')).toBeNull();
    expect(container.querySelector('section.dmap')).toBe(map);
    expect(map.hasAttribute('hidden')).toBe(false);
    expect(relayout).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText('건물명 또는 주소') as HTMLInputElement).value).toBe('테헤란로');
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '왼쪽 칸 접기' }));

    // 띠의 「지도」 = 펼치고 지도 머리 단추에 커서.
    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 접기' }));
    fireEvent.click(screen.getByRole('button', { name: '지도' }));
    expect(app().classList.contains('app--lcollapsed')).toBe(false);
    expect(relayout).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(container.querySelector('section.dmap .dmap__toggle'));
  });

  it('「○○구 다른 건물 찾기」 보통 누름 — 두 칸에선 왼쪽 칸 입력칸에 커서(접혀 있으면 펼친 뒤) · 보던 건물 그대로', async () => {
    mediaAt(1280);
    render(<App />);
    await pickGu();
    await searchAndOpen();
    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 접기' }));
    fireEvent.click(screen.getByRole('link', { name: /강남구 다른 건물 찾기/ }));
    expect(app().classList.contains('app--lcollapsed')).toBe(false);
    expect(document.activeElement).toBe(screen.getByLabelText('건물명 또는 주소'));
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
  });

  it('★ 인쇄 — 「상권 지도 넣기」 체크란(기본 끔) · 켜면 `.app--printmap` · 끄면 빠짐 · 저장 0', async () => {
    mediaAt(1280);
    render(<App />);
    await pickGu();
    await searchAndOpen();
    const box = screen.getByRole('checkbox', { name: '상권 지도 넣기' }) as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(app().classList.contains('app--printmap')).toBe(false);
    fireEvent.click(box);
    expect(box.checked).toBe(true);
    expect(app().classList.contains('app--printmap')).toBe(true);
    expect(window.localStorage.length).toBe(1); // 역할 열쇠 하나뿐 — 체크란은 저장하지 않는다
    expect(window.location.search).not.toMatch(/map/);
    fireEvent.click(box);
    expect(app().classList.contains('app--printmap')).toBe(false);
  });

  it('★ 1023 — 두 칸 아님 · 지금 한 열 그대로(건물을 열면 S1 바 · 입구 숨김 · 지도 안 그림 · 체크란·띠·안내 없음)', async () => {
    mediaAt(1023);
    const { container } = render(<App />);
    expect(app().classList.contains('app--wide')).toBe(false);
    expect(container.querySelector('.entry__fold')).toBeNull();
    expect(container.querySelector('.rpane-empty')).toBeNull();
    expect(screen.getByText('위에서 건물을 검색해 선택해 주세요.')).toBeTruthy();
    await pickGu();
    expect(container.querySelector('section.dmap')).not.toBeNull();
    await searchAndOpen();
    expect(container.querySelector('.entrybar')).not.toBeNull();
    expect(entry().hidden).toBe(true);
    expect(container.querySelector('section.dmap')).toBeNull();
    expect(container.querySelector('.mapprint')).toBeNull();
    expect(container.querySelector('.lrail')).toBeNull();
    const cls = [...app().classList];
    for (const c of ['app--wide', 'app--lcollapsed', 'app--wbld', 'app--printmap']) expect(cls).not.toContain(c);
  });

  it('★ 두 칸과 휴대폰 탭은 겹치지 않는다 — 412 = 탭만 · 1280 = 두 칸만 · 1024 경계 = 두 칸', () => {
    for (const [w, wide, tabs] of [
      [412, false, true],
      [720, false, true],
      [721, false, false],
      [1023, false, false],
      [1024, true, false],
      [1280, true, false],
    ] as const) {
      mediaAt(w);
      const { unmount } = render(<App />);
      expect(app().classList.contains('app--wide'), `${w}`).toBe(wide);
      expect(app().classList.contains('app--tabs'), `${w}`).toBe(tabs);
      unmount();
    }
  });

  it('질의 글자는 CSS 묶음 머리와 같다', () => {
    expect(`@media ${WIDE_QUERY}`).toBe(WIDE);
    expect(readFileSync('src/styles.css', 'utf8')).toContain(`${WIDE} {`);
  });
});

// ── CSS 자리 ─────────────────────────────────────────────────────────────────────

const WIDE = '@media screen and (min-width: 1024px)';
const PRINT = '@media print';

type Rule = { sel: string[]; body: string; media: string | null };

/** 주석을 지우고 맨 위 규칙과 `@media` 한 겹 안 규칙을 (선택자들 · 본문 · 묶음 머리)로 편다. */
function cssRules(raw: string): Rule[] {
  const src = raw.replace(/\/\*[\s\S]*?\*\//g, '');
  const out: Rule[] = [];
  const take = (chunk: string, media: string | null) => {
    for (const m of chunk.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      out.push({ sel: m[1].split(',').map((x) => x.trim()), body: m[2], media });
    }
  };
  let i = 0;
  let plain = '';
  while (i < src.length) {
    const at = src.indexOf('@media', i);
    if (at < 0) {
      plain += src.slice(i);
      break;
    }
    plain += src.slice(i, at);
    const open = src.indexOf('{', at);
    let depth = 1;
    let j = open + 1;
    while (j < src.length && depth > 0) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') depth -= 1;
      j += 1;
    }
    take(src.slice(open + 1, j - 1), src.slice(at, open).trim());
    i = j;
  }
  take(plain, null);
  return out;
}

const W5_NAME = /\.app--wide|\.app--lcollapsed|\.app--wbld|\.app--printmap|\.lrail|\.entry__fold|\.rpane-empty|\.mapprint/;

/**
 * W5 이름표가 나오는 규칙의 묶음 머리들 — 인쇄 묶음과 '누르는 것 44px' 목록(`@media screen` 의 min-height 44)은 뺀다.
 * 가드 본체와 양성 대조가 이 함수를 같이 지난다. 못 보는 것: 이름표 없이 `.app__main` 만으로 쓴 두 칸 규칙 · 두 겹 이상 겹친 @media.
 */
function w5Medias(src: string): (string | null)[] {
  return cssRules(src)
    .filter((r) => r.media !== PRINT && r.sel.some((s) => W5_NAME.test(s)))
    .filter((r) => !(r.media === '@media screen' && /min-height:\s*44px/.test(r.body)))
    .map((r) => r.media);
}

/** 종이 갈래 셋 — 접기·띠·체크란·안내 감춤 · 건물을 연 채 왼쪽 칸 감춤 · 지도 넣기면 숨은 지도 되살림. */
function printGuards(src: string) {
  const print = cssRules(src).filter((r) => r.media === PRINT);
  const hide = print.filter((r) => /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
  return {
    controls: ['.entry__fold', '.lrail', '.mapprint', '.rpane-empty'].every((s) => hide.includes(s)),
    leftOut: hide.includes('.app--wide.app--wbld:not(.app--printmap) .entry'),
    mapBack: print.some((r) => r.sel.includes('.app--printmap .entry .dmap[hidden]') && /display:\s*block/.test(r.body)),
  };
}

describe('PC 두 칸 — CSS', () => {
  const css = readFileSync('src/styles.css', 'utf8');
  const rules = cssRules(css);

  it('★ 두 칸 규칙은 전부 `min-width: 1024px` 화면 묶음 안 — 기본 규칙·720 묶음엔 0 · 양성 대조(기본 규칙 꼴 + 다른 묶음 꼴)', () => {
    const medias = w5Medias(css);
    expect(medias.length).toBeGreaterThan(8);
    expect(new Set(medias)).toEqual(new Set([WIDE]));
    expect(w5Medias(`${css}\n.app--wide .app__main { display: grid; }`)).toContain(null);
    expect(w5Medias(`${css}\n@media (min-width: 1024px) {\n  .x,\n  .lrail { width: 56px; }\n}`)).toContain(
      '@media (min-width: 1024px)',
    );
  });

  it('두 칸 묶음 — 1/3 : 2/3 grid · 접히면 56px · 왼쪽 칸 sticky + 안에서 굴림 · 휴대폰 이름표(`.app--tabs`)는 안 건드린다', () => {
    const wide = rules.filter((r) => r.media === WIDE);
    const main = wide.find((r) => r.sel.includes('.app--wide .app__main'))!;
    expect(main.body).toMatch(/display:\s*grid/);
    expect(main.body).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*2fr\)/);
    const col = wide.find((r) => r.sel.includes('.app--wide.app--lcollapsed .app__main'))!;
    expect(col.body).toMatch(/grid-template-columns:\s*56px/);
    const left = wide.find((r) => r.sel.includes('.app--wide .app__main > .entry'))!;
    expect(left.sel).toContain('.app--wide .app__main > .lrail');
    for (const re of [/position:\s*sticky/, /overflow-y:\s*auto/, /max-height:\s*calc\(100vh/, /grid-column:\s*1/])
      expect(left.body).toMatch(re);
    const hide = wide.find((r) => r.sel.includes('.app--wide.app--lcollapsed .app__main > .entry'))!;
    expect(hide.body).toMatch(/display:\s*none/);
    expect(wide.filter((r) => r.sel.some((s) => s.includes('.app--tabs')))).toEqual([]);
  });

  it('★ 종이 — 접기·띠·체크란·안내는 빠지고 · 건물을 연 채면 왼쪽 칸째 · 지도 넣기면 숨은 지도를 되살린다 · 양성 대조(갈래 하나씩 지운 꼴)', () => {
    expect(printGuards(css)).toEqual({ controls: true, leftOut: true, mapBack: true });
    const noLeft = css.replace('.app--wide.app--wbld:not(.app--printmap) .entry,', '');
    expect(noLeft).not.toBe(css);
    expect(printGuards(noLeft).leftOut).toBe(false);
    const noBack = css.replace(/\.app--printmap \.entry \.dmap\[hidden\]\s*\{[^}]*\}/, '');
    expect(noBack).not.toBe(css);
    expect(printGuards(noBack).mapBack).toBe(false);
  });

  it('종이 묶음에는 폭 조건이 없다(종이는 폭이 없다 — 이름표로 가른다)', () => {
    const start = css.indexOf(`${PRINT} {`);
    expect(start).toBeGreaterThan(0);
    const printChunks = rules.filter((r) => r.media === PRINT).map((r) => r.body + r.sel.join(','));
    expect(printChunks.join('\n')).not.toMatch(/1024/);
    expect(css.match(/@media print[^{]*\{/g)!.every((h) => !/width/.test(h))).toBe(true);
  });

  it('누르는 것 44px 목록에 「왼쪽 칸 접기」·띠 단추·「상권 지도 넣기」', () => {
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body)).flatMap((r) => r.sel);
    for (const s of ['.entry__fold', '.lrail__btn', '.mapprint']) expect(tall, s).toContain(s);
  });
});
