import { useEffect, useState } from 'react';
import { supabase, INDUSTRY_MIX_FN, INDUSTRY_DETAIL_FN } from '../lib/supabase';
import type { IndustryDetail, IndustryMix, IndustryScope } from '../types';
import { formatQuarter } from '../lib/format';
import {
  catOptions,
  districtLabel,
  districtSources,
  toBars,
  type MixBar,
} from '../lib/industryMix';

/**
 * "둘레의 업종 분포" 섹션 — 결정 0014(상권 지표 계산) 1단계.
 *
 * ⚠️ **이 건물의 점포가 아니다.** 층별 스택의 점포 칸은 (땅 + 층)으로 붙인 이 건물 것이고,
 *    여기 숫자는 이 땅 **둘레**(속한 상권 · 반경 500m)에 있는 남의 가게까지 전부 센 것이다.
 *    세는 대상이 아예 다르므로 두 숫자를 견주면 안 된다 — 그래서 제목부터 "둘레"라 적는다.
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

const TITLE = '둘레의 업종 분포';

export function IndustryMixSection({ pnu }: Props) {
  const [mix, setMix] = useState<IndustryMix | null>(null);
  /** 못 읽었나. 못 읽었으면 섹션을 통째로 감춘다 — 마이그레이션 적용 전 라이브가 이 상태다. */
  const [failed, setFailed] = useState(false);
  /** 고른 대분류 코드. null = 아직 아무것도 안 골랐다(첫 화면). */
  const [pickedCat, setPickedCat] = useState<string | null>(null);
  const [detail, setDetail] = useState<IndustryDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 필지가 바뀌면 옛 답을 지운다 — 안 지우면 새 건물 밑에 앞 건물의 분포가 잠깐
    // 붙어 보이고, 그 짧은 순간이 그대로 틀린 정보다(상권 줄과 같은 원칙).
    setMix(null);
    setFailed(false);
    setPickedCat(null);
    setDetail(null);

    supabase.rpc(INDUSTRY_MIX_FN, { p_pnu: pnu }).then(({ data, error }) => {
      if (cancelled) return;
      // ⚠️ 모양까지 본다. `districts` 가 배열이 아닌 답(옛 함수·다른 함수의 응답·PostgREST
      //    오류 객체)이 들어오면 아래에서 `.length` 를 읽다 터지는데, 이 컴포넌트가 터지면
      //    **층별 화면 전체가 하얗게 죽는다.** 곁다리 섹션 하나 때문에 본체를 잃지 않는다.
      if (error || !data || !Array.isArray((data as IndustryMix).districts)) {
        // 못 읽었으면 "업종 없음"이라고 적지 않는다 — 없는 것과 모르는 것은 다르다.
        // 마이그레이션 적용 전에는 함수가 아예 없어(PGRST202) 여기로 온다.
        console.warn('업종 분포 조회 실패 — 그 섹션 없이 표시합니다', error);
        setFailed(true);
        return;
      }
      setMix(data as IndustryMix);
    });

    return () => {
      cancelled = true;
    };
  }, [pnu]);

  useEffect(() => {
    if (pickedCat === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);

    supabase
      .rpc(INDUSTRY_DETAIL_FN, { p_pnu: pnu, p_cat: pickedCat })
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error || !data) {
          console.warn('업종 상세 조회 실패 — 상세 없이 표시합니다', error);
          return;
        }
        const got = data as IndustryDetail;
        // 위와 같은 이유의 모양 검사 — 상세가 이상하면 상세만 접는다(위쪽 분포는 남는다).
        if (!Array.isArray(got.districts)) {
          console.warn('업종 상세의 모양이 뜻밖입니다 — 상세 없이 표시합니다', got);
          return;
        }
        // ⚠️ 늦게 도착한 답은 버린다. 사용자가 그 사이 다른 업종을 골랐으면 이 답은
        //    엉뚱한 업종의 목록이고, 그대로 그리면 제목과 내용이 어긋난다.
        //    (cancelled 만으로는 못 막는다 — 같은 pnu 안에서 업종만 바뀌면 effect 가
        //     정리되지 않고 이어지는 경우가 있다.)
        if (got.cat_l_cd !== pickedCat) return;
        setDetail(got);
      });

    return () => {
      cancelled = true;
    };
  }, [pnu, pickedCat]);

  if (failed) return null;

  if (mix === null) {
    return (
      <section className="mix mix--wait">
        <h3 className="mix__h">{TITLE}</h3>
        <p className="mix__lead">불러오는 중…</p>
      </section>
    );
  }

  const hasDistricts = mix.districts.length > 0;
  const hasRadius = mix.radius !== null;
  // 상권도 없고 반경도 못 쟀으면(좌표 없음) 할 말이 없다. 빈 제목만 남기지 않는다.
  if (!hasDistricts && !hasRadius) return null;

  const options = catOptions(mix);
  const sources = districtSources(mix.districts);
  const pickedNm = options.find((o) => o.cd === pickedCat)?.nm ?? null;

  return (
    <section className="mix">
      <h3 className="mix__h">{TITLE}</h3>
      <p className="mix__lead">
        <strong>이 건물이 아니라 이 땅 둘레의 가게들입니다.</strong> 무슨 장사가 몇 곳 있는지
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
        <DetailBlocks mix={mix} detail={detail} pickedCat={pickedCat} pickedNm={pickedNm} />
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
    </section>
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
  pickedCat,
  pickedNm,
}: {
  mix: IndustryMix;
  detail: IndustryDetail | null;
  pickedCat: string;
  pickedNm: string | null;
}) {
  const label = pickedNm || pickedCat;

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
