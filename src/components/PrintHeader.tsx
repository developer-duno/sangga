import { useEffect, useState } from 'react';
import { flushSync } from 'react-dom';
import { printStamp } from '../lib/printStamp';

/**
 * **종이에만 나오는 머리글.** 화면에서는 아예 안 보인다(`@media print` 에서만 편다).
 *
 * 왜 필요한가
 * -----------
 * 인쇄 규칙 없이 그냥 뽑아 보니(2026-08-25 라이브 실측) 종이에 **언제 뽑았는지도, 원본이
 * 어디인지도** 없었다. 그 종이를 며칠 뒤에 다시 보거나 남에게 건네면 "이게 언제 것이고
 * 어느 건물이며 어디서 다시 볼 수 있나"를 알 길이 없다. 세 줄이면 셋 다 풀린다.
 *
 * ⓘ 주소를 QR 이 아니라 **글자 그대로** 적는다. QR 은 꾸러미가 하나 더 붙는데, 이 주소는
 *   손으로 옮겨 적을 만한 길이라(물음표 방식이라 폴더가 안 늘어난다) 지금은 글자로 충분하다.
 * ⓘ 건물 이름·주소가 아래 `.stack__head` 와 겹친다. 종이에서 그 겹침은 결함이 아니라
 *   **문서의 머리글**이다 — 지도가 사이에 끼어 있어 첫 줄에 이름이 없으면 무슨 서류인지
 *   모른 채 지도부터 보게 된다.
 */
type Props = {
  /** 건물 이름. 없는 건물이 실재하므로 null 을 받는다. */
  name: string | null;
  /** 도로명주소. 없는 건물이 실재하므로 null 을 받는다. */
  address: string | null;
  /** 이 화면의 온전한 주소 — `ShareButton` 이 복사해 주는 것과 같은 값이다. */
  url: string;
};

export function PrintHeader({ name, address, url }: Props) {
  const [stamp, setStamp] = useState(() => printStamp(new Date()));

  /*
    인쇄가 시작되기 직전에 시각을 다시 맞춘다.

    ⚠️ `flushSync` 로 **지금 당장** 다시 그린다. 브라우저는 이 핸들러가 끝나는 즉시 화면을
       찍어 가므로, 리액트가 평소처럼 다음 차례로 미루면 **낡은 시각이 종이에 박힌다.**
       (화면을 열어 두고 한참 뒤에 인쇄하는 것이 오히려 흔한 쓰임이다.)
    ⚠️ 어긋나도 종이가 깨지지는 않는다 — 못 맞추면 화면을 연 시각이 적힌다. 없는 값이
       생기는 종류의 실패가 아니다.
    ⓘ 버튼을 눌러도, Ctrl+P 를 눌러도, 브라우저 메뉴로 들어와도 이 이벤트는 똑같이 온다 —
       그래서 시각 맞추기를 버튼 쪽에 두지 않았다(`PrintButton` 머리말과 같은 원칙).
  */
  useEffect(() => {
    function refresh() {
      flushSync(() => setStamp(printStamp(new Date())));
    }
    window.addEventListener('beforeprint', refresh);
    return () => window.removeEventListener('beforeprint', refresh);
  }, []);

  return (
    <div className="printmeta">
      <p className="printmeta__title">{name || '(이름 없는 건물)'}</p>
      <p className="printmeta__addr">{address || '주소 없음'}</p>
      <p className="printmeta__foot">
        <span className="printmeta__app">상가 층별 스택뷰</span>
        <span className="printmeta__when">{stamp} 뽑음</span>
        <span className="printmeta__url">{url}</span>
      </p>
    </div>
  );
}
