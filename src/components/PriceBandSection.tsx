import { TX_BASEMENT_MISSING_SINCE } from '../lib/appConstants';
import { SECTION_PLAN } from '../lib/sectionCards';
import { SectionCard } from './SectionCard';
import type { BasePrice, FloorRow, PriceBand } from '../types';
import { pairBasePrices, type BasePriceRow } from '../lib/basePrice';
import {
  formatArea,
  formatEokBand,
  formatFloor,
  formatManWon,
  formatManWonBand,
  formatYearMonth,
} from '../lib/format';
import {
  describeStage,
  groupBands,
  isFarStage,
  isSinglePoint,
  toTotalWon,
  type BandGroup,
} from '../lib/priceBand';

/**
 * "참고 매매 시세" 섹션 — Stage B(결정 0013).
 *
 * ⚠️ 여기 나오는 숫자는 **추정이다.** 위 `.tx`(신고된 사실)와 카드를 갈라 두는 것이 이
 *    화면에서 사실과 추정을 가르는 장치다 — 두 블록을 합치지 말 것(styles.css 의 ⛔ 주석과
 *    한 쌍이다). 파일을 따로 뺀 것도 같은 이유다: 주석이 아니라 구조로 갈라 둔다.
 *
 * 말해야 하는 상태가 다섯이고, 다섯을 절대 같은 문장으로 뭉뚱그리지 않는다:
 *  · gate_fail   — 이 구는 아직 안 낸다. 표본이 모자란 게 **아니다**(판정이 아예 없는 구도 여기다)
 *  · floor_1f    — 1층은 방침상 안 낸다. 자료가 없는 게 **아니다**
 *  · no_evidence — 검증에 쓸 거래가 한 건도 없었다. **쌓여도 안 나온다** → 줄 대신 각주 1회
 *  · no_estimate — 곁 거래를 못 찾았다. **쌓이면 나온다**
 *  · ok          — 값. 근거 단계·표본 수를 항상 함께 적는다(절대 규칙 3)
 */
type Props = {
  /** null = 아직 안 옴(자리만 잡아 둔다). */
  bands: PriceBand[] | null;
  /**
   * 이 필지의 층별 국세청 기준시가. **추정이 아니라 고시된 값**이라 카드 맨 끝에 따로 적는다.
   *
   * null = 아직 안 왔거나 못 읽음(마이그레이션 적용 전 라이브가 그 상태다). 둘 다 **줄을
   * 안 그리는 것**으로 끝난다 — 곁다리 한 줄 때문에 자리를 잡아 두거나 "없음"이라 적으면,
   * 모르는 것을 아는 것처럼 말하게 된다.
   */
  basePrices: BasePrice[] | null;
  /** true = 못 읽음 → 아무 말도 하지 않는다(없는 것과 모르는 것은 다르다). */
  failed: boolean;
  /** 이 **건물**의 층. 서버는 필지 전체를 주므로 여기서 걸러진다. */
  floors: FloorRow[];
  /** 『층대별 거래 단가』 블록이 실제로 화면에 있나(대안 안내를 낼지 정한다). */
  hasTxStats: boolean;
  openFloor: number | null;
  onPickFloor: (floorNo: number) => void;
};

// 제목은 `SECTION_PLAN.band.title` 하나뿐이다(카드 머리에 적힌다) — 여기 또 적으면
// 카드 머리와 본문이 서로 다른 이름을 말하는 날이 온다.

/**
 * 이보다 적은 곁 거래로 낸 폭에는 '표본 적음' 표식을 붙인다.
 *
 * ⚠️ 아래 각주의 한글 문구("곁 거래가 **다섯 건**이 안 된다는 뜻입니다")와 짝이다 —
 *    바꿀 땐 두 곳을 함께 고친다(숫자만 고치면 표식과 설명이 어긋난다).
 * ⛔ 이름이 비슷한 이웃 둘과 **뜻이 다르다. 합치지 말 것**:
 *    · `FloorStack` 의 `MIN_SAMPLE` — 구 층대별 단가에서 수치를 아예 안 적는 임계
 *    · 서버 L5 의 `min_n`(`supabase/schema.sql`) — 그 근거 단계를 채택할지 정하는 임계
 *    여기 것은 "값은 내되 못 미덥다고 표시할" 임계다.
 */
const THIN_SAMPLE = 5;

export function PriceBandSection({
  bands,
  basePrices,
  failed,
  floors,
  hasTxStats,
  openFloor,
  onPickFloor,
}: Props) {
  // 못 읽었으면 "참고 시세 없음"이라고 적지 않는다 — 없는 것과 모르는 것은 다르다.
  if (failed) return null;

  // 아직 안 왔으면 자리를 잡아 둔다. 이 질문은 500m 반경 + 층 루프라 형제들보다 늦게
  // 온다 — 나중에 섹션이 툭 튀어나오면 페이지가 밀리고, 그 사이 "모름"이 "없음"과
  // 같아 보인다.
  if (bands === null) {
    return (
      <SectionCard plan={SECTION_PLAN.band} className="band band--wait" summary="불러오는 중…" />
    );
  }
  if (bands.length === 0) return null;

  // ⚠️ gate_fail 은 floor_no=null 한 줄로 온다 — 층과 짝지으면 조용히 사라진다.
  //    그래서 짝짓기보다 **먼저** 가른다.
  if (bands.some((b) => b.status === 'gate_fail')) {
    return (
      <SectionCard
        plan={SECTION_PLAN.band}
        className="band"
        // 접혀 있어도 이 한 줄은 보인다 — 아래 본문과 **같은 글자를 쓰지 않는다**(같은 말이
        // 화면에 둘이면 이름으로 찾는 시험이 어느 쪽을 잡았는지 모르게 된다).
        summary="아직 참고 시세를 내지 않는 구입니다"
      >
        <p className="band__gate">
          <strong>이 건물이 속한 구 전체는 아직 참고 시세를 내지 않습니다.</strong> 지난 거래로
          미리 맞혀 보는 시험에서 기준을 넘은 지역에서만 냅니다 — 아직 시험을 보지 않았거나,
          봤는데 기준에 못 미친 곳입니다. 나중에 다시 시험해 기준을 넘으면 그때 열립니다.
          {hasTxStats && (
            <> 『층대별 거래 단가』는 신고된 거래를 그대로 센 값이라 그대로 보실 수 있습니다.</>
          )}
        </p>
      </SectionCard>
    );
  }

  const { listed, silent } = groupBands(bands, floors);
  if (listed.length === 0 && silent.length === 0) return null;

  // 고시가격은 밴드와 **다른 자료**다 — 밴드가 없어도 있을 수 있고, 있어도 없을 수 있다.
  // 그래서 짝짓기도 따로 한다(밴드 목록에 끼워 넣으면 두 값이 한 줄에서 섞인다).
  const baseRows = pairBasePrices(basePrices, floors);

  const okGroups = listed.filter((g) => g.band.status === 'ok');
  const hasOk = okGroups.length > 0;
  const hasFar = okGroups.some((g) => isFarStage(g.band.stage));
  // '표본 적음' 각주는 그 표식이 실제로 붙은 줄이 있을 때만 낸다. 배제 조건이 `isSinglePoint`
  // (= 폭 0)이면 n=2~4 동률 줄에서 표식은 붙는데 각주만 사라진다 — 배제는 n=1 하나뿐이다.
  const hasThin = okGroups.some((g) => g.band.n !== 1 && (g.band.n ?? 0) < THIN_SAMPLE);
  const noEvidenceNames = silent.map((f) => formatFloor(f.floor_no, f.floor_label));
  const hasUnderground = silent.some((f) => f.floor_no < 0);
  // 기간은 화면에 글자로 박지 않는다 — 서버가 준 창의 시작 달을 그대로 쓴다.
  const from = bands.find((b) => b.window_from)?.window_from ?? null;

  // 접혀 있어도 보이는 한 줄 — 값을 낸 층이 몇 개인지.
  // ⛔ 여기에 **숫자(값)를 적지 않는다.** 요약 줄에는 근거 단계·표본 수를 함께 실을 자리가
  //    없는데, 값만 떼어 내보내는 것은 절대 규칙 3 위반이다(값과 근거는 한 몸이다).
  const okFloorCnt = okGroups.reduce((sum, g) => sum + g.floors.length, 0);
  const summary =
    okFloorCnt > 0 ? `값을 낸 층 ${okFloorCnt}개` : '이 건물에서는 값을 낸 층이 없습니다';

  return (
    <SectionCard plan={SECTION_PLAN.band} className="band" summary={summary}>
      <p className="band__lead">
        곁에서 실제로 팔린 값으로 어림한 폭입니다.{' '}
        <strong>사고파는 값이고 월세·보증금이 아닙니다.</strong>
      </p>

      {listed.length > 0 && (
        <ol className="band__rows">
          {listed.map((g) => {
            // 여러 층을 묶은 줄은 맨 위 층을 펼친다. 지금 펼쳐진 층이 이 줄에 들어 있으면
            // 줄을 표시해 둔다 — 위아래 두 목록이 서로를 가리키게 하는 유일한 표시다.
            const open = g.floors.some((f) => f.floor_no === openFloor);
            return (
              <li key={g.key} className={`band__row${open ? ' band__row--on' : ''}`}>
                <button
                  type="button"
                  className="band__hit"
                  aria-expanded={open}
                  onClick={() => onPickFloor(g.floors[0].floor_no)}
                >
                  <span className="band__floor">{g.label}</span>
                  <BandBody group={g} />
                </button>
              </li>
            );
          })}
        </ol>
      )}

      {noEvidenceNames.length > 0 && (
        <p className="band__none-note">
          <strong>참고 시세를 내지 않은 층: {noEvidenceNames.join(' · ')}</strong> — 맞혀 보는
          시험에 쓸 거래가 한 건도 없어 <strong>검증한 적이 없습니다</strong>. 거래가 쌓이면
          나오는 것이 아니라 원래 자료에 없는 것입니다.
          {hasUnderground && (
            <>
              {' '}
              (지하는 {TX_BASEMENT_MISSING_SINCE}년부터 실거래 자료에 층 표기가 아예 오지
              않습니다.)
            </>
          )}
        </p>
      )}

      {hasOk && (
        <>
          <p className="grade">
            <span className="grade__badge grade__badge--est">C등급 · 파생 추정</span>
            신고된 값이 아니라 <strong>곁의 거래로 어림한 값</strong>입니다.
          </p>
          <ul className="band__why">
            <li>
              총액은 이 층 전체가 아니라 <strong>비슷한 호실 한 칸</strong>을 곁 거래들의 가운데
              면적으로 환산한 값입니다. 이 층의 실제 면적과는 다릅니다.
            </li>
            <li>
              우리가 지난 거래로 맞혀 본 것은 <strong>가운데값</strong>입니다. 위아래 폭은 곁
              거래들이 흩어진 정도일 뿐이라, 그 안에 들어맞을 확률은 아직 재본 적이 없습니다.
            </li>
            {hasFar && (
              <li>
                <strong>먼 근거</strong>는 이 땅에서 멀리 떨어진 거래로 어림했다는 뜻입니다 —
                가까운 거래로 낸 값보다 많이 빗나갑니다. 특히 넓게 보셔야 합니다.
              </li>
            )}
            {hasThin && (
              <li>
                <strong>표본 적음</strong>은 곁 거래가 다섯 건이 안 된다는 뜻입니다. 폭이
                통계라기보다 우연에 가깝습니다.
              </li>
            )}
            <li>
              같은 건물이라도 자리·상태에 따라 실제 계약은 이 폭을 벗어납니다.{' '}
              <strong>“이 가격이다”가 아니라 “이 언저리다”</strong>로만 봐 주세요.
            </li>
          </ul>
          <p className="band__src">
            출처: 국토교통부 상업업무용 부동산 매매 실거래가 · 집합(구분소유) 거래
            {from ? ` ${formatYearMonth(from)} 이후 계약분` : ''}으로 계산.
          </p>
        </>
      )}

      {(listed.some((g) => g.band.status !== 'ok') || noEvidenceNames.length > 0) && hasTxStats && (
        <p className="band__alt">
          값을 내지 않은 층도 『층대별 거래 단가』에서{' '}
          <strong>신고된 거래를 그대로 센 값</strong>은 보실 수 있습니다.
        </p>
      )}

      <BasePriceBlock rows={baseRows} />
    </SectionCard>
  );
}

/**
 * 국세청 기준시가 — 이 카드에서 **유일하게 추정이 아닌 값**이다.
 *
 * ⛔ 위 밴드와 **같은 줄에 섞지 않는다.** 사람은 나란히 놓인 두 숫자를 자동으로 "같은 것의
 *    두 가지 측정"으로 읽는데, 이 둘은 다른 자로 잰 다른 값이다(세금 매기는 기준 vs 곁
 *    거래로 어림한 값). 그래서 자리도 맨 끝이고, 배지도 색이 다르고(사실 = 호박), 첫 문장이
 *    "시세가 아니다"라고 못 박는다.
 * ⛔ 두 값을 빼거나 나눠 "몇 배"를 적지 말 것 — 그건 우리가 만든 새 추정이고, 결재받은
 *    적이 없다.
 * ⛔ **총액(억)으로 환산하지 말 것.** 서버가 면적을 안 준다. 바로 위 `BandBody` 의
 *    `toTotalWon(band.median, area)` 를 베껴 오고 싶어지는 자리인데, 그 면적은 **곁 거래들의
 *    전용면적 중앙값**이라 이 값과 아무 상관이 없고(남의 면적), 애초에 고시가격의 총액은
 *    전용이 아니라 (전용 + 공유)를 곱해야 한다. 그래서 여기는 ㎡당만 적는다.
 * ⓘ 부기는 **카드 안에서 한 번만** 한다(줄마다 반복하면 목록이 안 읽힌다).
 */
function BasePriceBlock({ rows }: { rows: BasePriceRow[] }) {
  // 자료가 없거나 못 읽었으면 아무것도 안 그린다 — "기준시가 없음"이라고 적지 않는다
  // (이 카드의 다른 블록들과 같은 원칙: 없는 것과 모르는 것은 다르다).
  if (rows.length === 0) return null;

  return (
    <div className="band__base">
      <h4 className="band__base-h">국세청 기준시가</h4>
      <ul className="band__base-rows">
        {rows.map((r) => (
          <li key={r.key}>
            <span className="band__base-floor">{r.label}</span>
            {/*
              ⛔ 뒤에 '원'을 덧붙이지 않는다. `formatManWon` 은 1만 원 미만이면 **원 단위로**
                 적는데(그래야 '0만'으로 사라지지 않는다), 기준시가 원본 최저값이 5,000원/㎡ 라
                 그 층이 실제로 있다 — 덧붙이면 그 줄만 '㎡당 5,000원 원'이 된다.
                 화면의 다른 단가 표기('㎡당 380만')와도 이 형태가 같다.
            */}
            <span className="band__base-val">㎡당 {formatManWon(r.base.median_price_per_m2)}</span>
            {/*
              표본(호 수)을 값과 **한 몸으로** 적는다 — 이 값은 층 하나의 고시가격이 아니라
              그 층 호실들의 가운데값이다(절대 규칙 3). 고시일도 서버가 준 글자를 그대로
              쓴다: 해가 바뀌면 자료만 갈아 끼워도 화면이 저절로 따라온다.
            */}
            <span className="band__base-sub">
              호 {r.base.ho_cnt.toLocaleString('ko-KR')}개 가운데값
              {r.base.notice_date ? ` · ${r.base.notice_date} 고시` : ''}
            </span>
          </li>
        ))}
      </ul>
      <p className="grade">
        <span className="grade__badge">A등급 · 공식 고시</span>
        국세청이 해마다 고시하는 <strong>세금 매길 때 쓰는 기준가격</strong>입니다 —{' '}
        <strong>시세가 아닙니다.</strong> 우리가 어림한 값이 아니라 고시된 값 그대로이고, 위
        참고 폭과는 다른 자로 잰 값이라 서로 견주기 어렵습니다.
      </p>
    </div>
  );
}

/** 값 칸. status 넷이 각각 다른 말을 한다. */
function BandBody({ group }: { group: BandGroup }) {
  const band = group.band;
  if (band.status !== 'ok') {
    return <span className="band__none">{missingLabel(band.status)}</span>;
  }

  // 근거를 말할 수 없으면 값도 내지 않는다 — 절대 규칙 3은 "값과 근거는 한 몸"이라는 뜻이다.
  const label = describeStage(band.stage, group.floors[0].floor_no);
  if (
    label === null ||
    band.n === null ||
    band.median === null ||
    band.p25 === null ||
    band.p75 === null
  ) {
    return <span className="band__none">근거를 표시할 수 없어 값을 내지 않습니다</span>;
  }

  const area = band.median_area_m2;
  const count = `거래 ${band.n.toLocaleString('ko-KR')}건`;
  // 층대 평균은 층별로 따로 잰 값이 아니다. 라벨만으로도 알 수 있게 했지만, 한 줄로 묶여
  // 여러 층을 덮을 때가 많아 한 번 더 못 박는다.
  const note = band.stage === 'L6' ? '층별로 따로 잰 값이 아닙니다' : null;

  // 폭이 0인 밴드는 '2.4억~2.4억'으로 적지 않는다 — 사람은 그걸 "아주 정확하다"로 읽는데
  // 사실은 정반대다. 밴드가 아니라 사실로 적는다(채택의 절반이 최소 표본 1건짜리 단계라
  // 드문 예외가 아니다).
  //
  // ⚠️ 다만 폭이 0인 **까닭이 둘**이라 문장을 갈라야 한다: ① 곁 거래가 한 건뿐이라 폭이
  //    없는 것 ② 여러 건인데 **전부 같은 단가**로 신고돼 사분위 셋이 같아진 것(`unit_price`
  //    가 생성 컬럼이라 같은 층 동일 단가 신고가 겹치면 그렇게 된다 — 라이브에 실제로 있다).
  //    하나로 뭉뚱그리면 "1건뿐"이라 적어 놓고 바로 밑 근거 줄에서 "거래 10건"이라 말하는
  //    자기모순이 난다. 판정(`isSinglePoint`)은 폭을 묻는 것이므로 그대로 두고, **문구만** 가른다.
  if (isSinglePoint(band)) {
    const one = toTotalWon(band.median, area);
    const pointMarks = [
      isFarStage(band.stage) ? '먼 근거' : null,
      // n=1 은 헤드라인이 이미 "1건뿐"이라 말한다 — 표식을 겹쳐 붙이지 않는다.
      band.n > 1 && band.n < THIN_SAMPLE ? '표본 적음' : null,
    ].filter((m): m is string => m !== null);
    return (
      <>
        <span className="band__val">
          {band.n === 1
            ? `곁의 거래 1건뿐 — 그 거래는 ㎡당 ${formatManWon(band.median)}`
            : `곁 거래 ${band.n.toLocaleString('ko-KR')}건이 모두 같은 값 — ㎡당 ${formatManWon(band.median)}`}
        </span>
        <span className="band__sub">
          {one !== null && (
            <>
              비슷한 호실 한 칸 {formatArea(area)} 기준 {formatEokBand(one, one)} ·{' '}
            </>
          )}
          근거: {label} · {count}
          {note !== null && <> · {note}</>}
          {pointMarks.length > 0 && <> · {pointMarks.join(' · ')}</>}
        </span>
      </>
    );
  }

  const lo = toTotalWon(band.p25, area);
  const hi = toTotalWon(band.p75, area);
  const perBand = formatManWonBand(band.p25, band.p75);
  const marks = [
    isFarStage(band.stage) ? '먼 근거' : null,
    band.n < THIN_SAMPLE ? '표본 적음' : null,
  ].filter((m): m is string => m !== null);

  return (
    <>
      <span className="band__val">
        {lo !== null && hi !== null
          ? `비슷한 호실 한 칸 ${formatArea(area)} 기준 ${formatEokBand(lo, hi)}`
          : `㎡당 ${perBand}`}
      </span>
      <span className="band__sub">
        {lo !== null && hi !== null && <>㎡당 {perBand} · </>}
        가운데값 ㎡당 {formatManWon(band.median)} · 근거: {label} · {count}
        {note !== null && <> · {note}</>}
        {marks.length > 0 && <> · {marks.join(' · ')}</>}
      </span>
    </>
  );
}

/**
 * 값을 못 내는 층의 사유.
 *
 * ⛔ `no_evidence` 에 "표본 부족"을 쓰지 않는다 — "조금만 더 모으면 나오나?"라는 오해를
 *    만든다(결정 0001). 그 층은 아예 줄로 그리지 않고 각주에서 한 번만 말한다.
 */
function missingLabel(status: string): string {
  if (status === 'floor_1f') {
    return '1층은 내지 않습니다 — 같은 1층이라도 큰길 코너인지 골목 안쪽인지에 따라 값이 크게 갈리는데, 그 자리를 알려 주는 자료가 공공데이터에 없습니다.';
  }
  return '표본 부족 — 곁에서 참고할 만한 거래를 아직 찾지 못했습니다. 거래가 쌓이면 나올 수 있습니다.';
}
