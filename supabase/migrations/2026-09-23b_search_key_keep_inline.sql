-- 2026-09-23b: search_key 는 search_path 를 고정하지 않는다 — 인라인을 살려 점포 검색 속도를 되돌림
--   mibunyang 세션566 · 라이브 적용완료(psql, 한 트랜잭션 안 자체검사 후 COMMIT) · 2026-09-23a 의 일부를 되돌린다
--
-- 왜: SET 절이 붙은 SQL 함수는 플래너가 인라인하지 못한다. search_stores 는 땅마다
--   `unnest → search_key → like` 로 search_key 를 행마다 부르므로(2026-09-10b 머리 주석) 호출 비용이 그대로 드러난다.
--   실측(구 코드 11680, 캐시가 데워진 상태, 되돌림 트랜잭션 안 비교):
--     search_stores('카페')     SET 7개 334~428ms · search_key 만 풀면 276~283ms · 7개 모두 풀면 280~288ms
--     search_stores('스타벅스') SET 46~47ms · search_key 만 풀면 29ms
--     search_buildings('테헤란로') 35~40ms → 31~34ms (차이 작음)
--   → 느려짐의 원인은 search_key 하나. 나머지 6개는 고정해도 속도 영향이 없어 그대로 둔다.
--   적용 후 재측정: 카페 309ms · 스타벅스 30ms · 테헤란로 38ms (적용 직후 첫 회 429ms 는 계획 재작성).
--
-- 결과: 보안 고문 경고 "Function Search Path Mutable: search_key" 1건은 **일부러 남긴다**.
--   search_key 는 SECURITY INVOKER immutable 헬퍼라 search_path 탈취 위험이 사실상 없고, 속도는 상가 검색의 핵심이다.
--   출력은 변경 전후 동일(자체검사).
--
-- ROLLBACK (다시 고정 — 점포 검색이 20~50% 느려진다):
-- ALTER FUNCTION public.search_key(text) SET search_path = public, extensions, pg_temp;

ALTER FUNCTION public.search_key(text) RESET search_path;
