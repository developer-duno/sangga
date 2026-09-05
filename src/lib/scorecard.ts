import { SCORECARD_URL } from './appConstants';
import type { PriceGateRow, Scorecard, ScorecardOpsMode } from '../types';

/**
 * "참고 시세는 얼마나 맞나" 카드의 **순수 계산**만 모은다(로드맵 Wave 4 — 성적표 공개).
 *
 * ⛔ **이 파일과 `ScorecardSection.tsx` 에는 통계 수치가 한 개도 없다.**
 *    로드맵이 "숫자 복사 금지"라고 못박은 자리라, 오차·커버리지·비중은 전부 서버
 *    (`list_price_gate()`)와 구워 둔 파일(`/scorecard-v1.json`)에서 읽는다. 숫자를 한 번
 *    옮겨 적으면 성적표를 다시 뽑는 날 화면만 옛 성적을 말하고, 그것은 에러가 아니라
 *    **조용한 거짓말**이다. 그 사실을 `scorecard.test.ts` 가 정규식으로 지킨다.
 *
 * ⛔ **판정을 다시 하지 않는다.** "이 구가 통과했나"는 서버가 준 `gate_pass` 그대로다.
 *    기준선(결정 0013 §2)을 화면이 다시 계산하면 기준을 바꾸는 날 두 곳이 다른 말을 한다 —
 *    아래 `GATE_MDAPE_LIMIT` 은 **판정용이 아니라 설명용**이다(왜 떨어졌는지 말할 때만 쓴다).
 */

/**
 * 출시 기준선의 오차 상한(결정 0013 §2 ①). **비율**이다.
 *
 * ⛔ **판정에 쓰지 않는다.** 통과 여부는 서버가 이미 정해 `gate_pass` 로 주고, 화면은 그것을
 *    그대로 믿는다. 이 상수가 쓰이는 곳은 딱 하나 — 떨어진 구에서 `gateLine()` 이
 *    "무엇을 못 넘었나"를 **글자로 설명할 때**뿐이다. (조건 ②(구평균을 이길 것)는 값 둘을
 *    견주면 나오므로 따로 적어 둘 상수가 없다.)
 * ⚠️ **기준선의 주인은 `scripts/backtest_price.py` 의 `GATE_MAX_MDAPE` 다**(그 파일의
 *    `gate_pass()` 가 판정을 계산하고, `통과구.csv` → `price_gate_sigungu` 로 흘러간다).
 *    `scripts/load_price_gate.py` 는 그 판정을 **다시 계산해 대조**만 하므로 기준선을 갖고
 *    있지 않다. 기준선 자체를 바꾸는 것은 **사장님 재결재 사항**이고(결정 0013 §4), 그때
 *    `backtest_price.GATE_MAX_MDAPE` 와 이 상수를 같은 커밋에서 함께 고친다.
 *    ⓘ 둘이 갈라지면 `tests/test_price_gate_migration.py` 가 잡는다 — 화면 문구만 옛
 *      기준선을 말하는 상태는 에러가 안 나서 아무도 모른다.
 */
export const GATE_MDAPE_LIMIT = 0.3;

/** 운영모드 표에서 "사다리가 실제로 어느 칸에서 멈췄나"를 담고 있는 줄들의 이름표. */
const ADOPTED_STAGE_KIND = '채택단계';
/** 같은 표에서 전체 합계를 담고 있는 줄의 이름표. */
const OVERALL_KIND = '전체';

/**
 * 단계 코드가 무슨 뜻인지 **사람 말로**.
 *
 * ⓘ 여기 있는 것은 성적이 아니라 **방법의 정의**다(성적표 v1 §1 의 단계 표를 쉬운 말로
 *   옮긴 것 — 거기 §0 이 이미 같은 말을 하고 있다). 그래서 숫자 복사 금지에 걸리지 않는다:
 *   성적표를 다시 뽑아도 "L2 = 같은 건물 같은 층"이라는 뜻은 안 변한다.
 * ⚠️ 모르는 코드가 오면 **지어내지 않는다** — 코드를 그대로 적고 설명은 비운다.
 *   부동산원 종류 목록(`rentStats.BLD_TYPE_ORDER`)에서와 같은 원칙이다.
 */
const STAGE_NOTES: Record<string, string> = {
  L2: '같은 건물 같은 층에서 실제로 팔린 값',
  L4: '걸어서 1~2분 거리(100m) 안, 같은 층',
  L5: '500m 안, 같은 층',
  L6: '같은 동네(법정동)의 비슷한 층',
  no_estimate: '곁에 견줄 거래가 없어 값을 못 냄',
};

/** 화면에 그리는 단계 분포 한 줄. */
export type StageShare = {
  /** 'L2'·'L6'·'no_estimate' — 성적표가 쓰는 코드 그대로. */
  code: string;
  /** 그 코드가 무슨 뜻인지 사람 말로. 모르는 코드면 빈 문자열. */
  note: string;
  /** 이 단계에서 멈춘 거래 수. */
  n: number;
  /** 전체 검증 거래 중 비중(0~1). 화면이 %로 바꿔 적는다. */
  share: number | null;
  /** 그 단계에서 잰 오차 중앙값(0~1). 값을 못 낸 줄은 **null 이 정상**이다. */
  mdape: number | null;
  /** ±20% 안에 맞힌 비율(0~1). */
  hit20: number | null;
};

/* ── 서버에서 오는 것(게이트) ────────────────────────────────────────────── */

function isNullableNumber(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'number';
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

/**
 * 서버 응답의 **모양**을 본다.
 *
 * 타입 단언(`as PriceGateRow[]`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아 주지
 * 않는다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 카드는 **입구**에 있어
 * 터지면 검색창·지역 고르개까지 함께 사라진다(LH 공고 카드와 같은 이유).
 */
export function isPriceGateRow(x: unknown): x is PriceGateRow {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.sigungu_code === 'string' &&
    isNullableString(r.sigungu_nm) &&
    isNullableNumber(r.n_paired) &&
    isNullableNumber(r.ladder_mdape) &&
    isNullableNumber(r.base_mdape) &&
    typeof r.gate_pass === 'boolean' &&
    isNullableString(r.loaded_at)
  );
}

/** ⓘ 빈 배열은 "게이트 표가 아직 안 채워졌다"는 뜻이라 **정상 답이 아니다**(화면이 가른다). */
export function isPriceGateList(x: unknown): x is PriceGateRow[] {
  return Array.isArray(x) && x.every(isPriceGateRow);
}

/** 고른 구의 줄. 없으면 null — "아직 성적을 안 낸 지역"과 같은 뜻이다. */
export function pickGate(
  rows: readonly PriceGateRow[],
  sigunguCode: string | null,
): PriceGateRow | null {
  if (!sigunguCode) return null;
  return rows.find((r) => r.sigungu_code === sigunguCode) ?? null;
}

/* ── 구워 둔 파일에서 오는 것(방법·단계 분포) ───────────────────────────── */

function isOpsRow(x: unknown): x is ScorecardOpsMode {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.kind === 'string' &&
    typeof r.axis_value === 'string' &&
    typeof r.axis_name === 'string' &&
    isNullableNumber(r.n_verified) &&
    isNullableNumber(r.coverage) &&
    isNullableNumber(r.mdape) &&
    isNullableNumber(r.hit20)
  );
}

/**
 * 구워 둔 파일의 **모양**을 본다.
 *
 * ⚠️ `stages` 는 있는지만 본다 — 지금 화면이 읽는 것은 `ops_modes` 뿐이라, 없는 것을
 *    까다롭게 따지면 파일을 조금만 손봐도 카드가 통째로 사라진다.
 */
export function isScorecard(x: unknown): x is Scorecard {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.version === 'string' &&
    typeof r.generated_at === 'string' &&
    Array.isArray(r.stages) &&
    Array.isArray(r.ops_modes) &&
    r.ops_modes.every(isOpsRow)
  );
}

/** 진행 중인 요청까지 함께 잡아 둔다 — 두 곳에서 동시에 불러도 왕복은 한 번이다. */
let cached: Promise<Scorecard> | null = null;

/**
 * 성적표 파일 하나만 읽는 창구(`districts.ts` 와 같은 틀).
 *
 * 한 번 받으면 세션 내내 다시 받지 않는다 — 구를 바꿔도 성적표는 그대로다.
 */
export function loadScorecard(): Promise<Scorecard> {
  if (!cached) {
    cached = fetch(SCORECARD_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`성적표 파일 응답이 ${res.status} 입니다`);
        return res.json();
      })
      .then((doc: unknown) => {
        // 모양이 아니면 여기서 막는다 — 반쪽짜리 파일이 화면으로 흘러가면 카드가
        // "0%"처럼 **그럴듯하게 틀린** 값을 적게 된다.
        if (!isScorecard(doc)) throw new Error('성적표 파일의 모양이 다릅니다');
        return doc;
      })
      .catch((err) => {
        // ⚠️ 실패는 캐시하지 않는다. 여기서 지우지 않으면 잠깐 끊겼던 한 번 때문에
        //    새로고침 전까지 성적표가 영영 안 뜬다(다시 시도할 길이 막힌다).
        cached = null;
        throw err;
      });
  }
  return cached;
}

/** ⓘ 시험이 각 경우를 처음부터 다시 보게 하는 용도. 화면은 안 쓴다. */
export function resetScorecardCache(): void {
  cached = null;
}

/* ── 사람이 읽는 글자로 ──────────────────────────────────────────────────── */

/**
 * 비율(0~1)을 백분율 글자로. 값이 아니면 null.
 *
 * ⛔ 백분율 글자를 화면에 **직접 적지 않기 위한** 함수다. 숫자는 전부 서버·파일에서 오고
 *    여기서 모양만 입는다.
 * ⓘ 이 주석에도 예시 수치를 적지 않는다 — 가드(`scorecard.test.ts`)가 주석·코드를 가리지
 *   않고 훑는다. 가리게 만들면 "주석에는 적어도 된다"는 구멍이 생기고, 그 구멍으로 옛
 *   숫자가 들어와 다음 사람을 헷갈리게 한다.
 */
export function formatPercent(ratio: number | null | undefined, digits = 1): string | null {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return null;
  return `${(ratio * 100).toFixed(digits)}%`;
}

/**
 * 접혀 있어도 보이는 한 줄 — **고른 구가 참고 시세를 받는가**.
 *
 * ⛔ 떨어진 구에는 **왜 떨어졌는지**를 적는다. "제공하지 않음"만 적으면 사람은 자료가
 *    없는 줄 알지만, 실제로는 자료가 있는데도 **이미 화면에 있는 구 평균보다 못해서**
 *    안 내는 경우가 있다(결정 0013 §2 의 조건 ②가 있는 이유). 그 구별이 이 카드의 본론이다.
 */
export function gateLine(row: PriceGateRow | null): string {
  if (row === null) return '이 지역은 아직 성적을 내지 않았습니다';

  const ladder = formatPercent(row.ladder_mdape);
  const base = formatPercent(row.base_mdape);

  if (row.gate_pass) {
    const parts = ['참고 시세 제공'];
    if (ladder !== null) parts.push(`오차 중앙값 ${ladder}`);
    // 근거 표본 수를 함께 적는다(절대 규칙 3 — 값에는 늘 근거와 표본이 붙는다).
    if (row.n_paired !== null && row.n_paired !== undefined) {
      parts.push(`검증 거래 ${row.n_paired.toLocaleString('ko-KR')}건`);
    }
    return parts.join(' · ');
  }

  const reasons: string[] = [];
  const overLimit = row.ladder_mdape !== null && row.ladder_mdape > GATE_MDAPE_LIMIT;
  const losesToBase =
    row.ladder_mdape !== null &&
    row.base_mdape !== null &&
    row.ladder_mdape >= row.base_mdape;

  if (overLimit && ladder !== null) {
    reasons.push(`오차 중앙값 ${ladder} 가 기준선 ${formatPercent(GATE_MDAPE_LIMIT, 0)} 를 넘습니다`);
  }
  if (losesToBase && base !== null) {
    // 앞 문장이 이미 사다리 오차를 말했으면 되풀이하지 않는다.
    reasons.push(
      overLimit ? `구평균 ${base} 보다도 큽니다` : `사다리 ${ladder} 가 구평균 ${base} 를 못 이깁니다`,
    );
  }

  if (reasons.length === 0) return '참고 시세를 제공하지 않습니다';
  return `참고 시세 제공 안 함 — ${reasons.join(' · ')}`;
}

/**
 * 사다리가 실제로 어느 칸에서 멈췄나 — **화면에서 체감하는 분포**.
 *
 * ⚠️ 단계별 성적표(`stages`)와 **다른 집합**이라 섞으면 안 된다. 사다리는 앞 단계가 못 푼
 *    거래만 뒤로 넘기므로, 뒤 단계 칸에는 "앞이 못 푼 어려운 거래"만 남는다(성적표 v1 §3-4
 *    의 경고). 여기서 쓰는 것은 `ops_modes` 의 '채택단계' 줄들뿐이다.
 *
 * ⛔ **비중이 큰 것부터** 세운다. 로드맵 Wave 4 가 "폴백 단계를 맨 앞에"라고 정한 이유가
 *    그것이다 — 제일 정확한 단계(같은 건물)를 먼저 보이면 사람은 그 성적을 이 서비스의
 *    성적으로 읽는데, 실제로 가장 자주 만나는 것은 맨 아래 폴백이다. 순서를 코드에
 *    못 박지 않고 **비중으로** 정하므로, 자료가 바뀌면 순서도 사실을 따라 바뀐다.
 */
export function stageDistribution(scorecard: Scorecard): StageShare[] {
  const rows = scorecard.ops_modes.filter((r) => r.kind === ADOPTED_STAGE_KIND);
  const overall = scorecard.ops_modes.find((r) => r.kind === OVERALL_KIND);

  const fallbackTotal = rows.reduce((sum, r) => sum + (r.n_verified ?? 0), 0);
  const total = overall?.n_verified ?? fallbackTotal;

  const out = rows.map((r) => {
    const n = r.n_verified ?? 0;
    return {
      code: r.axis_value,
      note: STAGE_NOTES[r.axis_value] ?? '',
      n,
      share: total > 0 ? n / total : null,
      mdape: r.mdape,
      hit20: r.hit20,
    };
  });

  // 같은 비중이면 코드 순으로 — 순서가 흔들리면 다시 그릴 때마다 줄이 춤춘다.
  out.sort((a, b) => (b.share ?? 0) - (a.share ?? 0) || a.code.localeCompare(b.code));
  return out;
}

/**
 * 커버리지를 **유리한 숫자라고 밝히는** 한 줄(결정 0013 §3 의 정직 공지).
 *
 * 백테스트의 커버리지는 "거래가 있었던 필지"에서 잰 값이다. 화면에서 만나는 보통 건물은
 * 자기 거래가 없어 대부분 아래 단계로 내려가므로, 이 숫자를 그냥 적으면 실제보다 잘
 * 맞는 것처럼 읽힌다. 값을 못 읽으면 **문장 자체를 안 만든다**(지어내지 않는다).
 */
export function coverageNote(scorecard: Scorecard): string | null {
  const overall = scorecard.ops_modes.find((r) => r.kind === OVERALL_KIND);
  const coverage = formatPercent(overall?.coverage);
  if (coverage === null) return null;
  return (
    `채점한 거래 가운데 ${coverage} 에서 값이 나왔습니다 — 다만 이 숫자는 실제보다 ` +
    '유리합니다. 채점 대상이 애초에 "거래가 있었던 땅"이라, 화면에서 만나는 보통 건물은 ' +
    '자기 거래가 없어 대부분 아래 단계로 내려갑니다.'
  );
}

/**
 * '2026-08-15T23:44:00+09:00' → '2026년 8월 15일'. 읽을 수 없으면 null.
 *
 * ⚠️ 시각까지 적지 않는다 — 성적표는 하루 단위로 이야기하는 자료라 분 단위는 정확해
 *    보이기만 하고 뜻이 없다.
 */
export function stampDate(generatedAt: string | null | undefined): string | null {
  if (!generatedAt) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(generatedAt.trim());
  if (!m) return null;
  return `${m[1]}년 ${Number(m[2])}월 ${Number(m[3])}일`;
}
