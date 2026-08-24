/**
 * 주소창에 "지금 무엇을 보고 있는지"를 담고, 다시 읽어 내는 **순수 부품**.
 *
 * 왜 필요한가
 * -----------
 * 지금까지 이 앱은 새로고침하면 **처음 화면으로 돌아갔다.** 한참 찾아 들어간 건물을
 * 다시 찾으려면 구를 고르고 검색어를 치는 일을 되풀이해야 했다. 주소에 담아 두면
 * 그 셋이 한꺼번에 풀린다 — **새로고침 복원 · 즐겨찾기 · 폰에서 이어보기.**
 * 이름은 '공유 링크'지만 값어치의 절반은 혼자 쓸 때 나온다.
 *
 * 왜 물음표 방식인가 (`/?sgg=...&bld=...`)
 * ----------------------------------------
 * 폴더 방식(`/건물/1234`)이 주소줄은 깔끔하지만, 그러려면 "무슨 주소로 들어와도 첫
 * 화면을 보여줘라"라는 서버 설정(SPA rewrite)이 필요하다. 그 설정은 **정적 파일까지
 * 첫 화면으로 바꿔치기할 위험**을 함께 진다 — 이 앱에는 지도 상권 파일(1.1MB)이
 * 그렇게 죽을 수 있다. 물음표 방식은 주소가 늘 첫 화면이라 서버 설정을 아예 안 건드린다
 * (사장님 결정 2026-08-25).
 *
 * 왜 값을 검사하나
 * ----------------
 * 주소는 **누구나 손으로 고칠 수 있는 입력**이다. 형식이 아닌 값을 그대로 믿으면
 * 쓸데없는 서버 요청이 나가고, 화면은 "찾는 중"에서 멈춘 것처럼 보인다. 형식에 안
 * 맞으면 **없는 것으로 친다** — 그러면 그냥 첫 화면이 뜬다(고장난 화면이 아니다).
 *
 * 이 파일은 일부러 아무 일도 하지 않는다 — `window` 도 `supabase` 도 건드리지 않는다.
 * 그래야 테스트가 브라우저를 흉내 낼 필요 없이 값만 넣어 확인할 수 있다
 * (`appConstants.ts` 가 같은 이유로 순수 모듈인 것과 같은 결).
 */

/** 주소에 담기는 것. 담을 게 없으면 null. */
export type AppUrlState = {
  /** 시군구 코드 5자리. 예: '11680'(강남구) */
  sigungu: string | null;
  /** 건물 번호. 예: '1168010100107110006_10241100261590' */
  bldId: string | null;
};

/** 주소에 쓰는 이름. 짧게 두되, 한글을 안 쓴다(주소창에서 %ED%95%9C… 로 깨져 보인다). */
export const SIGUNGU_PARAM = 'sgg';
export const BLD_PARAM = 'bld';

/** 시군구 코드는 숫자 5자리다. */
const SIGUNGU_RE = /^\d{5}$/;

/**
 * 건물 번호는 `PNU(19자리)_숫자` 다.
 *
 * 라이브 실측(2026-08-25): 242,631개 **전부** 이 형식이고 가장 긴 것이 42자다.
 * 뒷자리 상한을 32로 두어 넉넉히 받으면서도 끝없이 긴 값은 거른다.
 */
const BLD_RE = /^\d{19}_\d{1,32}$/;

/** 형식에 맞을 때만 값을 돌려준다. 아니면 null(= 없는 것으로 친다). */
function clean(value: string | null, pattern: RegExp): string | null {
  if (value === null) return null;
  const trimmed = value.trim();
  return pattern.test(trimmed) ? trimmed : null;
}

/**
 * 주소의 물음표 뒷부분에서 상태를 읽는다.
 *
 * @param search `window.location.search` 그대로(`'?sgg=11680&bld=...'`). 빈 문자열도 된다.
 */
export function parseAppUrl(search: string): AppUrlState {
  const params = new URLSearchParams(search);
  const sigungu = clean(params.get(SIGUNGU_PARAM), SIGUNGU_RE);
  const bldId = clean(params.get(BLD_PARAM), BLD_RE);

  // 구가 형식에 안 맞는데 건물만 성한 경우가 있다(주소를 손으로 잘못 고친 때).
  // 건물 번호 앞 5자리가 곧 시군구 코드라 거기서 되찾는다 — 링크 하나가 통째로
  // 버려지는 것보다 낫다.
  if (bldId && !sigungu) {
    return { sigungu: bldId.slice(0, 5), bldId };
  }
  return { sigungu, bldId };
}

/**
 * 상태를 주소의 물음표 뒷부분으로 만든다.
 *
 * 담을 게 없으면 **빈 문자열**을 돌려준다 — `'?'` 만 남은 주소를 만들지 않는다.
 * 값이 있는 것만 넣으므로 구만 고른 상태도 그대로 표현된다.
 */
export function buildAppSearch(state: AppUrlState): string {
  const params = new URLSearchParams();
  const sigungu = clean(state.sigungu, SIGUNGU_RE);
  const bldId = clean(state.bldId, BLD_RE);

  if (sigungu) params.set(SIGUNGU_PARAM, sigungu);
  if (bldId) params.set(BLD_PARAM, bldId);

  const query = params.toString();
  return query ? `?${query}` : '';
}

/**
 * 남에게 보낼 수 있는 온전한 주소를 만든다.
 *
 * @param origin  `window.location.origin` (`'https://sangga-one.vercel.app'`)
 * @param pathname `window.location.pathname` (`'/'`)
 */
export function buildShareUrl(origin: string, pathname: string, state: AppUrlState): string {
  return `${origin}${pathname}${buildAppSearch(state)}`;
}

/**
 * 지금 주소와 새 주소가 같은지 본다.
 *
 * 같은 값을 다시 쓰면 브라우저 기록이 쓸데없이 흔들리므로, 바뀐 때만 쓰기 위해 쓴다.
 */
export function isSameSearch(currentSearch: string, state: AppUrlState): boolean {
  const next = buildAppSearch(state);
  const now = currentSearch === '?' ? '' : currentSearch;
  return now === next;
}
