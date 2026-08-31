주간 **의견함 주간 알림**이 실패했습니다.

감시가 죽어 있는 동안에는 의견함에 무엇이 쌓였는지 아무도 모릅니다 — 넣는 길만 열려
있고 읽을 계기가 이 알림 하나뿐이라, 알림이 조용히 실패하면 우편함은 다시 "아무도
안 읽는" 상태로 돌아갑니다. 이 레포는 이미 그 일을 겪었습니다(감시가 죽은 걸 나흘
뒤에야 알았습니다).

## 지금 할 일 (내 PC에서 — `.env` 를 자동으로 읽습니다)

```powershell
cd D:\sangga
python scripts/feedback_digest.py
```

- **"알릴 일이 없습니다"** 이면 놓친 것이 없습니다. 이 이슈를 닫으세요.
- **알릴 일이 있으면** 아래 명령으로 직접 확인하세요(이 스크립트는 건수만 압니다):

```powershell
python scripts/dbx.py -c "select id, kind, left(body, 200) as body, context, created_at from app_feedback order by created_at desc limit 50"
```

## 흔한 원인

- **저장소 변수 문제(401/403)** — `SANGGA_SUPABASE_URL` / `SANGGA_SUPABASE_ANON_KEY` 가
  잘못 들어갔거나 anon 권한이 바뀌었습니다. 내 PC 에서 위 명령이 되는데 러너에서만
  실패하면 저장소 **Variables**(Secrets 아님) 쪽을 의심하세요.
- **함수 이름·스키마 문제(404, PGRST106)** — `get_feedback_stats` 함수가 없거나 `api`
  스키마가 안 열린 것입니다. `Content-Profile: api` 헤더가 빠지면 이 앱이 옛 문(public)을
  닫은 그 사고를 워크플로에서 그대로 재현합니다 — `scripts/feedback_digest.py` 의 `rpc()`
  를 보세요.
- **연결 실패(간헐적)** — GitHub 러너에서 Supabase 로 가는 연결이 잠깐 끊길 수 있습니다.
  스크립트는 5번까지(사이사이 5·10·20·40초를 쉬며 총 약 75초) 다시 시도하므로, 그걸
  넘겼다면 한동안 닫혀 있었다는 뜻입니다. **이 경우 내 PC 에서 위 명령이 그냥 되는 일이
  흔합니다** — 되고 "알릴 일이 없습니다"면 놓친 것이 없으니 이 이슈를 닫으면 끝입니다.
- **응답 모양 변경** — "응답 모양이 예상과 다릅니다"류 오류면 `get_feedback_stats` 함수의
  반환 칸이 바뀐 것입니다. `scripts/feedback_digest.py` 의 `fetch_stats` 를 보세요.

---

*이 이슈는 의견함 주간 알림 워크플로가 자동으로 열었습니다. 같은 이슈가 열려 있는
동안은 다시 열리지 않으므로, 확인이 끝나면 꼭 닫아 주세요 — 닫아야 다음 실패를 다시
알립니다.*
