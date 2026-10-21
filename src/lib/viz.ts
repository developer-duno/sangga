/**
 * 건물 화면의 그림 — 값을 좌표·폭(%)으로 바꾸는 순수 함수와 색 두 벌(결정 0038 §2·§5 V1).
 *
 * 왜 한 곳에 모으나 — 카드마다 같은 좌표 함수를 쓰고 색만 다르다(사실 = 호박 · 추정·비교값 = 회청 · §2-6). 좌표를
 * 카드마다 따로 셈하면 같은 값이 카드마다 다른 자리에 선다. (참고 시세 띠(A)는 결정 0041 로 카드째 내렸다 —
 * 그 띠의 축 상한·범위 함수 `niceCeil`·`rangePct` 는 실거래 구 층대 띠(B · V2 · `txViz.ts`)가 원형 그대로 다시 쓴다.)
 *
 * 지키는 것:
 *  · DOM 을 재지 않는다 — 모든 자리는 %(접힌 카드는 폭이 0 이라, 재서 그리면 종이에서 백지가 된다 · §2-3).
 *  · 없는 값은 그리지 않는다 — null·NaN·무한대·음수·합 0 이면 null 을 돌려준다. 0 으로 그리면 "모르는 것"이
 *    "없음"이 된다(§2-4). 부르는 쪽은 null 이면 그 조각을 안 그린다.
 *  · 비율을 글자로 내지 않는다 — 여기 숫자는 폭·자리에만 쓴다(결정 0033 · §2-6).
 *
 * 못 보는 것: 값의 단위가 맞는지(㎡당 원인지 만원인지)는 부르는 쪽 책임이다 — 여기는 같은 단위의 수 둘을 견줄 뿐이다.
 */

/**
 * 색 두 벌 + 층 미상 — CSS 변수 **이름**(`styles.css` 의 `:root`). 그림은 `cssVar(이름)` 으로 칠한다.
 * ⛔ 사실(A·B등급)과 추정(C등급)을 한 그림에 섞지 않는다 — 좌표 함수만 공유한다.
 */
export const VIZ_TONES = {
  /** 사실 — 호박. `steps` = 한 색의 진하기 4단(옅음 → 짙음). */
  fact: {
    bg: '--warn-bg',
    line: '--warn-line',
    steps: ['--fact-1', '--fact-2', '--fact-3', '--fact-4'],
  },
  /** 추정 — 회청. `band` = 띠 · `far` = 먼 근거의 연한 띠 · `ink` = 눈금·▲ · `track` = 바탕. */
  est: {
    bg: '--est-bg',
    line: '--est-line',
    track: '--est-chip',
    band: '--est-band',
    far: '--est-line',
    ink: '--est-ink',
  },
  /** 층 미상 — 회색(값이지 경고가 아니다 · §2-4). */
  na: '--viz-na',
} as const;

/** CSS 변수 이름 → `var(--이름)`. */
export function cssVar(name: string): string {
  return `var(${name})`;
}

function isFiniteNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/**
 * 축 상한 — 값보다 크거나 같은 가장 작은 '보기 좋은 수'(1 · 2 · 2.5 · 5 × 10ⁿ).
 * 예: 1,904.6 → 2,000 · 2,000 → 2,000 · 2,001 → 2,500 · 0.37 → 0.5.
 * 0 이하·NaN·무한대면 null(축을 세울 수 없다).
 */
export function niceCeil(v: number | null | undefined): number | null {
  if (!isFiniteNum(v) || v <= 0) return null;
  const mag = 10 ** Math.floor(Math.log10(v));
  for (const step of [1, 2, 2.5, 5, 10]) {
    const c = step * mag;
    // 부동소수 오차(2000 이 1999.9999… 로 나뉘는 것)를 견딘다 — 같은 값이면 그 값이 상한이다.
    if (c >= v * (1 - 1e-12)) return Number(c.toPrecision(12));
  }
  return Number((10 * mag).toPrecision(12));
}

/**
 * 값 → 0~100 축 위의 자리(%). 0 ≤ 값 ≤ 상한일 때만 — 상한보다 크면 100 에 붙인다(축 밖으로 안 나가게).
 * 값이 null·NaN·음수이거나 상한이 0 이하면 null.
 */
export function pctOf(value: number | null | undefined, max: number | null | undefined): number | null {
  if (!isFiniteNum(value) || !isFiniteNum(max) || max <= 0 || value < 0) return null;
  return Math.min(100, (value / max) * 100);
}

/**
 * 범위(lo~hi) → 띠의 `[왼쪽 %, 폭 %]`. lo > hi · 값 없음 · 음수 · 상한 0 이하면 null.
 * lo = hi 면 폭 0 — 부르는 쪽이 "띠 없이 눈금만"으로 그린다(폭 0 띠를 최소 폭으로 키우지 않는다).
 */
export function rangePct(
  lo: number | null | undefined,
  hi: number | null | undefined,
  max: number | null | undefined,
): { left: number; width: number } | null {
  const l = pctOf(lo, max);
  const h = pctOf(hi, max);
  if (l === null || h === null || (lo as number) > (hi as number)) return null;
  return { left: l, width: h - l };
}

/**
 * 쌓은 막대 칸 나누기 — 칸마다 `n ÷ 합 × 100`(차례는 받은 그대로).
 * 0 인 칸은 빼고 돌려준다(최소 폭 강제 금지 — "0곳"이 "조금 있음"처럼 보인다).
 * 칸 하나라도 음수·소수가 아닌 수가 아니거나(NaN 등) 합이 0 이면 null — 그림 전체를 안 그린다.
 */
export function stackPct<K extends string>(
  parts: ReadonlyArray<{ key: K; n: number }>,
): Array<{ key: K; pct: number }> | null {
  if (parts.length === 0) return null;
  if (!parts.every((p) => isFiniteNum(p.n) && p.n >= 0)) return null;
  const sum = parts.reduce((s, p) => s + p.n, 0);
  if (sum <= 0) return null;
  return parts.filter((p) => p.n > 0).map((p) => ({ key: p.key, pct: (p.n / sum) * 100 }));
}
