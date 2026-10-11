/**
 * 중개사가 종이 머리에 찍을 **내 사무소 정보**를 이 기기에만 적어 두는 부품(결정 0036 결정 3 · 물결 1-C2 ·
 * 「이 기기 저장」 ①~⑤).
 *
 * ⛔ 서버로 보내지 않는다 — 주소(결정 0019)·의견함(`feedbackContext` · 결정 0034)에 이 칸들을 싣지 않는다.
 * ⛔ **저장이 막힌 창**(사생활 보호 창·앱 안 브라우저)에서는 읽기·쓰기·지우기·저장소 접근 예외를 전부
 *    여기서 삼킨다 — 입력과 인쇄는 그대로 되고 다음 방문에 기억하지 못할 뿐이다.
 * ⛔ 읽을 때 **칸마다** 모양을 본다(글자이고 상한 안인가) — 틀린 칸만 버리고 나머지는 산다(LH `.every()` 교훈).
 * ⓘ 저장소를 인자로 받는 이유 — 시험이 '예외를 던지는 저장소'를 넣어 위 약속을 확인한다.
 */
export const BROKER_OFFICE_STORAGE_KEY = 'sangga.brokerOffice';

export type BrokerOffice = {
  /** 사무소 이름 */
  name: string;
  /** 대표 */
  rep: string;
  /** 등록번호 */
  regNo: string;
  /** 전화 */
  phone: string;
  /** 메모(짧은 여러 줄) */
  memo: string;
};

export type BrokerOfficeField = keyof BrokerOffice;

/** 칸마다 글자 수 상한 — 이름류 60 · 메모 200(종이 머리 오른쪽 상자에 들어갈 만큼). */
export const BROKER_OFFICE_MAX: Readonly<Record<BrokerOfficeField, number>> = {
  name: 60,
  rep: 60,
  regNo: 60,
  phone: 60,
  memo: 200,
};

/** 칸 차례와 이름표(화면 입력 칸 · 종이 머리 둘 다 이 차례). */
export const BROKER_OFFICE_FIELDS: ReadonlyArray<readonly [BrokerOfficeField, string]> = [
  ['name', '사무소 이름'],
  ['rep', '대표'],
  ['regNo', '등록번호'],
  ['phone', '전화'],
  ['memo', '메모'],
];

export const EMPTY_BROKER_OFFICE: BrokerOffice = { name: '', rep: '', regNo: '', phone: '', memo: '' };

type OfficeStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function browserStorage(): OfficeStorage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** 한 칸을 상한 안으로 자른다(입력 칸의 `maxLength` 와 같은 자 — 붙여넣기 등으로 넘쳐도). */
export function clampOfficeField(field: BrokerOfficeField, v: string): string {
  return v.slice(0, BROKER_OFFICE_MAX[field]);
}

/** 한 칸이라도 채워졌나(공백만이면 빈 칸). 종이 머리 상자를 그릴지 정한다. */
export function hasBrokerOffice(o: BrokerOffice | null | undefined): boolean {
  return !!o && BROKER_OFFICE_FIELDS.some(([k]) => o[k].trim() !== '');
}

/** 적어 둔 사무소 정보. 없거나 깨졌거나 못 읽으면 빈 칸들. 모양이 틀린 칸은 그 칸만 빈다. */
export function loadBrokerOffice(storage: OfficeStorage | null = browserStorage()): BrokerOffice {
  if (!storage) return { ...EMPTY_BROKER_OFFICE };
  let raw: string | null;
  try {
    raw = storage.getItem(BROKER_OFFICE_STORAGE_KEY);
  } catch {
    return { ...EMPTY_BROKER_OFFICE };
  }
  if (raw === null) return { ...EMPTY_BROKER_OFFICE };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...EMPTY_BROKER_OFFICE };
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return { ...EMPTY_BROKER_OFFICE };
  const r = parsed as Record<string, unknown>;
  const out = { ...EMPTY_BROKER_OFFICE };
  for (const [k] of BROKER_OFFICE_FIELDS) {
    const v = r[k];
    if (typeof v === 'string' && v.length <= BROKER_OFFICE_MAX[k]) out[k] = v;
  }
  return out;
}

/** 적는다(칸마다 상한으로 자른 뒤). 모든 칸이 비면 열쇠를 지운다. 실패는 조용히 넘긴다. */
export function saveBrokerOffice(office: BrokerOffice, storage: OfficeStorage | null = browserStorage()): void {
  if (!storage) return;
  try {
    if (!hasBrokerOffice(office)) {
      storage.removeItem(BROKER_OFFICE_STORAGE_KEY);
      return;
    }
    const clamped = { ...EMPTY_BROKER_OFFICE };
    for (const [k] of BROKER_OFFICE_FIELDS) clamped[k] = clampOfficeField(k, office[k]);
    storage.setItem(BROKER_OFFICE_STORAGE_KEY, JSON.stringify(clamped));
  } catch {
    // 저장이 막힌 창 — 입력·인쇄는 그대로 되고 기억만 못 한다(위 머리말).
  }
}

/** 전부 지운다(「지우기」 단추). 돌려주는 것은 빈 칸들. */
export function clearBrokerOffice(storage: OfficeStorage | null = browserStorage()): BrokerOffice {
  if (storage) {
    try {
      storage.removeItem(BROKER_OFFICE_STORAGE_KEY);
    } catch {
      // 막힌 창 — 애초에 적힌 것도 없다.
    }
  }
  return { ...EMPTY_BROKER_OFFICE };
}
