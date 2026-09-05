import { useCallback, useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { OPEN_SIGUNGU_FN } from '../lib/appConstants';
import { SIDOS } from '../lib/regions';
import type { OpenSigungu } from '../types';

/**
 * 자료가 **실제로 있는 지역만** 보여준다 (사장님 결정 2026-08-13).
 *
 * ⛔ 결정 0006 은 원래 "전국 17개 시도를 다 보여주되 잠긴 곳은 🔒 로 표시"였다.
 *    이유는 "목록에서 빼면 우리 지역은 영영 안 되나? 가 된다"였는데, 사장님이
 *    바로잡으셨다 — **서비스하지 않는 도시를 굳이 보여줄 이유가 없다.**
 *    "다른 지역은 준비 중이에요"라는 한 줄이 그 뜻을 이미 전달하므로,
 *    누를 수 없는 칩 15개를 늘어놓을 필요가 없다.
 *
 * ⭐ 목록의 진실은 **서버(`list_open_sigungu()`)뿐**이다. 시도도 구도 그 응답에서
 *    뽑는다 — 프론트에 하드코딩하면 ① 자료 없는 곳을 고를 수 있게 되고(고르면
 *    아무것도 안 나와 "고장난 것"처럼 보인다) ② 지역이 늘 때마다 화면을 손으로
 *    고쳐야 한다. 서버에서 뽑으면 자료가 들어오는 순간 화면이 저절로 따라온다.
 *    `SIDOS` 는 짧은 이름(서울/대전)을 붙이는 데만 쓴다.
 *
 * 검색은 **고른 구 안에서만** 한다(2026-08-13e) — 같은 건물 이름이 여러 구에
 * 겹치기 때문이다(이름 33,851종 중 2,443종). 그래서 시도를 누르면 그 시도의 구가 펼쳐진다.
 */
type Props = {
  /** 지금 고른 시군구 코드. 아무것도 안 골랐으면 null. 상태 소유는 App.tsx. */
  selectedSigungu: string | null;
  /** 구를 고르거나 해제할 때 부모에게 알린다. name은 화면 표시용(검색 결과 문구)이다. */
  onSelectSigungu: (code: string | null, name?: string | null) => void;
  /**
   * 지금 고른 구의 **이름**을 알려 준다(고르는 행위와 무관하게).
   *
   * 링크로 들어온 사람은 주소에서 구 **코드**만 받아 이름을 모른다. 이름이 없어도
   * 화면은 안 깨지지만 "고른 지역 상권 지도"라고 적혀 링크를 받은 사람이 보는 첫
   * 화면이 아쉬워진다. 이 컴포넌트는 서버 목록을 이미 갖고 있어 이름을 아는 유일한
   * 자리라, 목록이 도착해 짝이 맞는 순간 부모에게 건넨다.
   *
   * ⓘ 이름을 주소에 담지 않는 이유 — 담으면 구 이름이 바뀌는 날 옛 링크가 옛 이름을
   *    말한다. 코드만 담고 이름은 늘 서버 목록에서 얻으면 그 어긋남이 없다.
   */
  onSigunguNameResolved?: (name: string) => void;
};

/** 서버가 준 구 목록에서 시도를 뽑는다(중복 제거, 코드순). 짧은 이름은 SIDOS 에서. */
function sidosFrom(guList: OpenSigungu[]) {
  const seen = new Map<string, { code: string; name: string }>();
  for (const g of guList) {
    if (seen.has(g.sido_code)) continue;
    const known = SIDOS.find((s) => s.code === g.sido_code);
    seen.set(g.sido_code, { code: g.sido_code, name: known?.name ?? g.sido_nm });
  }
  return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
}

export function RegionPicker({
  selectedSigungu,
  onSelectSigungu,
  onSigunguNameResolved,
}: Props) {
  const [expandedSido, setExpandedSido] = useState<string | null>(null);
  const [guList, setGuList] = useState<OpenSigungu[]>([]);
  const [guLoading, setGuLoading] = useState(true);
  const [guError, setGuError] = useState<string | null>(null);

  const loadGuList = useCallback(async () => {
    setGuLoading(true);
    setGuError(null);
    try {
      const { data, error } = await supabase.rpc(OPEN_SIGUNGU_FN);
      if (error) throw error;
      setGuList((data ?? []) as OpenSigungu[]);
    } catch (ex) {
      // 실패해도 화면 본체(검색 등)는 살아 있어야 한다 — 지역 고르기만 잠깐 못 쓸 뿐이다.
      console.error('지역 목록 조회 실패', ex);
      setGuError('지역 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
      setGuList([]);
    } finally {
      setGuLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGuList();
  }, [loadGuList]);

  const sidos = sidosFrom(guList);
  const selectedGu = guList.find((g) => g.sigungu_code === selectedSigungu) ?? null;

  // 목록이 도착해 지금 고른 구의 이름을 알게 되면 부모에게 건넨다.
  // (직접 눌러서 고른 경우엔 부모가 이미 이름을 알고 있어 아무 일도 일어나지 않는다 —
  //  받는 쪽이 "이미 알면 무시"하도록 되어 있다.)
  useEffect(() => {
    if (selectedGu) onSigunguNameResolved?.(selectedGu.sigungu_nm);
  }, [selectedGu, onSigunguNameResolved]);
  const gusInExpanded = expandedSido ? guList.filter((g) => g.sido_code === expandedSido) : [];

  function pickGu(g: OpenSigungu) {
    const already = g.sigungu_code === selectedSigungu;
    onSelectSigungu(already ? null : g.sigungu_code, already ? null : g.sigungu_nm);
  }

  return (
    <section className="region">
      {/*
        ⚠️ 안내 문구도 **서버 목록에서 만든다.** 예전에는 `openRegionLabel()`(코드에 박힌
           ['11','30'] · **지금은 삭제됨**)을 썼는데, 칩 목록은 서버에서 오므로 **부산 자료가 들어오면 칩은
           뜨는데 문구는 "서울·대전"으로 남는** 드리프트가 생긴다(2026-08-13 2차 검증).
           진실을 한 곳(서버)으로 모으면 그런 어긋남이 아예 불가능해진다.
      */}
      <p className="region__lead">
        {sidos.length > 0 ? (
          <>
            지금 보실 수 있는 지역은 <strong>{sidos.map((s) => s.name).join('·')}</strong>입니다.
            다른 지역은 준비 중이에요.
          </>
        ) : (
          <>볼 수 있는 지역을 불러오는 중이에요.</>
        )}
      </p>

      {selectedGu && (
        <p className="region__selected">
          선택한 지역:{' '}
          <strong>
            {selectedGu.sido_nm} {selectedGu.sigungu_nm}
          </strong>
          <button
            type="button"
            className="region__clear"
            onClick={() => onSelectSigungu(null, null)}
          >
            선택 해제
          </button>
        </p>
      )}

      {guLoading && <p className="msg">지역 목록을 불러오는 중…</p>}

      {!guLoading && guError && (
        <p className="msg msg--error">
          {guError}{' '}
          <button type="button" className="region__retry" onClick={loadGuList}>
            다시 시도
          </button>
        </p>
      )}

      {!guLoading && !guError && sidos.length === 0 && (
        <p className="msg">아직 볼 수 있는 지역이 없습니다.</p>
      )}

      {!guLoading && !guError && sidos.length > 0 && (
        <ul className="region__list">
          {/*
            ⚠️ 강조는 **한 번에 하나**여야 한다. 예전에는 `--on` 이 "열린 지역"을 뜻해서
               열린 시도가 전부 파랗게 칠해졌고, 자료 있는 곳만 보여주게 된 지금은
               **모든 칩이 선택된 것처럼** 보였다(2026-08-13 사장님 발견).
               이제 `--on` 은 "지금 펼친 시도" 하나만 가리킨다.
          */}
          {sidos.map((s) => {
            const expanded = expandedSido === s.code;
            return (
              <li key={s.code}>
                <button
                  type="button"
                  className={`region__chip${expanded ? ' region__chip--on' : ''}`}
                  aria-expanded={expanded}
                  onClick={() => setExpandedSido((cur) => (cur === s.code ? null : s.code))}
                >
                  {s.name}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {expandedSido && gusInExpanded.length > 0 && (
        <div className="region__gus">
          <ul className="region__gu-list">
            {gusInExpanded.map((g) => {
              const on = g.sigungu_code === selectedSigungu;
              return (
                <li key={g.sigungu_code}>
                  <button
                    type="button"
                    className={`region__gu-chip${on ? ' region__gu-chip--on' : ''}`}
                    aria-pressed={on}
                    onClick={() => pickGu(g)}
                  >
                    {g.sigungu_nm}
                    {/*
                      그 구에 자료가 들어와 있는 건물 수. 서버(`list_open_sigungu`)가 이미
                      주는 값이라 더 묻지 않는다 — 고르기 전에 "여기는 볼 게 얼마나 있나"를
                      알 수 있다. 0이면 안 적는다("0동"은 고장처럼 보인다).
                      앞의 공백은 span **안**에 둔다 — 밖에 두면 0일 때도 공백이 남아
                      textContent 단언이 흔들리고, 안에 둬야 스크린리더도 "강남구 14,223동"으로
                      띄어 읽는다(공백 없이 붙이면 접근성 이름이 한 덩어리가 된다).
                    */}
                    {g.building_cnt > 0 && (
                      <span className="region__gu-cnt">
                        {' '}
                        {g.building_cnt.toLocaleString('ko-KR')}동
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
