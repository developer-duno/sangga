import { useEffect, useState } from 'react';
import { supabase, FLOOR_STACK_VIEW } from '../lib/supabase';
import type { BuildingHit, FloorRow } from '../types';
import { formatArea, formatApproveDate, formatFloor } from '../lib/format';

/**
 * 층별 스택 뷰 — 이 서비스의 시그니처 화면(§8.6).
 *
 * 위가 고층, 아래가 지하로 쌓는다. 막대 길이는 그 층의 임대 가능 면적에 비례한다.
 *
 * ⚠️ 지금 채울 수 있는 칸은 층·용도·면적·점포 4개뿐이다. 추정 시세는 Phase 3,
 *    공실 이력은 Phase 5 산출물이라 여기서는 그리지 않는다(빈칸을 그럴듯하게
 *    채우면 없는 근거를 있는 것처럼 보이게 만든다).
 */

type Props = { building: BuildingHit };

export function FloorStack({ building }: Props) {
  const [floors, setFloors] = useState<FloorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openFloor, setOpenFloor] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setOpenFloor(null);

    supabase
      .from(FLOOR_STACK_VIEW)
      .select('*')
      .eq('bld_id', building.bld_id)
      .order('floor_no', { ascending: false })
      .then(({ data, error: err }) => {
        if (cancelled) return;
        if (err) setError(err.message);
        else setFloors((data ?? []) as FloorRow[]);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [building.bld_id]);

  if (loading) return <p className="msg">층 정보를 불러오는 중…</p>;
  if (error) return <p className="msg msg--error">불러오기 실패: {error}</p>;
  if (floors.length === 0) return <p className="msg">이 건물에는 층 정보가 없습니다.</p>;

  const head = floors[0];
  const maxArea = Math.max(...floors.map((f) => f.floor_area_m2 ?? 0), 1);
  const totalStores = floors.reduce((sum, f) => sum + (f.store_cnt ?? 0), 0);

  return (
    <section className="stack">
      <header className="stack__head">
        <h2 className="stack__title">{head.bld_nm || '(이름 없는 건물)'}</h2>
        <p className="stack__addr">{head.road_addr || '주소 없음'}</p>
        <dl className="stack__facts">
          <div>
            <dt>사용승인</dt>
            <dd>{formatApproveDate(head.approve_date)}</dd>
          </div>
          <div>
            <dt>건물 종류</dt>
            <dd>{head.is_jiphap ? '집합건물' : '일반건물'}</dd>
          </div>
          <div>
            <dt>층 수</dt>
            <dd>{floors.length}개</dd>
          </div>
          <div>
            <dt>점포(참고)</dt>
            <dd>{totalStores.toLocaleString('ko-KR')}곳</dd>
          </div>
        </dl>
      </header>

      {head.bld_cnt_in_pnu > 1 && (
        <p className="warn">
          <strong>이 땅에 건물이 {head.bld_cnt_in_pnu}동 있습니다.</strong> 점포는 호수가 아니라
          “땅 + 층”으로만 붙일 수 있어서(상권정보에 호 정보가 없음), 아래 점포 목록에 옆 동
          점포가 섞여 보일 수 있습니다.
        </p>
      )}

      <ol className="floors">
        {floors.map((f) => {
          // 면적이 아예 없는 층(그 층이 전부 연면적 제외분 — 전체의 약 3%)에는 막대를
          // 그리지 않는다. 최소 폭 2%를 강제하면 "면적 미상"이 "아주 좁은 층"처럼 보인다.
          const hasArea = f.floor_area_m2 != null;
          const ratio = hasArea ? f.floor_area_m2! / maxArea : 0;
          const isOpen = openFloor === f.floor_no;
          return (
            <li key={f.floor_no} className={`floor${f.floor_no < 0 ? ' floor--under' : ''}`}>
              <button className="floor__row" onClick={() => setOpenFloor(isOpen ? null : f.floor_no)}>
                <span className="floor__label">{formatFloor(f.floor_no, f.floor_label)}</span>
                <span className="floor__bar">
                  {hasArea && (
                    <span className="floor__fill" style={{ width: `${Math.max(ratio * 100, 2)}%` }} />
                  )}
                </span>
                <span className="floor__use">{f.main_use || '용도 미상'}</span>
                <span className="floor__area">{formatArea(f.floor_area_m2)}</span>
                <span className="floor__stores">
                  {f.store_cnt ? `점포 ${f.store_cnt}` : '—'}
                </span>
                <span className="floor__caret">{isOpen ? '▲' : '▼'}</span>
              </button>

              {isOpen && <FloorDetail floor={f} />}
            </li>
          );
        })}
      </ol>

      <p className="grade">
        <span className="grade__badge">D등급 · 간접 추론</span>
        점포 목록은 호수가 아니라 <strong>“땅 + 층”</strong>으로 맞춘 값입니다. 어느 호실인지까지는
        알 수 없습니다. 면적·용도는 건축물대장 <strong>실측(A등급)</strong>입니다.
      </p>
      <p className="grade grade--sub">
        <strong>점포 수는 실제와 다를 수 있습니다.</strong> ① <strong>빠짐</strong> — 상권정보에 층이
        적히지 않은 점포가 <strong>약 3곳 중 1곳(32.9%)</strong>인데, 이런 점포는 어느 층에도 붙지
        않아 목록에서 통째로 빠집니다. ② <strong>겹침</strong> — 한 주소를 여러 점포가 나눠 쓰는
        공유오피스나 같은 땅의 옆 동 점포가 함께 잡혀 실제보다 많아 보일 수 있습니다.
        <br />
        근거: 강남 2026년 1분기 상권정보 64,239곳 기준(2026-08-08 실측).
      </p>
    </section>
  );
}

function FloorDetail({ floor }: { floor: FloorRow }) {
  const uses = floor.uses ?? [];
  const stores = floor.stores ?? [];

  return (
    <div className="detail">
      <div className="detail__col">
        <h3 className="detail__h">용도별 구획 {uses.length > 0 && `(${uses.length})`}</h3>
        {uses.length === 0 ? (
          <p className="detail__none">구획 정보 없음</p>
        ) : (
          <ul className="detail__list">
            {uses.map((u, i) => (
              <li key={i}>
                <span className="detail__name">{u.use || '용도 미상'}</span>
                {u.detail && <span className="detail__sub">{u.detail}</span>}
                <span className="detail__val">{formatArea(u.area_m2)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="detail__note">
          전체 면적 {formatArea(floor.floor_area_gross_m2)} 중 계단실·물탱크실 등을 뺀 값이
          위의 {formatArea(floor.floor_area_m2)}입니다.
        </p>
      </div>

      <div className="detail__col">
        <h3 className="detail__h">점포 {stores.length > 0 && `(${stores.length})`}</h3>
        {stores.length === 0 ? (
          <p className="detail__none">이 층에 등록된 점포가 없습니다</p>
        ) : (
          <ul className="detail__list">
            {stores.map((s, i) => (
              <li key={i}>
                <span className="detail__name">{s.name || '상호 미상'}</span>
                <span className="detail__sub">{s.cat || '업종 미상'}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
