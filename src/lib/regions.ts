/**
 * 시도 목록과 "지금 열려 있는 지역".
 *
 * 결정 0006: **데이터·코드·화면은 전국을 전제로 짜되, 실제로 여는 지역만 가른다.**
 * 범위를 좁히는 게 아니라 전국 프레임 위에서 열림/잠김만 나눈다 — 나중에 지역을
 * 열 때 화면을 다시 설계하지 않기 위해서다.
 *
 * ⭐ **열린 지역의 진실은 이 파일 하나뿐이다.** 지역을 열려면 OPEN_SIDO_CODES 에
 *    코드를 더하면 된다. 화면 문구·잠금 표시·안내 팝업이 전부 여기서 파생된다.
 *
 * ⛔ 데이터가 실제로 들어오기 **전에** 코드를 더하면 화면이 거짓말을 한다
 *    (그 지역을 검색해도 아무것도 안 나온다). 적재 완료를 확인한 뒤에 연다.
 */

/** 시도 하나. code = 시군구코드·PNU 앞 2자리 (이름은 바뀌어도 코드는 안 바뀐다). */
export type Sido = {
  code: string;
  /** 화면에 쓰는 짧은 이름. '서울특별시'가 아니라 '서울' — 칩이 좁다. */
  name: string;
  /** 공식 명칭. 안내 문구에서 한 번씩 쓴다. */
  fullName: string;
};

/**
 * 전국 17개 시도. 순서는 인구·규모 대략순이 아니라 **행정 코드순**이다 —
 * 자의적인 순서는 "왜 우리 지역이 뒤에 있냐"는 오해를 부른다.
 *
 * ⚠️ 강원(51)·전북(52)은 특별자치도 전환 후 코드다. 옛 코드(42·45)는 과거 분기
 *    스냅샷에만 나오므로 화면 목록에는 넣지 않는다.
 *
 * ⚠️ 2026Q2부터 광주(29)·전남(46)이 폐지되고 `전남광주통합특별시`(코드 12)로
 *    통합됐다(라이브 실측: `bjd_code`에서 12는 활성 3,204건, 29·46은 비활성).
 *    옛 코드(29·46)는 과거 분기 스냅샷에만 나오므로 화면 목록에는 넣지 않는다.
 */
export const SIDOS: readonly Sido[] = [
  { code: '11', name: '서울', fullName: '서울특별시' },
  { code: '12', name: '전남광주', fullName: '전남광주통합특별시' },
  { code: '26', name: '부산', fullName: '부산광역시' },
  { code: '27', name: '대구', fullName: '대구광역시' },
  { code: '28', name: '인천', fullName: '인천광역시' },
  { code: '30', name: '대전', fullName: '대전광역시' },
  { code: '31', name: '울산', fullName: '울산광역시' },
  { code: '36', name: '세종', fullName: '세종특별자치시' },
  { code: '41', name: '경기', fullName: '경기도' },
  { code: '43', name: '충북', fullName: '충청북도' },
  { code: '44', name: '충남', fullName: '충청남도' },
  { code: '47', name: '경북', fullName: '경상북도' },
  { code: '48', name: '경남', fullName: '경상남도' },
  { code: '50', name: '제주', fullName: '제주특별자치도' },
  { code: '51', name: '강원', fullName: '강원특별자치도' },
  { code: '52', name: '전북', fullName: '전북특별자치도' },
] as const;

/**
 * 지금 자료가 들어와 있어 **실제로 볼 수 있는** 시도.
 *
 * 여기 코드를 더하기 전에 반드시 확인할 것:
 *   1) `parcel`·`unit_business` 에 그 지역 행이 있는가 (필지·점포)
 *   2) `building`·`building_floor` 에 그 지역 행이 있는가 (건물 — 이게 없으면 검색해도 안 나온다)
 */
export const OPEN_SIDO_CODES: readonly string[] = ['11', '30'];

const OPEN = new Set(OPEN_SIDO_CODES);

export function isOpenSido(code: string): boolean {
  return OPEN.has(code);
}

export const OPEN_SIDOS: readonly Sido[] = SIDOS.filter((s) => isOpenSido(s.code));

/** '서울·대전' — 안내 문구에 그대로 넣는다. 하드코딩 금지(여기서 만든다). */
export function openRegionLabel(): string {
  return OPEN_SIDOS.map((s) => s.name).join('·');
}

/** PNU·시군구코드 앞 2자리로 그 지역이 열려 있는지. */
export function isOpenPnu(pnu: string | null | undefined): boolean {
  return !!pnu && isOpenSido(pnu.slice(0, 2));
}
