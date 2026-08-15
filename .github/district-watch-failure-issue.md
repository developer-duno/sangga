주간 **상권 원천 갱신 감시**가 실패했습니다.

감시가 죽어 있는 동안 원천이 갱신되면 화면의 "속한 상권"이 옛 경계를 계속 보여줍니다 —
에러가 나지 않으니 **조용히 낡습니다.** 게다가 포털은 파일을 통째로 갈아끼우기 때문에,
갱신이 두 번 일어나면 **중간 판은 영영 못 받습니다**(이전 판은 포털에서 사라집니다).

## 지금 할 일 (내 PC에서 — 한국에서는 포털이 잘 열립니다)

```bash
cd /d/sangga
python scripts/check_district_source_update.py
```

- **"변경: 없음"** 이면 놓친 것이 없습니다. 이 이슈를 닫으세요.
- **갱신이 보이면** 지금 받으세요:

```bash
# 서울시 상권영역 (1,650개)
python scripts/collectors/fetch_seoul_district.py --probe
python scripts/collectors/fetch_seoul_district.py
python scripts/collectors/load_seoul_district.py --dry-run
python scripts/collectors/load_seoul_district.py

# 소진공 주요상권현황 (대전 37개 — 서울(11)은 적재기가 거부합니다)
python scripts/collectors/fetch_sbiz_district.py --probe
python scripts/collectors/fetch_sbiz_district.py
python scripts/collectors/load_sbiz_district.py --dry-run
python scripts/collectors/load_sbiz_district.py

# 공통 마무리
python scripts/build_rone_map.py --seed scripts/seeds/district_rone_map.csv   # exit 0 이어야 한다
python scripts/build_district_geojson.py   # 지도용 파일을 다시 굽고 **커밋**한다
python scripts/post_load.py
python scripts/backup_raw.py               # 외장 SSD(F:) 연결 필요
```

적재까지 끝나면 `scripts/check_district_source_update.py` 의 `SBIZ_KNOWN_UPDATE` /
`SEOUL_KNOWN_UPDATE` 를 새 날짜로 올리고 이 이슈를 닫습니다.

## 흔한 원인

GitHub 러너(미국)에서 한국 포털(data.go.kr · data.seoul.go.kr)로 가는 연결이
**간헐적으로** 막힙니다. 2026-08-10 에 형제 감시가 `Errno 110 Connection timed out` 으로
죽었는데, 이틀 전 같은 러너는 같은 포털을 8초 만에 읽었습니다. 이 스크립트도 30초
타임아웃으로 3번까지 다시 시도하므로, 그걸 넘겼다면 포털이 한동안 닫혀 있었다는 뜻입니다.

상세 페이지 HTML 구조가 바뀌어도 같은 실패가 납니다 — 이 감시는 화면의 "수정일 /
데이터 갱신일" 칸을 읽어서 판단하기 때문입니다(기계용 메타의 `updtDt` 는 null 로 와서
쓸 수 없습니다). 위 명령을 **내 PC에서 돌렸는데도** 실패하면 그쪽을 의심하세요
(`check_district_source_update.py` 의 `RE_SBIZ_UPDATE` · `RE_SEOUL_UPDATE`).

---

*이 이슈는 상권 원천 감시 워크플로우가 자동으로 열었습니다. 같은 이슈가 열려 있는 동안은
다시 열리지 않으므로, 확인이 끝나면 꼭 닫아 주세요 — 닫아야 다음 실패를 다시 알립니다.*
