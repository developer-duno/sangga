-- =====================================================================
-- 호 목록 정렬 — 같은 글자 덩어리끼리 모은다 (2026-10-05a · 결정 0032 후속)
-- =====================================================================
-- 왜
-- --
-- list_floor_units(2026-10-04b)는 호 이름 안의 **숫자 덩어리만** 차례로 numeric 으로 견줬다.
-- 그래서 '3가001호'·'3나001호'·'3다001호' 는 숫자 배열 [3,1] 이 같아 이름 글자 순으로 서고, 그 다음에
-- '3가002호' 가 왔다 — 가·나·다 구역이 한 줄씩 번갈아 섞였다(신구로자이 나인스에비뉴 3층 543칸 실측
-- 2026-10-05). 👤 사장님 결정(2026-10-05 00시): 이름을 숫자 덩어리·글자 덩어리로 나눠 **앞에서부터
-- 차례로** 견준다 — 숫자 덩어리는 수로, 글자 덩어리는 글자로.
--
-- 무엇을 하나 / 안 하나
-- --------------------
--   · public.list_floor_units 하나를 다시 만든다(정렬 식 · 그 설명 주석 · comment 한 구절).
--     머리(returns table·language sql·stable·security definer·set search_path)·판정 블록·거르기·
--     쪽 나누기는 글자 그대로다(정본 supabase/schema.sql 에서 잘라 붙였다 — tests/
--     test_unit_order_migration.py 가 정본과 글자 대조한다).
--   · ⛔ list_unit_floor_summary 는 건드리지 않는다(정렬이 없다 · 층 종류 판정도 그대로).
--   · ⛔ api 쌍둥이는 다시 만들지 않는다 — `select * from public.list_floor_units(…)` 통과라 새 정렬을
--     그대로 받는다. 권한도 그대로(public 원본은 닫힌 채 · grant 0줄).
--   · ⛔ 'N세대' 꼴을 살림집 이름 목록에 더하는 안(같은 날 함께 검토)은 넣지 않았다 — 실측해 보니
--     원본이 '세대'를 '칸' 뜻으로 쓴 가게 줄이 대부분이었다(결정 0032 「2026-10-05 후속」).
--
-- 새 정렬 열쇠
-- -----------
--   덩어리 = regexp_matches(이름에서 끝의 '호' 한 글자를 뗀 것, '[0-9]+|[^0-9]+', 'g') 를 차례대로.
--     ('호'를 떼는 까닭: 안 떼면 '-'(0x2D)가 '호'보다 앞 글자라 '1층2호' 가 '1층2-3호' 뒤로 간다 —
--      떼면 '1층2' 가 '1층2-3' 의 앞부분이라 먼저다. 옛 판 순서와도 같다 · 👤 2026-10-05 01시 메인 지시)
--     숫자 덩어리 → 앞 0 을 떼고(전부 0 이면 '0') 그 길이를 세 자리로 앞에 붙인 글자
--                   (9 → '0019', 10 → '00210' — 글자로 견줘도 수 순서다. 고정 폭 채우기는 긴 숫자를 자른다)
--     글자 덩어리 → 그대로
--   이 덩어리들의 배열(text[])을 collate "C" 로 견준다 — 배열 비교는 원소별이고(앞 원소가 같으면 짧은
--   배열이 먼저), "C" 는 바이트 순이라 데이터베이스 기본 정렬 규칙(en_US.UTF-8)에 기대지 않는다.
--   ⓘ 덩어리를 한 글자로 이어 붙이지 않고 배열로 둔 까닭: 이어 붙이면 덩어리 경계가 사라져
--     'A1' 과 'A-1' 처럼 글자 덩어리 길이가 다른 꼴에서 원소별 비교와 다른 답이 나온다.
--   ⛔ 빈 배열(이름이 빈 값·NULL — 운영 NULL 호 2,005행)은 nullif(…, '{}') 로 NULL 로 바꿔 nulls last —
--     빈 배열은 어떤 배열보다 작아 그대로 두면 빈 이름이 숫자 없는 이름들 앞에 선다(시험 표가 지킨다).
--   그대로 둔 것: 숫자 든 이름 먼저 · 빈 이름 맨 끝(nullif … nulls last) · 마지막 동률은 이름 글자 순 →
--   unit_id(쪽 나누기 안정).
--
-- 실측(운영 읽기 전용 · begin…rollback · pg_temp 에 옛·새 두 판 · 2026-10-05)
--   · 숫자 사이 글자 덩어리(동·층 제외)가 둘 이상 섞인 층 298곳(124동) 중 목록이 나오는 224곳에서
--     137곳 순서가 바뀜 · 무작위 목록 층 500곳 중 9곳(글자 덩어리 섞임 2 · 'B102호'·'사무동14층1호' 처럼
--     앞 글자가 붙은 꼴 6 · 그 밖 1 = '402-1-가' 가 '402-1-1' 들 뒤로) · 옛·새 목록의 원소 집합 차이 0.
--   · 949칸 층 200줄: 옛 96.5ms · 새 101.8ms(더운 캐시 3회 중앙값 · 네트워크 왕복 포함).
--
-- 잠금
-- ----
-- `create or replace function` 은 함수만 바꾼다 — 표·뷰 잠금이 없고 drop 도 없다. 아무 때나 적용해도 된다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;` (`scripts/dbx.py -f` 는 자동커밋). `notify pgrst` 는 commit **뒤**.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-10-05a_unit_order.sql
--   (합친 뒤 본 폴더 main 에서 — 그다음 python scripts/post_load.py --check : 허용 목록 변화 없음 · 총계 27 그대로)
--
-- 되돌리기 = 2026-10-04b 의 list_floor_units 정의(create … 부터 revoke 까지)를 같은 begin…commit 으로 다시
-- 실행한다(표·칸 변화 없음). 적용된 이 파일은 고치지 않는다(원장).
-- =====================================================================

begin;

create or replace function list_floor_units(
  p_bld_id   text,
  p_floor_no int,
  p_limit    int default 50,
  p_offset   int default 0
)
returns table (
  ho           text,
  excl_area_m2 numeric,
  total_cnt    bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with u as (
    -- p_floor_no 가 빈 값이면 `=` 가 참이 안 돼 0줄이다("층 미상" 호실은 목록을 주지 않는다).
    select un.unit_id, un.floor_no, un.ho, un.excl_area_m2, un.floor_use
    from unit un
    where un.bld_id = p_bld_id
      and un.floor_no = p_floor_no
  ),
  fl as (
    select u.floor_no,
           max(u.floor_use) as first_use
    from u
    group by u.floor_no
  ),
  -- ▼ 층 종류 판정 — list_unit_floor_summary 와 글자 그대로 같다(tests/test_unit_table_migration.py) ▼
  kind as (
    select fl.*,
           case
             -- 층별개요에 쓸 줄이 없다 → 그 층 호실들의 첫 용도(unit.floor_use) 이름으로.
             -- ⓘ 이 길은 치지 않는 것·건물 주용도 규칙을 안 본다 — 이 길로 오는 층의 첫 용도에
             --    부대시설·복리시설·주차장은 0층이라(2026-10-04 검사관 실측) 지금은 해가 없다.
             when bf.n = 0 then
               case
                 when fl.first_use ~ nm.officetel_re then 'officetel'
                 when fl.first_use ~ nm.home_re then 'residential'
                 when nullif(btrim(fl.first_use), '') is not null then 'commercial'
                 else 'unknown'
               end
             when bf.has_other and bf.has_counted_home_or_ot then 'mixed'
             when bf.has_other then 'commercial'
             when bf.has_officetel then 'officetel'
             when bf.has_home then 'residential'
             -- 치지 않는 것(부대시설·복리시설·주차장)뿐인 층 — 이때만 건물 주용도를 본다.
             when (select b.main_use from building b where b.bld_id = p_bld_id) = '공동주택'
               then 'residential'
             else 'commercial'
           end as floor_kind
    from fl
    cross join (
      -- 이름 목록은 여기 한 곳뿐이다. 바꾸면 층 종류별 층 수가 바뀐다(결정 0032 실측과 대조할 것).
      -- ⓘ '공관'만은 이름 **전체**가 '공관'일 때만(^공관$) — 부분 일치면 외국공관·이공관·건공관이
      --    살림집으로 잡힌다(2026-10-04 실측 · 그 밖으로 간다). 나머지 낱말은 부분 일치.
      -- ⓘ 아파트(?!형공장) — '아파트형공장'(지식산업센터 옛 이름 · 기타용도 1,110행 · 84동)은 살림집이
      --    아니다('아파트형주택' 28행은 살림집이라 (?!형) 으로 넓히지 않는다). 주택·(?<!비)주거 —
      --    '점포,주택'·'노인복지주택'·'사무실,주거시설' 꼴이 그 밖으로 가 목록이 나가던 것을 막는다.
      --    '(비주거)'·'비주거(기타…)' 는 비주거라는 뜻이라 뒤보기 부정으로 뺀다(검사관 지적 2026-10-04).
      -- ⓘ 주택(?!용?계단)·주거(?!용?계단) — '주거계단실'·'주택계단실'·'주택용계단실'은 상가 층에 붙은
      --    계단 이름이지 살림집이 아니다(재검사 실측 9층 · 2026-10-04). '주택용대피소'는 그대로 걸린다.
      select '(아파트(?!형공장)|공동주택|다세대|연립|다가구|단독주택|다중주택|기숙사|도시형생활|주택(?!용?계단)|(?<!비)주거(?!용?계단)|^공관$)'::text as home_re,
             '오피스텔'::text                                       as officetel_re,
             array['부대시설', '복리시설', '주차장']::text[]        as skip_nm
    ) nm
    cross join lateral (
      select count(*) as n,
             coalesce(bool_or(f.main_purps_nm ~ nm.home_re
                              or coalesce(f.etc_purps, '') ~ nm.home_re), false)      as has_home,
             coalesce(bool_or(f.main_purps_nm ~ nm.officetel_re
                              or coalesce(f.etc_purps, '') ~ nm.officetel_re), false) as has_officetel,
             -- 섞임 판정 전용: 치지 않는 것(부대시설·복리시설·주차장) 줄은 "섞임 판정에서 없는 셈 친다"
             -- (결정 0032 :75) — 그 줄의 기타용도에 '(아파트)'·'(오피스텔)'이 적혀 있어도 상가 층을 섞임으로
             -- 보내지 않는다. ⓘ has_home·has_officetel 은 모든 줄 그대로(그 줄뿐인 층은 지금처럼 주거·오피스텔).
             coalesce(bool_or(not (f.main_purps_nm = any (nm.skip_nm))
                              and (f.main_purps_nm ~ nm.home_re or f.main_purps_nm ~ nm.officetel_re
                                   or coalesce(f.etc_purps, '') ~ nm.home_re
                                   or coalesce(f.etc_purps, '') ~ nm.officetel_re)), false) as has_counted_home_or_ot,
             -- 한 줄 = 한 갈래: 주용도·기타용도 어느 쪽에도 살림집·오피스텔 낱말이 없고 치지 않는 것도
             -- 아닌 줄만 '그 밖'이다('업무시설 / 기타용도 오피스텔' 한 줄은 오피스텔이지 섞임이 아니다).
             coalesce(bool_or(f.main_purps_nm !~ nm.home_re
                              and f.main_purps_nm !~ nm.officetel_re
                              and coalesce(f.etc_purps, '') !~ nm.home_re
                              and coalesce(f.etc_purps, '') !~ nm.officetel_re
                              and not (f.main_purps_nm = any (nm.skip_nm))), false)   as has_other
      from building_floor f
      where f.bld_id = p_bld_id
        and f.floor_no = fl.floor_no
        and not f.area_excluded
        and nullif(btrim(f.main_purps_nm), '') is not null
    ) bf
  )
  -- ▲ 층 종류 판정 끝 ▲
  select u.ho,
         u.excl_area_m2,
         count(*) over () as total_cnt   -- 쪽 나누기 전 그 층 호실 줄 전부의 수
  from u
  join kind k on k.floor_no = u.floor_no
  -- ⛔ 목록은 commercial·mixed 층에서만 — 주거·오피스텔·미상 층은 0줄(서버가 막는다).
  where k.floor_kind in ('commercial', 'mixed')
  -- 자연 정렬(2026-10-05a · 결정 0032 후속): 숫자가 든 이름 먼저. 이름을 숫자 덩어리·글자 덩어리로
  -- 나눠 **앞에서부터 차례로** 견준다 — 숫자 덩어리는 수로, 글자 덩어리는 글자로. 그래서 '3가001호 …
  -- 3가 마지막 호, 3나001호 …' 처럼 같은 글자 덩어리끼리 모인다(옛 판은 숫자만 견줘 가·나·다가 번갈아 섰다).
  --   · 숫자 덩어리 = 앞 0 을 떼고(전부 0 이면 '0') 그 길이를 세 자리로 앞에 붙인 글자 — 글자로 견줘도
  --     수 순서가 된다(9 → '0019' < 10 → '00210'). ⛔ 고정 폭으로 채우지 않는다(긴 숫자를 잘라 버린다).
  --   · 덩어리 배열(text[])을 collate "C" 로 견준다 — 원소별·바이트 순이라 데이터베이스 기본 정렬 규칙에
  --     기대지 않는다. 짧은 배열이 앞 덩어리가 같으면 먼저다.
  --   · 이름 끝의 '호' 한 글자는 떼고 나눈다 — 안 떼면 '1층2호' 가 '1층2-3호' 뒤로 간다('-' 가 '호' 보다
  --     앞 글자라서). 떼면 '1층2' 가 '1층2-3' 의 앞부분이라 먼저 온다(사람 눈 순서 · 옛 판도 그랬다).
  --   · ⛔ 빈 배열(이름이 빈 값·NULL)은 nullif(…, '{}') 로 NULL 로 바꿔 맨 끝에 둔다 — 빈 배열은 어떤 배열보다
  --     작아서 그대로 두면 빈 이름이 숫자 없는 이름들 **앞**에 선다(운영 NULL 호 2,005행 · 2026-10-05 실측).
  -- 숫자 없는 이름은 그 뒤, 빈 이름은 맨 끝. 마지막 동률은 이름 글자 순, 그래도 같으면 unit_id(쪽 나누기 안정).
  order by coalesce(u.ho ~ '[0-9]', false) desc,
           nullif(array(select case when m.g[1] ~ '^[0-9]'
                                    then lpad(length(coalesce(nullif(ltrim(m.g[1], '0'), ''), '0'))::text, 3, '0')
                                         || coalesce(nullif(ltrim(m.g[1], '0'), ''), '0')
                                    else m.g[1]
                               end
                          from regexp_matches(regexp_replace(u.ho, '호$', ''), '[0-9]+|[^0-9]+', 'g')
                               with ordinality as m(g, i)
                         order by m.i), '{}') collate "C" asc nulls last,
           nullif(u.ho, '') asc nulls last,   -- 빈 글자도 NULL 과 같이 맨 끝
           u.unit_id
  -- 한 번에 최대 200줄(결정 0026·0028 과 같은 상한) · 1 미만·빈 값이면 기본 50 · offset 음수면 0.
  limit  case when p_limit is null or p_limit < 1 then 50 else least(p_limit, 200) end
  offset greatest(0, coalesce(p_offset, 0));
$$;

comment on function list_floor_units(text, int, int, int) is
  '결정 0032 호실 구성표 — 한 건물(bld_id)의 한 층 호 목록(호 이름은 대장 원문 그대로 · 전용면적 · '
  '쪽 나누기 전 그 층 전체 수 total_cnt). ⛔ 그 층 종류가 commercial·mixed 가 아니면 0줄이다 — '
  '주거·오피스텔·미상 층의 세대 목록은 어떤 인자로도 나가지 않는다(서버가 막는다). '
  '층 종류는 list_unit_floor_summary 와 글자 그대로 같은 판정식. mixed 층에는 주거·오피스텔 호실도 '
  '함께 나온다(결정 0032 결정 3 — 호실마다의 용도는 아직 담지 않았다). p_floor_no 가 빈 값이면 0줄. '
  '한 번에 최대 200줄(p_limit 1 미만이면 50) · 자연 정렬(이름을 숫자·글자 덩어리로 나눠 앞에서부터 — '
  '숫자는 수로, 글자는 글자로 · collate "C" · 2026-10-05a). '
  '⛔ 인자는 bld_id 다(pnu 로 받으면 같은 땅 옆 동 호실이 섞인다). '
  'security definer (unit·building_floor·building 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다).';

revoke all on function list_floor_units(text, int, int, int) from public, anon, authenticated;

commit;

-- PostgREST 가 바뀐 정의를 다시 읽게 한다(commit 뒤 — 묶음 안이면 commit 전 정의를 읽을 수 있다).
notify pgrst, 'reload schema';
