**구 입구 주소의 첫 HTML 이 허브가 아닙니다 — 사람 화면은 멀쩡히 뜰 수 있습니다. 화면이 멀쩡해도 이 이슈는 닫지 마세요.**

구 입구 주소(예: <https://sangga-one.vercel.app/?sgg=11680>)의 첫 HTML 에는 그 구의 건물 링크 전부가 들어가야 합니다(결정 0043).
검색 엔진은 이 링크로 건물 주소를 찾습니다. 이번에는 그 첫 HTML 이 허브가 아니었습니다 — 제목·h1 이 첫 화면 것이거나, 허브 파일을 못 읽었습니다.
사람이 열면 화면은 지금처럼 구 화면으로 보일 수 있습니다(화면은 앱이 다시 그린다). 그래서 **눈으로 보고 멀쩡하다고 닫으면 안 됩니다** — 망가진 것은 눈에 안 보이는 첫 HTML 입니다.

## 먼저 확인 (30초 · PowerShell)

```powershell
[Console]::OutputEncoding = [Text.Encoding]::UTF8; curl.exe -s "https://sangga-one.vercel.app/?sgg=11680" | Select-String -Pattern '<h1 class="seo-title">[^<]*' -AllMatches | ForEach-Object { $_.Matches.Value }
```

(Git Bash 라면 `curl -s "https://sangga-one.vercel.app/?sgg=11680" | grep -o '<h1 class="seo-title">[^<]*'`)

- h1 글자가 **「상가 건물 층별 보기」로 끝난다**(예: `서울 강남구 상가 건물 층별 보기`) → 지금은 다시 섰습니다. 아래 「이 이슈를 닫아도 될 때」로 갑니다.
- 그 밖(사이트 이름 h1 · h1 없음 · 응답 없음) → 아래로 갑니다.

## 흔한 원인

| 무엇 | 확인할 곳 |
|---|---|
| `public/hub/` 를 굽지 않은 채 배포했다(파일이 없거나 비었다) | `git log -- public/hub` · `python scripts/build_sitemap.py --dry-run` |
| `middleware.ts` 의 허브 갈래(`hubRewriteTarget`)가 빠졌다 | `git log -p -- middleware.ts` |
| 서버 조각 함수(`api/hub.ts`)가 오류를 낸다(허브 파일 503·모양 틀림·치환 실패) | Vercel 대시보드 → 그 배포 → Functions 로그(`구 허브` 로 찾기) |

허브만 끄고 싶으면 `middleware.ts` 의 `?? hubRewriteTarget(request.url)` 을 지우고 PR 로 배포합니다(되돌리기 — 구 입구가 첫 화면 그대로가 된다).

## 이 이슈를 닫아도 될 때

위 확인 명령의 h1 이 **「상가 건물 층별 보기」로 끝날 때**만 닫습니다. 사이트가 열린다는 것은 닫아도 되는 이유가 아닙니다.
닫아야 다음 고장을 다시 알립니다(같은 제목의 열린 이슈가 있으면 감시가 새 이슈를 열지 않습니다).
