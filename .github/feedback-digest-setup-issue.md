**의견함에 무엇이 쌓였는지 매주 알려 주는 예약이 돌긴 하는데, 아무 일도 못 하고 있습니다.**

창고에 물어보려면 주소와 공개키가 필요한데 저장소 변수에 없습니다. 그래서 매주 조용히
건너뛰고 있고, **그 사이 들어온 의견은 아무도 안 읽습니다.**

## 넣는 방법 (Secrets 아니라 **Variables** 입니다)

Settings → Secrets and variables → Actions → **Variables** 탭 → New repository variable

| 이름 | 값 |
|---|---|
| `SANGGA_SUPABASE_URL` | 내 PC `D:\sangga\.env` 의 `SANGGA_SUPABASE_URL` 값 |
| `SANGGA_SUPABASE_ANON_KEY` | 같은 파일의 `SANGGA_SUPABASE_ANON_KEY` 값 |

⚠️ **`SANGGA_SUPABASE_SERVICE_KEY` 는 절대 넣지 마세요.** 그건 창고를 통째로 고칠 수 있는
열쇠입니다. 위 두 개는 이미 배포된 화면 안에 들어 있어 누구나 볼 수 있는 값이라, 여기 둬도
새로 새는 것이 없습니다(그래서 Secrets 가 아니라 Variables 입니다).

## 넣은 뒤

Actions 탭 → **의견함 주간 알림** → **Run workflow** 로 한 번 돌려 보고, 잘 돌면 이 이슈를 닫으세요.

내 PC 에서 미리 확인해 볼 수도 있습니다(`.env` 를 자동으로 읽습니다):

```powershell
cd D:\sangga
python scripts/feedback_digest.py
```

---

⚠️ 이 이슈를 **닫지 않으면** 다음 주에 같은 알림이 다시 열리지 않습니다(같은 제목은 한 번만).
반대로 변수를 안 넣은 채 닫으면, 다음 주에 다시 열립니다.
