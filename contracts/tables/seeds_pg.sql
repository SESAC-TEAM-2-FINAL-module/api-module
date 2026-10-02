-- PostgreSQL 시드 SQL — 생성본 (common/seeds.py에서 자동 생성, 직접 수정 금지)
-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (4.3절, 개정 19)
-- 시드 변경 시 generate_seed_sql_pg()를 다시 실행해 이 파일을 갱신한다
-- areas.yaml sha256: 88d03c5525a1ec63c3b4b7aa8ee71a0dac5e5e436d8111062199b1368f458b20
-- area_aliases.yaml sha256: 5217282900ec420e1699ba57838ea3b531da502cea8e2c686437d4cb2a195138
-- axis_coverage.yaml sha256: f803d9e6acfcfe59047bf2d6d73345c8c33cfb51f0d02aac6eb8d845697694b8

BEGIN;

DELETE FROM axis_coverage;
DELETE FROM area_aliases;
DELETE FROM areas;

INSERT INTO areas (area_id, name, center_lat, center_lng, radius_km) VALUES
  ('gyeongnam_geoje', '경남 거제', 34.8, 128.621, 20.0),
  ('gyeongnam_namhae', '경남 남해', 34.84, 127.892, 22.0),
  ('gyeongnam_sacheon', '경남 사천', 34.915, 128.075, 15.0),
  ('gyeongnam_tongyeong', '경남 통영', 34.845, 128.435, 25.0),
  ('jeonnam_deukryang', '전남 득량만', 34.61, 127.235, 15.0),
  ('jeonnam_goheung', '전남 고흥', 34.608, 127.28, 20.0),
  ('jeonnam_yeoja', '전남 여자만', 34.68, 127.52, 13.0),
  ('jeonnam_yeosu', '전남 여수', 34.74, 127.73, 20.0);

INSERT INTO area_aliases (alias_key, area_id, source) VALUES
  ('경남 거제', 'gyeongnam_geoje', 'r1_r3_fixtures'),
  ('경남 남해', 'gyeongnam_namhae', 'r1_r3_fixtures'),
  ('경남 남해군 미조', 'gyeongnam_namhae', 'r1_r3_fixtures'),
  ('경남 남해군 미조면 조도', 'gyeongnam_namhae', 'r1_r3_fixtures'),
  ('경남 남해군 상주', 'gyeongnam_namhae', 'r1_r3_fixtures'),
  ('경남 사천', 'gyeongnam_sacheon', 'r1_r3_fixtures'),
  ('경남 통영', 'gyeongnam_tongyeong', 'r1_r3_fixtures'),
  ('산양읍 장군봉 내만', 'gyeongnam_tongyeong', 'r1_r3_fixtures'),
  ('산양읍 풍화리 월명도 북측', 'gyeongnam_tongyeong', 'r1_r3_fixtures'),
  ('전남 고흥', 'jeonnam_goheung', 'r1_r3_fixtures'),
  ('전남 고흥군 금산', 'jeonnam_goheung', 'r1_r3_fixtures'),
  ('전남 득량만', 'jeonnam_deukryang', 'r1_r3_fixtures'),
  ('전남 여수', 'jeonnam_yeosu', 'r1_r3_fixtures'),
  ('전남 여수 보돌바다', 'jeonnam_yeosu', 'r1_r3_fixtures'),
  ('전남 여자만', 'jeonnam_yeoja', 'r1_r3_fixtures');

INSERT INTO axis_coverage (area_id, axis, covered, season_months, reason) VALUES
  ('gyeongnam_geoje', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('gyeongnam_namhae', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('gyeongnam_sacheon', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('gyeongnam_tongyeong', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('jeonnam_deukryang', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('jeonnam_goheung', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('jeonnam_yeoja', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL),
  ('jeonnam_yeosu', 'red_tide', TRUE, '[5, 6, 7, 8, 9, 10]', NULL);

COMMIT;
