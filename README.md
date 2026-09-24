# 가장 가까운 화장실

공공데이터(행정안전부 공중화장실정보)로 모바일에서 현재 위치 기준 가장 가까운 공중·개방화장실을 찾는 개인 개발 사례(비영리).

## 처음 한 번 (2026-09-22에 실행함)
1. `python collect_toilets.py` — OpenAPI로 전국 수집(54회 호출) → `data/raw/toilets_<날짜>.csv`
2. `python profile_toilets.py` — 현황 보고
3. `python refine_address.py` — 도로명주소 API 정제·검증·건물관리번호
4. `python geocode_toilets.py` — 카카오 좌표 + 정확도 등급(A·B·B산·P·C·X) + 산지 교차 확인
5. `python report_geo.py` — 표시 기준 적용 결과
6. `python build_registry.py` — 영구 번호 대장(`data/id_registry.json`) + 기준본(`data/snapshots/`)
7. `python campus_coords.py` — 캠퍼스·단지 건물 좌표(`data/coord_overrides.csv`)
8. `python verify_locations.py [--naver-sample 300]` — 위치 검증: 도로명·지번 어긋남, 필지 번지 불일치, **시설 이름으로 찾기**(카카오·네이버) → `data/location_fixes.csv`
   - 검수 시트: `python make_check_sheet.py` (주소 판단 보류 목록)
9. `python build_app_data.py` — 앱 데이터(지도 칸 파일, `app/data/`, 학교·폐쇄 숨김, 중복 합치기)
10. `python check_data.py` — 앱 데이터 불변조건 검사(실패면 배포하지 않음)
11. `python audit_data.py` — 내용 정밀 점검 보고(고치지 않고 보고만)
12. `python fetch_holidays.py` — 공휴일 목록(1년에 한 번, `app/data/holidays.json`)
13. `python build_gov_links.py` — 시군구 홈페이지 주소(오류 신고 안내용, `data/gov_sites.json`)

## 주 1회 갱신
- `python update.py` — 수집 → 변경 분류 → 바뀐 곳만 정제·좌표(나머지는 좌표 이어받기) → 제안 + 보고서(`data/processed/update_<날짜>/report.md`)
- 보고서의 확인 목록 3가지를 본 뒤 `python update.py --publish data/processed/update_<날짜>` — 대장·기준본 반영
- 반영(`--publish`)이 캠퍼스 건물 좌표·위치 검증까지 다시 돌린다. 이어서 `python build_app_data.py` → `python check_data.py --prev <지난 index.json>` → `python audit_data.py`
- 원천 주소를 급히 고칠 때: `data/address_overrides.csv` (영구번호, 수정주소, 사유, 날짜)

## 앱 (1단계 완료)
- `python -m http.server 8000 --directory app` → `http://localhost:8000` (카카오 JS 키에 `localhost:8000` 등록 필요)
- 화면: 첫 화면 → 핀으로 위치 확정 → 가까운 목록(거리·지금 열림·정확도 뱃지·안내 문구). 다른 곳은 장소·주소 검색 + 반경
- 검수용: `?la=37.5665&lo=126.9780&acc=15` — 위치 허용 없이 그 자리에서 시작
- 보기 설정(첫 화면 `⚙`): 밝게·어둡게·기기 설정 / 글씨 보통·크게·아주 크게 (설정만 저장, 위치는 저장하지 않음)
- 오프라인: `app/sw.js`(화면 파일 + 본 지도 칸 80개까지). 카카오 지도는 저장할 수 없어 오프라인에서는 목록·상세만 됩니다
- 화면 파일을 고치면 `python bump_version.py` (브라우저가 옛 파일을 쓰지 않게 주소에 내용 해시를 붙임 — 배포 전 필수)
- 구성: `app/index.html` · `app/style.css` · `app/app.js` · `app/hours.js`(개방시간 판정) · `app/img/`(시간대 배경)

## 백업·문서
- `python backup_data.py [--prune]` — 원본·캐시·기준본 비공개 백업(+기준본 보관 정책: 최근 8주 전체 → 월 1개 → 연 1개)
- `python check_docs.py` — 문서끼리·문서와 코드가 어긋나지 않았는지

## 시험
- `python test_diff_update.py` — 변경 분류·번호 유지(15항목)
- `python test_hours.py` — 개방시간 해석(57항목)
- `python test_hours_js.py` — 파이썬(`hours.py`)과 앱(`app/hours.js`)의 개방시간 판정 맞대보기(node 필요)
- `python golden.py` — 골든 표본 100곳(규칙을 고친 뒤 확인). 기대값 갱신은 `--make`

시설 종류 사전: `data/classify.json` (고치면 `check_data.py`가 새 값·대체 비율을 검사)

키: `.env`의 `DATAGOKR_KEY`·`JUSO_KEY`·`KAKAO_REST_KEY` (없으면 `../착한식당/.env`를 읽음).

## 문서
- [앱 구현 시작점](docs/앱구현-시작점.md) — 다음 작업은 여기부터
- [사례 지식](docs/사례지식.md) — 조사·결정·결과
- [버그 이력](docs/버그이력.md) — 무엇이 틀렸고 어떻게 막나
- 화면 목업: `design/mockup_mobile_v2.html`
- 재사용 모듈: `../착한식당/docs/` 공공데이터-파이프라인 · 외부플랫폼-레퍼런스 · 분류-검색매핑 · 지식화-프로세스
