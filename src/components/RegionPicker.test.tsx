import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { RegionPicker } from './RegionPicker';
import { SIDOS, OPEN_SIDO_CODES, isOpenSido, openRegionLabel, isOpenPnu } from '../lib/regions';

/**
 * 지역 게이트 테스트 (결정 0006).
 *
 * 핵심 불변식은 하나다: **전국을 다 보여주되 열린 곳만 열려 있다고 말한다.**
 * 지역명을 테스트에 박지 않는다 — 박으면 지역을 열 때 테스트가 같이 거짓말을 한다.
 */

afterEach(cleanup);

describe('regions.ts', () => {
  it('전국 17개 시도를 담는다', () => {
    expect(SIDOS).toHaveLength(17);
  });

  it('시도 코드는 2자리 숫자이고 중복이 없다', () => {
    const codes = SIDOS.map((s) => s.code);
    expect(new Set(codes).size).toBe(codes.length);
    for (const c of codes) expect(c).toMatch(/^\d{2}$/);
  });

  it('열린 코드는 반드시 목록 안에 있는 시도여야 한다', () => {
    // 오타로 없는 코드를 열어 두면 화면엔 아무 표시도 안 나고 조용히 무시된다.
    const known = new Set(SIDOS.map((s) => s.code));
    for (const c of OPEN_SIDO_CODES) expect(known.has(c)).toBe(true);
  });

  it('openRegionLabel 은 열린 시도 이름을 이어 붙인다', () => {
    const expected = SIDOS.filter((s) => isOpenSido(s.code))
      .map((s) => s.name)
      .join('·');
    expect(openRegionLabel()).toBe(expected);
  });

  it('isOpenPnu 는 PNU 앞 2자리로 판정한다', () => {
    const open = OPEN_SIDO_CODES[0];
    expect(isOpenPnu(open + '68010100108230004')).toBe(true);
    expect(isOpenPnu('9999999999999999999')).toBe(false);
    expect(isOpenPnu(null)).toBe(false);
    expect(isOpenPnu('')).toBe(false);
  });
});

describe('RegionPicker', () => {
  it('잠긴 지역도 숨기지 않고 17개를 전부 보여준다', () => {
    render(<RegionPicker />);
    for (const s of SIDOS) {
      expect(screen.getByRole('button', { name: new RegExp(s.name) })).toBeTruthy();
    }
  });

  it('열린 지역과 잠긴 지역을 눈에 보이게 가른다', () => {
    render(<RegionPicker />);
    for (const s of SIDOS) {
      const btn = screen.getByRole('button', { name: new RegExp(s.name) });
      if (isOpenSido(s.code)) {
        expect(btn.className).toContain('region__chip--on');
      } else {
        expect(btn.className).toContain('region__chip--off');
        expect(btn.getAttribute('aria-label')).toMatch(/준비 중/);
      }
    }
  });

  it('잠긴 칩에는 aria-disabled 를 걸지 않는다 — 눌러야 안내에 닿을 수 있어서다', () => {
    // aria-disabled=true 면 보조기술 사용자가 "비활성"으로 안내받아 클릭을 시도하지
    // 않을 수 있다. 이 컴포넌트는 일부러 눌리게 설계됐다(상단 주석 4-9행).
    render(<RegionPicker />);
    for (const s of SIDOS) {
      const btn = screen.getByRole('button', { name: new RegExp(s.name) });
      expect(btn.getAttribute('aria-disabled')).toBeNull();
    }
  });

  it('잠긴 지역을 누르면 "준비 중"이라고 알려준다', () => {
    const locked = SIDOS.find((s) => !isOpenSido(s.code))!;
    render(<RegionPicker />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(locked.name) }));

    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('준비 중');
    // 대안을 반드시 함께 알려준다 — "안 된다"만 말하면 사용자가 갈 곳이 없다.
    expect(dialog.textContent).toContain(openRegionLabel());
  });

  it('열린 지역을 누르면 준비 중이라고 하지 않는다', () => {
    const open = SIDOS.find((s) => isOpenSido(s.code))!;
    render(<RegionPicker />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(open.name) }));
    expect(screen.getByRole('dialog').textContent).not.toContain('준비 중');
  });

  it('닫기 버튼으로 팝업을 닫을 수 있다', () => {
    const locked = SIDOS.find((s) => !isOpenSido(s.code))!;
    render(<RegionPicker />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(locked.name) }));
    expect(screen.queryByRole('dialog')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Esc 로도 닫힌다 — 빠져나갈 길이 하나뿐이면 안 된다', () => {
    const locked = SIDOS.find((s) => !isOpenSido(s.code))!;
    render(<RegionPicker />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(locked.name) }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('바깥을 눌러도 닫힌다', () => {
    const locked = SIDOS.find((s) => !isOpenSido(s.code))!;
    const { container } = render(<RegionPicker />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(locked.name) }));
    fireEvent.click(container.querySelector('.modal__back')!);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('팝업 안을 눌렀을 때는 닫히지 않는다', () => {
    const locked = SIDOS.find((s) => !isOpenSido(s.code))!;
    render(<RegionPicker />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(locked.name) }));
    fireEvent.click(screen.getByRole('dialog'));
    expect(screen.queryByRole('dialog')).toBeTruthy();
  });
});
