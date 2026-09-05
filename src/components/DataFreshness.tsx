import { useEffect, useId, useState } from 'react';

import { DATA_FRESHNESS_FN } from '../lib/appConstants';
import { basisText, isDataFreshnessList, nextText } from '../lib/dataFreshness';
import { supabase } from '../lib/supabase';
import type { DataFreshnessRow } from '../types';

/**
 * "이 자료는 언제 것인가" — 화면 맨 아래, 면책 안내와 의견함 사이의 표 한 장. 2026-09-05d.
 *
 * 왜 필요한가
 * -----------
 * 이 화면의 숫자가 **언제 것인지** 아는 길이 지금까지 `python scripts/post_load.py --check`
 * 뿐이었다 — 우리만 볼 수 있는 자리다. 보는 사람 입장에서는 3개월 전 분기를 보고 있는지
 * 어제 것을 보고 있는지 알 방법이 없었고, 그건 "믿어도 되나"를 스스로 판단할 수 없다는 뜻이다.
 *
 * ⛔ **별도 화면이 아니라 푸터의 표다**(👤 사장님 결재 2026-09-05). 자료 목록을 보러 일부러
 *    다른 화면으로 들어가는 사람은 없다 — 궁금해지는 순간은 숫자를 보고 있는 바로 그때다.
 *
 * ⛔ **날짜도 분기도 주기도 이 파일에 안 적혀 있다.** 자료 이름·기준값·다음 갱신 예정일·
 *    주기까지 전부 서버가 준다. 신선도를 화면에 박아 두면 적재하는 순간부터 그 글자만
 *    거짓말을 한다 — 이 표가 존재하는 이유가 바로 그것을 없애는 것인데, 그걸 박아 두면
 *    표 자체가 자기가 없애려던 결함이 된다.
 *
 * ⛔ 못 읽었으면 **표를 통째로 생략한다.** "자료 없음"이라 적으면 모르는 것을 없는 것이라
 *    말하게 된다(LH 공고 카드와 같은 규칙). 아래 면책 안내와 의견함은 그대로 선다.
 *
 * ⓘ 접히지 않는다 — 네 칸짜리 표 한 장이라 접는 장치가 내용보다 커진다.
 */
export function DataFreshness() {
  /**
   * 받아 온 줄들. **아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다.**
   * 기다리는 동안 아무것도 안 그리므로 두 상태의 결과가 같다(`LhNoticeSection` 과 같은 결).
   */
  const [rows, setRows] = useState<DataFreshnessRow[] | null>(null);
  const headingId = useId();

  useEffect(() => {
    let cancelled = false;
    supabase.rpc(DATA_FRESHNESS_FN).then(({ data, error }) => {
      if (cancelled) return;
      // ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 표는
      //    화면 맨 아래에 있어 터지면 면책 안내와 의견함까지 함께 사라진다.
      if (error || !isDataFreshnessList(data)) {
        console.warn('자료 기준일 조회 실패 — 그 표 없이 표시합니다', error ?? data);
        return;
      }
      setRows(data);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // 빈손이면 표를 만들지 않는다 — 머리글만 있는 표는 소음이다.
  if (rows === null || rows.length === 0) return null;

  return (
    <section className="fresh" aria-labelledby={headingId}>
      <h2 className="fresh__h" id={headingId}>
        이 자료는 언제 것인가
      </h2>
      <table className="fresh__table">
        <thead>
          <tr>
            <th scope="col">자료</th>
            <th scope="col">기준</th>
            <th scope="col">다음 갱신 예정</th>
            <th scope="col">주기</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.src}>
              <th scope="row">{row.src}</th>
              <td>
                {/* 기준값이 **무엇인가**(분기·계약월·고시일…)를 값과 함께 적는다. 값만 적으면
                    '2026년 8월 27일'이 고시일인지 우리가 받아 둔 날인지 알 수 없다. */}
                <span className="fresh__kind">{row.basis_kind}</span>{' '}
                <span className="fresh__val">{basisText(row)}</span>
              </td>
              <td>{nextText(row)}</td>
              <td>{row.cadence}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fresh__note">
        날짜는 창고에서 읽은 값이라 새 자료가 들어오면 저절로 바뀝니다.
      </p>
    </section>
  );
}
