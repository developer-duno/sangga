import type { FloorRow, PriceBand } from '../types';
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
  /** true = 못 읽음 → 아무 말도 하지 않는다(없는 것과 모르는 것은 다르다). */
  failed: boolean;
  /** 이 **건물**의 층. 서버는 필지 전체를 주므로 여기서 걸러진다. */
  floors: FloorRow[];
  /** 『층대별 거래 단가』 블록이 실제로 화면에 있나(대안 안내를 낼지 정한다). */
  hasTxStats: boolean;
  openFloor: number | null;
  onPickFloor: (floorNo: number) => void;
};

const TITLE = '참고 매매 시세 (추정값)';

export function PriceBandSection({
  bands,
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
      <section className="band band--wait">
        <h3 className="band__h">{TITLE}</h3>
        <p className="band__lead">불러오는 중…</p>
      </section>
    );
  }
  if (bands.length === 0) return null;

  // ⚠️ gate_fail 은 floor_no=null 한 줄로 온다 — 층과 짝지으면 조용히 사라진다.
  //    그래서 짝짓기보다 **먼저** 가른다.
  if (bands.some((b) => b.status === 'gate_fail')) {
    return (
      <section className="band">
        <h3 className="band__h">{TITLE}</h3>
        <p className="band__gate">
          <strong>이 건물이 속한 구 전체는 아직 참고 시세를 내지 않습니다.</strong> 지난 거래로
          미리 맞혀 보는 시험에서 기준을 넘은 지역에서만 냅니다 — 아직 시험을 보지 않았거나,
          봤는데 기준에 못 미친 곳입니다. 나중에 다시 시험해 기준을 넘으면 그때 열립니다.
          {hasTxStats && (
            <> 『층대별 거래 단가』는 신고된 거래를 그대로 센 값이라 그대로 보실 수 있습니다.</>
          )}
        </p>
      </section>
    );
  }

  const { listed, silent } = groupBands(bands, floors);
  if (listed.length === 0 && silent.length === 0) return null;

  const okGroups = listed.filter((g) => g.band.status === 'ok');
  const hasOk = okGroups.length > 0;
  const hasFar = okGroups.some((g) => isFarStage(g.band.stage));
  // '표본 적음' 각주는 그 표식이 실제로 붙은 줄이 있을 때만 낸다. 배제 조건이 `isSinglePoint`
  // (= 폭 0)이면 n=2~4 동률 줄에서 표식은 붙는데 각주만 사라진다 — 배제는 n=1 하나뿐이다.
  const hasThin = okGroups.some((g) => g.band.n !== 1 && (g.band.n ?? 0) < 5);
  const noEvidenceNames = silent.map((f) => formatFloor(f.floor_no, f.floor_label));
  const hasUnderground = silent.some((f) => f.floor_no < 0);
  // 기간은 화면에 글자로 박지 않는다 — 서버가 준 창의 시작 달을 그대로 쓴다.
  const from = bands.find((b) => b.window_from)?.window_from ?? null;

  return (
    <section className="band">
      <h3 className="band__h">{TITLE}</h3>
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
          {hasUnderground && <> (지하는 2017년부터 실거래 자료에 층 표기가 아예 오지 않습니다.)</>}
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
    </section>
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
      band.n > 1 && band.n < 5 ? '표본 적음' : null,
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
    band.n < 5 ? '표본 적음' : null,
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
