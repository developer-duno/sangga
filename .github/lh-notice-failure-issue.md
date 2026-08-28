주간 **LH 상가 공고 감시**가 실패했습니다.

감시가 멈춘 동안 뜬 공고는 마감까지 아무도 모릅니다 — 공고는 대개 2~3주면 닫히고,
지나간 공고는 나중에 받아도 이미 끝난 것을 창고에 넣는 일이 됩니다.

## 지금 할 일 (내 PC에서 — 한국에서는 포털이 잘 열립니다)

```powershell
cd D:\sangga
python scripts/check_lh_notices.py
```

- **"새 공고: 없음"** 이면 놓친 것이 없습니다. 이 이슈를 닫으세요.
- **새 공고가 보이면** 지금 받으세요:

```powershell
python scripts/collectors/collect_lh_notices.py --dry-run   # 무엇이 들어올지 먼저 본다
python scripts/collectors/collect_lh_notices.py             # 적재(한 트랜잭션)
python scripts/post_load.py                                 # 요약표 갱신 + 신선도 점검
```

적재까지 끝나면 `scripts/check_lh_notices.py` 의 `LATEST_KNOWN_NOTICE_DATE` 를 그 판의
가장 최근 공고일로 올리고 이 이슈를 닫습니다.

## 흔한 원인

- **인증키 거절(403)** — 포털 활용신청이 만료됐거나 `MOLIT_KEY` 가 잘못 들어갔습니다.
  내 PC 에서 위 명령이 되는데 러너에서만 실패하면 Secrets 쪽을 의심하세요.
- **연결 실패** — GitHub 러너(미국)에서 한국 포털(data.go.kr)로 가는 연결이 간헐적으로
  막힙니다. 스크립트가 이미 60초 타임아웃으로 3번까지 다시 시도하므로, 그걸 넘겼다면
  포털이 한동안 닫혀 있었다는 뜻입니다.
- **응답 형식 변경** — "dsList 칸이 없습니다"류 오류면 LH 가 응답 모양을 바꾼 것입니다.
  `scripts/collectors/collect_lh_notices.py` 의 `extract_rows` 를 보세요.
- **상가 0건** — 상위 유형코드(`UPP_AIS_TP_CD='22'`)가 바뀌었을 수 있습니다. 0건은
  정상이 아니라서 일부러 실패로 처리합니다(조용한 빈손 금지).

---

*이 이슈는 LH 공고 감시 워크플로가 자동으로 열었습니다. 같은 이슈가 열려 있는 동안은
다시 열리지 않으므로, 확인이 끝나면 꼭 닫아 주세요 — 닫아야 다음 실패를 다시 알립니다.*
