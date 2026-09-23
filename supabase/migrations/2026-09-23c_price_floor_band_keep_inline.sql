-- 2026-09-23c: price_floor_band 도 search_path 를 고정하지 않는다 — 인라인을 살려 층대별 가격 속도를 되돌림
--   mibunyang 세션566 · 라이브 적용완료(psql, 한 트랜잭션 안 자체검사 후 COMMIT) · 2026-09-23a 의 일부를 되돌린다
--
-- 왜: list_price_bands 의 L6 단계가 같은 법정동 거래를 훑으며 행마다 `price_floor_band(t.floor_no) = v_band` 를 부른다
--   (2026-08-16b). SET 절이 붙으면 인라인되지 않아 호출 비용이 행마다 붙는다(세션566 코드 검사관 지적 → 실측).
--   실측(거래가 가장 많은 필지, 같은 동 964행, 되돌림 트랜잭션 안 비교):
--     list_price_bands  SET 105~110ms · RESET 45~56ms  (약 2.3배)
--   같은 방식으로 잰 mask_person_name(list_parcel_buildings, 건물 168개 필지)은 20~23ms vs 18~20ms 로 차이가 작아 SET 유지.
--
-- 결과: 보안 고문 경고 "Function Search Path Mutable: price_floor_band" 1건은 **일부러 남긴다**
--   (SECURITY INVOKER immutable 헬퍼라 search_path 탈취 위험이 사실상 없고, 속도가 우선). 층 -3~60 출력 전후 동일(자체검사).
--
-- ROLLBACK (다시 고정 — list_price_bands 가 약 2배 느려진다):
-- ALTER FUNCTION public.price_floor_band(smallint) SET search_path = public, extensions, pg_temp;

ALTER FUNCTION public.price_floor_band(smallint) RESET search_path;
