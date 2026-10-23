import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { useEffect, useRef } from 'react';
import type { BuildingHit, DistrictLand, FloorRow, OpenSigungu } from './types';
import { WIDE_QUERY } from './lib/useIsWide';
import type { DistrictMapPick } from './lib/districtMapPick';
import { DistrictBuildings } from './components/DistrictBuildings';

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
/** 가짜 지도가 받은 `paneArea`(👤 10-22 L2 — 상권 건물 목록 주소 줄이기는 DistrictMap 을 거쳐 넘어간다). */
const mapPaneArea = vi.fn();

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

/** 가짜 지도의 「누른 자리」(지도를 처음 누른 것 흉내 — 한 배열). */
const FAKE_PICKED = ['D1'];

function FakeMap({
  sigungu,
  visible = true,
  paneArea = null,
  pick,
  onPickChange,
  onSelectBuilding,
  selected = null,
  listHost = null,
  onListChange,
}: {
  sigungu: string | null;
  visible?: boolean;
  paneArea?: { sido: string; sigungu: string } | null;
  pick?: DistrictMapPick;
  onPickChange?: (next: DistrictMapPick) => void;
  onSelectBuilding?: (hit: BuildingHit) => void;
  selected?: BuildingHit | null;
  listHost?: HTMLElement | null;
  onListChange?: (label: string | null) => void;
}) {
  mapPaneArea(paneArea);
  const was = useRef(visible);
  useEffect(() => {
    const before = was.current;
    was.current = visible;
    if (visible && !before) relayout();
  }, [visible]);
  const openId = pick?.openId ?? null;
  return sigungu ? (
    <section className="dmap" hidden={!visible}>
      <button type="button" className="dmap__toggle">
        지도 접기
      </button>
      가짜 지도
      {/* 누른 자리의 상권 단추 흉내(👤 10-22 방법 나) — 진짜처럼 App 이 쥔 누른 것을 바꾸고, 열린 상권이면 진짜 상권 건물 목록을 그린다. */}
      <button
        type="button"
        className="dmap__picked-btn"
        aria-expanded={openId === 'D1'}
        // 진짜 `PickedList` 처럼 누른 자리(같은 배열)는 그대로 두고 펼친 상권만 바꾼다 — 지도를 새로 누를 때만 새 배열이 온다(App 이 둘을 가른다 · B2).
        onClick={() =>
          onPickChange?.({ sigungu, pickedIds: pick?.pickedIds ?? FAKE_PICKED, openId: openId === 'D1' ? null : 'D1' })
        }
      >
        가짜상권
      </button>
      {openId === 'D1' && onSelectBuilding && (
        <DistrictBuildings
          districtId="D1"
          districtNm="가짜상권"
          onSelect={onSelectBuilding}
          selectedBldId={selected?.bld_id ?? null}
          paneArea={paneArea}
          listHost={listHost}
          onListChange={onListChange}
        />
      )}
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
  mapPaneArea.mockReset();
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
    // DOM 차례 = 입구 → 안내 → LH → 단가 흐름 → (숨은) 오른쪽 목록 자리(👤 10-22 방법 나 · grid 자리만 바뀐다).
    expect(kids).toEqual(['entry', 'rpane-empty', 'card', 'card', 'rlist']);
    expect((main.querySelector('.rlist') as HTMLElement).hidden).toBe(true);
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

const W5_NAME =
  /\.app--wide|\.app--lcollapsed|\.app--wbld|\.app--printmap|\.app--rfold|\.app--wlist|\.lrail|\.entry__fold|\.rpane-empty|\.mapprint|\.regionfold|\.rlist|\.rback|\.rtable/;

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

// ── 보완 1(검사관 3인 + 메인 실사진 + 👤 결정 3 · 2026-10-21 08:1x) ──────────────────────────────────────────

/** 크기를 바꿀 수 있는 흉내 `matchMedia` — 폭을 바꾸면 듣는 쪽(`useIsWide`·`useIsPhone`) 전부에 change 를 보낸다. */
function resizableMedia(width: number) {
  const st = { width };
  const listeners = new Set<() => void>();
  window.matchMedia = ((q: string) => ({
    media: q,
    get matches() {
      const min = /min-width:\s*(\d+)px/.exec(q);
      const max = /max-width:\s*(\d+)px/.exec(q);
      return q !== 'print' && (!min || st.width >= Number(min[1])) && (!max || st.width <= Number(max[1]));
    },
    addEventListener: (_t: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_t: string, cb: () => void) => listeners.delete(cb),
  })) as unknown as typeof window.matchMedia;
  return {
    setWidth(v: number) {
      st.width = v;
      act(() => listeners.forEach((cb) => cb()));
    },
  };
}

describe('PC 두 칸 보완 1 (W5)', () => {
  it('★ D1 두 칸에서 새로 검색해도 오른쪽 건물은 그대로(§7-1 과 같은 규칙) — 결과를 눌러야 바뀐다 · 1023 한 열은 지금처럼 비운다(양성 대조)', async () => {
    mediaAt(1280);
    const { container } = render(<App />);
    await pickGu();
    await searchAndOpen();
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '다른동' } });
    fireEvent.submit(input.closest('form')!);
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    await screen.findByRole('button', { name: /둘째빌딩/ });
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    expect(container.querySelector('.rpane-empty')).toBeNull();
    expect(app().classList.contains('app--wbld')).toBe(true);
    cleanup();
    window.history.replaceState(null, '', '/'); // 앞 그림이 주소에 적은 구·건물을 비운다

    mediaAt(1023);
    render(<App />);
    await pickGu();
    await searchAndOpen();
    const input2 = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    fireEvent.change(input2, { target: { value: '다른동' } });
    fireEvent.submit(input2.closest('form')!);
    expect(screen.queryByRole('heading', { name: '테스트빌딩' })).toBeNull();
  });

  it('★ D2 구를 고르면 칩 상자는 접고 「서울 강남구 · 바꾸기」 한 줄 · 커서는 「바꾸기」 · 펼치면 칩 상자(같은 노드) · 다른 구를 고르면 다시 접힘 · 구를 풀면 한 줄 없음 · 1023 은 한 줄 없음', async () => {
    rpc.mockImplementation((fn: string) => {
      if (fn === 'list_open_sigungu')
        return Promise.resolve({ data: [gu(), gu({ sigungu_code: '11650', sigungu_nm: '서초구' })], error: null });
      return Promise.resolve({ data: [], error: null });
    });
    mediaAt(1280);
    const { container } = render(<App />);
    const region = container.querySelector('section.region')!;
    expect(region).not.toBeNull();
    expect(container.querySelector('.regionfold')).toBeNull();
    expect(app().classList.contains('app--rfold')).toBe(false);
    await pickGu();
    const fold = container.querySelector('.regionfold')!;
    expect(fold.querySelector('.regionfold__place')!.textContent).toBe('서울 강남구');
    const change = screen.getByRole('button', { name: '바꾸기' });
    expect(change.getAttribute('aria-expanded')).toBe('false');
    expect(change.getAttribute('aria-controls')).toBe('region-panel');
    expect(region.id).toBe('region-panel');
    expect(app().classList.contains('app--rfold')).toBe(true);
    expect(document.activeElement).toBe(change);
    // 칩 상자는 다시 태어나지 않는다(숨기기만) — 같은 노드 · 차례 = 지역 한 줄 → 칩 상자(지역 고르개 자리).
    expect(container.querySelector('section.region')).toBe(region);
    expect(fold.nextElementSibling).toBe(region);

    fireEvent.click(change);
    expect(change.getAttribute('aria-expanded')).toBe('true');
    expect(app().classList.contains('app--rfold')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /^서초구/ }));
    expect(app().classList.contains('app--rfold')).toBe(true);
    expect(container.querySelector('.regionfold__place')!.textContent).toBe('서울 서초구');
    const change2 = screen.getByRole('button', { name: '바꾸기' });
    expect(change2.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(change2);
    expect(container.querySelector('section.region')).toBe(region);

    // 「바꾸기」 → 고른 구를 다시 누르면(풀기) 한 줄이 없어지고 칩 상자 그대로.
    fireEvent.click(change2);
    fireEvent.click(screen.getByRole('button', { name: /^서초구/ }));
    expect(container.querySelector('.regionfold')).toBeNull();
    expect(app().classList.contains('app--rfold')).toBe(false);
    cleanup();
    window.history.replaceState(null, '', '/'); // 앞 그림이 주소에 적은 구·건물을 비운다

    mediaAt(1023);
    const r2 = render(<App />);
    await pickGu();
    expect(r2.container.querySelector('.regionfold')).toBeNull();
    expect(app().classList.contains('app--rfold')).toBe(false);
    expect(r2.container.querySelector('section.region')!.id).toBe('');
  });

  it('★ F6 띠로 접은 채 1023 으로 줄었다 1280 으로 돌아오면 왼쪽 칸은 펼친 채(지도가 보이는 칸에서 다시 태어남)', async () => {
    const media = resizableMedia(1280);
    const { container } = render(<App />);
    await pickGu();
    await searchAndOpen();
    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 접기' }));
    expect(app().classList.contains('app--lcollapsed')).toBe(true);
    media.setWidth(1023);
    expect(app().classList.contains('app--wide')).toBe(false);
    media.setWidth(1280);
    expect(app().classList.contains('app--wide')).toBe(true);
    expect(app().classList.contains('app--lcollapsed')).toBe(false);
    expect(container.querySelector('.lrail')).toBeNull();
    expect(entry().hasAttribute('inert')).toBe(false);
    const map = container.querySelector('section.dmap')!;
    expect(map).not.toBeNull();
    expect(map.hasAttribute('hidden')).toBe(false);
  });

  it('F6 양성 대조 — 두 칸 안에서 크기만 바뀌면(1280 → 1100) 접힌 채 그대로', async () => {
    const media = resizableMedia(1280);
    render(<App />);
    await pickGu();
    await searchAndOpen();
    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 접기' }));
    media.setWidth(1100);
    expect(app().classList.contains('app--lcollapsed')).toBe(true);
  });
});

/**
 * 두 칸 묶음 안의 `(max-width: 1279px)` 갈래 규칙(F2·F4) — 가드 본체와 양성 대조가 이 함수를 같이 지난다.
 * 못 보는 것: 갈래 머리 글자를 바꾼 꼴(예: `1280px`)은 못 찾아 빈 목록이 된다(= 빨강) · 두 칸 묶음이 둘 이상이면 첫 묶음만 본다.
 */
function narrowRules(src: string): Rule[] {
  const clean = src.replace(/\/\*[\s\S]*?\*\//g, '');
  const at = clean.indexOf(`${WIDE} {`);
  if (at < 0) return [];
  const open = clean.indexOf('{', at);
  let depth = 1;
  let j = open + 1;
  while (j < clean.length && depth > 0) {
    if (clean[j] === '{') depth += 1;
    else if (clean[j] === '}') depth -= 1;
    j += 1;
  }
  return cssRules(clean.slice(open + 1, j - 1)).filter((r) => r.media === '@media (max-width: 1279px)');
}

/** 층 줄 칸 합(px) — 고정 칸 + `minmax(n, …)` 의 n + 틈 × (칸 수 − 1) + 안쪽 여백 20 + 테두리 2. */
function floorRowPx(body: string): number {
  const cols = /grid-template-columns:\s*([^;]+);/.exec(body)![1];
  const tracks = cols.match(/minmax\([^)]*\)|\S+/g)!;
  const px = tracks.reduce((s, t) => s + Number(/(\d+)px/.exec(t)![1]), 0);
  const gap = Number(/gap:\s*(\d+)px/.exec(body)![1]);
  return px + gap * (tracks.length - 1) + 20 + 2;
}

describe('PC 두 칸 보완 1 — CSS', () => {
  const css = readFileSync('src/styles.css', 'utf8');
  const rules = cssRules(css);

  it('★ F2 1024~1279 층 줄 = 칸 합 640px 미만 · 사양 칸 틈 18 — 두 칸 묶음 안 1279 갈래 · 양성 대조(갈래 삭제 · 기본 폭으로 되돌린 꼴) · F4 표지 이름 숨김은 두 칸 전체로 옮김(👤 10-22 L4 — 아래 「왼쪽 칸 다듬기」)', () => {
    const narrow = narrowRules(css);
    const row = narrow.find((r) => r.sel.includes('.app--wide .floor__row'))!;
    expect(floorRowPx(row.body)).toBeLessThan(640);
    // 기본 층 줄은 그대로(1280 이상 · 721~1023) — 기본 칸 합은 640 을 넘는다(그래서 갈래가 필요하다).
    const baseRow = rules.find((r) => r.media === null && r.sel.includes('.floor__row') && /grid-template-columns/.test(r.body))!;
    expect(floorRowPx(baseRow.body)).toBeGreaterThan(640);
    expect(narrow.find((r) => r.sel.includes('.app--wide .stack__facts'))!.body).toMatch(/gap:\s*18px/);
    // 양성 대조 — 갈래를 통째로 지운 꼴 · 층 줄을 기본 칸으로 되돌린 꼴.
    const noBranch = css.replace(/@media \(max-width: 1279px\) \{[\s\S]*?\r?\n {2}\}\r?\n/, '');
    expect(noBranch).not.toBe(css);
    expect(narrowRules(noBranch)).toEqual([]);
    const wideRow = css.replace(
      '64px minmax(60px, 1fr) 100px 140px 56px 60px 20px',
      '74px minmax(80px, 1fr) 118px 168px 62px 66px 20px',
    );
    expect(wideRow).not.toBe(css);
    const back = narrowRules(wideRow).find((r) => r.sel.includes('.app--wide .floor__row'))!;
    expect(floorRowPx(back.body)).toBeGreaterThanOrEqual(640);
  });

  it('★ 첫 방문 큰 카드 — 두 칸에서는 오른쪽 칸(👤 10-22 L6)이라 한 줄에 셋: 두 칸 묶음에 세로 쌓기 규칙 0(W5 보완 F1 걷음) · 기본 규칙도 한 줄 그대로', () => {
    const stacked = (src: string) =>
      cssRules(src).some(
        (r) => (r.media === WIDE || r.media === null) && r.sel.some((s) => s.includes('.rolecards__list')) && /flex-direction:\s*column/.test(r.body),
      );
    expect(stacked(css)).toBe(false);
    // 양성 대조 — 두 칸 묶음 꼴 · 기본 규칙 꼴(선택자 목록 변형)을 실제로 잡는다.
    expect(stacked(`${css}\n${WIDE} {\n  .app--wide .rolecards__list { flex-direction: column; }\n}`)).toBe(true);
    expect(stacked(`${css}\n.x,\n.rolecards__list {\n  flex-direction:column;\n}`)).toBe(true);
  });

  it('★ D2 지역 한 줄 — 접힘이면 칩 상자 숨김(두 칸 묶음) · 「바꾸기」 44px 목록 · 한 줄은 종이에서 빠진다', () => {
    const wide = rules.filter((r) => r.media === WIDE);
    expect(wide.find((r) => r.sel.includes('.app--wide.app--rfold .entry .region'))!.body).toMatch(/display:\s*none/);
    const tall = rules.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body)).flatMap((r) => r.sel);
    expect(tall).toContain('.regionfold__btn');
    const hide = rules.filter((r) => r.media === PRINT && /display:\s*none/.test(r.body)).flatMap((r) => r.sel);
    expect(hide).toContain('.regionfold');
  });
});

// ── 왼쪽 칸 다듬기(👤 2026-10-22 「가」 · 분석 페이지 RgXTDKCXH9ACziRd8rhvek) ─────────────────────────────────
// 화면 배선(큰 카드 자리 · 주소 길 이름부터 · 짧은 안내 글)은 여기, 실제 자리(말줄임 0 · 굴림 하나)는 E2E 「CC」가 잰다.
describe('PC 두 칸 왼쪽 칸 다듬기 — 배선 (👤 2026-10-22)', () => {
  const PANE_PLACEHOLDER = '건물명·주소·가게 이름';
  /** 점 앞은 줄이 안 바뀌는 공백(U+00A0 — 이스케이프 표기로 적는다). */
  const PANE_EXAMPLE = '예: 미도맨션\u00a0· 테헤란로 117\u00a0· 역삼동 823-4\u00a0· 스타벅스';

  function searchWith(rows: BuildingHit[]) {
    rpc.mockImplementation((fn: string) => {
      if (fn === 'list_open_sigungu') return Promise.resolve({ data: [gu()], error: null });
      if (fn === 'search_buildings') return Promise.resolve({ data: rows, error: null });
      return Promise.resolve({ data: [], error: null });
    });
  }

  it('★ L6 첫 방문 큰 카드 = 오른쪽 빈 칸(`.app__main` 의 오른쪽 덩어리 · 왼쪽 칸 밖) · 그동안 왼쪽엔 역할 줄 0 · 고르면 사라지고 왼쪽 작은 줄 + 커서 · 저장', async () => {
    window.localStorage.clear();
    mediaAt(1280);
    const { container } = render(<App />);
    const cards = container.querySelector('section.rolecards')!;
    expect(cards).not.toBeNull();
    expect(entry().contains(cards)).toBe(false);
    expect(cards.parentElement).toBe(container.querySelector('.app__main'));
    // 오른쪽 맨 위 — 왼쪽 칸 바로 다음 · 오른쪽 안내 한 줄 앞.
    expect(cards.previousElementSibling).toBe(entry());
    expect(cards.nextElementSibling!.className).toBe('rpane-empty');
    expect(entry().querySelector('section.role')).toBeNull();
    await pickGu();
    // 구를 골라도 그대로 오른쪽(입구 카드 둘 위).
    expect(container.querySelector('section.rolecards')).toBe(cards);
    fireEvent.click(screen.getByRole('button', { name: /가게를 열려고/ }));
    expect(container.querySelector('section.rolecards')).toBeNull();
    const chip = entry().querySelector<HTMLButtonElement>('section.role button[aria-pressed="true"]')!;
    expect(chip.textContent).toBe('창업자');
    expect(document.activeElement).toBe(chip);
    expect(window.localStorage.getItem('sangga.viewerRole')).toBe('창업자');
  });

  it('★ L6 보완 1 — 왼쪽 칸을 띠로 접은 채 오른쪽 큰 카드를 고르면 커서는 띠의 펼치기 단추(숨은 칸·BODY 아님 · 검사 🟡d)', async () => {
    window.localStorage.clear();
    mediaAt(1280);
    const { container } = render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 접기' }));
    expect(entry().hasAttribute('inert')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /투자·매입하려고/ }));
    expect(container.querySelector('section.rolecards')).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '왼쪽 칸 펼치기' }));
    expect(window.localStorage.getItem('sangga.viewerRole')).toBe('투자자');
  });

  it('★ L6 아직 안 물어본 채 건물을 열면 오른쪽은 건물 — 큰 카드는 숨고 왼쪽에 작은 줄(질문 한 번) · 저장 0', async () => {
    window.localStorage.clear();
    mediaAt(1280);
    const { container } = render(<App />);
    await pickGu();
    await searchAndOpen();
    expect(container.querySelector('section.rolecards')).toBeNull();
    expect(entry().querySelector('section.role')).not.toBeNull();
    expect(window.localStorage.getItem('sangga.viewerRole')).toBeNull();
  });

  it('L6 양성 대조 — 1023 한 열은 지금 그대로 왼쪽(입구) 맨 위 · 건물 직행 링크(1280)는 어디에도 안 뜬다(W3 ①)', async () => {
    window.localStorage.clear();
    mediaAt(1023);
    const r1 = render(<App />);
    const cards = r1.container.querySelector('section.rolecards')!;
    expect(entry().contains(cards)).toBe(true);
    cleanup();

    window.history.replaceState(null, '', `/?sgg=11680&bld=${BLD}`);
    mediaAt(1280);
    const r2 = render(<App />);
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(r2.container.querySelector('section.rolecards')).toBeNull();
    expect(window.localStorage.getItem('sangga.viewerRole')).toBeNull();
  });

  it('★ L2·L5 1280 — 검색칸 안내 글 짧게 · 결과 주소는 고른 구면 길 이름부터(도로명·지번) · 다른 구는 그대로 · 지도에도 같은 시·구', async () => {
    searchWith([
      hit({ road_addr: '서울특별시 강남구 테헤란로 1', jibun_addr: '서울특별시 강남구 역삼동 823-4' }),
      hit({ bld_id: `${BLD}9`, bld_nm: '둘째빌딩', road_addr: '서울특별시 서초구 강남대로 2', jibun_addr: null }),
    ]);
    mediaAt(1280);
    const { container } = render(<App />);
    expect((screen.getByLabelText('건물명 또는 주소') as HTMLInputElement).placeholder).toBe(PANE_PLACEHOLDER);
    // 보완 1 — 검색칸 바로 아래 예시 한 줄(두 칸만 · 글을 쳐도 남는다).
    expect(container.querySelector('.search__eg')!.textContent).toBe(PANE_EXAMPLE);
    await pickGu();
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    expect(input.placeholder).toBe(PANE_PLACEHOLDER);
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    await screen.findByRole('button', { name: /둘째빌딩/ });
    const addrs = [...container.querySelectorAll('.hit__addr')].map((e) => e.textContent);
    expect(addrs).toEqual(['테헤란로 1', '서울특별시 서초구 강남대로 2']);
    expect(container.querySelector('.hit__jibun')!.textContent).toBe('지번 역삼동 823-4');
    expect(container.querySelector('.search__eg')!.textContent).toBe(PANE_EXAMPLE);
    expect(mapPaneArea).toHaveBeenLastCalledWith({ sido: '서울특별시', sigungu: '강남구' });
  });

  it('L2·L5 양성 대조 — 1023 한 열은 안내 글·주소 지금 그대로 · 지도에 시·구를 안 넘긴다', async () => {
    searchWith([hit({ road_addr: '서울특별시 강남구 테헤란로 1', jibun_addr: '서울특별시 강남구 역삼동 823-4' })]);
    mediaAt(1023);
    const { container } = render(<App />);
    await pickGu();
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    expect(input.placeholder).not.toBe(PANE_PLACEHOLDER);
    expect(input.placeholder).toContain('스타벅스');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    await screen.findByRole('button', { name: /테스트빌딩/ });
    expect(container.querySelector('.hit__addr')!.textContent).toBe('서울특별시 강남구 테헤란로 1');
    expect(container.querySelector('.hit__jibun')!.textContent).toBe('지번 서울특별시 강남구 역삼동 823-4');
    expect(container.querySelector('.search__eg')).toBeNull();
    expect(mapPaneArea).toHaveBeenLastCalledWith(null);
  });
});

/**
 * 왼쪽 칸 다듬기 CSS(L1 두 줄 · L3 굴림 하나 · L4 표지 짧게) — 두 칸 묶음 안의 규칙을 본다. 가드 본체와 양성 대조가 이 함수를 같이 지난다.
 * 못 보는 것: 실제 픽셀(말줄임 0·안쪽 굴림 0·표지 겹침 0)은 jsdom 이 못 잰다 → E2E 「CC」(표지는 E2E 에 지도 키가 없어 계산으로만).
 */
function paneRules(src: string) {
  const wide = cssRules(src).filter((r) => r.media === WIDE);
  const find = (sel: string) => wide.filter((r) => r.sel.includes(sel));
  const has = (sel: string, re: RegExp) => find(sel).some((r) => re.test(r.body));
  return {
    // 👤 2026-10-22 방법 나 — 왼쪽 칸 목록 규칙(L1 두 줄 · L3 굴림 하나)은 걷었다(두 칸에서 왼쪽 칸에 목록이 안 선다). 남은 것이 0 인가.
    leftListGone: !wide.some((r) => r.sel.some((s) => /\.entry \.(hits|hit|stores|stores__row|dbld__list|dbld__row)\b/.test(s))),
    example13: has('.app--wide .search__eg', /font-size:\s*13px/),
    offShort:
      has('.app--wide .dmap__off-nm', /display:\s*none/) &&
      has('.app--wide .dmap__off-etc', /display:\s*none/) &&
      !narrowRules(src).some((r) => r.sel.some((s) => s.includes('.dmap__off'))),
  };
}

describe('PC 두 칸 왼쪽 칸 다듬기 — CSS (👤 2026-10-22)', () => {
  const css = readFileSync('src/styles.css', 'utf8');

  it('★ L4 표지 짧게(두 칸 전체 — 1279 갈래 밖) · 예시 줄 13px · 왼쪽 칸 목록 규칙(L1·L3)은 걷음(👤 10-22 방법 나) — 전부 두 칸 묶음', () => {
    expect(paneRules(css)).toEqual({ leftListGone: true, example13: true, offShort: true });
  });

  it('양성 대조 — 규칙을 하나씩 걷은 꼴을 실제로 잡는다(흔한 꼴 + 변형 꼴)', () => {
    // 왼쪽 칸 목록 규칙이 되살아난 꼴 — 흔한 꼴 + 선택자 목록 변형.
    expect(paneRules(`${css}\n${WIDE} {\n  .app--wide .entry .hit { display: flex; }\n}`).leftListGone).toBe(false);
    expect(paneRules(`${css}\n${WIDE} {\n  .x,\n  .app--wide .entry .dbld__list {\n    max-height: none;\n  }\n}`).leftListGone).toBe(false);
    // 표지 숨김을 1279 갈래로 되돌린 꼴(옛 W5 F4) — 두 칸 전체에서 걷고 갈래에 넣는다.
    const back = css
      .replace(/ {2}\.app--wide \.dmap__off-nm,\r?\n {2}\.app--wide \.dmap__off-etc \{\r?\n {4}display: none;\r?\n {2}\}\r?\n/, '')
      .replace(/(\.app--wide \.stack__facts \{\r?\n {6}gap: 18px;\r?\n {4}\})/, '$1\n    .app--wide .dmap__off-nm,\n    .app--wide .dmap__off-etc { display: none; }');
    expect(back).not.toBe(css);
    expect(paneRules(back).offShort).toBe(false);
  });
});

// ── 오른쪽 목록(👤 2026-10-22 방법 나 · R1~R8) ──────────────────────────────────────────────────────────────
// 배선(목록이 어느 칸에 서나 · 건물 ↔ 목록 · 뒤로가기 · 굴린 자리 · 단추 글자)은 여기, 실제 자리(표 네 칸 · 말줄임 0 · 넘침 0)는 E2E 「CD」.
describe('PC 두 칸 오른쪽 목록 — 배선 (👤 2026-10-22 방법 나)', () => {
  function land(over: Partial<DistrictLand> = {}): DistrictLand {
    return {
      pnu: '1168010100100020000',
      store_cnt: 317,
      bld_cnt_in_pnu: 1,
      bld_id: `${BLD}7`,
      bld_nm: '상권빌딩',
      road_addr: '서울특별시 강남구 테헤란로 7',
      jibun_addr: null,
      lat: null,
      lng: null,
      floor_cnt: 6,
      min_floor: -1,
      max_floor: 5,
      has_roof: false,
      total_parcel_cnt: 2,
      total_bld_cnt: 3,
      ...over,
    };
  }

  function serve(hits: BuildingHit[]) {
    rpc.mockImplementation((fn: string) => {
      if (fn === 'list_open_sigungu') return Promise.resolve({ data: [gu()], error: null });
      if (fn === 'search_buildings') return Promise.resolve({ data: hits, error: null });
      if (fn === 'list_district_buildings')
        return Promise.resolve({
          data: [land(), land({ pnu: '1168010100100030000', bld_id: `${BLD}8`, bld_nm: '둘동땅', bld_cnt_in_pnu: 2, store_cnt: 12 })],
          error: null,
        });
      return Promise.resolve({ data: [], error: null });
    });
  }

  const TWO = [
    hit({ road_addr: '서울특별시 강남구 테헤란로 1', jibun_addr: '서울특별시 강남구 역삼동 823-4', bld_cnt_in_pnu: 3, min_floor: -2, max_floor: 9, floor_cnt: 12 }),
    hit({ bld_id: `${BLD}9`, bld_nm: '둘째빌딩' }),
  ];
  const rlist = () => document.querySelector<HTMLElement>('section.rlist')!;
  const panes = () => [...document.querySelectorAll<HTMLElement>('.rlist__pane')];
  /** 오른쪽 굴린 자리 흉내 — jsdom 은 굴리지 않는다(창 굴림 값만 바꿔 둔다). */
  function scrollAt(y: number) {
    Object.defineProperty(window, 'scrollY', { value: y, configurable: true, writable: true });
  }

  afterEach(() => scrollAt(0));
  /*
    쌓은 뒤로가기 칸 수 = `pushState` 를 부른 횟수(그대로 지나가는 감시). ⓘ `history.length` 는 못 믿는다 — jsdom 창 하나를 시험들이
    나눠 써서, 앞 시험이 뒤로 간 자리에서 새 칸을 쌓으면 앞쪽 칸이 잘려 길이가 그대로일 수 있다.
  */
  beforeEach(() => {
    vi.spyOn(window.history, 'pushState');
  });
  const pushes = () => vi.mocked(window.history.pushState).mock.calls.length;

  async function search(word = '테헤란로') {
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: word } });
    fireEvent.submit(input.closest('form')!);
    await screen.findByRole('button', { name: /둘째빌딩/ });
  }

  it('★ R1·R4 1280 — 검색 결과는 오른쪽 목록 자리에 표(이름 · 길 주소 · 층 · 점포) · 왼쪽 칸엔 목록 0 · 다른 오른쪽 덩어리는 숨김 이름표 · 큰 카드는 물러나 왼쪽 작은 줄(저장 0)', async () => {
    window.localStorage.clear(); // 아직 안 물어봄 — 큰 카드가 오른쪽에 서 있다
    serve(TWO);
    mediaAt(1280);
    const { container } = render(<App />);
    await pickGu();
    expect(container.querySelector('section.rolecards')).not.toBeNull();
    await search();
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(rlist().hidden).toBe(false);
    expect(rlist().querySelectorAll('.hit')).toHaveLength(2);
    expect(entry().querySelector('.hit, .hits, .search__count')).toBeNull();
    expect(panes().map((p) => p.hidden)).toEqual([false, true]);
    // 건물 검색 결과 표는 세 칸(👤 2026-10-22 「검색 결과는 세 칸」 — 점포 칸 자체가 없다 · 빈 칸·「–」 0) · 줄마다 같은 세 칸.
    const head = [...rlist().querySelectorAll('.rtable__head .rcell')].map((e) => e.textContent);
    expect(head).toEqual(['이름', '길 주소', '층']);
    expect(rlist().querySelector('.rtable__head')!.className).toBe('rtable__head rtable__head--3');
    const row = rlist().querySelector('.hit')!;
    expect([...row.children].map((c) => c.className)).toEqual([
      'rcell rcell--name',
      'rcell rcell--addr',
      'rcell rcell--floor',
    ]);
    expect(rlist().querySelector('.hits .rcell--store')).toBeNull();
    // 지번 · 「같은 땅에 N동」은 주소 칸 아래(R4) · 주소는 길 이름부터(L2 그대로).
    const addr = row.querySelector('.rcell--addr')!;
    expect([...addr.children].map((c) => c.textContent)).toEqual(['테헤란로 1', '지번 역삼동 823-4', '같은 땅에 3동']);
    expect(row.querySelector('.rcell--floor')!.textContent).toBe('지하 2층 ~ 9층 · 12개 층');
    // 큰 카드는 물러나고 왼쪽 작은 줄(건물을 열었을 때와 같은 처리) · 오른쪽 안내 한 줄 없음 · 보던 건물이 없어 「← 보던 건물로」 없음.
    expect(container.querySelector('section.rolecards')).toBeNull();
    expect(entry().querySelector('section.role')).not.toBeNull();
    expect(container.querySelector('.rpane-empty')).toBeNull();
    expect(container.querySelector('.rlist__back')).toBeNull();
    expect(window.localStorage.getItem('sangga.viewerRole')).toBeNull();
  });

  it('★ R3 목록에서 고르면 오른쪽 = 건물 + 「← 목록으로(테헤란로 검색)」 · 뒤로가기 한 칸 · 단추 = 뒤로가기 → 목록(굴린 자리 그대로 · 커서 「← 보던 건물로」) · 보던 건물로 = 앞으로가기 → 건물 자리 · 다시 뒤로가기 = 목록', async () => {
    serve(TWO);
    mediaAt(1280);
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const { container } = render(<App />);
    await pickGu();
    await search();
    scrollAt(500); // 목록을 내려 고른다
    fireEvent.click(screen.getByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(rlist().hidden).toBe(true);
    // 단추 글에 수는 없다(할루 🟡a — 건물 표·가게 표 수가 갈려 합친 수는 표 머리와 어긋난다).
    const back = screen.getByRole('button', { name: '목록으로(테헤란로 검색)' });
    expect(back.textContent).toBe('← 목록으로(테헤란로 검색)');
    // 누른 줄이 숨어도 커서는 BODY 가 아니라 「← 목록으로」 · 건물은 맨 위부터.
    expect(document.activeElement).toBe(back);
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
    expect(window.history.state?.sanggaTab).toBe('bld');
    expect(window.location.search).toContain(`bld=${BLD}`);

    scrollAt(30); // 건물을 조금 내려 본 뒤 목록으로
    fireEvent.click(back);
    await vi.waitFor(() => expect(app().classList.contains('app--wlist')).toBe(true));
    expect(window.history.state?.sanggaTab).toBe('base');
    expect(scrollTo).toHaveBeenLastCalledWith(0, 500);
    const toBld = container.querySelector<HTMLButtonElement>('.rlist__back')!;
    expect(toBld.textContent).toBe('← 보던 건물(테스트빌딩)로');
    expect(document.activeElement).toBe(toBld);
    // 건물은 쥐고 있다(화면에서 숨기만) · 주소 꼴 그대로.
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    expect(window.location.search).toContain(`bld=${BLD}`);

    // 「← 보던 건물로」 = 앞 칸(건물)으로 앞으로가기 — 칸을 새로 쌓지 않는다(👤 10-23 D1 · 칸이 헛돌지 않게).
    scrollAt(120);
    const len = pushes();
    fireEvent.click(toBld);
    await vi.waitFor(() => expect(app().classList.contains('app--wlist')).toBe(false));
    expect(pushes()).toBe(len);
    expect(scrollTo).toHaveBeenLastCalledWith(0, 30);
    expect(document.activeElement).toBe(container.querySelector('.rback__btn'));
    expect(window.history.state?.sanggaTab).toBe('bld');
    // 브라우저 뒤로가기 = 다시 목록(굴린 자리 120).
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'base' } }));
    });
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(scrollTo).toHaveBeenLastCalledWith(0, 120);
    // 앞으로 = 건물.
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'bld' } }));
    });
    expect(app().classList.contains('app--wlist')).toBe(false);
  });

  it('★ R2 건물을 보다가 새로 검색하면 오른쪽이 목록 + 「← 보던 건물(이름)로」 · 건물은 쥐고 있다(D1) · 새 목록은 맨 위부터 · 목록에서 다른 건물 → 그 건물', async () => {
    serve(TWO);
    mediaAt(1280);
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    render(<App />);
    await pickGu();
    await searchAndOpen();
    scrollAt(800);
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '다른동' } });
    fireEvent.submit(input.closest('form')!);
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
    expect(screen.getByRole('button', { name: '보던 건물(테스트빌딩)로' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy(); // 쥐고 있다(D1)
    fireEvent.click(await screen.findByRole('button', { name: /둘째빌딩/ }));
    expect(app().classList.contains('app--wlist')).toBe(false);
    await screen.findByRole('button', { name: '목록으로(다른동 검색)' });
  });

  it('★ D1 건물을 쥔 채 검색하면 뒤로가기 한 칸 — 목록에서 뒤로가기 = 보던 건물(사이트를 안 떠남) · 다시 검색해도 칸은 하나 · 건물 없이 검색하면 칸 0(뒤로가기 = 이전 페이지)', async () => {
    serve(TWO);
    mediaAt(1280);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    render(<App />);
    await pickGu();
    // 건물 없이 검색 — 칸 0(지금처럼 이전 페이지로).
    const len0 = pushes();
    await search();
    expect(pushes()).toBe(len0);
    expect(window.history.state?.sanggaTab).toBeUndefined();
    // 목록에서 건물을 연다(R3 — 여기서 한 칸).
    fireEvent.click(screen.getByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    const len1 = pushes(); // 목록에서 골라 한 칸(R3)
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '다른동' } });
    fireEvent.submit(input.closest('form')!);
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(pushes()).toBe(len1 + 1);
    expect(window.history.state?.sanggaTab).toBe('base');
    await screen.findByRole('button', { name: /둘째빌딩/ });
    // 목록이 선 채 또 검색 — 칸을 더 쌓지 않는다.
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    expect(pushes()).toBe(len1 + 1);
    // 브라우저 뒤로가기 = 보던 건물(「← 보던 건물로」와 같다).
    act(() => window.history.back());
    await vi.waitFor(() => expect(app().classList.contains('app--wlist')).toBe(false));
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    expect(window.history.state?.sanggaTab).toBe('bld');
    // 그 칸에서 「← 목록으로」 = 앞 칸(목록)으로 앞으로가기.
    fireEvent.click(screen.getByRole('button', { name: '목록으로(테헤란로 검색)' }));
    await vi.waitFor(() => expect(app().classList.contains('app--wlist')).toBe(true));
    expect(pushes()).toBe(len1 + 1);
  });

  it('★ D2 「목록 닫기 ✕」 — 건물을 쥐고 있으면 건물로(목록은 비움 · 「← 목록으로」 없음 · 뒤로가기 칸 헛돌지 않음) · 건물 없이 닫으면 입구 카드(LH·단가 흐름)·큰 카드로 · 커서 · 상권 목록도 닫힘', async () => {
    window.localStorage.clear(); // 큰 카드가 다시 서는지도 본다
    serve(TWO);
    mediaAt(1280);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const { container } = render(<App />);
    await pickGu();
    await search();
    const close = screen.getByRole('button', { name: '목록 닫기' });
    expect(close.textContent).toBe('목록 닫기 ✕');
    // 건물 없이 닫기 → 입구 카드 둘 · 오른쪽 안내 한 줄 · 큰 카드 · 결과 비움 · 커서 = 검색칸(검색어 그대로).
    fireEvent.click(close);
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(container.querySelector('.lh')).not.toBeNull();
    expect(container.querySelector('.flow')).not.toBeNull();
    expect(container.querySelector('.rpane-empty')).not.toBeNull();
    expect(container.querySelector('section.rolecards')).not.toBeNull();
    expect(container.querySelector('.hit')).toBeNull();
    const input = screen.getByLabelText('건물명 또는 주소') as HTMLInputElement;
    expect(input.value).toBe('테헤란로');
    expect(document.activeElement).toBe(input);
    // 건물을 쥔 채 검색 → 닫기 → 건물(뒤로가기 칸으로 돌아감 · 「← 목록으로」 없음 · 커서 = 건물 첫 단추).
    await search();
    fireEvent.click(screen.getByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    await search('다른동');
    const len = pushes();
    fireEvent.click(screen.getByRole('button', { name: '목록 닫기' }));
    // 이웃 칸(건물)으로 뒤로 간다 — 그 이동은 비동기라 표식을 기다린다.
    await vi.waitFor(() => expect(window.history.state?.sanggaTab).toBe('bld'));
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(pushes()).toBe(len);
    expect(container.querySelector('.rback')).toBeNull();
    expect(container.querySelector('.hit')).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('.takeout button'));
    // 상권 목록도 「목록 닫기」로 닫힌다(펼친 상권 접힘).
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    await vi.waitFor(() => expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: '목록 닫기' }));
    await vi.waitFor(() => expect(app().classList.contains('app--wlist')).toBe(false));
    expect(screen.getByRole('button', { name: '가짜상권' }).getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.dbld__row')).toBeNull();
  });

  it('★ R1 상권 건물 목록도 오른쪽 자리(표 · 점포 칸 = 그 땅 점포) · 왼쪽 지도 아래엔 0 · 고르면 「← 목록으로(가짜상권 상권 2곳)」 · 그 뒤 검색하면 오른쪽은 검색 목록(마지막에 연 것) · B2 숨은 상권 목록의 단추 = 앞으로 불러오기 · B1 보이는 상권 목록을 접으면 보던 건물', async () => {
    serve(TWO);
    mediaAt(1280);
    const { container } = render(<App />);
    await pickGu();
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    await screen.findByRole('button', { name: /상권빌딩/ });
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(panes().map((p) => p.hidden)).toEqual([true, false]);
    expect(entry().querySelector('.dbld, .dbld__row')).toBeNull();
    const row = rlist().querySelector('.dbld__row')!;
    // 상권 건물 목록 표는 네 칸 그대로(점포 칸 = 그 땅 점포 · 👤 「검색 결과는 세 칸」은 건물 검색 결과만).
    const dHead = [...panes()[1].querySelectorAll('.rtable__head .rcell')].map((e) => e.textContent);
    expect(dHead).toEqual(['이름', '길 주소', '층', '점포']);
    expect(row.querySelectorAll(':scope > .rcell')).toHaveLength(4);
    expect(row.querySelector('.rcell--store')!.textContent).toBe('점포 317곳');
    expect(row.querySelector('.rcell--floor')!.textContent).toBe('지하 1층 ~ 5층');
    expect(row.querySelector('.rcell--addr')!.textContent).toBe('테헤란로 7');
    expect(rlist().querySelectorAll('.dbld__row')[1].querySelector('.rcell--addr')!.textContent).toBe('테헤란로 7같은 땅에 2동');
    fireEvent.click(row);
    await screen.findByRole('heading', { name: '상권빌딩' });
    expect(screen.getByRole('button', { name: '목록으로(가짜상권 상권 2곳)' })).toBeTruthy();
    await search();
    expect(panes().map((p) => p.hidden)).toEqual([false, true]);
    expect(container.querySelector('.rlist__back')!.textContent).toBe('← 보던 건물(상권빌딩)로');
    // B2 — 상권 목록은 (검색 목록 뒤에 숨은 채) 열려 있다 → 그 상권 단추 첫 누름 = 앞으로 불러오기(접지 않는다 · 맹점 검사 B2).
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    expect(panes().map((p) => p.hidden)).toEqual([true, false]);
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(screen.getByRole('button', { name: '가짜상권' }).getAttribute('aria-expanded')).toBe('true');
    expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2);
    // B1 — 보이는 상권 목록을 접으면 남은 옛 검색 목록이 아니라 보던 건물(상권빌딩).
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    await vi.waitFor(() => expect(app().classList.contains('app--wlist')).toBe(false));
    // 보던 건물 = 상권 목록에서 고른 그 건물(주소에 그 번호 · ⓘ 층 화면 제목은 가짜 층 자료의 이름이라 번호로 본다).
    expect(document.querySelector('section.stack')).not.toBeNull();
    expect(rlist().hidden).toBe(true);
    expect(window.location.search).toContain(`bld=${BLD}7`);
    expect(screen.getByRole('button', { name: '가짜상권' }).getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.rback')).toBeNull(); // 닫힌 목록으로 가는 단추는 없다
  });

  it('★ B1 건물 → 상권 목록 열기(뒤로가기 한 칸 · D1) → 접기 = 보던 건물 · 옛 검색 목록이 서지 않는다 · 건물 없이 접으면 입구 카드', async () => {
    serve(TWO);
    mediaAt(1280);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    render(<App />);
    await pickGu();
    await searchAndOpen();
    const len = pushes();
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    await vi.waitFor(() => expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2));
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(pushes()).toBe(len + 1);
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    // 이웃 칸(건물)으로 뒤로 간다 — 비동기라 표식을 기다린다(안 기다리면 다음 시험에 popstate 가 샌다).
    await vi.waitFor(() => expect(window.history.state?.sanggaTab).toBe('bld'));
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(screen.getByRole('heading', { name: '테스트빌딩' })).toBeTruthy();
    // 닫힌 목록 대신 옛 검색 목록으로 가는 「← 목록으로」도 서지 않는다(남은 목록으로 넘어가는 갈래 0).
    expect(document.querySelector('.rback')).toBeNull();
    cleanup();
    window.history.replaceState(null, '', '/');

    // 건물 없이 — 검색한 뒤 상권 목록을 열었다 접으면 옛 검색 목록이 아니라 입구 카드(뒤로가기 칸 0 · D2 와 같은 결).
    mediaAt(1280);
    render(<App />);
    await pickGu();
    await search();
    const len0 = pushes();
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    await vi.waitFor(() => expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: '가짜상권' }));
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(document.querySelector('.lh')).not.toBeNull();
    expect(document.querySelector('.rpane-empty')).not.toBeNull();
    expect(pushes()).toBe(len0);
  });

  it('★ 후속 빈 칸 지나치기 — 검색 → 건물 → 새 검색 → 「목록 닫기」 → 뒤로 = 닫힌 옛 목록 칸에서 멈추지 않고 한 칸 더(뒤로) · 앞으로 가다 닿아도 한 칸 더(앞으로) · 목록이 살아 있으면 그 목록(지나치지 않음)', async () => {
    serve(TWO);
    mediaAt(1280);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    render(<App />);
    await pickGu();
    await searchAndOpen(); // 검색 → 건물(목록에서 골라 한 칸)
    await search('다른동'); // 새 검색(D1 — 목록 칸 하나)
    fireEvent.click(screen.getByRole('button', { name: '목록 닫기' })); // ✕ → 이웃 칸(건물)으로 뒤로
    await vi.waitFor(() => expect(window.history.state?.sanggaTab).toBe('bld'));
    expect(app().classList.contains('app--wlist')).toBe(false);
    // 이제 뒤로가기 — 뒤 칸은 첫 검색의 목록 칸인데 그 목록은 닫혔다(「목록 닫기」가 검색 결과를 비웠다) → 한 칸 더 뒤로.
    // ⓘ jsdom 은 시험들이 창 하나를 나눠 써서 진짜 뒤로가기는 앞 시험의 칸으로 샌다 — 칸 이동을 흉내 내고 앱이 부르는 것만 본다.
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    const fwd = vi.spyOn(window.history, 'forward').mockImplementation(() => {});
    const step = window.history.state?.sanggaStep as number;
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'base', sanggaStep: step - 1 } }));
    });
    expect(back).toHaveBeenCalledTimes(1);
    expect(fwd).not.toHaveBeenCalled();
    expect(app().classList.contains('app--wlist')).toBe(false); // 화면은 그대로 건물
    // 앞으로 가다 빈 목록 칸에 닿아도 한 칸 더(앞으로).
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'base', sanggaStep: step + 5 } }));
    });
    expect(fwd).toHaveBeenCalledTimes(1);
    expect(back).toHaveBeenCalledTimes(1);
    // 양성 대조 — 목록이 살아 있으면(다시 검색) 목록 칸에서 그 목록을 세운다(지나치지 않는다).
    await search('테헤란로');
    expect(app().classList.contains('app--wlist')).toBe(true);
    // 건물 칸으로(앞으로 흉내) → 다시 뒤로 목록 칸(흉내) — 목록이 살아 있으니 그 목록이 선다.
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'bld', sanggaStep: step + 9 } }));
    });
    expect(app().classList.contains('app--wlist')).toBe(false);
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { sanggaTab: 'base', sanggaStep: 0 } }));
    });
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(back).toHaveBeenCalledTimes(1);
  });

  it('★ 후속 커서 — 지도의 상권 단추로 상권 목록을 접으면 커서는 그 단추에 그대로(건물 첫 단추·검색칸으로 안 감) · 건물을 쥐었든(칸 이동) 안 쥐었든', async () => {
    serve(TWO);
    mediaAt(1280);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    render(<App />);
    await pickGu();
    // 건물 없이 — 바로 입구 카드로.
    const btn = () => screen.getByRole('button', { name: '가짜상권' });
    btn().focus();
    fireEvent.click(btn());
    await vi.waitFor(() => expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2));
    btn().focus();
    fireEvent.click(btn());
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(document.activeElement).toBe(btn());
    // 건물을 쥔 채 — 상권 목록을 열면 목록 칸(D1) · 접으면 이웃 칸(건물)으로 뒤로 가는데 커서는 그대로.
    await searchAndOpen();
    btn().focus();
    fireEvent.click(btn());
    await vi.waitFor(() => expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2));
    btn().focus();
    fireEvent.click(btn());
    await vi.waitFor(() => expect(window.history.state?.sanggaTab).toBe('bld'));
    expect(app().classList.contains('app--wlist')).toBe(false);
    expect(document.activeElement).toBe(btn());
    // 양성 대조 — 「목록 닫기」로 닫으면 커서는 건물 첫 단추(지금 규칙 그대로).
    btn().focus();
    fireEvent.click(btn());
    await vi.waitFor(() => expect(rlist().querySelectorAll('.dbld__row')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: '목록 닫기' }));
    await vi.waitFor(() => expect(window.history.state?.sanggaTab).toBe('bld'));
    await vi.waitFor(() => expect(document.activeElement).toBe(document.querySelector('.takeout button')));
  });

  it('★ 보완 3 찾는 중 — 느린 검색은 답이 오기 전 오른쪽에 「찾는 중…」 한 줄(낭독 자리 · 앞 결과·옛 줄 0) · 답이 오면 같은 자리에서 결과 · 너무 넓음·오류로 끝나도 같은 자리에서 그 안내(깜빡임 0)', async () => {
    serve(TWO);
    mediaAt(1280);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    render(<App />);
    await pickGu();
    await searchAndOpen(); // 건물을 보던 중
    // 다음 검색은 답을 손으로 늦춘다(느린 응답 흉내).
    let release: (rows: BuildingHit[]) => void = () => {};
    const slow = new Promise<{ data: BuildingHit[]; error: null }>((res) => {
      release = (rows) => res({ data: rows, error: null });
    });
    let scope: { too_broad: boolean; match_cnt: number } | null = null;
    let fail = false;
    rpc.mockImplementation((fn: string) => {
      if (fn === 'search_buildings') return fail ? Promise.reject(new Error('boom')) : slow;
      if (fn === 'search_scope') return Promise.resolve({ data: scope ? [scope] : [], error: null });
      return Promise.resolve({ data: [], error: null });
    });
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '느린동' } });
    fireEvent.submit(input.closest('form')!);
    // 오른쪽 = 목록 · 「찾는 중…」(13px 이름표 · 낭독 자리 안) · 앞 검색의 건물 줄은 숨는다 · 「← 목록으로」 글은 지금 물은 검색어.
    expect(app().classList.contains('app--wlist')).toBe(true);
    const live = rlist().querySelector<HTMLElement>('.msg--live[role="status"]')!;
    expect(live.getAttribute('aria-live')).toBe('polite');
    expect(live.querySelector('.rlist__loading')!.textContent).toBe('찾는 중…');
    expect(rlist().querySelector('.hit')).toBeNull();
    expect(screen.getByRole('button', { name: '보던 건물(테스트빌딩)로' })).toBeTruthy();
    // 너무 넓음으로 끝나도 같은 낭독 자리에서 그 안내로(목록이 사라졌다 다시 서지 않는다).
    scope = { too_broad: true, match_cnt: 1234 };
    await act(async () => {
      release([]);
      await slow;
    });
    await vi.waitFor(() => expect(live.textContent).toContain('너무 넓은 검색'));
    expect(rlist().querySelector('.msg--live[role="status"]')).toBe(live);
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(live.querySelector('.rlist__loading')).toBeNull();
    // 오류로 끝나도 오른쪽 목록 자리에서 그 안내(왼쪽 칸엔 0).
    fail = true;
    fireEvent.change(input, { target: { value: '오류동' } });
    fireEvent.submit(input.closest('form')!);
    await vi.waitFor(() => expect(rlist().querySelector('.msg--error')).not.toBeNull());
    expect(entry().querySelector('.msg--error')).toBeNull();
    expect(app().classList.contains('app--wlist')).toBe(true);
  });

  it('★ 보완 3 찾는 중 → 결과 — 답이 오면 「찾는 중…」이 결과 줄로 바뀐다 · 1023 한 열은 「찾는 중…」 0(지금 그대로)', async () => {
    serve(TWO);
    let release: () => void = () => {};
    const gate = new Promise<void>((res) => {
      release = res;
    });
    rpc.mockImplementation((fn: string) => {
      if (fn === 'list_open_sigungu') return Promise.resolve({ data: [gu()], error: null });
      if (fn === 'search_buildings') return gate.then(() => ({ data: TWO, error: null }));
      return Promise.resolve({ data: [], error: null });
    });
    mediaAt(1280);
    render(<App />);
    await pickGu();
    const input = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input, { target: { value: '테헤란로' } });
    fireEvent.submit(input.closest('form')!);
    // 첫 검색(앞 결과 0) — 답이 오기 전부터 오른쪽이 목록(숨은 자리 안의 글이 아니라 보이는 목록)이고 그 글이 「찾는 중…」.
    expect(app().classList.contains('app--wlist')).toBe(true);
    expect(rlist().hidden).toBe(false);
    expect(rlist().querySelector('.rlist__loading')!.textContent).toBe('찾는 중…');
    expect(rlist().querySelector('.rlist__pane')!.hasAttribute('hidden')).toBe(false);
    await act(async () => {
      release();
      await gate;
    });
    await screen.findByRole('button', { name: /둘째빌딩/ });
    expect(rlist().querySelector('.rlist__loading')).toBeNull();
    expect(rlist().querySelectorAll('.hit')).toHaveLength(2);
    cleanup();
    window.history.replaceState(null, '', '/');

    // 1023 한 열 — 찾는 동안에도 「찾는 중…」 0(지금 그대로 · 검색 단추가 「찾는 중…」을 말한다).
    let release2: () => void = () => {};
    const gate2 = new Promise<void>((res) => {
      release2 = res;
    });
    rpc.mockImplementation((fn: string) => {
      if (fn === 'list_open_sigungu') return Promise.resolve({ data: [gu()], error: null });
      if (fn === 'search_buildings') return gate2.then(() => ({ data: TWO, error: null }));
      return Promise.resolve({ data: [], error: null });
    });
    mediaAt(1023);
    const r = render(<App />);
    await pickGu();
    const input2 = screen.getByLabelText('건물명 또는 주소');
    fireEvent.change(input2, { target: { value: '테헤란로' } });
    fireEvent.submit(input2.closest('form')!);
    expect(r.container.querySelector('.rlist__loading')).toBeNull();
    expect(entry().querySelector('.msg--live')!.textContent).toBe('');
    await act(async () => {
      release2();
      await gate2;
    });
    await screen.findByRole('button', { name: /둘째빌딩/ });
  });

  it('★ D3 위를 줄여 올리기 — 「왼쪽 칸 접기」는 사이트 제목 줄(왼쪽 칸 안 0 · 접힌 동안 없음 · 펼치면 다시 커서) · 역할 안내 글은 보이는 줄 0 → 단추 설명(title · aria-describedby · 글자 그대로) · 1023 은 둘 다 지금 그대로', async () => {
    const NOTE = '고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제';
    mediaAt(1280);
    const { container } = render(<App />);
    const head = container.querySelector('.app__head')!;
    const fold = screen.getByRole('button', { name: '왼쪽 칸 접기' });
    expect(head.contains(fold)).toBe(true);
    expect(entry().querySelector('.entry__fold')).toBeNull();
    const note = entry().querySelector<HTMLElement>('.role__note')!;
    expect(note.hidden).toBe(true);
    expect(note.textContent).toBe(NOTE);
    const chip = entry().querySelector<HTMLButtonElement>('.role__chip')!;
    expect(chip.title).toBe(NOTE);
    expect(chip.getAttribute('aria-describedby')).toBe(note.id);
    // 접으면 제목 줄의 단추는 사라지고(띠가 대신) · 펼치면 다시 서고 커서가 간다.
    fireEvent.click(fold);
    expect(container.querySelector('.app__head .entry__fold')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '왼쪽 칸 펼치기' }));
    expect(document.activeElement).toBe(container.querySelector('.app__head .entry__fold'));
    cleanup();

    mediaAt(1023);
    const r = render(<App />);
    expect(r.container.querySelector('.entry__fold')).toBeNull();
    const note2 = entry().querySelector<HTMLElement>('.role__note')!;
    expect(note2.hidden).toBe(false);
    expect(entry().querySelector<HTMLButtonElement>('.role__chip')!.hasAttribute('title')).toBe(false);
    expect(entry().querySelector<HTMLButtonElement>('.role__chip')!.hasAttribute('aria-describedby')).toBe(false);
  });

  it('양성 대조 — 1023 한 열은 결과가 왼쪽(입구) 지금 꼴 그대로 · 오른쪽 목록 자리·표 머리·「← 목록으로」 0 · 뒤로가기 표식 0', async () => {
    serve(TWO);
    mediaAt(1023);
    const { container } = render(<App />);
    await pickGu();
    await search();
    expect(container.querySelector('section.rlist')).toBeNull();
    expect(container.querySelector('.rtable__head')).toBeNull();
    expect(entry().querySelectorAll('.hit')).toHaveLength(2);
    expect(entry().querySelector('.hit .rcell')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /테스트빌딩/ }));
    await screen.findByRole('heading', { name: '테스트빌딩' });
    expect(container.querySelector('.rback')).toBeNull();
    expect(window.history.state?.sanggaTab).toBeUndefined();
  });
});

/**
 * 오른쪽 목록 CSS(👤 2026-10-22 방법 나) — 가드 본체와 양성 대조가 이 함수를 같이 지난다.
 * 못 보는 것: 실제 픽셀(표 네 칸이 한 줄 · 말줄임 0 · 넘침 0 · 지도 높이)은 jsdom 이 못 잰다 → E2E 「CD」.
 */
function rlistRules(src: string) {
  const all = cssRules(src);
  const wide = all.filter((r) => r.media === WIDE);
  const print = all.filter((r) => r.media === PRINT);
  const has = (rs: Rule[], sel: string, re: RegExp) => rs.some((r) => r.sel.includes(sel) && re.test(r.body));
  const fourCols = /grid-template-columns:\s*minmax\(0,\s*2fr\)\s+minmax\(0,\s*2fr\)\s+minmax\([^)]*\)\s+minmax\([^)]*\)\s*(;|$)/;
  // 세 칸 = 건물 검색 결과(👤 2026-10-22 「검색 결과는 세 칸」) — 넷째 칸이 붙으면 아니다.
  const threeCols = /grid-template-columns:\s*minmax\(0,\s*2fr\)\s+minmax\(0,\s*2fr\)\s+minmax\([^)]*\)\s*(;|$)/;
  const tall = all.filter((r) => r.media === '@media screen' && /min-height:\s*44px/.test(r.body)).flatMap((r) => r.sel);
  return {
    hideOthers: has(wide, '.app--wide.app--wlist .app__main > :not(.entry):not(.lrail):not(.rlist)', /display:\s*none/),
    // 숨김은 화면 두 칸 묶음에만 — 종이(인쇄 묶음)·기본 규칙에는 `.app--wlist` 0(종이는 건물 그대로).
    hideScreenOnly: !all.some((r) => r.media !== WIDE && r.sel.some((s) => s.includes('.app--wlist'))),
    table: ['.rtable__head', '.rlist .dbld__row'].every((s) => has(wide, s, fourCols)),
    // 건물 검색 결과·가게 이름 결과는 세 칸(👤 10-22 · 10-23 D4) — 세 칸 규칙이 있고, 같은 선택자에 네 칸 규칙이 없다(덮어쓰는 꼴도 막는다).
    table3: ['.rtable__head--3', '.rlist .hit', '.rlist .stores__row'].every(
      (s) => has(wide, s, threeCols) && !has(wide, s, fourCols),
    ),
    storeRight: has(wide, '.rlist .rcell--store', /text-align:\s*right/),
    noEllipsis: ['.rlist .hit__name', '.rlist .stores__name', '.rlist .dbld__name', '.rlist .hit__addr'].every((s) =>
      has(wide, s, /white-space:\s*normal/),
    ),
    oneScroll: ['.rlist .hits', '.rlist .stores', '.rlist .dbld__list'].every(
      (s) => has(wide, s, /max-height:\s*none/) && has(wide, s, /overflow-y:\s*visible/),
    ),
    small13: ['.rlist .hit__jibun', '.rlist .hit__own', '.rlist .stores__jibun', '.rlist .dbld__warn'].every((s) =>
      has(wide, s, /font-size:\s*13px/),
    ),
    // 👤 2026-10-23 D3 — 왼쪽 칸 = 세로 flex · 높이 = 첫 화면 남은 높이(`--wide-top`) · 지도 덩어리가 자라고 지도 칸이 남는 높이를 채운다(최소 300 · 상한 640).
    fillMap:
      has(wide, '.app--wide .app__main > .entry', /height:\s*calc\(100vh - var\(--wide-top/) &&
      has(wide, '.app--wide .app__main > .entry', /flex-direction:\s*column/) &&
      has(wide, '.app--wide .app__main > .entry > .dmap:not([hidden])', /flex:\s*1 0 auto/) &&
      has(wide, '.app--wide .app__main > .entry > .dmap > .dmap__canvas', /flex:\s*1 0 300px/) &&
      has(wide, '.app--wide .app__main > .entry > .dmap > .dmap__canvas', /min-height:\s*300px/) &&
      has(wide, '.app--wide .app__main > .entry > .dmap > .dmap__canvas', /max-height:\s*640px/),
    // 「왼쪽 칸 접기」는 제목 줄 옆(D3) — 제목 줄 flex · 접기 단추가 제목 다음 · 소개 한 줄은 다음 줄 전체.
    foldInHead:
      has(wide, '.app--wide .app__head', /display:\s*flex/) &&
      has(wide, '.app--wide .app__head > .entry__fold', /order:\s*1/) &&
      has(wide, '.app--wide .app__head > .app__sub', /flex:\s*0 0 100%/),
    printOut: ['.rlist', '.rback'].every((s) => print.some((r) => r.sel.includes(s) && /display:\s*none/.test(r.body))),
    printMapH: has(print, '.app--wide .entry .dmap__canvas', /height:\s*var\(--dmap-h,\s*300px\)/),
    tall44: ['.rlist__back', '.rlist__close', '.rback__btn'].every((s) => tall.includes(s)),
  };
}

describe('PC 두 칸 오른쪽 목록 — CSS (👤 2026-10-22 방법 나)', () => {
  const css = readFileSync('src/styles.css', 'utf8');
  const ALL = {
    hideOthers: true,
    hideScreenOnly: true,
    table: true,
    table3: true,
    storeRight: true,
    noEllipsis: true,
    oneScroll: true,
    small13: true,
    fillMap: true,
    foldInHead: true,
    printOut: true,
    printMapH: true,
    tall44: true,
  };

  it('★ 목록이 서면 다른 오른쪽 덩어리 숨김(화면만) · 표 네 칸 · 점포 오른쪽 맞춤 · 말줄임 0 · 굴림 하나 · 13px · 지도 크게 · 종이 = 목록·「← 목록으로」 빠짐 + 지도 높이 = 그린 높이 · 44px', () => {
    expect(rlistRules(css)).toEqual(ALL);
  });

  it('양성 대조 — 규칙을 하나씩 걷은·되돌린 꼴을 실제로 잡는다(흔한 꼴 + 변형 꼴)', () => {
    const swap = (from: string | RegExp, to: string) => {
      const out = css.replace(from, to);
      expect(out).not.toBe(css);
      return rlistRules(out);
    };
    expect(swap('.app--wide.app--wlist .app__main > :not(.entry)', '.app--wide.app--wlistx .app__main > :not(.entry)').hideOthers).toBe(false);
    // 숨김이 종이로 샌 꼴(변형 — 인쇄 묶음 안 선택자 목록 끝).
    expect(rlistRules(`${css}\n${PRINT} {\n  .x,\n  .app--wlist .stack { display: none; }\n}`).hideScreenOnly).toBe(false);
    // 세 칸으로 줄인 꼴.
    expect(swap(/(\.rlist \.dbld__row \{\s*grid-template-columns: )[^;]*;/, '$1minmax(0, 2fr) minmax(0, 2fr) auto;').table).toBe(false);
    expect(swap('.rlist .rcell--store {', '.rlist .rcell--storex {').storeRight).toBe(false);
    // 건물 검색 결과에도 넷째(점포) 칸을 단 꼴 — 흔한 꼴(세 칸 규칙 값 되돌림) + 변형 꼴(네 칸 규칙 목록에 다시 넣음).
    expect(swap(/(\.rlist \.stores__row \{\s*grid-template-columns: [^;]*1\.4fr\));/, '$1 minmax(7em, 1.2fr);').table3).toBe(false);
    expect(swap(/(\.rtable__head,)(\r?\n {2}\.rlist \.dbld__row \{)/, '$1\n  .rlist .hit,$2').table3).toBe(false);
    expect(swap(/ {2}\.rlist,\r?\n {2}\.rback,\r?\n/, '').printOut).toBe(false);
    expect(swap('height: var(--dmap-h, 300px);', 'height: 300px;').printMapH).toBe(false);
    // 지도 칸을 고정 높이로 되돌린 꼴(흔한 꼴) · 지도 칸 규칙 무게를 낮춰 `> *`(flex: none)에 지는 꼴(변형 꼴 — 선택자만 바꿈).
    expect(swap(/ {4}flex: 1 0 300px;(\r?\n)/, '    height: 300px;$1').fillMap).toBe(false);
    expect(swap('.app--wide .app__main > .entry > .dmap > .dmap__canvas {', '.app--wide .entry .dmap__canvas {').fillMap).toBe(false);
    expect(swap('.app--wide .app__head > .entry__fold {', '.app--wide .app__head > .entry__foldx {').foldInHead).toBe(false);
  });
});
