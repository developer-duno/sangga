import { useId, useState } from 'react';

import { FEEDBACK_MAX_LEN } from '../lib/appConstants';
import { submitFeedback, type FeedbackContext } from '../lib/feedback';

/**
 * 보던 사람이 한마디 남기는 자리.
 *
 * 왜 필요한가 — 2026-08-24 첫 배포로 이 화면은 남이 볼 수 있는 곳이 됐는데, 다 보고 나서
 * 할 수 있는 일이 **뒤로 가기뿐**이었다. 무엇이 부족한지 들을 길이 한 곳도 없으면 다음에
 * 무엇을 만들지도 짐작으로 정하게 된다.
 *
 * ⛔ 이름·연락처를 받지 않는다. 받는 순간 개인정보가 되어 처리방침·보관기간·파기절차가
 *    따라붙는데, 답장이 필요할 만큼 문의가 쌓이지도 않은 지금 그 의무부터 지는 것은
 *    순서가 거꾸로다. 그래서 **답장을 못 한다는 사실을 미리 적어 둔다** — 답을 기다리게
 *    만들어 놓고 안 하는 것이 가장 나쁘다.
 *
 * ⛔ 실패를 성공처럼 말하지 않는다. 못 보냈으면 못 보냈다고 적는다(거짓 안심 금지).
 */

interface Props {
  /**
   * 무엇을 보던 중이었나(건물·구). 사람이 손으로 적지 않아도 함께 실린다 —
   * "어디를 보다 무엇이 아쉬웠나"가 이 의견함의 값어치 전부다.
   */
  context?: FeedbackContext;
}

type Status = 'idle' | 'sending' | 'sent' | 'failed';

export function FeedbackBox({ context }: Props) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const fieldId = useId();

  const trimmed = body.trim();
  const tooLong = body.length > FEEDBACK_MAX_LEN;
  const canSend = trimmed.length > 0 && !tooLong && status !== 'sending';

  async function handleSend() {
    if (!canSend) return;
    setStatus('sending');
    const ok = await submitFeedback('opinion', trimmed, context);
    if (ok) {
      setStatus('sent');
      setBody('');
    } else {
      setStatus('failed');
    }
  }

  if (!open) {
    return (
      <div className="fb">
        <button
          type="button"
          className="fb__open"
          onClick={() => {
            setOpen(true);
            // 한 번 보낸 뒤 다시 열면 지난 안내가 남아 있지 않게 한다.
            setStatus('idle');
          }}
        >
          의견 보내기
        </button>
        {/* 보낸 뒤 접었을 때도 결과는 남겨 둔다 — 접히면서 사라지면 보냈는지 알 수 없다. */}
        {status === 'sent' && (
          <p className="fb__note fb__note--ok" role="status">
            보내 주셔서 고맙습니다.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="fb">
      <label className="fb__label" htmlFor={fieldId}>
        무엇이 불편하거나 아쉬우셨나요?
      </label>
      <p className="fb__guide">
        보고 계시던 건물·지역은 자동으로 함께 전달됩니다.{' '}
        <strong>이름·전화번호·이메일은 적지 말아 주세요</strong> — 저희는 개인정보를 받지 않고,
        그래서 답장을 드릴 수 없습니다.
      </p>
      <textarea
        id={fieldId}
        className="fb__input"
        rows={4}
        value={body}
        maxLength={FEEDBACK_MAX_LEN}
        onChange={(e) => {
          setBody(e.target.value);
          // 고쳐 쓰기 시작하면 지난 결과 안내는 치운다(옛 안내가 새 글에 붙어 보이지 않게).
          if (status !== 'idle') setStatus('idle');
        }}
        placeholder="예: 3층 정보가 안 보여요 / 이 건물 주차 칸이 실제와 달라요"
      />
      <div className="fb__foot">
        <span className="fb__count">
          {body.length} / {FEEDBACK_MAX_LEN}자
        </span>
        <div className="fb__acts">
          <button
            type="button"
            className="fb__btn fb__btn--ghost"
            onClick={() => {
              setOpen(false);
              setBody('');
              // ⚠️ status 를 여기서 비우지 않는다 — 보내고 나서 닫으면 "보냈다"는 사실까지
              //    사라져, 보낸 사람이 보냈는지 아닌지 알 수 없게 된다. 접힌 모습은
              //    'sent' 일 때만 안내를 보여주므로 실패 안내가 남아 돌 걱정은 없다.
            }}
          >
            닫기
          </button>
          <button type="button" className="fb__btn" onClick={handleSend} disabled={!canSend}>
            {status === 'sending' ? '보내는 중…' : '보내기'}
          </button>
        </div>
      </div>

      {/* aria-live — 결과가 바뀌면 화면을 읽어 주는 기기가 그 자리에서 알려 준다. */}
      <p className="fb__note" role="status">
        {status === 'sent' && '보내 주셔서 고맙습니다. 확인하고 반영하겠습니다.'}
        {status === 'failed' &&
          '보내지 못했습니다. 잠시 뒤 다시 시도해 주세요. (같은 증상이 이어지면 저희 쪽 문제입니다)'}
      </p>
    </div>
  );
}
