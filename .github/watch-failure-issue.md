주간 **분기 스냅샷 감시**가 실패했습니다.

감시가 멈춘 동안 새 분기가 올라왔다 내려가면 그대로 손실입니다 — 이 데이터는 포털에서
내려가면 **다시 받을 수 없습니다**(CLAUDE.md 절대 규칙 6). 공실 이력·점포 생존기간이
전부 여기서 나옵니다.

## 지금 할 일 (내 PC에서 — 한국에서는 포털이 잘 열립니다)

```powershell
cd D:\sangga
python scripts/check_new_sangkwon_quarter.py
```

- **"새 분기: 없음"** 이면 놓친 것이 없습니다. 이 이슈를 닫으세요.
- **새 분기가 보이면** 지금 받으세요:

```powershell
python scripts/download_sangkwon_history.py    # 새 분기만 이어받는다
python scripts/collectors/load_sangkwon_snapshot.py
python scripts/backup_raw.py                   # 외장 SSD(F:) 연결 필요
python scripts/backup_raw.py --verify
```

적재·백업까지 끝나면 `scripts/check_new_sangkwon_quarter.py` 의
`LATEST_KNOWN_QUARTER` 를 그 분기로 올리고 이 이슈를 닫습니다.

## 흔한 원인

GitHub 러너(미국)에서 한국 포털(data.go.kr)로 가는 연결이 **간헐적으로** 막힙니다.
2026-08-10 에 `Errno 110 Connection timed out` 으로 죽었는데, 이틀 전 같은 러너는
같은 포털을 8초 만에 읽었습니다. 스크립트가 이미 30초 타임아웃으로 3번까지 다시
시도하므로, 그걸 넘겼다면 포털이 한동안 닫혀 있었다는 뜻입니다.

포털 목록 HTML 구조가 바뀌어도 같은 실패가 납니다. 위 명령을 **내 PC에서 돌렸는데도**
실패하면 그쪽을 의심하세요(`download_sangkwon_history.py` 의 정규식).

---

*이 이슈는 분기 감시 워크플로우가 자동으로 열었습니다. 같은 이슈가 열려 있는 동안은
다시 열리지 않으므로, 확인이 끝나면 꼭 닫아 주세요 — 닫아야 다음 실패를 다시 알립니다.*
