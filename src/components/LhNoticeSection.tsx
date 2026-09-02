import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { LH_NOTICES_FN } from '../lib/appConstants';
import { ENTRY_SECTION_PLAN } from '../lib/sectionCards';
import { closeText, isHttpUrl, isLhNoticeList, lhSummary, sidoOf } from '../lib/lhNotices';
import { SectionCard } from './SectionCard';
import type { LhNotice } from '../types';

/**
 * "LH 상가 분양·입점 공고" 카드 — **입구**(구는 골랐고 건물은 아직 안 고른 자리)에 선다.
 *
 * 왜 입구인가
 * -----------
 * 이 목록은 건물 하나를 들여다보는 이야기가 아니라 "지금 이 시·도에서 무엇이 열려 있나"다.
 * 건물을 고르고 나면 화면의 주제가 그 건물로 바뀌므로 그때는 사라진다 — 분석 화면을
 * 어지럽히지 않는다(App.tsx 의 노출 조건).
 *
 * ⛔ **값(분양가·보증금·임대료)·신청 방법을 옮겨 적지 않는다.** 조건은 공고문마다 다르고
 *    정정 공고로 바뀌기도 해서, 옮겨 적는 순간 틀릴 수 있는 값이 된다. 우리 몫은 "무엇이
 *    열려 있는지"까지고 나머지는 링크로 넘긴다(전략 — 매물은 링크로, 우리는 분석에 집중).
 * ⛔ 못 읽었거나 빈손이면 **카드를 통째로 생략한다.** "공고 없음"이라 적으면 모르는 것을
 *    없는 것이라 말하게 된다(업종 분포 섹션과 같은 규칙).
 */
type Props = {
  /**
   * 고른 구 코드 5자리. 여기서 앞 두 자리(시도)만 떼어 서버에 묻는다 — 같은 시도 안에서
   * 구만 바꾸면 답이 같으므로 다시 묻지 않는다(effect 가 시도 코드에만 달려 있다).
   */
  sigungu: string;
};

export function LhNoticeSection({ sigungu }: Props) {
  const sido = sidoOf(sigungu);
  /**
   * 받아 온 공고들. **아직 못 받았을 때와 못 읽었을 때가 똑같이 null 이다.**
   *
   * ⓘ 다른 카드들(업종 분포·참고 시세)은 "못 읽음"을 따로 담아 둔다 — 거기서는 기다리는
   *   동안 "불러오는 중…"을 그리므로 실패와 갈라야 물레방아가 영영 돌지 않는다. 여기서는
   *   기다리는 동안에도 아무것도 안 그리므로(아래) 두 상태의 결과가 같다. 결과가 같은
   *   상태를 둘로 나눠 두면, 읽는 사람은 "어딘가 다르게 쓰이겠지" 하고 찾아 헤맨다.
   */
  const [notices, setNotices] = useState<LhNotice[] | null>(null);

  useEffect(() => {
    setNotices(null);
    // 구 코드가 다섯 자리 숫자가 아니면 물을 수가 없다. 뜻 모를 값을 서버에 보내고
    // 그 빈손을 "공고 없음"으로 읽는 것보다, 아예 안 묻는 편이 정직하다.
    if (sido === null) return;

    let cancelled = false;
    supabase.rpc(LH_NOTICES_FN, { p_sido: sido }).then(({ data, error }) => {
      if (cancelled) return;
      // ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 카드는
      //    **입구**에 있어 터지면 검색창·지역 고르개까지 함께 사라진다(마지막 그물이
      //    화면 전체를 안내로 바꾼다). 곁다리 하나 때문에 본체를 잃지 않는다.
      if (error || !isLhNoticeList(data)) {
        // 담지 않고 돌아간다 = 카드 없음. "공고 없음"이라 적지 않는다 — 모르는 것을
        // 없는 것이라 말하게 된다(업종 분포 섹션과 같은 규칙).
        console.warn('LH 공고 조회 실패 — 그 카드 없이 표시합니다', error ?? data);
        return;
      }
      setNotices(data);
    });

    return () => {
      cancelled = true;
    };
  }, [sido]);

  /*
    ⓘ 기다리는 동안 **아무것도 그리지 않는다**(다른 카드들의 "불러오는 중…" 과 다르다).
      여기서는 빈손이 흔한 정상 결과라 로딩 카드를 먼저 띄우면, 공고가 없는 시·도에서는
      카드가 잠깐 나타났다 사라진다 — 화면이 깜빡이는 것을 사람은 고장으로 읽는다.
    ⛔ 0건일 때도 카드를 만들지 않는다. 빈 카드는 입구를 가로막기만 한다.
  */
  if (notices === null || notices.length === 0) return null;

  return (
    <SectionCard plan={ENTRY_SECTION_PLAN.lhNotice} className="lh" summary={lhSummary(notices)}>
      <p className="lh__lead">
        한국토지주택공사(LH)가 낸 상가 분양·임대 공고입니다.{' '}
        <strong>신청 방법과 가격·자격은 공고문에 있습니다</strong> — 여기서는 지금 무엇이 열려
        있는지만 알려 드립니다.
      </p>

      <ul className="lh__list">
        {notices.map((n) => (
          <li key={n.pan_id}>
            {/* 종류는 서버 글자를 그대로 적는다 — 우리가 다시 이름 붙이면 새 종류가 생기는
                날 화면만 옛말을 한다. */}
            <span className="lh__kind">{n.kind_nm}</span>
            <span className="lh__nm">{n.pan_nm}</span>
            {/* pan_ss 는 DB nullable(원본 결측)이라 없을 수 있다 — 없으면 그 칸만 비우고
                줄은 그대로 그린다(§types.ts LhNotice.pan_ss 참조).
                ⛔ `!== null` 이 아니라 **참/거짓**으로 본다. 검증기(isNullableString)는
                   undefined 도 통과시키고 빈 문자열('')은 아무도 안 막는데, 둘 다 `!== null`
                   을 지나 **빈 <span> 을 그린다** — 값이 없는데 있는 척하는 자리가 생긴다
                   (2026-09-01 독립 검토 지적). */}
            {n.pan_ss ? <span className="lh__ss">{n.pan_ss}</span> : null}
            {/* 마감이 이 목록에서 가장 중요한 값이라 한 덩어리 글자로 낸다. */}
            <span className="lh__close">{closeText(n.close_date)}</span>
            {/* ⚠️ 새 창으로 열되 `rel` 을 함께 준다 — 없으면 열린 쪽이 우리 창을 되돌려
                다른 주소로 보낼 수 있다. 주소 모양이 아니면 링크를 아예 안 만든다. */}
            {isHttpUrl(n.dtl_url) && (
              <a className="lh__link" href={n.dtl_url} target="_blank" rel="noopener noreferrer">
                LH에서 보기
              </a>
            )}
          </li>
        ))}
      </ul>

      {/* 출처표시는 공공누리 의무다. 어디까지가 우리 말이고 어디부터가 LH 말인지도 가른다. */}
      <p className="lh__src">출처: 한국토지주택공사(LH) 분양·임대 공고.</p>
    </SectionCard>
  );
}
