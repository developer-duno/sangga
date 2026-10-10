import { useState } from 'react';
import type { RecentPrinted as RecentPrintedEntry } from '../lib/recentPrintedStore';

/**
 * 중개사 「최근 뽑은 건물」 접힌 줄(결정 0036 결정 18 ⑥⑩ · 「이 기기 저장」 ②③④).
 *
 * 검색창 덩어리 안, `BuildingSearch` 바로 뒤에 선다(App 이 역할 = 중개사일 때만 그린다).
 * ⛔ 목록이 비면 줄 자체를 안 그린다 · 처음엔 접혀 있다(눌러 펼침).
 * ⛔ 종이에서 빠진다(`.recent` — 누르는 장치 · styles.css 인쇄 블록).
 * ⓘ 목록·지우기의 주인은 App(저장소와 맞춘 상태)이다 — 이 부품은 그리기만 한다.
 */
type Props = {
  items: readonly RecentPrintedEntry[];
  onPick: (item: RecentPrintedEntry) => void;
  onClear: () => void;
};

export function RecentPrinted({ items, onPick, onClear }: Props) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <section className="recent" aria-label="최근 뽑은 건물">
      <button
        type="button"
        className="recent__toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        최근 뽑은 건물 {items.length} <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="recent__body">
          <ul className="recent__list">
            {items.map((r) => (
              <li key={r.bld_id}>
                <button type="button" className="recent__row" onClick={() => onPick(r)}>
                  <span className="recent__name">{r.bld_nm || '(이름 없는 건물)'}</span>
                  <span className="recent__addr">{r.road_addr || '주소 없음'}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="recent__note">이 기기에만 저장 · 서버로 보내지 않음</p>
          <p className="recent__note">여럿이 쓰는 사무소 컴퓨터라면 다 본 뒤 지워 주세요</p>
          <button type="button" className="recent__clear" onClick={onClear}>
            지우기
          </button>
        </div>
      )}
    </section>
  );
}
