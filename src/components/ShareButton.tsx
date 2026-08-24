import { useEffect, useId, useRef, useState } from 'react';

/**
 * 지금 보고 있는 화면의 주소를 복사해 주는 버튼.
 *
 * 왜 버튼이 따로 필요한가
 * -----------------------
 * 주소창에 이미 주소가 떠 있으니 버튼이 없어도 복사는 된다 — **컴퓨터에서는.**
 * 휴대폰 브라우저는 주소창이 반쯤 접혀 있고 길게 눌러 고르는 일이 번거롭다.
 * 이 앱은 좁은 화면에서 쓰는 일이 많아(모바일 E2E 를 따로 도는 이유) 버튼 하나가
 * "가지고 나가기"의 실제 문턱을 크게 낮춘다.
 *
 * ⛔ 복사에 실패했는데 "복사했습니다"라고 말하지 않는다
 * ----------------------------------------------------
 * 복사(`navigator.clipboard`)는 **https 나 localhost 가 아니면 아예 없다.** 브라우저가
 * 권한을 막아도 실패한다. 그때 성공한 척하면 사용자는 아무것도 없는 클립보드를
 * 붙여넣게 된다 — 이 저장소가 의견함에서 이미 정한 원칙과 같다(서버가 못 받았는데
 * "보냈습니다"라고 하지 않는다, 결정 0016).
 *
 * 그래서 실패하면 **주소를 그대로 보여주고** 직접 고를 수 있게 한다. 붙여넣기가
 * 목적이므로 주소만 보이면 목적은 달성된다.
 */
type Props = {
  /** 복사할 온전한 주소. `buildShareUrl()` 이 만든 값. */
  url: string;
  /** 무엇을 가리키는 주소인지(읽어 주는 기기용). 예: '역삼빌딩' */
  label?: string | null;
};

type Phase = 'idle' | 'copied' | 'failed';

export function ShareButton({ url, label }: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const fallbackId = useId();
  const fallbackRef = useRef<HTMLInputElement | null>(null);

  // 주소가 바뀌면(다른 건물로 옮겨 가면) 안내를 지운다 — 안 그러면 **다른 건물**
  // 주소를 복사해 놓고 "복사했습니다"가 그대로 남아 방금 것을 복사한 줄 알게 된다.
  useEffect(() => {
    setPhase('idle');
  }, [url]);

  // 복사가 막힌 자리에서는 주소를 바로 고를 수 있게 해 준다(한 번 더 누르는 수고 제거).
  useEffect(() => {
    if (phase === 'failed') fallbackRef.current?.select();
  }, [phase]);

  async function handleCopy() {
    try {
      // `navigator.clipboard` 자체가 없는 환경이 있다(https 가 아닌 곳).
      if (!navigator.clipboard?.writeText) throw new Error('클립보드를 쓸 수 없습니다');
      await navigator.clipboard.writeText(url);
      setPhase('copied');
    } catch {
      setPhase('failed');
    }
  }

  return (
    <div className="share">
      <button type="button" className="share__btn" onClick={handleCopy}>
        링크 복사
      </button>

      {/*
        읽어 주는 기기에도 결과가 전달되어야 한다. 버튼 글자는 안 바뀌므로(바꾸면
        누를 때마다 버튼이 흔들린다) 결과는 옆에 따로 적는다.
      */}
      <span className="share__msg" role="status" aria-live="polite">
        {phase === 'copied' && '주소를 복사했습니다.'}
        {phase === 'failed' && '복사가 막혀 있어 주소를 아래에 띄웠습니다. 길게 눌러 복사해 주세요.'}
      </span>

      {phase === 'failed' && (
        <>
          <label className="share__label" htmlFor={fallbackId}>
            {label ? `${label} 주소` : '이 화면 주소'}
          </label>
          <input
            id={fallbackId}
            ref={fallbackRef}
            className="share__url"
            type="text"
            value={url}
            readOnly
            onFocus={(e) => e.currentTarget.select()}
          />
        </>
      )}
    </div>
  );
}
