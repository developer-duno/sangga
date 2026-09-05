import type { FeedbackContext } from '../lib/feedback';

import { DataFreshness } from './DataFreshness';
import { FeedbackBox } from './FeedbackBox';
import { HandoffLinks } from './HandoffLinks';

/**
 * 화면 맨 아래 — 이 자료를 어떻게 받아들여야 하는지 + 한마디 남기는 자리.
 *
 * 왜 필요한가 — 배포 전까지 이 앱에는 하단 영역이 아예 없었다. 그래서 보는 사람은
 * ①이 숫자를 어디까지 믿어도 되는지 ②이상한 걸 봤을 때 어디에 말해야 하는지를
 * 알 길이 없었다. 둘 다 "다 보고 난 다음"에 필요한 것이라 같은 자리에 둔다.
 *
 * ⛔ 안내 문구에 '적정가격·감정가·평가액·가치평가' 를 쓰지 않는다(절대 규칙 2 — 감정평가는
 *    감정평가사 독점 업무다). 여기서는 그 반대를 말한다: **이것은 평가가 아니다.**
 * ⛔ 자료 출처(공공누리 1유형 의무)를 여기에 모아 적지 않는다. 출처는 그 자료를 실제로
 *    쓴 섹션이 **자기가 쓴 것만** 적는다(지도·상권 카드) — 여기에 모아 두면 안 쓴 출처를
 *    덧붙이게 되고 그건 지어낸 출처다.
 */

interface Props {
  /** 무엇을 보던 중이었나. 의견함이 함께 실어 보낸다. */
  feedbackContext?: FeedbackContext;
}

export function AppFooter({ feedbackContext }: Props) {
  return (
    <footer className="foot">
      <div className="foot__notice">
        <p className="foot__lead">이 화면을 어디까지 믿어도 되나</p>
        <ul className="foot__list">
          <li>
            공공데이터(건축물대장·상권정보·실거래·상권경계)를 가공한 <strong>참고 자료</strong>
            입니다. 감정평가가 아니며, 그 대신으로 쓸 수 없습니다.
          </li>
          <li>
            <strong>추정한 값에는 "추정"이라고 적고, 근거와 표본 수를 함께 적습니다.</strong>{' '}
            그 표시가 없는 숫자는 원본 자료를 그대로 옮긴 것입니다.
          </li>
          <li>
            원본이 안 적어 둔 칸은 <strong>"미상"</strong>으로 보입니다 — 값이 0이라는 뜻이
            아닙니다.
          </li>
          <li>
            실제 계약 전에는 등기부등본·건축물대장 원본과 <strong>현장 확인</strong>이
            필요합니다.
          </li>
        </ul>
      </div>

      {/*
        넘기기 링크 구역(결정 0014 §5) — 안내 문구 **바로 뒤**다. "여기까지가 우리가 아는
        것"을 말한 다음에 "그 다음은 저기서"가 오는 순서라, 이 두 덩어리 사이에 다른 것이
        끼면 말이 끊긴다. 종이에서는 이 구역만 통째로 빠진다(`@media print` 의 `.links`).
      */}
      <HandoffLinks />
      {/* "언제 것인가"는 "어디까지 믿어도 되나"의 나머지 절반이다 — 근거와 한계를 읽은
          바로 다음에 오는 것이 자연스럽다. 서버가 못 답하면 이 자리만 조용히 빈다. */}
      <DataFreshness />

      <FeedbackBox context={feedbackContext} />
    </footer>
  );
}
