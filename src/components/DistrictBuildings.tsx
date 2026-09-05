import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { supabase } from '../lib/supabase';
import { DISTRICT_BUILDINGS_FN, DISTRICT_BUILDINGS_PAGE, PARCEL_BUILDINGS_FN } from '../lib/appConstants';
import {
  hasMore,
  isDistrictLandList,
  isParcelBuildingList,
  landToHit,
  landsSummary,
  parcelBuildingToHit,
} from '../lib/districtBuildings';
import { describeRange } from '../lib/format';
import type { BuildingHit, DistrictLand, ParcelBuilding } from '../types';

/**
 * "이 상권의 건물" 목록 — 지도에서 상권 이름을 누르면 그 아래에 펼쳐진다.
 *
 * 왜 있나
 * -------
 * 지도는 여태 상권 **이름과 유형만** 알려주고 끝나는 막다른 길이었다. 창업자는 건물
 * 이름을 모르므로 검색으로 들어올 수 없다 — 그들이 아는 것은 "이 동네"뿐이다.
 * 이 목록이 그 길을 잇는다: 상권 → 건물 → (누르면) 층별 화면.
 *
 * ⛔ 한 줄은 **건물이 아니라 땅(필지)** 이다
 * ------------------------------------------
 * 점포 수를 필지 단위로만 셀 수 있어서다(`unit_business.unit_id` 295만 행 전량 NULL).
 * 건물로 줄세우면 한 땅의 동들이 같은 점포 수를 **복사해** 갖는다 — 명동 상위 10에
 * `롯데호텔 및 백화점 317` 이 네 줄 연달아 나온다(본관동·신관동·부속건물 2동).
 * 한 땅에 동이 여럿인 것은 예외가 아니라 정상이다: 전국 20동 초과 637곳(21,635동),
 * 최대 168동(헬리오시티) · 창덕궁 157 · 서울대 154 · 경복궁 140.
 * 그래서 땅이 한 줄이고, 여러 동이면 눌러서 펼친다.
 *
 * ⛔ 점포 수 문구에 "이 건물"이라 쓰지 않는다 — 층별 화면의 점포 칸과 **세는 대상이
 *    다르다**(거기는 그 건물의 층에 붙은 점포). 흐리면 두 화면이 서로 다른 말을 하는
 *    것처럼 보인다(둘레의 업종 분포 카드와 같은 규칙).
 */
type Props = {
  districtId: string;
  districtNm: string;
  /** 건물을 고르면 검색 결과를 골랐을 때와 **똑같은 길**로 들어간다(App 의 같은 handler). */
  onSelect: (hit: BuildingHit) => void;
  selectedBldId: string | null;
};

/**
 * 한 땅을 펼쳤을 때의 상태. 셋을 갈라 둬야 물레방아가 영영 돌지 않는다.
 *
 * ⓘ 'loading' 만 **요청 번호(`token`)** 를 든다 — 답이 도착했을 때 "지금 기다리는 그 요청의
 *   답인가"를 가리려면 시각이 아니라 **신원**이 필요하기 때문이다(아래 `settle` 주석).
 */
type Expanded =
  | { at: 'loading'; token: number }
  | { at: 'done'; rows: ParcelBuilding[] }
  | { at: 'failed' };

export function DistrictBuildings({ districtId, districtNm, onSelect, selectedBldId }: Props) {
  const [lands, setLands] = useState<DistrictLand[] | null>(null);
  const [loading, setLoading] = useState(true);
  /**
   * 못 읽었다.
   *
   * ⛔ 형제 카드들(LH 공고·업종 분포)은 못 읽으면 **통째로 생략**하는데 여기는 다르다 —
   *    저기는 저절로 뜨는 곁다리라 조용히 빠져도 아무도 기다리지 않지만, 여기는 사람이
   *    **직접 누른** 결과다. 아무 반응이 없으면 고장으로 읽는다. 그래서 "못 불러왔다"고
   *    적는다. ⓘ "건물이 없다"고는 여전히 말하지 않는다 — 모르는 것과 없는 것은 다르다.
   */
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, Expanded>>({});
  /**
   * 이 목록 안에서 쓰는 id 의 공통 앞머리 — 머릿글 하나와 줄마다의 펼침 칸 하나씩에 쓴다.
   *
   * ⚠️ 훅(`useId`)을 줄마다 부를 수는 없다(map 안은 훅을 부를 수 없는 자리다). 그래서
   *    **앞머리 하나를 받아 땅(pnu)을 붙여** 줄별 id 를 만든다 — pnu 는 이 목록 안에서 유일하다.
   */
  const idBase = useId();
  const headId = `${idBase}-head`;
  /**
   * 펼치기 요청에 붙이는 일련번호. 줄이 아니라 **요청**을 세므로 목록 전체가 하나를 공유한다
   * (같은 줄을 접었다 펼치면 번호가 다른 두 요청이 된다 — 그게 이 번호의 존재 이유다).
   */
  const nextToken = useRef(0);
  /**
   * 늦게 도착한 **옛 상권**의 응답이 새 상권 목록을 건드리는 것을 막는다.
   *
   * ⛔ 처음 불러오기와 '더 보기'가 **같은 신호를 봐야** 한다. 예전에는 처음 불러오기에만
   *    가드가 있어서, 더 보기를 누른 직후 지도에서 다른 상권을 누르면 옛 상권의 2쪽이
   *    새 상권 이름 아래 붙었다. 더 나쁜 경로도 있었다 — 새 목록이 아직 비어 있는
   *    순간에 옛 응답이 닿으면 `prev === null` 가지를 타서 **목록 전체가 옛 상권 것으로
   *    바뀌었다**(이어 붙기가 아니라 바꿔치기).
   * ⓘ 방식은 BuildingSearch 의 `latestRun` 과 **글자 그대로 같다** — 이 레포가 이미 쓰는
   *   패턴을 재사용한다(경합 가드를 화면마다 다르게 만들면 어느 쪽이 옳은지 흐려진다).
   */
  const latestRun = useRef(0);

  /** 한 쪽(50곳)을 받아 뒤에 잇는다. `offset` 이 0 이면 처음부터 새로 담는다. */
  const load = useCallback(
    (offset: number) => {
      const runId = ++latestRun.current;
      setLoading(true);
      return supabase
        .rpc(DISTRICT_BUILDINGS_FN, {
          p_district_id: districtId,
          p_limit: DISTRICT_BUILDINGS_PAGE,
          p_offset: offset,
        })
        .then(({ data, error }) => {
          if (runId !== latestRun.current) return; // 그새 상권이 바뀌었다
          setLoading(false);
          // ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이
          //    목록은 **지도 안**에 있어 터지면 지도까지 함께 사라진다.
          if (error || !isDistrictLandList(data)) {
            console.warn('상권 건물 목록 조회 실패', error ?? data);
            setFailed(true);
            return;
          }
          setFailed(false);
          setLands((prev) => (offset === 0 || prev === null ? data : [...prev, ...data]));
        });
    },
    [districtId],
  );

  useEffect(() => {
    // 다른 상권을 누르면 앞의 것을 통째로 비운다 — 안 그러면 새 목록을 기다리는 동안
    // **옛 상권의 건물들이 새 상권 이름 아래** 서 있다.
    setLands(null);
    setExpanded({});
    setFailed(false);
    const runId = ++latestRun.current;
    setLoading(true);
    supabase
      .rpc(DISTRICT_BUILDINGS_FN, {
        p_district_id: districtId,
        p_limit: DISTRICT_BUILDINGS_PAGE,
        p_offset: 0,
      })
      .then(({ data, error }) => {
        if (runId !== latestRun.current) return;
        setLoading(false);
        if (error || !isDistrictLandList(data)) {
          console.warn('상권 건물 목록 조회 실패', error ?? data);
          setFailed(true);
          return;
        }
        setLands(data);
      });
    // ⓘ 정리(cleanup) 함수를 두지 않는다. 상권이 바뀌면 **다음 effect 가 번호를 올리므로**
    //   날아가 있던 옛 요청은 그 순간 저절로 무효가 된다 — 정리에서 한 번 더 올리는 것은
    //   같은 일을 두 번 하는 셈이다. 이 목록이 통째로 사라질 때(언마운트) 늦은 응답이
    //   닿는 경우는 React 18 부터 아무 일도 일어나지 않는다(setState 가 무시된다).
  }, [districtId]);

  /** "같은 땅에 N동"을 펼친다. 이미 받아 뒀으면 접는다(다시 묻지 않는다). */
  function toggle(land: DistrictLand) {
    const cur = expanded[land.pnu];
    if (cur && cur.at !== 'failed') {
      setExpanded(({ [land.pnu]: _drop, ...rest }) => rest);
      return;
    }
    const myToken = ++nextToken.current;
    setExpanded((prev) => ({ ...prev, [land.pnu]: { at: 'loading', token: myToken } }));
    /**
     * 답이 왔을 때 **내가 보낸 바로 그 요청의 답일 때만** 쓴다.
     *
     * ⛔ 여기는 위의 세대 번호로 못 잡는 별개 경합이다(세대는 상권 단위인데 여기는 줄 단위).
     *    그냥 쓰면 두 가지가 어긋난다: ① 펼치는 중에 사용자가 **접으면** 답이 도착하며
     *    **저절로 되펼쳐진다**(사용자 뜻을 덮는다) ② 상권이 바뀌어 `setExpanded({})` 로
     *    비운 뒤 옛 답이 닿으면 **아무도 안 누른 줄이 펼쳐진 채** 나타난다.
     * ⛔ **"아직 'loading' 인가"만 보는 것으로는 모자란다**(2026-09-05 감사). 펼쳤다 접고 다시
     *    펼치면 같은 줄을 가리키는 요청이 둘(A·B) 날아가 있는데, 이때 먼저 닿은 **A 의 실패**가
     *    B 의 'loading' 을 'failed' 로 덮어 버리고, 뒤이어 닿은 **B 의 성공은 더 이상 'loading'
     *    이 아니라며 버려진다** — 자료는 왔는데 화면은 오류를 적는 상태다. 그래서 상태의
     *    이름만이 아니라 **요청 번호**까지 본다(내 번호일 때만 반영).
     */
    const settle = (next: Expanded) =>
      setExpanded((prev) => {
        const at = prev[land.pnu];
        return at?.at === 'loading' && at.token === myToken ? { ...prev, [land.pnu]: next } : prev;
      });
    supabase.rpc(PARCEL_BUILDINGS_FN, { p_pnu: land.pnu }).then(({ data, error }) => {
      if (error || !isParcelBuildingList(data)) {
        console.warn('땅의 동 목록 조회 실패', error ?? data);
        settle({ at: 'failed' });
        return;
      }
      settle({ at: 'done', rows: data });
    });
  }

  /*
    ⓘ 이 조각의 메시지 역할 규약 — **알림은 `role="status"`, 실패는 `role="alert"`** 한 벌로만 쓴다.

    왜 갈랐나: 이 목록은 사람이 **직접 누른** 결과라 결과가 화면에 나타나는 것을 읽어 주는
    기기도 알아야 한다. 그런데 둘의 급함이 다르다 — "불러오는 중"은 하던 말을 끊으면서까지
    알릴 일이 아니고(`status` = 하던 말이 끝난 뒤), "못 불러왔다"는 그 자리에서 알려야
    다음 행동을 정할 수 있다(`alert` = 즉시). 둘 다 `alert` 로 두면 로딩 문구가 매번 말을
    끊고, 둘 다 `status` 면 오류를 나중에야 듣는다.
    ⛔ 새 메시지를 더할 때도 이 두 가지 밖으로 나가지 않는다(`aria-live` 를 손으로 붙이지
       않는다 — 두 역할이 이미 그 뜻을 담고 있고, 섞이면 어느 쪽이 옳은지 흐려진다).
  */
  if (loading && lands === null) {
    return (
      <p className="dbld__msg" role="status">
        {districtNm}의 건물을 불러오는 중…
      </p>
    );
  }

  if (failed && lands === null) {
    return (
      <p className="dbld__msg dbld__msg--error" role="alert">
        건물 목록을 불러오지 못했습니다.
      </p>
    );
  }

  if (lands === null) return null;

  if (lands.length === 0) {
    // ⓘ 상권 1,687곳 중 10곳은 실제로 건물이 한 동도 없다(라이브 실측). 빈 목록을 띄우고
    //   "왜 아무것도 없지?" 하게 두는 대신, 자료가 없다고 말한다(지도의 빈 구와 같은 규칙).
    return (
      <p className="dbld__msg" role="status">
        이 상권에는 아직 건물 자료가 없습니다.
      </p>
    );
  }

  return (
    <div className="dbld">
      <p className="dbld__head" id={headId}>
        <strong>{districtNm}</strong>의 건물 — {landsSummary(lands)}
      </p>
      {/* ⛔ 무엇을 센 숫자인지 밝힌다. 이 값은 그 **땅**의 점포 수라, 한 땅에 여러 동이
          서 있으면 그 동들이 같은 수를 나눠 갖는 것이 아니라 함께 쓴다. */}
      <p className="dbld__note">
        점포 수가 많은 곳부터입니다. 점포 수는 <strong>그 땅 전체</strong>를 센 것이라, 한 땅에
        여러 동이 서 있으면 그 동들이 같은 수를 함께 씁니다.
      </p>

      {/* ⓘ 목록에 **이름표를 붙인다** — 예전에는 `id` 만 달아 두고 아무도 가리키지 않아
          읽어 주는 기기에는 그냥 "목록"이었다. 머릿글이 이미 "◯◯의 건물 — N곳"이라
          말하므로 그 글을 이름으로 빌린다(글을 두 번 적지 않는다). */}
      <ul className="dbld__list" aria-labelledby={headId}>
        {lands.map((land) => {
          const many = land.bld_cnt_in_pnu > 1;
          const open = expanded[land.pnu];
          /** 이 줄이 펼치는 칸의 id. 훅을 줄마다 못 부르므로 앞머리에 땅을 붙여 만든다. */
          const panelId = `${idBase}-${land.pnu}`;
          return (
            <li key={land.pnu}>
              <button
                type="button"
                className={`dbld__row${land.bld_id === selectedBldId ? ' dbld__row--on' : ''}`}
                aria-expanded={many ? open !== undefined && open.at !== 'failed' : undefined}
                /* ⚠️ 동이 하나뿐인 줄은 **펼치는 버튼이 아니라 고르는 버튼**이다 — 열 칸이
                   영영 없으므로 `aria-controls` 도 주지 않는다(없는 곳을 가리키면 거짓말이 된다).
                   ⓘ 여러 동인 줄에서는 펼친 순간 **셋 중 하나가 반드시 그 id 를 달고 선다**
                     (불러오는 중 · 못 불러왔다 · 동 목록). 그래서 펼쳐 놓고 가리킬 곳이 없는
                     순간이 생기지 않는다 — 접혀 있을 때만 비어 있고, 그때는 `aria-expanded`
                     가 이미 '안 펼쳐졌다'고 말한다. */
                aria-controls={many ? panelId : undefined}
                onClick={() => (many ? toggle(land) : onSelect(landToHit(land)))}
              >
                <span className="dbld__name">{land.bld_nm || '(이름 없는 건물)'}</span>
                <span className="dbld__addr">{land.road_addr || '주소 없음'}</span>
                <span className="dbld__meta">
                  점포 {land.store_cnt.toLocaleString('ko-KR')}곳 · {describeRange(landToHit(land))}
                  {many && <span className="dbld__warn"> · 같은 땅에 {land.bld_cnt_in_pnu}동</span>}
                </span>
              </button>

              {many && open?.at === 'loading' && (
                <p className="dbld__msg" id={panelId} role="status">
                  동 목록을 불러오는 중…
                </p>
              )}
              {many && open?.at === 'failed' && (
                <p className="dbld__msg dbld__msg--error" id={panelId} role="alert">
                  동 목록을 불러오지 못했습니다.
                </p>
              )}
              {many && open?.at === 'done' && (
                <ul className="dbld__dongs" id={panelId}>
                  {open.rows.map((b) => (
                    <li key={b.bld_id}>
                      <button
                        type="button"
                        className={`dbld__dong${b.bld_id === selectedBldId ? ' dbld__dong--on' : ''}`}
                        onClick={() => onSelect(parcelBuildingToHit(land, b))}
                      >
                        {/* 이름은 같은 일이 흔해서(롯데호텔 4동 전부 '롯데호텔 및 백화점')
                            동명칭과 층 범위가 실제로 가르는 값이다. */}
                        <span className="dbld__dong-nm">
                          {b.dong_nm || b.bld_nm || '(이름 없는 동)'}
                        </span>
                        <span className="dbld__dong-meta">
                          {describeRange(parcelBuildingToHit(land, b))} · {b.floor_cnt}개 층
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      {hasMore(lands) && (
        <button
          type="button"
          className="dbld__more"
          disabled={loading}
          onClick={() => load(lands.length)}
        >
          {loading ? '불러오는 중…' : '더 보기'}
        </button>
      )}
      {/* 더 받다가 실패한 경우 — 이미 받은 목록은 그대로 두고 그 사실만 알린다. */}
      {failed && lands.length > 0 && (
        <p className="dbld__msg dbld__msg--error" role="alert">
          더 불러오지 못했습니다.
        </p>
      )}

      {/* ⛔ 경계 판정은 건물 화면의 "속한 상권"과 **같은 자**를 쓴다. 그 사실을 적어 두는
          이유는, 땅을 점 하나로 보고 판정하므로 경계에 걸친 땅이 그 점의 위치에 따라
          들어오거나 빠지기 때문이다 — 안 적으면 "왜 저 건물이 빠졌지?"가 된다. */}
      <p className="dbld__src">
        상권 경계 안에 <strong>땅의 대표 위치</strong>가 들어가는 건물만 셉니다. 경계에 걸친 땅은
        그 위치에 따라 빠질 수 있습니다.
      </p>
    </div>
  );
}
