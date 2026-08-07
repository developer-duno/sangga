# sangga

상업용 부동산을 **층별·업종별**로 공간분석하는 플랫폼. 설계 정본은 [`docs/상세계획.md`](docs/상세계획.md),
진행 상황은 [`docs/PROGRESS.md`](docs/PROGRESS.md).

## 화면 띄우기 (층별 스택뷰)

```bash
python scripts/make_env_local.py   # .env → .env.local (브라우저용 공개키만 추림)
pnpm install
pnpm dev                           # http://localhost:5173
```

첫 명령을 건너뛰면 화면이 뜨자마자 "환경변수가 필요합니다" 오류로 멈춘다. `.env.local`은
`.gitignore` 대상이라 커밋되지 않으므로 **새 PC마다 한 번씩** 실행해야 한다.

> ⚠️ 브라우저에 실리는 값은 `VITE_`로 시작하는 것뿐이다. 관리자 키(`SERVICE_KEY`)에는
> 절대 `VITE_`를 붙이지 않는다 — 붙이면 그 키가 번들에 그대로 들어가 누구나 DB를 고칠 수 있다.
> `scripts/make_env_local.py`가 내보낼 항목을 코드로 고정해 그 사고를 막는다.

## 데이터 수집·적재 (Python)

```bash
python -m pytest tests/ -q            # 단위 테스트
python -m ruff check scripts/ tests/  # 린트
python scripts/collectors/collect_building_ledger.py   # 건축물대장 수집 (이어받기)
python scripts/collectors/load_building_ledger.py      # raw → DB 적재
```

수집기는 일 예산에 닿으면 스스로 안전 종료하고 다음 실행에서 이어받는다.
`data/raw/`는 절대 덮어쓰지 않는다 — 정제는 다시 할 수 있어도 원본은 복구 불가다.
