import { useEffect, useState } from 'react';
import { supabase, FLOOR_STACK_VIEW, COVERAGE_STATS_VIEW } from '../lib/supabase';
import type { BuildingHit, CoverageStats, FloorRow } from '../types';
import { formatArea, formatApproveDate, formatFloor, formatQuarter, oneInEvery } from '../lib/format';

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
  /** 각주에 쓸 집계. 건물과 무관하므로 처음 한 번만 읽는다. */
  const [stats, setStats] = useState<CoverageStats | null>(null);

  useEffect(() => {
    let cancelled = false;
    supabase
      .from(COVERAGE_STATS_VIEW)
      .select('*')
      .limit(1)
      .then(({ data, error: err }) => {
        if (cancelled) return;
        if (err || !data || data.length === 0) {
          // 각주 숫자는 없어도 화면 본체는 정상이다. 실패해도 옛 숫자를 되살리지 않는다
          // — 틀린 숫자를 보여주는 것이 숫자를 안 보여주는 것보다 나쁘다.
          console.warn('각주 집계 조회 실패 — 숫자 없이 표시합니다', err);
          return;
        }
        const row = data[0] as CoverageStats;
        setStats({
          snapshot_ym: row.snapshot_ym,
          store_cnt: Number(row.store_cnt),
          floor_missing_cnt: Number(row.floor_missing_cnt),
          floor_missing_pct: Number(row.floor_missing_pct),
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
        if (err) {
          // 원문에는 내부 표 이름이 섞여 나올 수 있다 — 콘솔에만 남긴다.
          console.error('층 정보 조회 실패', err);
          setError('층 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
        } else setFloors((data ?? []) as FloorRow[]);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [building.bld_id]);

  if (loading) return <p className="msg">층 정보를 불러오는 중…</p>;
  if (error) return <p className="msg msg--error">{error}</p>;
  if (floors.length === 0) return <p className="msg">이 건물에는 층 정보가 없습니다.</p>;

  const head = floors[0];
  const maxArea = Math.max(...floors.map((f) => f.floor_area_m2 ?? 0), 1);
  const totalStores = floors.reduce((sum, f) => sum + (f.store_cnt ?? 0), 0);

  // 각주 숫자는 DB에서 계산해 온다. 못 불러왔으면 숫자를 빼고 경고만 남긴다
  // — 옛 숫자로 되돌리면 이 코드가 고치려던 문제(화면만 틀려지는 것)가 그대로 살아난다.
  const missingEvery = stats ? oneInEvery(stats.floor_missing_pct) : null;
  const missingPhrase =
    stats && missingEvery
      ? `약 ${missingEvery}곳 중 1곳(${stats.floor_missing_pct}%)`
      : '적지 않은 수';
  const basisPhrase = stats
    ? `근거: ${formatQuarter(stats.snapshot_ym)} 상권정보 ${stats.store_cnt.toLocaleString('ko-KR')}곳 기준.`
    : '근거: 상권정보 최신 분기 기준.';

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
        적히지 않은 점포가 <strong>{missingPhrase}</strong>인데, 이런 점포는 어느 층에도 붙지
        않아 목록에서 통째로 빠집니다. ② <strong>겹침</strong> — 한 주소를 여러 점포가 나눠 쓰는
        공유오피스나 같은 땅의 옆 동 점포가 함께 잡혀 실제보다 많아 보일 수 있습니다.
        <br />
        {/*
          이 숫자들은 뷰 v_coverage_stats에서 읽어 온다. v_floor_stack의 점포가
          `snapshot_ym = (select max(snapshot_ym) from unit_business)`로 최신 분기를 자동
          추종하므로, 각주도 같은 기준으로 따라가야 새 분기 적재 때 화면만 틀려지지 않는다.
          (예전에는 "32.9%·64,239곳"이 문자열로 박혀 있었다.)
        */}
        {basisPhrase}
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
