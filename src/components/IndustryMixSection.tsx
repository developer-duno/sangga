import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { INDUSTRY_MIX_FN, INDUSTRY_DETAIL_FN, NEARBY_PERMITS_FN } from '../lib/appConstants';
import { SECTION_PLAN } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import type { IndustryDetail, IndustryMix, IndustryScope } from '../types';
import { formatQuarter } from '../lib/format';
import {
  catOptions,
  districtLabel,
  districtSources,
  isIndustryDetail,
  isIndustryMix,
  toBars,
  type MixBar,
} from '../lib/industryMix';
import { toPermitLine, type NearbyPermitLine } from '../lib/nearbyPermits';

/**
 * "둘레의 업종 분포" 섹션 — 결정 0014(상권 지표 계산) 1단계.
 *
 * ⚠️ **이 건물만의 점포가 아니다.** 층별 스택의 점포 칸은 (땅 + 층)으로 붙인 이 건물 것이고,
 *    여기 숫자는 이 땅 **둘레**(속한 상권 · 반경 500m)에 있는 이웃 가게까지 전부 센 것이다
 *    — 이 건물 것도 그 안에 **포함**된다(빼지 않는다). 세는 대상이 다르므로 두 숫자를
 *    견주면 안 된다. 그래서 제목부터 "둘레"라 적는다.
 *
 * ⛔ 여기에 값(원·시세)을 넣지 말 것. 이 섹션은 **개수만** 말한다. 서버도 개수만 주고
 *    상호명은 한 글자도 보내지 않는다(security definer 함수의 노출면).
 *
 * 두 자를 나란히 두는 이유:
 *  · 상권 — "장사판의 경계" 안이라 뜻이 분명하다. 다만 경계 밖 건물에는 아예 없다.
 *  · 반경 — 어디서나 잴 수 있다. 다만 큰길 건너편처럼 상권이 갈리는 자리도 함께 센다.
 * 하나만 보여주면 그 한계가 그대로 화면의 한계가 된다.
 */
type Props = {
  /** 이 필지. 바뀌면 두 질문을 처음부터 다시 던진다. */
  pnu: string;
};

// 제목은 `SECTION_PLAN.industry.title` 하나뿐이다 — 여기 또 적으면 카드 머리와 본문이
// 서로 다른 이름을 말하는 날이 온다.

export function IndustryMixSection({ pnu }: Props) {
  const [mix, setMix] = useState<IndustryMix | null>(null);
  /** 못 읽었나. 못 읽었으면 섹션을 통째로 감춘다 — 마이그레이션 적용 전 라이브가 이 상태다. */
  const [failed, setFailed] = useState(false);
  /** 고른 대분류 코드. null = 아직 아무것도 안 골랐다(첫 화면). */
  const [pickedCat, setPickedCat] = useState<string | null>(null);
  const [detail, setDetail] = useState<IndustryDetail | null>(null);
  /**
   * 상세를 못 읽었나.
   *
   * ⛔ 이 상태가 없으면 실패했을 때 detail 이 null 로 남아 **"불러오는 중…"이 영원히**
   *    돌아간다 — 사용자는 느린 것으로 알고 계속 기다린다. 실패는 실패라고 말한다.
   */
  const [detailFailed, setDetailFailed] = useState(false);
  /**
   * 둘레의 미준공 상업 인허가 한 줄. **null 이면 그 줄만 없다** — 아직 안 왔을 때·0동일
   * 때·함수가 아직 없을 때가 모두 같은 null 이다.
   *
   * ⓘ 업종 상세(`detailFailed`)와 달리 실패를 따로 담아 두지 않는다. 거기서는 기다리는
   *   동안 "불러오는 중…"을 그리므로 실패와 갈라야 물레방아가 안 돌지만, 여기서는 기다리는
   *   동안에도 아무것도 안 그려서 두 상태의 결과가 같다(LH 공고 카드와 같은 판단).
   *   ⛔ 그렇다고 "0동"이나 "새로 짓는 건물 없음"이라 적지 않는다 — 모르는 것을 없는 것이라
   *     말하게 된다(이 카드의 다른 자리와 같은 규칙).
   */
  const [permits, setPermits] = useState<NearbyPermitLine | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다 — 안 지우면 새 건물 밑에 앞 건물의 분포가 잠깐
    // 붙어 보이고, 그 짧은 순간이 그대로 틀린 정보다(상권 줄과 같은 원칙).
    setMix(null);
    setFailed(false);
    setPickedCat(null);
    setDetail(null);
    setDetailFailed(false);

    supabase.rpc(INDUSTRY_MIX_FN, { p_pnu: pnu }).then(({ data, error }) => {
      if (cancelled) return;
      // ⚠️ 모양까지 본다(isIndustryMix — 스코프·칸 하나하나까지). 뜻밖의 답이 들어오면
      //    렌더 도중에 터지고, 그러면 **층별 화면이 통째로 오류 안내로 바뀐다.**
      //    곁다리 섹션 하나 때문에 본체를 잃지 않는다.
      //    ⓘ 정정 2026-09-01 — 원래 "이 레포에는 ErrorBoundary 가 하나도 없다"고 적혀
      //      있었는데 2026-08-24 에 그물이 셋 생겼다(main·지도·층별 화면). 그래도 이
      //      모양 검사의 값어치는 그대로다: 그물은 **터진 뒤**를 수습할 뿐이고, 여기서
      //      걸러야 그 섹션만 조용히 빠지고 나머지가 산다.
      //      ⛔ 같은 문장의 사본이 **셋**이었다(industryMix.ts · industryMix.test.ts · 여기).
      //        문서 드리프트를 잡는 배치가 둘만 고치고 이것을 놓쳤다 — 다음엔
      //        `grep -rn "ErrorBoundary 가 하나도 없"` 한 번으로 전부 찾을 것.
      if (error || !isIndustryMix(data)) {
        // 못 읽었으면 "업종 없음"이라고 적지 않는다 — 없는 것과 모르는 것은 다르다.
        // 마이그레이션 적용 전에는 함수가 아예 없어(PGRST202) 여기로 온다.
        console.warn('업종 분포 조회 실패 — 그 섹션 없이 표시합니다', error);
        setFailed(true);
        return;
      }
      setMix(data);
    });

    return () => {
      cancelled = true;
    };
  }, [pnu]);

  /*
    둘레에 새로 올라오는 건물 — **따로 묻는다.**

    업종 분포와 한 카드에 서지만 자료가 달라(장사 중인 가게 수 ↔ 아직 안 지어진 건물 수)
    서버 함수도 다르다. 한 effect 에 묶으면 둘 중 하나가 느리거나 없을 때 나머지까지
    같이 늦거나 사라진다 — 곁다리 한 줄 때문에 카드 본문을 잃지 않는다.
  */
  useEffect(() => {
    let cancelled = false;
    // 앞 건물의 인허가 수가 새 건물 밑에 잠깐이라도 붙어 있으면 그 순간이 그대로 틀린
    // 정보다(위 분포와 같은 원칙).
    setPermits(null);

    supabase.rpc(NEARBY_PERMITS_FN, { p_pnu: pnu }).then(({ data, error }) => {
      if (cancelled) return;
      if (error) {
        // 마이그레이션 적용 전 라이브가 이 상태다(PGRST202). 줄만 빠지고 카드는 선다.
        console.warn('둘레 인허가 조회 실패 — 그 줄 없이 표시합니다', error);
        return;
      }
      // 모양 검사·0동 거르기·산수는 전부 `toPermitLine` 안에 있다 — 못 적을 값이면 null 이
      // 오고, 그때 화면은 그 줄을 아예 안 그린다.
      setPermits(toPermitLine(data));
    });

    return () => {
      cancelled = true;
    };
  }, [pnu]);

  useEffect(() => {
    if (pickedCat === null) {
      setDetail(null);
      setDetailFailed(false);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailFailed(false);

    supabase
      .rpc(INDUSTRY_DETAIL_FN, { p_pnu: pnu, p_cat: pickedCat })
      .then(({ data, error }) => {
        if (cancelled) return;
        // ⛔ 실패했으면 **반드시 상태를 바꾼다.** 그냥 돌아가면 detail 이 null 로 남아
        //    "불러오는 중…"이 영영 돌아간다(사용자는 느린 것으로 알고 계속 기다린다).
        //    모양 검사도 여기서 함께 한다 — 위쪽 분포는 살리고 상세만 접는다.
        if (error || !isIndustryDetail(data)) {
          console.warn('업종 상세 조회 실패 — 상세 없이 표시합니다', error ?? data);
          setDetailFailed(true);
          return;
        }
        // ⚠️ 늦게 도착한 답은 버린다. 사용자가 그 사이 다른 업종을 골랐으면 이 답은
        //    엉뚱한 업종의 목록이고, 그대로 그리면 제목과 내용이 어긋난다.
        //    (cancelled 만으로는 못 막는다 — 같은 pnu 안에서 업종만 바뀌면 effect 가
        //     정리되지 않고 이어지는 경우가 있다.)
        //    ⓘ 여기서는 detailFailed 를 켜지 않는다 — 실패가 아니라 **철 지난 답**이고,
        //      지금 고른 업종의 답은 아직 오는 중이다.
        if (data.cat_l_cd !== pickedCat) return;
        setDetail(data);
      });

    return () => {
      cancelled = true;
    };
  }, [pnu, pickedCat]);

  if (failed) return null;

  if (mix === null) {
    return (
      <SectionCard plan={SECTION_PLAN.industry} className="mix mix--wait" summary="불러오는 중…" />
    );
  }

  const hasDistricts = mix.districts.length > 0;
  const hasRadius = mix.radius !== null;
  // 상권도 없고 반경도 못 쟀으면(좌표 없음) 할 말이 없다. 빈 제목만 남기지 않는다.
  if (!hasDistricts && !hasRadius) return null;

  const options = catOptions(mix);
  const sources = districtSources(mix.districts);
  const pickedNm = options.find((o) => o.cd === pickedCat)?.nm ?? null;

  // 접혀 있어도 보이는 한 줄 — 몇 곳을 센 것인지.
  // ⚠️ 상권끼리 **더하지 않는다**(겹치는 자리의 가게가 양쪽에 들어간다). 그래서 상권은
  //    가게 수가 아니라 **몇 개 상권에 걸쳤는지**만 적는다.
  // ⚠️ 아래 블록 제목("… 안 200곳")과 같은 글자를 쓰지 않는다 — 같은 말이 화면에 둘이면
  //    이름으로 찾는 시험이 어느 쪽을 잡았는지 모르게 된다. 그래서 "안"이 아니라 "이내"다.
  const summary = [
    hasDistricts ? `속한 상권 ${mix.districts.length.toLocaleString('ko-KR')}개` : null,
    mix.radius
      ? `반경 ${mix.radius_m.toLocaleString('ko-KR')}m 이내 ${mix.radius.total.toLocaleString('ko-KR')}곳`
      : null,
  ]
    .filter((s): s is string => s !== null)
    .join(' · ');

  return (
    <SectionCard plan={SECTION_PLAN.industry} className="mix" summary={summary}>
      <p className="mix__lead">
        <strong>이 건물만이 아니라 이 땅 둘레의 가게들입니다.</strong> 무슨 장사가 몇 곳 있는지
        세어 본 것이고, 값이나 매출은 아닙니다.
      </p>

      {hasDistricts &&
        mix.districts.map((d) => (
          <ScopeBlock
            key={d.district_id}
            heading={`${districtLabel(d)} 안`}
            scope={d}
            emptyNote="이 상권 안에 등록된 점포가 없습니다."
          />
        ))}

      {mix.radius && (
        <ScopeBlock
          // 반경 길이는 서버가 준 값을 쓴다 — 화면에 '500m'를 박으면 서버가 바꾸는 날
          // 코드를 한 줄도 안 고쳤는데 문구만 거짓말이 된다.
          heading={`반경 ${mix.radius_m.toLocaleString('ko-KR')}m 안`}
          scope={mix.radius}
          emptyNote="이 반경 안에 등록된 점포가 없습니다."
        />
      )}

      {permits && <PermitLine line={permits} />}

      {options.length > 0 && (
        <div className="mix__pick">
          <label className="mix__pick-label" htmlFor="mix-cat">
            업종 골라보기
          </label>
          <select
            id="mix-cat"
            className="mix__select"
            value={pickedCat ?? ''}
            onChange={(e) => setPickedCat(e.target.value === '' ? null : e.target.value)}
          >
            <option value="">업종을 고르면 더 자세히 나뉩니다</option>
            {options.map((o) => (
              <option key={o.cd} value={o.cd}>
                {o.nm || o.cd}
              </option>
            ))}
          </select>
        </div>
      )}

      {pickedCat !== null && (
        <DetailBlocks
          mix={mix}
          detail={detail}
          failed={detailFailed}
          pickedCat={pickedCat}
          pickedNm={pickedNm}
        />
      )}

      <p className="grade">
        <span className="grade__badge">A등급 · 실측 집계</span>
        어림한 값이 아니라 <strong>등록된 점포를 그대로 센 값</strong>입니다. 다만 아래 두 가지
        때문에 실제와 다를 수 있습니다.
      </p>
      <ul className="mix__why">
        <li>
          <strong>겹쳐 세기</strong> — 상권 경계가 겹치는 자리의 가게는 <strong>양쪽에 모두</strong>{' '}
          들어갑니다. 그래서 위의 상권들을 <strong>서로 더하면 안 됩니다.</strong>
        </li>
        <li>
          <strong>시차</strong> — 분기마다 한 번 받는 자료라, 그 뒤에 문을 닫았거나 새로 연 가게는
          아직 반영되지 않았습니다.
        </li>
      </ul>
      <p className="mix__src">
        출처: 소상공인시장진흥공단 상가(상권)정보
        {mix.snapshot_ym ? ` ${formatQuarter(mix.snapshot_ym)} 기준` : ''}
        {sources.length > 0 && <> · 상권 경계 {sources.join(' · ')}</>}.
      </p>
    </SectionCard>
  );
}

/**
 * "둘레에 새로 올라오는 상가 건물" 한 줄.
 *
 * 왜 이 카드 안에 두나 — 묻는 것이 같은 자리(이 땅 둘레)이고, 창업·투자를 재는 사람에게
 * 지금 몇 곳이 있는지와 앞으로 몇 동이 더 서는지는 **한 호흡에 읽어야 뜻이 생기는 한 쌍**이기
 * 때문이다. 카드를 새로 만들면 첫 화면 펼침 상한(`SECTION_EXPAND_BUDGET`)이 흔들린다.
 *
 * ⛔ **앞일을 단정하지 않는다.** '예정'·'곧 완공'·'들어설 것'은 쓰지 않는다 — 허가를 받고도
 *    안 짓거나 용도가 바뀌는 일이 흔해서, 우리가 아는 사실은 "그 달 기준 이런 허가가 살아
 *    있다"까지다. 그래서 문장이 인허가 기준월로 끝나고, 바로 뒤에 그 한계를 덧붙인다.
 * ⛔ 이 숫자를 위 점포 수와 **더하거나 견주지 않는다.** 가게(개)와 건물(동)은 단위부터 다르다.
 */
function PermitLine({ line }: { line: NearbyPermitLine }) {
  const n = (v: number) => v.toLocaleString('ko-KR');
  return (
    <p className="mix__permits">
      둘레에{' '}
      {/* 한 덩어리 글자로 낸다 — 조각으로 쪼개면 화면에는 같아 보여도 한 낱말로 찾는
          시험이 못 찾는다(`.mix__rival` 과 같은 이유). */}
      <strong className="mix__permits-n">{`새로 올라오는 상가 건물 ${n(line.total)}동`}</strong>
      {` — 허가만 ${n(line.permitOnly)}동 · 착공 ${n(line.started)}동 (${line.baseLabel} 인허가 기준).`}
      {/* ⛔ **숫자를 빼지 않고 사실을 덧붙인다**(사장님 결재 2026-09-05). 걸러 내면 사용자가
          보는 수가 조용히 줄고, 그 기준(2년? 3년?)을 우리가 추정으로 정해야 한다.
          ⛔ **"실효됐다"고 단정하지 않는다** — 원본에 실효 칸이 아예 없어, 아는 것은 "그 달
          자료에 착공 기록이 없다"까지다. 그래서 "…있습니다"로 여지를 남긴다.
          ⓘ 0동이면 안 적는다 — '0동이 멈춰 있습니다'는 읽는 사람에게 아무 뜻이 없다. */}
      {line.stale !== null && line.stale > 0 && (
        <span className="mix__permits-stale">
          {`그중 ${n(line.stale)}동은 허가 후 2년 넘게 착공하지 않았습니다(건축법상 허가가 실효됐을 수 있습니다).`}
        </span>
      )}
      <span className="mix__permits-note">허가를 받았다고 모두 지어지는 것은 아닙니다.</span>
    </p>
  );
}

/**
 * 스코프 하나(상권 또는 반경)의 막대 목록.
 *
 * 총수를 제목에 함께 적는다 — 몫(%)만 있으면 "60%"가 6곳인지 6,000곳인지 알 수 없는데,
 * 그 둘은 창업을 판단할 때 완전히 다른 이야기다(절대 규칙 3의 표본 병기와 같은 뜻).
 */
function ScopeBlock({
  heading,
  scope,
  emptyNote,
}: {
  heading: string;
  scope: IndustryScope;
  emptyNote: string;
}) {
  const bars = toBars(scope);

  return (
    <div className="mix__block">
      <h4 className="mix__sub">
        {heading} <span className="mix__total">{scope.total.toLocaleString('ko-KR')}곳</span>
      </h4>
      {bars.length === 0 ? (
        <p className="mix__none">{emptyNote}</p>
      ) : (
        <ul className="mix__bars">
          {bars.map((b) => (
            <MixBarRow key={b.cd} bar={b} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** 막대 한 줄. 폭은 순수 CSS 비율이다(층 스택의 `.floor__bar` 와 같은 방식). */
function MixBarRow({ bar }: { bar: MixBar }) {
  return (
    <li>
      <span className="mix__cat">{bar.nm || bar.cd}</span>
      <span className="mix__bar">
        {/* 몫이 0 이면 막대를 그리지 않는다. 최소 폭을 강제하면 "0곳"이 "조금 있음"처럼 보인다. */}
        {bar.pct > 0 && <span className="mix__fill" style={{ width: `${bar.pct}%` }} />}
      </span>
      <span className="mix__n">{bar.n.toLocaleString('ko-KR')}곳</span>
      <span className="mix__pct">{bar.pct.toFixed(1)}%</span>
    </li>
  );
}

/**
 * 고른 업종의 상세 — 스코프마다 "같은 업종 N곳"(경쟁 카운트) + 중분류 나눔.
 *
 * ⚠️ 아직 답이 안 왔을 때 0곳이라고 적지 않는다. "지금 0곳"과 "아직 모름"은 창업을
 *    판단하는 사람에게 정반대의 뜻이다.
 */
function DetailBlocks({
  mix,
  detail,
  failed,
  pickedCat,
  pickedNm,
}: {
  mix: IndustryMix;
  detail: IndustryDetail | null;
  /** true = 못 읽음. "불러오는 중"과 **반드시** 갈라 말한다(아래 ⛔ 참조). */
  failed: boolean;
  pickedCat: string;
  pickedNm: string | null;
}) {
  const label = pickedNm || pickedCat;

  // ⛔ 실패를 "불러오는 중"으로 두면 영영 도는 물레방아가 된다 — 사용자는 느린 것으로
  //    알고 계속 기다린다. 그렇다고 "0곳"이라 적어서도 안 된다(모르는 것을 없는 것이라
  //    말하게 된다). 못 읽었다고 그대로 말하는 것이 유일하게 정직한 답이다.
  if (failed) {
    return (
      <div className="mix__detail">
        <p className="mix__none">{label} 상세를 불러오지 못했습니다.</p>
      </div>
    );
  }

  if (detail === null) {
    return (
      <div className="mix__detail">
        <p className="mix__none">{label} 상세를 불러오는 중…</p>
      </div>
    );
  }

  const blocks: Array<{ key: string; heading: string; scope: IndustryScope }> = [];
  for (const d of detail.districts) {
    // 이름표는 대분류 응답 쪽이 더 자세하다(상권 종류가 거기에만 온다).
    const named = mix.districts.find((x) => x.district_id === d.district_id);
    blocks.push({
      key: d.district_id,
      heading: `${named ? districtLabel(named) : d.name || '(이름 없는 상권)'} 안`,
      scope: d,
    });
  }
  if (detail.radius) {
    blocks.push({
      key: '__radius__',
      heading: `반경 ${detail.radius_m.toLocaleString('ko-KR')}m 안`,
      scope: detail.radius,
    });
  }

  if (blocks.length === 0) return null;

  return (
    <div className="mix__detail">
      {blocks.map((b) => (
        <div className="mix__block" key={b.key}>
          <h4 className="mix__sub">
            {b.heading}{' '}
            {/* 한 덩어리 글자로 낸다 — 조각으로 쪼개면 화면에는 같아 보여도 "음식 60곳"을
                한 낱말로 찾는 시험이 못 찾는다(사람이 읽는 단위와 DOM 단위를 맞춘다). */}
            <strong className="mix__rival">
              {`${label} ${b.scope.total.toLocaleString('ko-KR')}곳`}
            </strong>
          </h4>
          {b.scope.cats.length === 0 ? (
            <p className="mix__none">이 안에 {label} 가게가 없습니다.</p>
          ) : (
            <ul className="mix__bars">
              {toBars(b.scope).map((c) => (
                <MixBarRow key={c.cd} bar={c} />
              ))}
            </ul>
          )}
        </div>
      ))}
      <p className="mix__note">
        <strong>같은 업종이 많다고 나쁜 자리는 아닙니다.</strong> 먹자골목처럼 모여 있어서 손님이
        오는 곳도 있고, 이미 꽉 찬 곳도 있습니다. 이 숫자는 그 판단의 재료일 뿐입니다.
      </p>
    </div>
  );
}
